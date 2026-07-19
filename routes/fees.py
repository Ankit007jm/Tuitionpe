import urllib.parse
import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from models import db, Student, Payment
from sqlalchemy import func
from datetime import datetime, date, timedelta
from routes.payment_page import make_pay_token
from calendar import monthrange

fees_bp = Blueprint('fees', __name__)

PENDING_TEMPLATE = """------------------------------
       *TUITIONPE*
------------------------------

Namaste {parent_name},

This is a gentle reminder from *{tutor_name}* that the tuition fee for *{student_name}* is due:

  *Amount:* Rs.{amount}
  *Month:* {month}
  *Status:* Pending
{payment_details}
*Tap below to view QR code & pay:*
{pay_link}

Please pay at your earliest convenience.

Thank you!
-- *{tutor_name}*

------------------------------
_Powered by *TuitionPe*_
_Smart Tuition Management_"""

OVERDUE_TEMPLATE = """------------------------------
       *TUITIONPE*
------------------------------

Namaste {parent_name},

This is an *overdue payment* reminder from *{tutor_name}* for *{student_name}*:

  *Amount:* Rs.{amount}
  *Month:* {month}
  *Status:* OVERDUE
{payment_details}
*Tap below to view QR code & pay:*
{pay_link}

Kindly clear the dues at your earliest convenience.

Thank you!
-- *{tutor_name}*

------------------------------
_Powered by *TuitionPe*_
_Smart Tuition Management_"""


def _build_payment_details(tutor):
    """Build UPI/bank detail lines for WhatsApp message."""
    lines = []
    if tutor.upi_id:
        lines.append(f"  *UPI:* {tutor.upi_id}")
    if tutor.bank_account:
        bank = f"  *Bank:* {tutor.bank_account}"
        if tutor.ifsc_code:
            bank += f" (IFSC: {tutor.ifsc_code})"
        lines.append(bank)
    if lines:
        return "\n" + "\n".join(lines) + "\n"
    return ""

def generate_whatsapp_link(phone, message):
    phone = phone.replace('+91', '').replace(' ', '').replace('-', '').strip()
    encoded = urllib.parse.quote(message)
    return f"https://wa.me/91{phone}?text={encoded}"


def _auto_mark_overdue(tutor_id):
    """Mark any past-month pending payments as overdue."""
    current_month = datetime.now().strftime('%Y-%m')
    Payment.query.filter(
        Payment.tutor_id == tutor_id,
        Payment.status == 'pending',
        Payment.month_year < current_month
    ).update({'status': 'overdue'})
    db.session.commit()


def _get_due_date(month_year_str):
    """Calculate due date: 10th of the given month."""
    try:
        y, m = map(int, month_year_str.split('-'))
        # Due on 10th of the month (or last day if month has fewer days)
        day = min(10, monthrange(y, m)[1])
        return date(y, m, day)
    except Exception:
        return None


def calculate_prorata_amount(student, month_year_str):
    """
    Calculate pro-rata fee for a student based on their date_of_joining.

    Logic:
    - If no date_of_joining or joined before the month, full fee applies.
    - If joined in the given month, fee = (remaining_days / total_days) * fee_amount.
    - For weekly: full weekly rate (no proration within a week).
    - For daily/per_class: full rate always (already per-unit).
    """
    import math
    if not student.date_of_joining:
        return student.fee_amount

    try:
        y, m = map(int, month_year_str.split('-'))
    except Exception:
        return student.fee_amount

    total_days = monthrange(y, m)[1]
    first_of_month = date(y, m, 1)
    last_of_month = date(y, m, total_days)

    # If joined before this month, full fee
    if student.date_of_joining < first_of_month:
        return student.fee_amount

    # If joined after this month ends, no fee
    if student.date_of_joining > last_of_month:
        return 0.0

    # Student joined mid-month
    join_day = student.date_of_joining.day

    if student.payment_cycle in ('daily', 'per_class'):
        # These are already per-unit — no proration needed
        return student.fee_amount
    elif student.payment_cycle == 'weekly':
        # Calculate remaining full weeks (ceil) from joining date
        remaining_days = total_days - join_day + 1
        remaining_weeks = math.ceil(remaining_days / 7)
        total_weeks = math.ceil(total_days / 7)
        return round(student.fee_amount * remaining_weeks / total_weeks, 2)
    else:
        # monthly: prorate by day
        remaining_days = total_days - join_day + 1
        prorata = round(student.fee_amount * remaining_days / total_days, 2)
        return prorata


