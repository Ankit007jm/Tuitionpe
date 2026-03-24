"""
Public payment page — no login required.
Parents open this link from WhatsApp to see QR code, amount, and tutor details.
Also serves as TuitionPe branding / advertisement.
"""
import secrets
from flask import Blueprint, render_template, abort
from models import db, Tutor, Student, Payment
from datetime import datetime

pay_bp = Blueprint('pay', __name__)


def make_pay_token(tutor_id, student_id):
    """
    Generate a secure random token for the payment page URL.
    Stores the token in the Tutor record (per-tutor, not per-student)
    and returns a compound token: tutor_pay_token + student_id hash.
    """
    tutor = Tutor.query.get(tutor_id)
    if not tutor:
        return ''

    # Generate and store a random pay_token for the tutor if they don't have one
    if not tutor.pay_token:
        tutor.pay_token = secrets.token_hex(16)
        db.session.commit()

    # Combine tutor token with student_id for per-student uniqueness
    import hashlib
    raw = f"{tutor.pay_token}-{student_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@pay_bp.route('/pay/<int:tutor_id>/<int:student_id>/<token>')
def payment_page(tutor_id, student_id, token):
    """Public page showing payment QR code and details."""
    expected = make_pay_token(tutor_id, student_id)
    if not expected or token != expected:
        abort(404)

    tutor = Tutor.query.get_or_404(tutor_id)
    student = Student.query.filter_by(id=student_id, tutor_id=tutor_id).first_or_404()

    current_month = datetime.now().strftime('%Y-%m')
    payment = Payment.query.filter_by(
        tutor_id=tutor_id, student_id=student_id, month_year=current_month
    ).first()

    amount = payment.amount if payment else student.fee_amount
    status = payment.status if payment else 'pending'
    month_display = datetime.now().strftime('%B %Y')

    return render_template('pay.html',
        tutor=tutor, student=student,
        amount=amount, status=status,
        month_display=month_display)
