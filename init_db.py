"""Initialize database with schema and sample data."""
from app import app, db
from models import Tutor, Student, Schedule, Payment
from werkzeug.security import generate_password_hash
from datetime import datetime, date, timedelta

def init():
    with app.app_context():
        db.drop_all()
        db.create_all()

        # Sample Tutor
        tutor = Tutor(
            name="Ankita Kumari",
            phone="9876543210",
            email="ankita@email.com",
            password_hash=generate_password_hash("password123"),
            subjects="Physics,Maths",
            classes_taught="9-10,11-12",
            experience_years=10,
            qualification="M.Sc Physics",
            bio="Passionate teacher with 10+ years experience in Physics and Maths."
        )
        db.session.add(tutor)
        db.session.commit()

        # Sample Students
        students_data = [
            {"name": "Rahul Gupta", "class": "11", "subject": "Physics",
             "parent": "Mr. Gupta", "phone": "9876543211", "fee": 2000, "type": "regular"},
            {"name": "Sneha Sharma", "class": "10", "subject": "Maths",
             "parent": "Mrs. Sharma", "phone": "9876543212", "fee": 1500, "type": "regular"},
            {"name": "Amit Kumar", "class": "12", "subject": "Physics",
             "parent": "Mr. Kumar", "phone": "9876543213", "fee": 2000, "type": "regular"},
            {"name": "Priya Patel", "class": "9", "subject": "Maths",
             "parent": "Mr. Patel", "phone": "9876543214", "fee": 1800, "type": "exam"},
            {"name": "Vikram Singh", "class": "11", "subject": "Maths",
             "parent": "Mr. Singh", "phone": "9876543215", "fee": 2000, "type": "regular"},
        ]

        student_objects = []
        for sd in students_data:
            s = Student(
                tutor_id=tutor.id,
                student_name=sd['name'],
                class_grade=sd['class'],
                subject=sd['subject'],
                parent_name=sd['parent'],
                parent_phone=sd['phone'],
                fee_amount=sd['fee'],
                student_type=sd['type'],
            )
            db.session.add(s)
            student_objects.append(s)
        db.session.commit()

        # Sample Schedules (spread across week)
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        times = [('16:00', '17:00'), ('17:30', '18:30'), ('16:00', '17:00'), ('18:00', '19:00'), ('17:00', '18:00')]
        for i, s in enumerate(student_objects):
            sched = Schedule(
                tutor_id=tutor.id,
                student_id=s.id,
                day_of_week=days[i % 5],
                start_time=times[i][0],
                end_time=times[i][1],
                class_type='offline',
            )
            db.session.add(sched)

        # Also add some classes for today
        today_name = date.today().strftime('%A').lower()
        for i, s in enumerate(student_objects[:3]):
            sched = Schedule(
                tutor_id=tutor.id,
                student_id=s.id,
                day_of_week=today_name,
                start_time=f'{16+i}:00',
                end_time=f'{17+i}:00',
                class_type='offline',
            )
            db.session.add(sched)

        db.session.commit()

        # Sample Payments for current month
        current_month = datetime.now().strftime('%Y-%m')
        statuses = ['paid', 'paid', 'pending', 'pending', 'overdue']
        for i, s in enumerate(student_objects):
            p = Payment(
                tutor_id=tutor.id,
                student_id=s.id,
                amount=s.fee_amount,
                month_year=current_month,
                status=statuses[i],
                paid_date=date.today() if statuses[i] == 'paid' else None,
            )
            db.session.add(p)

        # Some historical data for chart (last 5 months)
        for m in range(5, 0, -1):
            month_date = datetime.now() - timedelta(days=30 * m)
            month_year = month_date.strftime('%Y-%m')
            for i, s in enumerate(student_objects):
                status = 'paid' if i < 3 else ('pending' if i == 3 else 'overdue')
                p = Payment(
                    tutor_id=tutor.id,
                    student_id=s.id,
                    amount=s.fee_amount,
                    month_year=month_year,
                    status=status,
                    paid_date=month_date.date() if status == 'paid' else None,
                )
                db.session.add(p)

        db.session.commit()
        print("✅ Database initialized with sample data!")
        print(f"📱 Login: Phone=9876543210, Password=password123")
        print(f"👩‍🏫 Tutor: Ankita Kumari")
        print(f"👨‍🎓 Students: {len(student_objects)} created")

if __name__ == '__main__':
    init()