def _generate_weekly_payments(student, month_year_str):
    """Generate weekly payment records for a month if they don't exist."""
    try:
        y, m = map(int, month_year_str.split('-'))
    except Exception:
        return
    # Get all Mondays in the month as week start dates
    first_day = date(y, m, 1)
    last_day = date(y, m, monthrange(y, m)[1])
    current = first_day
    week_num = 1
    while current <= last_day:
        # Each week's label
        week_label = f"{month_year_str}-W{week_num}"
        existing = Payment.query.filter_by(
            tutor_id=student.tutor_id, student_id=student.id,
            month_year=week_label
        ).first()
        if not existing:
            p = Payment(
                tutor_id=student.tutor_id,
                student_id=student.id,
                amount=student.fee_amount,
                month_year=week_label,
                due_date=current + timedelta(days=6),  # Due by end of week
                status='pending'
            )
            db.session.add(p)
        current += timedelta(days=7)
        week_num += 1
    db.session.commit()


@fees_bp.route('/fees')
@login_required
def fees():
    current_month = datetime.now().strftime('%Y-%m')
    selected_month = request.args.get('month', current_month)

    # Auto-mark overdue payments for past months
    _auto_mark_overdue(current_user.id)

    # Only auto-generate missing payment records for the CURRENT month or future
    if selected_month >= current_month:
        students = Student.query.filter_by(tutor_id=current_user.id, status='active').all()
        for student in students:
            if student.payment_cycle == 'weekly':
                _generate_weekly_payments(student, selected_month)
                continue
            # Monthly / daily / per_class — generate single monthly record
            existing = Payment.query.filter_by(
                tutor_id=current_user.id, student_id=student.id, month_year=selected_month
            ).first()
            if not existing:
                prorata_amount = calculate_prorata_amount(student, selected_month)
                if prorata_amount <= 0:
                    continue  # student hasn't joined yet in this month
                p = Payment(
                    tutor_id=current_user.id,
                    student_id=student.id,
                    amount=prorata_amount,
                    month_year=selected_month,
                    due_date=_get_due_date(selected_month),
                    status='pending'
                )
                db.session.add(p)
        db.session.commit()

    # For weekly students, also include week-labeled payments in the view
    # Filter: month_year starts with selected_month (covers both "2026-03" and "2026-03-W1")
    payments = Payment.query.filter(
        Payment.tutor_id == current_user.id,
        Payment.month_year.startswith(selected_month)
    ).all()

    # Summary
    collected = sum(p.amount for p in payments if p.status == 'paid')
    pending = sum(p.amount for p in payments if p.status == 'pending')
    overdue = sum(p.amount for p in payments if p.status == 'overdue')

    # Payment list
    payment_data = []
    for p in payments:
        student = Student.query.get(p.student_id)
        if student:
            initials = ''.join([w[0].upper() for w in student.student_name.split()[:2]])
            is_prorata = (student.fee_amount and abs(p.amount - student.fee_amount) > 0.01
                          and p.amount < student.fee_amount)
            payment_data.append({
                'payment': p, 'student': student, 'initials': initials,
                'is_prorata': is_prorata, 'full_fee': student.fee_amount,
            })

    # Month display
    try:
        month_display = datetime.strptime(selected_month, '%Y-%m').strftime('%B %Y')
    except:
        month_display = selected_month

    return render_template('fees.html',
        collected=float(collected), pending=float(pending), overdue=float(overdue),
        payment_data=payment_data, selected_month=selected_month,
        month_display=month_display)


