import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import db, Student, Payment, Schedule
from datetime import datetime
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
    student_data = []
    for s in students:
        payment = Payment.query.filter_by(
            tutor_id=current_user.id, student_id=s.id, month_year=current_month
        ).first()
        fee_status = payment.status if payment else 'pending'
        student_data.append({'student': s, 'fee_status': fee_status})

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
        )
        db.session.add(student)
        db.session.commit()

        # Create payment record for current month with due_date
        current_month = datetime.now().strftime('%Y-%m')
        from routes.fees import _get_due_date
        payment = Payment(
            tutor_id=current_user.id,
            student_id=student.id,
            amount=fee_val,
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
