from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app

from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Tutor
import os, random, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from collections import defaultdict
import threading

auth_bp = Blueprint('auth', __name__)


# ── Simple rate limiter ──────────────────────────────────────
_login_attempts = defaultdict(list)   # IP -> [timestamp, ...]
_rate_lock = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5       # max attempts
RATE_WINDOW_SECONDS = 300    # 5-minute window
LOCKOUT_SECONDS = 600        # 10-minute lockout after too many failures


def _is_rate_limited(ip):
    """Check if an IP is rate-limited. Clean up old entries."""
    now = datetime.now()
    with _rate_lock:
        # Clean old attempts
        _login_attempts[ip] = [
            t for t in _login_attempts[ip]
            if (now - t).total_seconds() < RATE_WINDOW_SECONDS
        ]
        if len(_login_attempts[ip]) >= MAX_LOGIN_ATTEMPTS:
            # Check if we're still in lockout period from the last attempt
            last = _login_attempts[ip][-1]
            if (now - last).total_seconds() < LOCKOUT_SECONDS:
                return True
            # Lockout expired, clear attempts
            _login_attempts[ip] = []
        return False


def _record_attempt(ip):
    """Record a failed login attempt."""
    with _rate_lock:
        _login_attempts[ip].append(datetime.now())


def generate_otp():
    """Generate a 6-digit OTP."""
    return str(random.randint(100000, 999999))