@fees_bp.route('/fees/<int:id>/mark-paid', methods=['POST'])
@login_required
def mark_paid(id):
    payment = Payment.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    payment.status = 'paid'
    payment.paid_date = date.today()
    db.session.commit()
    # Redirect to receipt options page
    return redirect(url_for('fees.receipt_options', id=payment.id))


@fees_bp.route('/fees/<int:id>/receipt')
@login_required
def receipt_options(id):
    """Show receipt send options: Email or WhatsApp."""
    payment = Payment.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    student = Student.query.get(payment.student_id)
    try:
        month_display = datetime.strptime(payment.month_year[:7], '%Y-%m').strftime('%B %Y')
    except:
        month_display = payment.month_year
    return render_template('receipt_options.html',
        payment=payment, student=student, month_display=month_display)


def _send_receipt_bg(app, tutor_id, student_id, payment_id):
    """Send receipt email in a background thread with its own app context."""
    with app.app_context():
        from models import Tutor
        from receipt import send_receipt_email
        tutor = Tutor.query.get(tutor_id)
        student = Student.query.get(student_id)
        payment = Payment.query.get(payment_id)
        if tutor and student and payment:
            ok, msg = send_receipt_email(app, tutor, student, payment)
            print(f"[TuitionPe] Receipt email {'sent' if ok else 'FAILED'}: {msg}")


@fees_bp.route('/fees/<int:id>/receipt/email', methods=['POST'])
@login_required
def send_receipt_email_route(id):
    """Send receipt PDF via email to the parent (async to avoid request timeout)."""
    payment = Payment.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    student = Student.query.get(payment.student_id)

    # Validate parent email exists
    if not student.parent_email:
        flash(f'Parent email not set for {student.student_name}. Update student details first.', 'error')
        month = payment.month_year[:7]
        return redirect(url_for('fees.fees', month=month))

    from flask import current_app
    app = current_app._get_current_object()
    parent_email = student.parent_email

    from utils import run_async
    run_async(_send_receipt_bg, app, current_user.id, student.id, payment.id)

    flash(f'Receipt is being sent to {parent_email}! Check your inbox in a moment.', 'success')
    month = payment.month_year[:7]
    return redirect(url_for('fees.fees', month=month))


@fees_bp.route('/fees/<int:id>/receipt/download')
@login_required
def download_receipt(id):
    """Generate and download receipt PDF."""
    payment = Payment.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    student = Student.query.get(payment.student_id)

    from receipt import generate_receipt_pdf
    from flask import make_response
    pdf_bytes = generate_receipt_pdf(current_user, student, payment)

    safe_name = student.student_name.replace(' ', '_')
    filename = f"Receipt_{safe_name}_{payment.month_year}.pdf"

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@fees_bp.route('/fees/<int:id>/receipt/whatsapp')
@login_required
def send_receipt_whatsapp(id):
    """
    Generate receipt PDF, save it, and redirect to WhatsApp with a message
    containing a download link for the PDF.
    """
    payment = Payment.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    student = Student.query.get(payment.student_id)

    from receipt import save_receipt_pdf
    from flask import current_app
    relative_path = save_receipt_pdf(current_user, student, payment, current_app.config['UPLOAD_FOLDER'])

    # Build download URL
    download_url = url_for('fees.download_receipt', id=payment.id, _external=True)

    try:
        month_display = datetime.strptime(payment.month_year[:7], '%Y-%m').strftime('%B %Y')
    except:
        month_display = payment.month_year

    paid_date_str = payment.paid_date.strftime('%d %B %Y') if payment.paid_date else date.today().strftime('%d %B %Y')
    receipt_no = f"TP-{payment.id:06d}"

    message = (
        f"------------------------------\n"
        f"       *TUITIONPE*\n"
        f"------------------------------\n\n"
        f"*PAYMENT RECEIPT*\n\n"
        f"  *Receipt No:* {receipt_no}\n"
        f"  *Student:* {student.student_name}\n"
        f"  *Amount:* Rs.{int(payment.amount)}\n"
        f"  *Month:* {month_display}\n"
        f"  *Status:* PAID\n"
        f"  *Paid On:* {paid_date_str}\n"
        f"  *Teacher:* {current_user.name}\n\n"
        f"*Download Receipt PDF:*\n"
        f"{download_url}\n\n"
        f"Thank you for your payment!\n\n"
        f"------------------------------\n"
        f"_Powered by *TuitionPe*_\n"
        f"_Smart Tuition Management_"
    )

    link = generate_whatsapp_link(student.parent_phone, message)
    return redirect(link)


