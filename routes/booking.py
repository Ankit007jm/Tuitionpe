"""
Public demo-class booking page + tutor-facing request management.

Parents open the tutor's shareable link (no login) and request a demo
class. The tutor reviews requests under /bookings.
"""
import secrets
import threading
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from models import db, Tutor, DemoRequest

booking_bp = Blueprint('booking', __name__)


def notify_tutor_new_request(tutor, req, source='booking link'):
    """Email the tutor the moment a demo request arrives (background thread).

    Fails silently — the request is already saved; email is best-effort.
    """
    if not tutor or not tutor.email:
        return
    app_obj = current_app._get_current_object()
    with app_obj.app_context():
        bookings_url = url_for('booking.bookings', _external=True)
    details = [
        ('Student', req.student_name),
        ('Class', req.class_grade or '-'),
        ('Subject', req.subject or 'Any'),
        ('Parent', req.parent_name or '-'),
        ('Phone', f'+91 {req.phone}'),
    ]
    if req.preferred_day or req.preferred_time:
        details.append(('Preferred', f"{(req.preferred_day or '').capitalize()} {req.preferred_time or ''}".strip()))
    if req.note:
        details.append(('Note', req.note))
    rows = ''.join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#7d8c88;font-size:13px;">{label}</td>'
        f'<td style="padding:6px 0;color:#10201c;font-size:13px;font-weight:600;">{value}</td></tr>'
        for label, value in details
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">
      <div style="background:#0d9488;border-radius:12px 12px 0 0;padding:18px 22px;">
        <h2 style="color:#fff;margin:0;font-size:18px;">New demo class request!</h2>
        <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">via your {source}</p>
      </div>
      <div style="border:1px solid #e3eae8;border-top:0;border-radius:0 0 12px 12px;padding:20px 22px;">
        <table style="border-collapse:collapse;">{rows}</table>
        <a href="https://wa.me/91{req.phone}" style="display:inline-block;margin-top:16px;background:#0d9488;color:#fff;
           text-decoration:none;padding:11px 20px;border-radius:10px;font-size:14px;font-weight:bold;">
           Reply on WhatsApp</a>
        <a href="{bookings_url}" style="display:inline-block;margin-top:16px;margin-left:8px;color:#0d9488;
           text-decoration:none;padding:11px 8px;font-size:13px;">View all requests</a>
        <p style="color:#a3b0ac;font-size:11px;margin-top:18px;">Respond fast — parents usually pick the first teacher who replies.</p>
      </div>
    </div>"""

    def _send(app, to_email, subject, body):
        from reminder import send_email
        send_email(app, to_email, subject, body)

    threading.Thread(
        target=_send,
        args=(app_obj, tutor.email, f'New demo request: {req.student_name} ({req.subject or "Any subject"})', html),
        daemon=True,
    ).start()

# Simple per-IP rate limit for the public form: max 5 submissions / 10 min
_submissions = {}
_MAX_SUBMISSIONS = 5
_WINDOW_SECONDS = 600


def _is_rate_limited(ip):
    now = time.time()
    hits = [t for t in _submissions.get(ip, []) if now - t < _WINDOW_SECONDS]
    _submissions[ip] = hits
    return len(hits) >= _MAX_SUBMISSIONS


def _record_submission(ip):
    _submissions.setdefault(ip, []).append(time.time())


def make_booking_token(tutor):
    """Lazily create and persist the tutor's public booking token."""
    if not tutor.booking_token:
        tutor.booking_token = secrets.token_hex(16)
        db.session.commit()
    return tutor.booking_token


DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


@booking_bp.route('/book/<int:tutor_id>/<token>', methods=['GET', 'POST'])
def book_demo(tutor_id, token):
    """Public page: parents request a demo class."""
    tutor = Tutor.query.get_or_404(tutor_id)
    if not tutor.booking_token or not secrets.compare_digest(tutor.booking_token, token):
        abort(404)

    subjects = [s.strip() for s in (tutor.subjects or '').split(',') if s.strip()]

    if request.method == 'POST':
        client_ip = request.remote_addr or '0.0.0.0'
        if _is_rate_limited(client_ip):
            flash('Too many requests. Please try again later.', 'error')
            return redirect(url_for('booking.book_demo', tutor_id=tutor_id, token=token))

        # Honeypot: bots fill every field; humans never see this one
        if request.form.get('website'):
            return redirect(url_for('booking.book_demo', tutor_id=tutor_id, token=token, sent='1'))

        student_name = request.form.get('student_name', '').strip()[:100]
        parent_name = request.form.get('parent_name', '').strip()[:100]
        phone = request.form.get('phone', '').strip()
        class_grade = request.form.get('class_grade', '').strip()[:20]
        subject = request.form.get('subject', '').strip()[:100]
        preferred_day = request.form.get('preferred_day', '').strip().lower()
        preferred_time = request.form.get('preferred_time', '').strip()[:20]
        note = request.form.get('note', '').strip()[:500]

        if len(student_name) < 2:
            flash('Please enter the student name.', 'error')
            return redirect(url_for('booking.book_demo', tutor_id=tutor_id, token=token))
        if len(phone) != 10 or not phone.isdigit():
            flash('Please enter a valid 10-digit phone number.', 'error')
            return redirect(url_for('booking.book_demo', tutor_id=tutor_id, token=token))
        if preferred_day and preferred_day not in DAYS:
            preferred_day = ''

        req = DemoRequest(
            tutor_id=tutor.id,
            student_name=student_name,
            parent_name=parent_name,
            phone=phone,
            class_grade=class_grade,
            subject=subject,
            preferred_day=preferred_day,
            preferred_time=preferred_time,
            note=note,
        )
        db.session.add(req)
        db.session.commit()
        _record_submission(client_ip)
        notify_tutor_new_request(tutor, req, source='booking link')
        return redirect(url_for('booking.book_demo', tutor_id=tutor_id, token=token, sent='1'))

    return render_template('book.html',
        tutor=tutor, token=token, subjects=subjects,
        days=DAYS, sent=request.args.get('sent') == '1')


@booking_bp.route('/bookings')
@login_required
def bookings():
    """Tutor page: list and manage demo requests."""
    booking_token = make_booking_token(current_user)
    booking_url = url_for('booking.book_demo', tutor_id=current_user.id,
                          token=booking_token, _external=True)

    requests_list = DemoRequest.query.filter_by(tutor_id=current_user.id) \
        .order_by(DemoRequest.created_at.desc()).all()
    new_count = sum(1 for r in requests_list if r.status == 'new')

    return render_template('bookings.html',
        requests=requests_list, new_count=new_count, booking_url=booking_url)


@booking_bp.route('/bookings/<int:id>/status', methods=['POST'])
@login_required
def update_booking_status(id):
    req = DemoRequest.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    status = request.form.get('status', '')
    if status not in ('new', 'contacted', 'closed'):
        flash('Invalid status.', 'error')
        return redirect(url_for('booking.bookings'))
    req.status = status
    db.session.commit()
    flash(f'Request marked as {status}.', 'success')
    return redirect(url_for('booking.bookings'))


@booking_bp.route('/bookings/<int:id>/delete', methods=['POST'])
@login_required
def delete_booking(id):
    req = DemoRequest.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    db.session.delete(req)
    db.session.commit()
    flash('Request deleted.', 'success')
    return redirect(url_for('booking.bookings'))
