from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Student, Schedule, Payment
from datetime import datetime
import os

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/profile')
@login_required
def profile():
    student_count = Student.query.filter_by(tutor_id=current_user.id, status='active').count()
    current_month = datetime.now().strftime('%Y-%m')
    month_collected = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0)).filter(
        Payment.tutor_id == current_user.id, Payment.month_year == current_month, Payment.status == 'paid'
    ).scalar()
    schedule_count = Schedule.query.filter_by(tutor_id=current_user.id, status='active').count()

    return render_template('profile.html',
        student_count=student_count,
        month_collected=float(month_collected),
        schedule_count=schedule_count)

@profile_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    section = request.form.get('section', 'personal')

    if section == 'personal':
        current_user.name = request.form.get('name', current_user.name).strip()
        current_user.phone = request.form.get('phone', current_user.phone).strip()
        current_user.email = request.form.get('email', current_user.email).strip()
    elif section == 'teaching':
        current_user.subjects = request.form.get('subjects', current_user.subjects)
        current_user.classes_taught = request.form.get('classes_taught', current_user.classes_taught)
        current_user.experience_years = int(request.form.get('experience', current_user.experience_years or 0))
        current_user.qualification = request.form.get('qualification', current_user.qualification)
    elif section == 'payment':
        current_user.upi_id = request.form.get('upi_id', current_user.upi_id)
        current_user.bank_account = request.form.get('bank_account', current_user.bank_account)
        current_user.ifsc_code = request.form.get('ifsc_code', current_user.ifsc_code)
    elif section == 'bio':
        current_user.bio = request.form.get('bio', current_user.bio)
    elif section == 'discovery':
        current_user.discoverable = request.form.get('discoverable') == '1'
        current_user.city = request.form.get('city', '').strip()[:100] or None
        mode = request.form.get('teaching_mode', 'both')
        current_user.teaching_mode = mode if mode in ('online', 'offline', 'both') else 'both'
    elif section == 'reminder':
        current_user.daily_reminder = request.form.get('daily_reminder') == '1'
        try:
            h = int(request.form.get('reminder_hour', 7))
            m = int(request.form.get('reminder_minute', 0))
            current_user.reminder_hour = max(0, min(23, h))
            current_user.reminder_minute = max(0, min(59, m))
        except (ValueError, TypeError):
            pass

    db.session.commit()
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('profile.profile'))

@profile_bp.route('/profile/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('profile.profile'))
    file = request.files['avatar']
    if file and file.filename:
        from werkzeug.utils import secure_filename
        from utils import upload_image
        filename = secure_filename(f"avatar_{current_user.id}_{file.filename}")
        current_user.profile_image = upload_image(file, filename)
        db.session.commit()
        flash('Profile photo updated!', 'success')
    return redirect(url_for('profile.profile'))

@profile_bp.route('/profile/upload-qr', methods=['POST'])
@login_required
def upload_qr():
    if 'qr_image' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('profile.profile'))
    file = request.files['qr_image']
    if file and file.filename:
        from werkzeug.utils import secure_filename
        from utils import upload_image
        filename = secure_filename(f"qr_{current_user.id}_{file.filename}")
        current_user.qr_image_path = upload_image(file, filename)
        db.session.commit()
        flash('QR code updated!', 'success')
    return redirect(url_for('profile.profile'))


@profile_bp.route('/profile/send-today-email')
@login_required
def send_today_email():
    """Manually send today's schedule email to the tutor."""
    from reminder import send_manual_daily_email
    ok, msg = send_manual_daily_email(current_app._get_current_object(), current_user.id)
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('profile.profile'))
