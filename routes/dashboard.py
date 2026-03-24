from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from models import db, Student, Schedule, Payment, Attendance
from sqlalchemy import func
from datetime import datetime, date, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

def get_dashboard_stats(tutor_id):
    current_month = datetime.now().strftime('%Y-%m')
    today_name = date.today().strftime('%A').lower()

    active_students = Student.query.filter_by(tutor_id=tutor_id, status='active').count()

    today_classes = Schedule.query.filter_by(
        tutor_id=tutor_id, day_of_week=today_name, status='active'
    ).count()

    pending = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.tutor_id == tutor_id,
        Payment.month_year == current_month,
        Payment.status.in_(['pending', 'overdue'])
    ).scalar()

    collected = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.tutor_id == tutor_id,
        Payment.month_year == current_month,
        Payment.status == 'paid'
    ).scalar()

    return {
        'active_students': active_students,
        'today_classes': today_classes,
        'pending_fees': float(pending),
        'collected_fees': float(collected)
    }

def get_chart_data(tutor_id, months=6):
    """Get chart data using proper month calculation (not 30-day approximation)."""
    data = {'labels': [], 'collected': [], 'pending': []}
    now = datetime.now()

    for i in range(months - 1, -1, -1):
        # Properly calculate month by going back i months
        month = now.month - i
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        month_year = f"{year:04d}-{month:02d}"
        month_label = datetime(year, month, 1).strftime('%b')

        collected = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.tutor_id == tutor_id,
            Payment.month_year == month_year,
            Payment.status == 'paid'
        ).scalar()

        pending = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.tutor_id == tutor_id,
            Payment.month_year == month_year,
            Payment.status.in_(['pending', 'overdue'])
        ).scalar()

        data['labels'].append(month_label)
        data['collected'].append(float(collected))
        data['pending'].append(float(pending))
    return data

def get_today_classes(tutor_id):
    today_name = date.today().strftime('%A').lower()
    today = date.today()
    now = datetime.now()

    schedules = Schedule.query.filter_by(
        tutor_id=tutor_id, day_of_week=today_name, status='active'
    ).all()

    classes = []
    current_month = datetime.now().strftime('%Y-%m')
    for s in schedules:
        student = Student.query.get(s.student_id)
        if not student:
            continue
        payment = Payment.query.filter_by(
            tutor_id=tutor_id, student_id=s.student_id, month_year=current_month
        ).first()
        fee_status = payment.status if payment else 'pending'

        # Check if class time has passed
        try:
            h, m = map(int, s.start_time.split(':'))
            class_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            is_past = now > class_dt
        except:
            is_past = False

        # Check attendance
        attendance = Attendance.query.filter_by(
            schedule_id=s.id, date=today
        ).first()

        classes.append({
            'id': s.id,
            'student_name': student.student_name,
            'subject': student.subject or '',
            'start_time': s.start_time,
            'end_time': s.end_time or '',
            'class_type': s.class_type,
            'fee_status': fee_status,
            'is_past': is_past,
            'attendance': attendance.status if attendance else None,
            'student_initials': ''.join([w[0].upper() for w in student.student_name.split()[:2]])
        })
    classes.sort(key=lambda x: x['start_time'])
    return classes


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    stats = get_dashboard_stats(current_user.id)
    chart_data = get_chart_data(current_user.id)
    today_classes = get_today_classes(current_user.id)
    total_expected = stats['pending_fees'] + stats['collected_fees']
    progress = int((stats['collected_fees'] / total_expected * 100)) if total_expected > 0 else 0
    return render_template('dashboard.html',
        stats=stats, chart_data=chart_data,
        today_classes=today_classes, progress=progress)

@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    return jsonify(get_dashboard_stats(current_user.id))

@dashboard_bp.route('/api/today-classes')
@login_required
def api_today_classes():
    return jsonify(get_today_classes(current_user.id))

@dashboard_bp.route('/api/chart-data')
@login_required
def api_chart_data():
    return jsonify(get_chart_data(current_user.id))
