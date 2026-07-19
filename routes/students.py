import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response
from flask_login import login_required, current_user
from models import db, Student, Payment, Schedule, Attendance
from sqlalchemy import func
from datetime import datetime, date
import os

students_bp = Blueprint('students', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _validate_phone(phone):
    """Validate Indian 10-digit phone number."""
    clean = phone.replace('+91', '').replace(' ', '').replace('-', '').strip()
    return clean.isdigit() and len(clean) == 10

def _check_duplicate(tutor_id, student_name, parent_phone, exclude_id=None):
    """Check if a student with same name+phone already exists."""
    clean_phone = parent_phone.replace('+91', '').replace(' ', '').replace('-', '').strip()
    query = Student.query.filter_by(
        tutor_id=tutor_id, status='active'
    ).filter(
        Student.student_name.ilike(student_name.strip()),
        Student.parent_phone.like(f'%{clean_phone[-10:]}')
    )
    if exclude_id:
        query = query.filter(Student.id != exclude_id)
    return query.first()


@students_bp.route('/students')
@login_required
def student_list():
    search = request.args.get('search', '').strip()
    filter_type = request.args.get('filter', 'all')
    show_archived = request.args.get('archived', '') == '1'

    if show_archived:
        query = Student.query.filter_by(tutor_id=current_user.id, status='archived')
    else:
        query = Student.query.filter_by(tutor_id=current_user.id, status='active')

    if search:
        query = query.filter(Student.student_name.ilike(f'%{search}%'))
    if filter_type == 'regular':
        query = query.filter_by(student_type='regular')
    elif filter_type == 'exam':
        query = query.filter_by(student_type='exam')

    students = query.order_by(Student.student_name).all()

    # Get fee status for each student
    current_month = datetime.now().strftime('%Y-%m')

    # Attendance rate per student (completed vs absent; cancelled excluded)
    att_counts = {}
    rows = db.session.query(
        Attendance.student_id, Attendance.status, func.count(Attendance.id)
    ).filter(
        Attendance.tutor_id == current_user.id,
        Attendance.status.in_(['completed', 'absent'])
    ).group_by(Attendance.student_id, Attendance.status).all()
    for sid, status, count in rows:
        att_counts.setdefault(sid, {})[status] = count

    student_data = []
    for s in students:
        payment = Payment.query.filter_by(
            tutor_id=current_user.id, student_id=s.id, month_year=current_month
        ).first()
        fee_status = payment.status if payment else 'pending'
        counts = att_counts.get(s.id, {})
        attended = counts.get('completed', 0)
        held = attended + counts.get('absent', 0)
        att_pct = round(attended / held * 100) if held else None
        student_data.append({'student': s, 'fee_status': fee_status, 'att_pct': att_pct})

    # Counts for filter tabs
    total = Student.query.filter_by(tutor_id=current_user.id, status='active').count()
    regular_count = Student.query.filter_by(tutor_id=current_user.id, status='active', student_type='regular').count()
    exam_count = Student.query.filter_by(tutor_id=current_user.id, status='active', student_type='exam').count()
    archived_count = Student.query.filter_by(tutor_id=current_user.id, status='archived').count()

    return render_template('students/list.html',
        student_data=student_data, search=search, filter_type=filter_type,
        total=total, regular_count=regular_count, exam_count=exam_count,
        archived_count=archived_count, show_archived=show_archived)

@students_bp.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form.get('student_name', '').strip()
        class_grade = request.form.get('class_grade', '')
        # Multiple subjects come as a list from checkboxes
        subject_list = request.form.getlist('subject')
        subject = ','.join(subject_list) if subject_list else request.form.get('subject', '')
        parent_name = request.form.get('parent_name', '').strip()
        parent_phone = request.form.get('parent_phone', '').strip()
        parent_email = request.form.get('parent_email', '').strip()
        fee_amount = request.form.get('fee_amount', '0').strip()
        payment_cycle = request.form.get('payment_cycle', 'monthly')
        student_type = request.form.get('student_type', 'regular')
        notes = request.form.get('notes', '')

        # Validation
        if not name or not parent_phone or not fee_amount:
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('students.add_student'))

        if not _validate_phone(parent_phone):
            flash('Please enter a valid 10-digit phone number.', 'error')
            return redirect(url_for('students.add_student'))

        try:
            fee_val = float(fee_amount)
            if fee_val <= 0:
                flash('Fee amount must be greater than 0.', 'error')
                return redirect(url_for('students.add_student'))
        except ValueError:
            flash('Please enter a valid fee amount.', 'error')
            return redirect(url_for('students.add_student'))

        # Duplicate check
        dup = _check_duplicate(current_user.id, name, parent_phone)
        if dup:
            flash(f'A student named "{dup.student_name}" with the same phone number already exists.', 'error')
            return redirect(url_for('students.add_student'))

        # Handle profile image
        from werkzeug.utils import secure_filename
        from utils import upload_image
        profile_image = None
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename:
                if not _allowed_file(file.filename):
                    flash('Only image files (PNG, JPG, GIF, WEBP) are allowed.', 'error')
                    return redirect(url_for('students.add_student'))
                filename = secure_filename(f"student_{parent_phone}_{file.filename}")
                profile_image = upload_image(file, filename)

        # Parse date of joining
        doj_str = request.form.get('date_of_joining', '').strip()
        date_of_joining = None
        if doj_str:
            try:
                date_of_joining = date.fromisoformat(doj_str)
            except (ValueError, TypeError):
                pass

        student = Student(
            tutor_id=current_user.id,
            student_name=name,
            class_grade=class_grade,
            parent_name=parent_name,
            parent_phone=parent_phone,
            parent_email=parent_email or None,
            subject=subject,
            fee_amount=fee_val,
            payment_cycle=payment_cycle,
            student_type=student_type,
            notes=notes,
            profile_image=profile_image,
            date_of_joining=date_of_joining,
        )
        db.session.add(student)
        db.session.commit()

        # Create payment record for current month with due_date (pro-rata if mid-month join)
        current_month = datetime.now().strftime('%Y-%m')
        from routes.fees import _get_due_date, calculate_prorata_amount
        prorata_amount = calculate_prorata_amount(student, current_month)
        payment = Payment(
            tutor_id=current_user.id,
            student_id=student.id,
            amount=prorata_amount,
            month_year=current_month,
            due_date=_get_due_date(current_month),
            status='pending'
        )
        db.session.add(payment)
        db.session.commit()

        flash(f'{name} added successfully!', 'success')
        return redirect(url_for('students.student_list'))

    subjects = []
    if current_user.subjects:
        subjects = [s.strip() for s in current_user.subjects.split(',')]
    return render_template('students/add.html', subjects=subjects)

