import os
from dotenv import load_dotenv

# Load .env file so MAIL_USERNAME, MAIL_PASSWORD etc. are available
load_dotenv()

from flask import Flask, redirect, url_for, session, request, abort
from flask_login import LoginManager
from config import Config
from models import db, Tutor

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config.from_object(Config)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)

# ── Template filter: converts stored image path or Cloudinary URL → src URL ──
@app.template_filter('img_url')
def img_url_filter(path):
    if not path:
        return ''
    if path.startswith(('http://', 'https://')):
        return path  # already a Cloudinary / external URL
    clean = path.replace('\\', '/').replace('static/', '', 1).lstrip('/')
    return url_for('static', filename=clean)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Tutor.query.get(int(user_id))


# ── Simple CSRF protection ──────────────────────────────────────
import secrets

@app.before_request
def csrf_protect():
    """Validate CSRF token on all POST requests."""
    if request.method == 'POST':
        token = session.get('csrf_token')
        form_token = request.form.get('csrf_token')
        if not token or token != form_token:
            # Allow if the token is in the header (for AJAX)
            header_token = request.headers.get('X-CSRFToken')
            if not token or token != header_token:
                abort(400, 'CSRF token missing or invalid. Please refresh the page and try again.')

@app.context_processor
def inject_csrf_token():
    """Make csrf_token available in all templates."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return {'csrf_token': session['csrf_token']}


# Register blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.students import students_bp
from routes.schedule import schedule_bp
from routes.fees import fees_bp
from routes.profile import profile_bp
from routes.payment_page import pay_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(students_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(fees_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(pay_bp)

@app.route('/')
def index():
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))

# Create tables + migrate missing columns
with app.app_context():
    db.create_all()

    # SQLite-only: add columns that were added after initial release
    if db.engine.dialect.name == 'sqlite':
        import sqlite3
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            existing = [row[1] for row in cursor.execute("PRAGMA table_info(tutors)").fetchall()]
            if 'daily_reminder' not in existing:
                cursor.execute("ALTER TABLE tutors ADD COLUMN daily_reminder BOOLEAN DEFAULT 1")
            if 'reminder_hour' not in existing:
                cursor.execute("ALTER TABLE tutors ADD COLUMN reminder_hour INTEGER DEFAULT 7")
            if 'reminder_minute' not in existing:
                cursor.execute("ALTER TABLE tutors ADD COLUMN reminder_minute INTEGER DEFAULT 0")
            if 'pay_token' not in existing:
                cursor.execute("ALTER TABLE tutors ADD COLUMN pay_token VARCHAR(32)")

            pay_cols = [row[1] for row in cursor.execute("PRAGMA table_info(payments)").fetchall()]
            if 'due_date' not in pay_cols:
                cursor.execute("ALTER TABLE payments ADD COLUMN due_date DATE")

            # Fix old image paths: normalize to "uploads/filename"
            for tbl, col in [('tutors', 'qr_image_path'), ('tutors', 'profile_image'), ('students', 'profile_image')]:
                rows = cursor.execute(f"SELECT rowid, {col} FROM {tbl} WHERE {col} IS NOT NULL").fetchall()
                for rowid, val in rows:
                    if val and ('static/' in val or 'static\\' in val):
                        clean = val.replace('\\', '/').replace('static/', '', 1)
                        cursor.execute(f"UPDATE {tbl} SET {col} = ? WHERE rowid = ?", (clean, rowid))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[TuitionPe] SQLite migration note: {e}")

    # All databases: auto-mark overdue payments
    try:
        from datetime import datetime
        from sqlalchemy import text
        current_month = datetime.now().strftime('%Y-%m')
        db.session.execute(
            text("UPDATE payments SET status = 'overdue' WHERE status = 'pending' AND month_year < :month"),
            {'month': current_month}
        )
        db.session.commit()
    except Exception as e:
        print(f"[TuitionPe] Overdue migration note: {e}")

# Start the background reminder scheduler (daily + per-class emails)
from reminder import init_reminders
init_reminders(app)

if __name__ == '__main__':
    # use_reloader=False prevents APScheduler from starting twice in debug mode
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
