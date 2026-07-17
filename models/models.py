from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Tutor(UserMixin, db.Model):
    __tablename__ = 'tutors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    email = db.Column(db.String(100))
    password_hash = db.Column(db.String(255), nullable=False)
    subjects = db.Column(db.Text)
    classes_taught = db.Column(db.Text)
    experience_years = db.Column(db.Integer, default=0)
    qualification = db.Column(db.String(100))
    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(255))
    upi_id = db.Column(db.String(100))
    qr_image_path = db.Column(db.String(255))
    bank_account = db.Column(db.String(50))
    ifsc_code = db.Column(db.String(20))
    pay_token = db.Column(db.String(32))                       # Random token for public payment page URLs
    booking_token = db.Column(db.String(32))                   # Random token for public demo-booking page URL
    discoverable = db.Column(db.Boolean, default=False)        # Opt-in: listed in parent-facing teacher search
    city = db.Column(db.String(100))                           # For discovery filtering
    teaching_mode = db.Column(db.String(20), default='both')   # online / offline / both
    daily_reminder = db.Column(db.Boolean, default=True)      # Enable daily email reminder
    reminder_hour = db.Column(db.Integer, default=7)           # Morning reminder hour (0-23)
    reminder_minute = db.Column(db.Integer, default=0)         # Morning reminder minute (0-59)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    students = db.relationship('Student', backref='tutor', lazy=True, cascade='all, delete-orphan')
    schedules = db.relationship('Schedule', backref='tutor', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='tutor', lazy=True, cascade='all, delete-orphan')


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutors.id', ondelete='CASCADE'), nullable=False)
    student_name = db.Column(db.String(100), nullable=False)
    class_grade = db.Column(db.String(20))
    parent_name = db.Column(db.String(100))
    parent_phone = db.Column(db.String(15), nullable=False)
    parent_email = db.Column(db.String(100))
    subject = db.Column(db.String(200))
    fee_amount = db.Column(db.Float, nullable=False)
    payment_cycle = db.Column(db.String(20), default='monthly')
    student_type = db.Column(db.String(20), default='regular')
    notes = db.Column(db.Text)
    profile_image = db.Column(db.String(255))
    status = db.Column(db.String(20), default='active')   # active / archived
    date_of_joining = db.Column(db.Date)                   # for pro-rata fee calculation
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    schedules = db.relationship('Schedule', backref='student', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='student', lazy=True, cascade='all, delete-orphan')


class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutors.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    day_of_week = db.Column(db.String(15), nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10))
    class_type = db.Column(db.String(20), default='offline')
    location = db.Column(db.String(255))
    batch_name = db.Column(db.String(60))                  # group/batch classes share a name + slot
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutors.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    month_year = db.Column(db.String(7), nullable=False)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='pending')  # pending / paid / overdue
    paid_date = db.Column(db.Date)
    reminder_sent = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Attendance(db.Model):
    """Track class attendance per schedule per date."""
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutors.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='completed')  # completed / absent / cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Parent(db.Model):
    """Parent/student account for the teacher-discovery marketplace."""
    __tablename__ = 'parents'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    child_name = db.Column(db.String(100))
    child_class = db.Column(db.String(20))
    city = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    demo_requests = db.relationship('DemoRequest', backref='parent', lazy=True)


class DemoRequest(db.Model):
    """Demo class requests submitted by parents via the tutor's public booking link."""
    __tablename__ = 'demo_requests'
    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutors.id', ondelete='CASCADE'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id', ondelete='SET NULL'), nullable=True)
    student_name = db.Column(db.String(100), nullable=False)
    parent_name = db.Column(db.String(100))
    phone = db.Column(db.String(15), nullable=False)
    class_grade = db.Column(db.String(20))
    subject = db.Column(db.String(100))
    preferred_day = db.Column(db.String(15))
    preferred_time = db.Column(db.String(20))
    note = db.Column(db.Text)
    status = db.Column(db.String(20), default='new')  # new / contacted / closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Review(db.Model):
    """Parent rating for a tutor after a demo request was acted on."""
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutors.id', ondelete='CASCADE'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id', ondelete='CASCADE'), nullable=False)
    demo_request_id = db.Column(db.Integer, db.ForeignKey('demo_requests.id', ondelete='CASCADE'),
                                nullable=False, unique=True)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