@students_bp.route('/students/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(id):
    student = Student.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    if request.method == 'POST':
        name = request.form.get('student_name', student.student_name).strip()
        parent_phone = request.form.get('parent_phone', student.parent_phone).strip()

        # Validate phone
        if not _validate_phone(parent_phone):
            flash('Please enter a valid 10-digit phone number.', 'error')
            return redirect(url_for('students.edit_student', id=id))

        # Validate fee
        fee_str = request.form.get('fee_amount', str(student.fee_amount)).strip()
        try:
            fee_val = float(fee_str)
            if fee_val <= 0:
                flash('Fee amount must be greater than 0.', 'error')
                return redirect(url_for('students.edit_student', id=id))
        except ValueError:
            flash('Please enter a valid fee amount.', 'error')
            return redirect(url_for('students.edit_student', id=id))

        # Duplicate check (exclude current student)
        dup = _check_duplicate(current_user.id, name, parent_phone, exclude_id=student.id)
        if dup:
            flash(f'Another student named "{dup.student_name}" with the same phone number already exists.', 'error')
            return redirect(url_for('students.edit_student', id=id))

        student.student_name = name
        student.class_grade = request.form.get('class_grade', student.class_grade)
        subject_list = request.form.getlist('subject')
        student.subject = ','.join(subject_list) if subject_list else request.form.get('subject', student.subject)
        student.parent_name = request.form.get('parent_name', student.parent_name).strip()
        student.parent_phone = parent_phone
        student.parent_email = request.form.get('parent_email', '').strip() or None
        student.fee_amount = fee_val
        student.payment_cycle = request.form.get('payment_cycle', student.payment_cycle)
        student.student_type = request.form.get('student_type', student.student_type)
        student.notes = request.form.get('notes', student.notes)

        doj_str = request.form.get('date_of_joining', '').strip()
        if doj_str:
            try:
                student.date_of_joining = date.fromisoformat(doj_str)
            except (ValueError, TypeError):
                pass

        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename:
                if not _allowed_file(file.filename):
                    flash('Only image files (PNG, JPG, GIF, WEBP) are allowed.', 'error')
                    return redirect(url_for('students.edit_student', id=id))
                from werkzeug.utils import secure_filename
                from utils import upload_image
                filename = secure_filename(f"student_{student.parent_phone}_{file.filename}")
                student.profile_image = upload_image(file, filename)

        db.session.commit()
        flash(f'{student.student_name} updated successfully!', 'success')
        return redirect(url_for('students.student_list'))

    subjects = []
    if current_user.subjects:
        subjects = [s.strip() for s in current_user.subjects.split(',')]
    return render_template('students/edit.html', student=student, subjects=subjects)

@students_bp.route('/students/<int:id>/delete', methods=['POST'])
@login_required
def delete_student(id):
    """Soft-delete: archive the student instead of permanently deleting."""
    student = Student.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()
    name = student.student_name
    student.status = 'archived'
    db.session.commit()
    flash(f'{name} has been archived. You can restore them from the archived list.', 'success')
    return redirect(url_for('students.student_list'))

@students_bp.route('/students/<int:id>/restore', methods=['POST'])
@login_required
def restore_student(id):
    """Restore an archived student back to active."""
    student = Student.query.filter_by(id=id, tutor_id=current_user.id, status='archived').first_or_404()
    student.status = 'active'
    db.session.commit()
    flash(f'{student.student_name} has been restored!', 'success')
    return redirect(url_for('students.student_list', archived='1'))

@students_bp.route('/students/<int:id>/permanently-delete', methods=['POST'])
@login_required
def permanently_delete_student(id):
    """Permanently delete an archived student and all their data."""
    student = Student.query.filter_by(id=id, tutor_id=current_user.id, status='archived').first_or_404()
    name = student.student_name
    db.session.delete(student)
    db.session.commit()
    flash(f'{name} and all related data permanently deleted.', 'success')
    return redirect(url_for('students.student_list', archived='1'))


# ────────────────────────────────────────────────────────────
# Student Progress Report (PDF for parents)
# ────────────────────────────────────────────────────────────

@students_bp.route('/students/<int:id>/progress-report')
@login_required
def progress_report(id):
    """Download a monthly progress report card PDF for a student."""
    try:
        from fpdf import FPDF
    except ImportError:
        flash('PDF generation is not available on this server (fpdf2 missing).', 'error')
        return redirect(url_for('students.student_list'))

    student = Student.query.filter_by(id=id, tutor_id=current_user.id).first_or_404()

    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    try:
        month_dt = datetime.strptime(month, '%Y-%m')
        month_display = month_dt.strftime('%B %Y')
    except ValueError:
        flash('Invalid month.', 'error')
        return redirect(url_for('students.student_list'))

    from calendar import monthrange
    first = date(month_dt.year, month_dt.month, 1)
    last = date(month_dt.year, month_dt.month, monthrange(month_dt.year, month_dt.month)[1])

    # Attendance: this month + overall
    month_rows = Attendance.query.filter(
        Attendance.tutor_id == current_user.id,
        Attendance.student_id == student.id,
        Attendance.date >= first, Attendance.date <= last,
    ).order_by(Attendance.date).all()
    all_rows = Attendance.query.filter_by(
        tutor_id=current_user.id, student_id=student.id).all()

    def _tally(rows):
        c = {'completed': 0, 'absent': 0, 'cancelled': 0, 'rescheduled': 0}
        for r in rows:
            c[r.status] = c.get(r.status, 0) + 1
        held = c['completed'] + c['absent']
        pct = round(c['completed'] / held * 100) if held else None
        return c, pct

    m_counts, m_pct = _tally(month_rows)
    a_counts, a_pct = _tally(all_rows)

    payment = Payment.query.filter_by(
        tutor_id=current_user.id, student_id=student.id, month_year=month).first()

    TEAL = (13, 148, 136)
    INK = (16, 32, 28)
    MUTED = (125, 140, 136)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Header band
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, 210, 34, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, 'Student Progress Report')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_xy(12, 17)
    pdf.cell(0, 6, f'{month_display}  |  Tutor: {current_user.name}')

    def label_value(label, value, bold=True):
        pdf.set_text_color(*MUTED)
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(62, 8, label)
        pdf.set_text_color(*INK)
        pdf.set_font('Helvetica', 'B' if bold else '', 11)
        pdf.cell(0, 8, str(value), new_x='LMARGIN', new_y='NEXT')

    # Student info
    pdf.set_y(44)
    pdf.set_text_color(*INK)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, 'Student', new_x='LMARGIN', new_y='NEXT')
    label_value('Name', student.student_name)
    label_value('Class', student.class_grade or '-')
    label_value('Subject', student.subject or '-')
    if student.date_of_joining:
        label_value('Learning since', student.date_of_joining.strftime('%d %b %Y'))

    # Attendance
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*INK)
    pdf.cell(0, 8, f'Attendance - {month_display}', new_x='LMARGIN', new_y='NEXT')
    label_value('Classes attended', m_counts['completed'])
    label_value('Classes missed', m_counts['absent'])
    if m_counts['cancelled']:
        label_value('Cancelled by tutor', m_counts['cancelled'])
    label_value('Attendance rate (this month)', f'{m_pct}%' if m_pct is not None else 'No classes held')
    label_value('Attendance rate (overall)', f'{a_pct}%' if a_pct is not None else '-')

    # Fee status
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*INK)
    pdf.cell(0, 8, 'Fee Status', new_x='LMARGIN', new_y='NEXT')
    if payment:
        status = payment.status.capitalize()
        label_value('Fee for the month', f'Rs. {int(payment.amount)}')
        pdf.set_text_color(*MUTED)
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(62, 8, 'Status')
        if payment.status == 'paid':
            pdf.set_text_color(5, 150, 105)
        elif payment.status == 'overdue':
            pdf.set_text_color(220, 38, 38)
        else:
            pdf.set_text_color(217, 119, 6)
        pdf.set_font('Helvetica', 'B', 11)
        paid_on = f" (paid on {payment.paid_date.strftime('%d %b %Y')})" if payment.paid_date else ''
        pdf.cell(0, 8, status + paid_on, new_x='LMARGIN', new_y='NEXT')
    else:
        label_value('Fee for the month', 'No record', bold=False)

    # Tutor remarks
    if student.notes:
        pdf.ln(4)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(*INK)
        pdf.cell(0, 8, 'Tutor Remarks', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(0, 6, student.notes[:1000])

    pdf.ln(8)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f'Generated by TuitionPe on {datetime.now().strftime("%d %b %Y")}')

    data = bytes(pdf.output())
    safe_name = ''.join(ch for ch in student.student_name if ch.isalnum() or ch in ' _-').strip().replace(' ', '_')
    return Response(data, mimetype='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="Progress_{safe_name}_{month}.pdf"'
    })