@fees_bp.route('/fees/bulk-mark-paid', methods=['POST'])
@login_required
def bulk_mark_paid():
    """Mark multiple payments as paid at once."""
    payment_ids = request.form.getlist('payment_ids')
    if not payment_ids:
        flash('No payments selected.', 'error')
        return redirect(url_for('fees.fees'))

    count = 0
    month = None
    for pid in payment_ids:
        try:
            p = Payment.query.filter_by(id=int(pid), tutor_id=current_user.id).first()
            if p and p.status != 'paid':
                p.status = 'paid'
                p.paid_date = date.today()
                count += 1
                month = p.month_year[:7]
        except (ValueError, TypeError):
            continue
    db.session.commit()
    flash(f'{count} payment(s) marked as paid!', 'success')
    return redirect(url_for('fees.fees', month=month or datetime.now().strftime('%Y-%m')))


@fees_bp.route('/fees/remind/<int:student_id>')
@login_required
def remind(student_id):
    student = Student.query.filter_by(id=student_id, tutor_id=current_user.id).first_or_404()
    current_month = datetime.now().strftime('%Y-%m')
    payment = Payment.query.filter_by(
        tutor_id=current_user.id, student_id=student_id, month_year=current_month
    ).first()

    month_display = datetime.now().strftime('%B %Y')
    amount = payment.amount if payment else student.fee_amount
    is_overdue = payment and payment.status == 'overdue'

    # Build the public payment page link
    token = make_pay_token(current_user.id, student.id)
    pay_link = url_for('pay.payment_page',
                        tutor_id=current_user.id,
                        student_id=student.id,
                        token=token, _external=True)

    template = OVERDUE_TEMPLATE if is_overdue else PENDING_TEMPLATE
    message = template.format(
        parent_name=student.parent_name or 'Sir/Madam',
        student_name=student.student_name,
        amount=int(amount),
        month=month_display,
        tutor_name=current_user.name,
        pay_link=pay_link,
        payment_details=_build_payment_details(current_user)
    )

    link = generate_whatsapp_link(student.parent_phone, message)

    if payment:
        payment.reminder_sent = (payment.reminder_sent or 0) + 1
        db.session.commit()

    return redirect(link)


@fees_bp.route('/fees/<int:id>/mark-unpaid', methods=['POST'])
@login_required
def mark_unpaid(id):
    """Undo an accidental 'Mark Paid' — revert to pending."""
    payment = Payment.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    if payment.status == 'paid':
        payment.status = 'pending'
        payment.paid_date = None
        db.session.commit()
        flash('Payment reverted to pending.', 'info')
    month = payment.month_year[:7]
    return redirect(url_for('fees.fees', month=month))


@fees_bp.route('/fees/history/<int:student_id>')
@login_required
def payment_history(student_id):
    """Show payment history for a specific student."""
    student = Student.query.filter_by(id=student_id, tutor_id=current_user.id).first_or_404()
    payments = Payment.query.filter_by(
        tutor_id=current_user.id, student_id=student_id
    ).order_by(Payment.month_year.desc()).all()

    total_paid = sum(p.amount for p in payments if p.status == 'paid')
    total_pending = sum(p.amount for p in payments if p.status in ('pending', 'overdue'))

    return render_template('payment_history.html',
        student=student, payments=payments,
        total_paid=total_paid, total_pending=total_pending)


