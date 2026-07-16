from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from models import db, Student, Schedule, Payment, Attendance, DemoRequest
from sqlalchemy import func
from datetime import datetime, date, timedelta
import random

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


MOTIVATIONAL_QUOTES = {
    'active_students': [
        "Every student is a seed of potential — you're the gardener.",
        "Teaching is the one profession that creates all other professions.",
        "Great teachers don't just teach, they inspire.",
        "A good teacher can change the trajectory of a life.",
        "Your impact as a teacher reaches far beyond the classroom.",
    ],
    'today_classes': [
        "Today is a blank page. Write a good one.",
        "Every class is a chance to make a difference.",
        "The best teachers teach from the heart, not from the book.",
        "Today's preparation determines tomorrow's achievement.",
        "Each lesson planted today will bloom in the future.",
    ],
    'pending_fees': [
        "Stay consistent. Success follows persistence.",
        "Financial discipline is the backbone of a great tuition business.",
        "Every pending payment is a relationship to nurture.",
        "Gentle reminders work wonders. Keep going!",
        "A well-managed fee system builds trust with parents.",
    ],
    'collected_fees': [
        "Your hard work is paying off — literally!",
        "Consistency in collection reflects consistency in quality.",
        "Financial growth is a sign of a thriving tuition practice.",
        "Well done! Every rupee collected fuels your passion.",
        "Celebrate the small wins — they add up to big success.",
    ]
}


def get_active_students_detail(tutor_id):
    """Get detailed list of active students for dashboard card."""
    students = Student.query.filter_by(tutor_id=tutor_id, status='active')\
        .order_by(Student.student_name).all()
    result = []
    for s in students:
        initials = ''.join([w[0].upper() for w in s.student_name.split()[:2]])
        result.append({
            'name': s.student_name,
            'subject': s.subject or 'Tuition',
            'class_grade': s.class_grade or '',
            'initials': initials,
            'payment_cycle': s.payment_cycle,
        })
    return result


def get_pending_fees_detail(tutor_id):
    """Get detailed list of pending/overdue fees for dashboard card."""
    current_month = datetime.now().strftime('%Y-%m')
    payments = Payment.query.filter(
        Payment.tutor_id == tutor_id,
        Payment.month_year == current_month,
        Payment.status.in_(['pending', 'overdue'])
    ).all()
    result = []
    for p in payments:
        student = Student.query.get(p.student_id)
        if student:
            result.append({
                'student_name': student.student_name,
                'amount': p.amount,
                'status': p.status,
                'due_date': p.due_date.strftime('%d %b') if p.due_date else '',
            })
    return result


def get_collected_fees_detail(tutor_id):
    """Get detailed list of collected fees for dashboard card."""
    current_month = datetime.now().strftime('%Y-%m')
    payments = Payment.query.filter(
        Payment.tutor_id == tutor_id,
        Payment.month_year == current_month,
        Payment.status == 'paid'
    ).all()
    result = []
    for p in payments:
        student = Student.query.get(p.student_id)
        if student:
            result.append({
                'student_name': student.student_name,
                'amount': p.amount,
                'paid_date': p.paid_date.strftime('%d %b') if p.paid_date else '',
            })
    return result


def get_recent_payments(tutor_id, limit=10):
    """Get recent payment activity for Monthly Collection history."""
    payments = Payment.query.filter(
        Payment.tutor_id == tutor_id,
        Payment.status == 'paid'
    ).order_by(Payment.paid_date.desc()).limit(limit).all()
    result = []
    for p in payments:
        student = Student.query.get(p.student_id)
        if student:
            result.append({
                'student_name': student.student_name,
                'amount': p.amount,
                'paid_date': p.paid_date.strftime('%d %b %Y') if p.paid_date else '',
                'month_year': p.month_year,
            })
    return result


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    stats = get_dashboard_stats(current_user.id)
    chart_data = get_chart_data(current_user.id)
    today_classes = get_today_classes(current_user.id)
    total_expected = stats['pending_fees'] + stats['collected_fees']
    progress = int((stats['collected_fees'] / total_expected * 100)) if total_expected > 0 else 0

    # Detail data for clickable cards
    active_students_detail = get_active_students_detail(current_user.id)
    pending_fees_detail = get_pending_fees_detail(current_user.id)
    collected_fees_detail = get_collected_fees_detail(current_user.id)
    recent_payments = get_recent_payments(current_user.id)

    # Motivational quotes for each card
    quotes = {k: random.choice(v) for k, v in MOTIVATIONAL_QUOTES.items()}

    # New demo-class requests (from the public booking link)
    new_demo_requests = DemoRequest.query.filter_by(
        tutor_id=current_user.id, status='new').count()

    return render_template('dashboard.html',
        stats=stats, chart_data=chart_data,
        today_classes=today_classes, progress=progress,
        active_students_detail=active_students_detail,
        pending_fees_detail=pending_fees_detail,
        collected_fees_detail=collected_fees_detail,
        recent_payments=recent_payments,
        new_demo_requests=new_demo_requests,
        quotes=quotes)

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
