import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # In production (Render sets RENDER=true) a missing SECRET_KEY must never
    # fall back to a value that is public in the repo — sessions would be
    # forgeable. Use an ephemeral random key instead (sessions reset on
    # restart) and rely on the env var being set for real deployments.
    _env_secret = os.environ.get('SECRET_KEY')
    if _env_secret:
        SECRET_KEY = _env_secret
    elif os.environ.get('RENDER') or os.environ.get('DATABASE_URL'):
        import secrets as _secrets
        SECRET_KEY = _secrets.token_hex(32)
        print('[TuitionPe] WARNING: SECRET_KEY env var not set in production; '
              'using an ephemeral key — sessions will not survive restarts.')
    else:
        SECRET_KEY = 'tuitionpe-dev-only-secret'

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = bool(os.environ.get('RENDER') or os.environ.get('FORCE_SECURE_COOKIES'))
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = bool(os.environ.get('RENDER') or os.environ.get('FORCE_SECURE_COOKIES'))

    # Database: use DATABASE_URL (PostgreSQL) in production, SQLite locally
    _db_url = os.environ.get('DATABASE_URL', '')
    if _db_url:
        # Render / Heroku give postgres:// but SQLAlchemy needs postgresql://
        if _db_url.startswith('postgres://'):
            _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'database.db'))
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DB_PATH

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Reconnect if a pooled connection has gone stale (fixes Neon SSL errors)
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max upload

    # Email SMTP settings (Gmail example — use App Password, not your real password)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')   # e.g. yourname@gmail.com
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')   # Gmail App Password
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'TuitionPe <noreply@tuitionpe.com>')

    # OTP settings
    OTP_EXPIRY_MINUTES = 10