def send_otp_email(to_email, otp, tutor_name):
    """Send OTP via email using SMTP. Returns True on success, error string on failure."""
    cfg = current_app.config
    if not cfg.get('MAIL_USERNAME') or not cfg.get('MAIL_PASSWORD'):
        return 'Email service is not configured. Please contact admin to reset your password.'

    subject = 'TuitionPe — Password Reset OTP'
    html_body = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#fff;border-radius:16px;overflow:hidden;">
        <div style="background:linear-gradient(135deg,#10b981,#059669);padding:28px 24px;text-align:center;">
            <h1 style="margin:0;font-size:24px;font-weight:700;color:#fff;">TuitionPe</h1>
        </div>
        <div style="padding:32px 24px;text-align:center;">
            <p style="color:#9ca3af;margin:0 0 8px;">Hello <strong style="color:#fff;">{tutor_name}</strong>,</p>
            <p style="color:#9ca3af;margin:0 0 24px;">Use this OTP to reset your password. It expires in 10 minutes.</p>
            <div style="background:#121212;border:1px solid rgba(16,185,129,0.3);border-radius:12px;padding:20px;margin:0 auto 24px;display:inline-block;letter-spacing:10px;font-size:32px;font-weight:800;color:#10b981;">
                {otp}
            </div>
            <p style="color:#6b7280;font-size:13px;margin:0;">If you didn't request this, please ignore this email.</p>
        </div>
        <div style="border-top:1px solid rgba(255,255,255,0.05);padding:16px 24px;text-align:center;">
            <p style="color:#6b7280;font-size:11px;margin:0;">TuitionPe — Manage your tuition business effortlessly</p>
        </div>
    </div>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = cfg['MAIL_DEFAULT_SENDER']
    msg['To'] = to_email
    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP(cfg['MAIL_SERVER'], cfg['MAIL_PORT'], timeout=20)
        server.ehlo()
        server.starttls()
        server.login(cfg['MAIL_USERNAME'], cfg['MAIL_PASSWORD'])
        server.sendmail(cfg['MAIL_USERNAME'], to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return f'Failed to send email: {str(e)}'

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    if request.method == 'POST':
        # Rate limiting check
        client_ip = request.remote_addr or '0.0.0.0'
        if _is_rate_limited(client_ip):
            flash('Too many login attempts. Please wait 10 minutes before trying again.', 'error')
            return redirect(url_for('auth.login'))

        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        if len(phone) != 10 or not phone.isdigit():
            flash('Please enter a valid 10-digit phone number.', 'error')
            return redirect(url_for('auth.login'))

        tutor = Tutor.query.filter_by(phone=phone).first()
        if tutor and check_password_hash(tutor.password_hash, password):
            login_user(tutor, remember=remember)
            return redirect(url_for('dashboard.dashboard'))

        # Record failed attempt
        _record_attempt(client_ip)
        remaining = MAX_LOGIN_ATTEMPTS - len(_login_attempts.get(client_ip, []))
        if remaining > 0:
            flash(f'Invalid phone number or password. {remaining} attempt(s) remaining.', 'error')
        else:
            flash('Too many failed attempts. Account locked for 10 minutes.', 'error')
        return redirect(url_for('auth.login'))
    return render_template('auth/login.html')

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        subjects = request.form.get('subjects', '')
        classes_taught = request.form.get('classes_taught', '')
        experience = request.form.get('experience', 0)
        qualification = request.form.get('qualification', '')
        bio = request.form.get('bio', '')
        upi_id = request.form.get('upi_id', '')
        bank_account = request.form.get('bank_account', '')
        ifsc_code = request.form.get('ifsc_code', '')

        # Validation
        if len(name) < 2:
            flash('Name must be at least 2 characters.', 'error')
            return redirect(url_for('auth.signup'))
        if len(phone) != 10 or not phone.isdigit():
            flash('Please enter a valid 10-digit phone number.', 'error')
            return redirect(url_for('auth.signup'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('auth.signup'))
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.signup'))
        if Tutor.query.filter_by(phone=phone).first():
            flash('Phone number already registered.', 'error')
            return redirect(url_for('auth.signup'))

        # Handle profile image upload
        from werkzeug.utils import secure_filename
        from utils import upload_image
        profile_image = None
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename:
                filename = secure_filename(f"tutor_{phone}_{file.filename}")
                profile_image = upload_image(file, filename)

        # Handle QR code upload
        qr_image_path = None
        if 'qr_image' in request.files:
            file = request.files['qr_image']
            if file and file.filename:
                filename = secure_filename(f"qr_{phone}_{file.filename}")
                qr_image_path = upload_image(file, filename)

        tutor = Tutor(
            name=name,
            phone=phone,
            email=email if email else None,
            password_hash=generate_password_hash(password),
            subjects=subjects,
            classes_taught=classes_taught,
            experience_years=int(experience) if experience else 0,
            qualification=qualification,
            bio=bio,
            profile_image=profile_image,
            upi_id=upi_id if upi_id else None,
            qr_image_path=qr_image_path,
            bank_account=bank_account if bank_account else None,
            ifsc_code=ifsc_code if ifsc_code else None,
        )
        db.session.add(tutor)
        db.session.commit()
        login_user(tutor)
        flash('Account created successfully! Welcome to TuitionPe.', 'success')
        return redirect(url_for('dashboard.dashboard'))
    return render_template('auth/signup.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('auth.login'))


# ============ FORGOT PASSWORD FLOW ============

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Step 1: User enters phone + email. If email matches profile, send OTP."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip().lower()

        if len(phone) != 10 or not phone.isdigit():
            flash('Please enter a valid 10-digit phone number.', 'error')
            return redirect(url_for('auth.forgot_password'))

        if not email:
            flash('Please enter your email address.', 'error')
            return redirect(url_for('auth.forgot_password'))

        tutor = Tutor.query.filter_by(phone=phone).first()

        if not tutor:
            flash('No account found with this phone number.', 'error')
            return redirect(url_for('auth.forgot_password'))

        # Check if tutor has an email and it matches
        if not tutor.email:
            flash('No email is linked to this account. Please contact admin (Ankit) to reset your password.', 'error')
            return redirect(url_for('auth.forgot_password'))

        if tutor.email.lower() != email:
            flash('Email does not match the one on your profile. Please contact admin (Ankit) to reset your password.', 'error')
            return redirect(url_for('auth.forgot_password'))

        # Email matches — generate OTP and send
        otp = generate_otp()
        result = send_otp_email(tutor.email, otp, tutor.name)

        if result is True:
            # Store OTP in session
            session['reset_otp'] = otp
            session['reset_phone'] = phone
            session['reset_tutor_id'] = tutor.id
            session['reset_otp_expiry'] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
            flash('OTP sent to your email! Check your inbox.', 'success')
            return redirect(url_for('auth.verify_otp'))
        else:
            flash(result, 'error')
            return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    """Step 2: User enters the 6-digit OTP from their email."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    # Must have a pending reset
    if 'reset_otp' not in session:
        flash('Please start the password reset process first.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()

        # Check expiry
        expiry = datetime.fromisoformat(session.get('reset_otp_expiry', '2000-01-01'))
        if datetime.utcnow() > expiry:
            session.pop('reset_otp', None)
            session.pop('reset_phone', None)
            session.pop('reset_tutor_id', None)
            session.pop('reset_otp_expiry', None)
            flash('OTP has expired. Please request a new one.', 'error')
            return redirect(url_for('auth.forgot_password'))

        if entered_otp == session.get('reset_otp'):
            # OTP verified — allow password reset
            session['otp_verified'] = True
            flash('OTP verified! Set your new password.', 'success')
            return redirect(url_for('auth.reset_password'))
        else:
            flash('Invalid OTP. Please try again.', 'error')
            return redirect(url_for('auth.verify_otp'))

    phone = session.get('reset_phone', '')
    return render_template('auth/verify_otp.html', phone=phone)


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Step 3: User sets a new password after OTP verification."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if not session.get('otp_verified'):
        flash('Please verify your OTP first.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('auth.reset_password'))

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.reset_password'))

        tutor_id = session.get('reset_tutor_id')
        tutor = Tutor.query.get(tutor_id)

        if not tutor:
            flash('Something went wrong. Please try again.', 'error')
            return redirect(url_for('auth.forgot_password'))

        tutor.password_hash = generate_password_hash(password)
        db.session.commit()

        # Clear all reset session data
        for key in ['reset_otp', 'reset_phone', 'reset_tutor_id', 'reset_otp_expiry', 'otp_verified']:
            session.pop(key, None)

        flash('Password reset successfully! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')


@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP to the same email."""
    if 'reset_tutor_id' not in session:
        flash('Please start the password reset process first.', 'error')
        return redirect(url_for('auth.forgot_password'))

    tutor = Tutor.query.get(session['reset_tutor_id'])
    if not tutor or not tutor.email:
        flash('Unable to resend OTP. Please try again.', 'error')
        return redirect(url_for('auth.forgot_password'))

    otp = generate_otp()
    result = send_otp_email(tutor.email, otp, tutor.name)

    if result is True:
        session['reset_otp'] = otp
        session['reset_otp_expiry'] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        flash('New OTP sent to your email!', 'success')
    else:
        flash(result, 'error')

    return redirect(url_for('auth.verify_otp'))