# ────────────────────────────────────────────────────────────
# Monthly Earnings Report (PDF download)
# ────────────────────────────────────────────────────────────

@fees_bp.route('/fees/report')
@login_required
def monthly_report():
    """Download a PDF earnings report for the selected month."""
    try:
        from fpdf import FPDF
    except ImportError:
        flash('PDF generation is not available on this server (fpdf2 missing).', 'error')
        return redirect(url_for('fees.fees'))

    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    try:
        month_display = datetime.strptime(month, '%Y-%m').strftime('%B %Y')
    except ValueError:
        flash('Invalid month.', 'error')
        return redirect(url_for('fees.fees'))

    payments = Payment.query.filter(
        Payment.tutor_id == current_user.id,
        Payment.month_year.startswith(month)
    ).all()

    collected = sum(p.amount for p in payments if p.status == 'paid')
    pending = sum(p.amount for p in payments if p.status == 'pending')
    overdue = sum(p.amount for p in payments if p.status == 'overdue')

    students = {s.id: s for s in Student.query.filter_by(tutor_id=current_user.id).all()}
    rows = []
    for p in sorted(payments, key=lambda x: (students.get(x.student_id) and students[x.student_id].student_name or '', x.month_year)):
        s = students.get(p.student_id)
        if not s:
            continue
        rows.append((
            s.student_name,
            p.month_year,
            f'Rs. {int(p.amount)}',
            p.status.capitalize(),
            p.paid_date.strftime('%d %b %Y') if p.paid_date else '-',
        ))

    TEAL = (13, 148, 136)
    INK = (16, 32, 28)
    MUTED = (125, 140, 136)
    LINE = (227, 234, 232)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Header band
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, 'TuitionPe - Earnings Report')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_xy(12, 17)
    pdf.cell(0, 6, f'{current_user.name}  |  {month_display}')

    # Summary
    pdf.set_y(40)
    pdf.set_text_color(*INK)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, 'Summary', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 11)
    total = collected + pending + overdue
    for label, value in (
        ('Collected', collected), ('Pending', pending),
        ('Overdue', overdue), ('Total billed', total),
    ):
        pdf.set_text_color(*MUTED)
        pdf.cell(60, 8, label)
        pdf.set_text_color(*INK)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 8, f'Rs. {int(value)}', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 11)

    # Table
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*INK)
    pdf.cell(0, 8, 'Payment Details', new_x='LMARGIN', new_y='NEXT')

    col_w = (58, 30, 30, 28, 40)
    headers = ('Student', 'Period', 'Amount', 'Status', 'Paid On')
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(240, 244, 243)
    pdf.set_text_color(*MUTED)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 8, h, fill=True)
    pdf.ln(8)

    pdf.set_font('Helvetica', '', 9)
    pdf.set_draw_color(*LINE)
    for name, period, amount, status, paid_on in rows:
        pdf.set_text_color(*INK)
        pdf.cell(col_w[0], 8, name[:32], border='B')
        pdf.set_text_color(*MUTED)
        pdf.cell(col_w[1], 8, period, border='B')
        pdf.set_text_color(*INK)
        pdf.cell(col_w[2], 8, amount, border='B')
        if status == 'Paid':
            pdf.set_text_color(5, 150, 105)
        elif status == 'Overdue':
            pdf.set_text_color(220, 38, 38)
        else:
            pdf.set_text_color(217, 119, 6)
        pdf.cell(col_w[3], 8, status, border='B')
        pdf.set_text_color(*MUTED)
        pdf.cell(col_w[4], 8, paid_on, border='B')
        pdf.ln(8)

    if not rows:
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 10, 'No payment records for this month.', new_x='LMARGIN', new_y='NEXT')

    pdf.ln(6)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f'Generated by TuitionPe on {datetime.now().strftime("%d %b %Y, %I:%M %p")}')

    data = bytes(pdf.output())
    return Response(data, mimetype='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="TuitionPe_Report_{month}.pdf"'
    })
