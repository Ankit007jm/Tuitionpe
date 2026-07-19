"""
TuitionPe application test suite.

Covers auth (login/signup/CSRF/rate-limit/Google OAuth), access control
(cross-tenant isolation), students, schedule (incl. batch classes),
attendance, fees, PDF reports, and the public demo-booking flow.

Run:  python -m unittest tests.test_app -v
Uses an isolated temp SQLite DB via the DB_PATH env var.
"""
import os
import re
import sys
import tempfile
import unittest

# Point the app at a throwaway database BEFORE importing it
_TMP = tempfile.mkdtemp(prefix='tuitionpe_test_')
os.environ['DB_PATH'] = os.path.join(_TMP, 'test.db')
os.environ.pop('DATABASE_URL', None)
os.environ.pop('GOOGLE_CLIENT_ID', None)
os.environ.pop('GOOGLE_CLIENT_SECRET', None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from models import db, Tutor, Student, Schedule, Payment, Attendance, DemoRequest, Parent, Review  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402
import routes.auth as auth_mod  # noqa: E402
import routes.booking as booking_mod  # noqa: E402
import routes.parents as parents_mod  # noqa: E402
from datetime import datetime, date, timedelta  # noqa: E402

TUTOR1 = {'phone': '9000000001', 'password': 'pass1secure'}
TUTOR2 = {'phone': '9000000002', 'password': 'pass2secure'}


def seed():
    """Create two tutors, each with one student + payment + schedule."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        month = datetime.now().strftime('%Y-%m')
        today_name = datetime.now().strftime('%A').lower()
        ids = {}
        for i, (creds, sname) in enumerate([(TUTOR1, 'Alpha Kid'), (TUTOR2, 'Beta Kid')], start=1):
            t = Tutor(name=f'Tutor {i}', phone=creds['phone'],
                      email=f'tutor{i}@test.local',
                      password_hash=generate_password_hash(creds['password']),
                      subjects='Mathematics')
            db.session.add(t)
            db.session.flush()
            s = Student(tutor_id=t.id, student_name=sname, parent_phone=f'98888888{i}0',
                        subject='Mathematics', class_grade='10', fee_amount=1000.0)
            db.session.add(s)
            db.session.flush()
            p = Payment(tutor_id=t.id, student_id=s.id, amount=1000.0,
                        month_year=month, status='pending')
            sch = Schedule(tutor_id=t.id, student_id=s.id, day_of_week=today_name,
                           start_time='10:00', end_time='11:00')
            db.session.add_all([p, sch])
            db.session.flush()
            ids[f'tutor{i}'] = t.id
            ids[f'student{i}'] = s.id
            ids[f'payment{i}'] = p.id
            ids[f'schedule{i}'] = sch.id
        db.session.commit()
        return ids


def get_csrf(client):
    """Fetch the session CSRF token (works logged-in or logged-out)."""
    with client.session_transaction() as s:
        if s.get('csrf_token'):
            return s['csrf_token']
    client.get('/login', follow_redirects=True)  # render any page to seed the token
    with client.session_transaction() as s:
        return s['csrf_token']


def login(client, creds=TUTOR1):
    token = get_csrf(client)
    return client.post('/login', data={
        'phone': creds['phone'], 'password': creds['password'],
        'csrf_token': token,
    }, follow_redirects=False)


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.ids = seed()

    def setUp(self):
        # Reset in-memory rate limiters between tests
        auth_mod._login_attempts.clear()
        booking_mod._submissions.clear()
        parents_mod._attempts.clear()
        self.client = app.test_client()


# ─────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────
class TestAuth(BaseCase):
    def test_login_page_renders(self):
        r = self.client.get('/login')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Continue with Google', r.data)
        self.assertNotIn(b'Apple', r.data)

    def test_login_success(self):
        r = login(self.client)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/dashboard', r.headers['Location'])

    def test_login_wrong_password(self):
        token = get_csrf(self.client)
        r = self.client.post('/login', data={
            'phone': TUTOR1['phone'], 'password': 'wrongpass', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Invalid phone number or password', r.data)

    def test_login_invalid_phone_format(self):
        token = get_csrf(self.client)
        r = self.client.post('/login', data={
            'phone': '12345', 'password': 'x', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'valid 10-digit phone number', r.data)

    def test_post_without_csrf_rejected(self):
        r = self.client.post('/login', data={
            'phone': TUTOR1['phone'], 'password': TUTOR1['password'],
        })
        self.assertEqual(r.status_code, 400)

    def test_login_rate_limit(self):
        token = get_csrf(self.client)
        for _ in range(5):
            self.client.post('/login', data={
                'phone': TUTOR1['phone'], 'password': 'bad', 'csrf_token': token,
            })
        r = self.client.post('/login', data={
            'phone': TUTOR1['phone'], 'password': TUTOR1['password'], 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Too many login attempts', r.data)

    def test_protected_routes_require_login(self):
        for path in ('/dashboard', '/students', '/fees', '/schedule',
                     '/bookings', '/attendance', '/profile'):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn('/login', r.headers['Location'], path)

    def test_signup_validation(self):
        token = get_csrf(self.client)
        r = self.client.post('/signup', data={
            'name': 'X', 'phone': '9111111111', 'password': 'abcdef',
            'confirm_password': 'abcdef', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Name must be at least 2 characters', r.data)

        r = self.client.post('/signup', data={
            'name': 'New Tutor', 'phone': TUTOR1['phone'], 'password': 'abcdef',
            'confirm_password': 'abcdef', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'already registered', r.data)

    def test_signup_success(self):
        token = get_csrf(self.client)
        r = self.client.post('/signup', data={
            'name': 'Fresh Tutor', 'phone': '9333333333', 'password': 'abcdef',
            'confirm_password': 'abcdef', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Account created successfully', r.data)
        with app.app_context():
            t = Tutor.query.filter_by(phone='9333333333').first()
            self.assertIsNotNone(t)
            self.assertNotIn('abcdef', t.password_hash)  # hashed, not plaintext

    def test_google_login_unconfigured(self):
        r = self.client.get('/login/google', follow_redirects=True)
        self.assertIn(b'not configured', r.data)

    def test_google_callback_forged_state(self):
        os.environ['GOOGLE_CLIENT_ID'] = 'x'
        os.environ['GOOGLE_CLIENT_SECRET'] = 'y'
        try:
            r = self.client.get('/login/google/callback?state=forged&code=z',
                                follow_redirects=True)
            self.assertIn(b'expired', r.data)
        finally:
            os.environ.pop('GOOGLE_CLIENT_ID')
            os.environ.pop('GOOGLE_CLIENT_SECRET')

    def test_legal_pages(self):
        self.assertEqual(self.client.get('/terms').status_code, 200)
        self.assertEqual(self.client.get('/privacy').status_code, 200)

    def test_security_headers_present(self):
        r = self.client.get('/login')
        self.assertEqual(r.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(r.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertIn('Referrer-Policy', r.headers)

    def test_otp_never_stored_in_session_cookie(self):
        """The session cookie is client-readable; the OTP must not be in it."""
        with app.app_context():
            auth_mod._store_otp(self.ids['tutor1'], '123456')
        with self.client.session_transaction() as s:
            s['reset_tutor_id'] = self.ids['tutor1']
            s['reset_phone'] = TUTOR1['phone']
        with self.client.session_transaction() as s:
            self.assertNotIn('reset_otp', s)

    def test_otp_attempt_limit(self):
        with app.app_context():
            auth_mod._store_otp(self.ids['tutor1'], '654321')
        with self.client.session_transaction() as s:
            s['reset_tutor_id'] = self.ids['tutor1']
        token = get_csrf(self.client)
        for _ in range(5):
            self.client.post('/verify-otp', data={'otp': '000000', 'csrf_token': token})
        r = self.client.post('/verify-otp', data={'otp': '654321', 'csrf_token': token},
                             follow_redirects=True)
        self.assertIn(b'Too many incorrect attempts', r.data)
        # OTP record is gone — even the right code no longer works
        from models import PasswordReset
        with app.app_context():
            self.assertIsNone(db.session.get(PasswordReset, self.ids['tutor1']))

    def test_otp_correct_flow(self):
        with app.app_context():
            auth_mod._store_otp(self.ids['tutor1'], '111222')
        with self.client.session_transaction() as s:
            s['reset_tutor_id'] = self.ids['tutor1']
        token = get_csrf(self.client)
        r = self.client.post('/verify-otp', data={'otp': '111222', 'csrf_token': token},
                             follow_redirects=True)
        self.assertIn(b'OTP verified', r.data)


# ─────────────────────────────────────────────────────────────
# Access control: tutor 1 must never touch tutor 2's data
# ─────────────────────────────────────────────────────────────
class TestAccessControl(BaseCase):
    def setUp(self):
        super().setUp()
        login(self.client)  # tutor 1
        self.token = get_csrf(self.client)

    def test_student_list_isolated(self):
        r = self.client.get('/students')
        self.assertIn(b'Alpha Kid', r.data)
        self.assertNotIn(b'Beta Kid', r.data)

    def test_cannot_edit_other_student(self):
        r = self.client.get(f"/students/{self.ids['student2']}/edit")
        self.assertEqual(r.status_code, 404)

    def test_cannot_view_other_payment_history(self):
        r = self.client.get(f"/fees/history/{self.ids['student2']}")
        self.assertEqual(r.status_code, 404)

    def test_cannot_download_other_progress_report(self):
        r = self.client.get(f"/students/{self.ids['student2']}/progress-report")
        self.assertEqual(r.status_code, 404)

    def test_cannot_mark_other_payment_paid(self):
        r = self.client.post(f"/fees/{self.ids['payment2']}/mark-paid",
                             data={'csrf_token': self.token})
        self.assertEqual(r.status_code, 404)

    def test_cannot_delete_other_schedule(self):
        r = self.client.post(f"/schedule/{self.ids['schedule2']}/delete",
                             data={'csrf_token': self.token})
        self.assertEqual(r.status_code, 404)

    def test_cannot_mark_other_attendance(self):
        r = self.client.post(f"/schedule/{self.ids['schedule2']}/attendance",
                             data={'csrf_token': self.token, 'attendance_status': 'completed'})
        self.assertEqual(r.status_code, 404)

    def test_cannot_archive_other_student(self):
        r = self.client.post(f"/students/{self.ids['student2']}/delete",
                             data={'csrf_token': self.token})
        self.assertEqual(r.status_code, 404)


# ─────────────────────────────────────────────────────────────
# Students
# ─────────────────────────────────────────────────────────────
class TestStudents(BaseCase):
    def setUp(self):
        super().setUp()
        login(self.client)
        self.token = get_csrf(self.client)

    def test_add_student(self):
        r = self.client.post('/students/add', data={
            'student_name': 'Gamma Kid', 'parent_phone': '9777777770',
            'fee_amount': '1200', 'payment_cycle': 'monthly',
            'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        with app.app_context():
            s = Student.query.filter_by(student_name='Gamma Kid').first()
            self.assertIsNotNone(s)
            self.assertEqual(s.tutor_id, self.ids['tutor1'])
            # A payment record is auto-created for the current month
            p = Payment.query.filter_by(student_id=s.id).first()
            self.assertIsNotNone(p)

    def test_add_student_invalid_phone(self):
        r = self.client.post('/students/add', data={
            'student_name': 'Bad Phone Kid', 'parent_phone': '123',
            'fee_amount': '500', 'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertIn(b'valid 10-digit phone number', r.data)

    def test_add_student_invalid_fee(self):
        r = self.client.post('/students/add', data={
            'student_name': 'Free Kid', 'parent_phone': '9777777771',
            'fee_amount': '-5', 'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertIn(b'greater than 0', r.data)

    def test_duplicate_student_blocked(self):
        data = {
            'student_name': 'Dup Kid', 'parent_phone': '9777777772',
            'fee_amount': '800', 'csrf_token': self.token,
        }
        self.client.post('/students/add', data=data, follow_redirects=True)
        r = self.client.post('/students/add', data=data, follow_redirects=True)
        self.assertIn(b'already exists', r.data)

    def test_attendance_pct_on_list(self):
        with app.app_context():
            sid = self.ids['student1']
            sch = self.ids['schedule1']
            tid = self.ids['tutor1']
            db.session.add(Attendance(tutor_id=tid, student_id=sid, schedule_id=sch,
                                      date=date.today() - timedelta(days=7), status='completed'))
            db.session.add(Attendance(tutor_id=tid, student_id=sid, schedule_id=sch,
                                      date=date.today() - timedelta(days=14), status='absent'))
            db.session.commit()
        r = self.client.get('/students')
        self.assertIn(b'50%', r.data)

    def test_progress_report_pdf(self):
        r = self.client.get(f"/students/{self.ids['student1']}/progress-report")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['Content-Type'], 'application/pdf')
        self.assertTrue(r.data.startswith(b'%PDF-'))


# ─────────────────────────────────────────────────────────────
# Schedule & batches
# ─────────────────────────────────────────────────────────────
class TestSchedule(BaseCase):
    # Days guaranteed not to collide with the seeded "today" schedules
    @staticmethod
    def _other_days():
        today = datetime.now().strftime('%A').lower()
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        return [d for d in days if d != today]

    def setUp(self):
        super().setUp()
        login(self.client)
        self.token = get_csrf(self.client)
        self.day_a, self.day_b, self.day_c = self._other_days()[:3]

    def test_single_class_add(self):
        r = self.client.post('/schedule/add', data={
            'student_ids': [str(self.ids['student1'])],
            'day_of_week': self.day_a, 'start_time': '09:00',
            'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertIn(b'Class scheduled successfully', r.data)
        with app.app_context():
            rows = Schedule.query.filter_by(day_of_week=self.day_a, start_time='09:00').all()
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0].batch_name)

    def test_batch_add_groups_students(self):
        with app.app_context():
            extra = Student(tutor_id=self.ids['tutor1'], student_name='Delta Kid',
                            parent_phone='9777777773', fee_amount=900.0)
            db.session.add(extra)
            db.session.commit()
            extra_id = extra.id
        r = self.client.post('/schedule/add', data={
            'student_ids': [str(self.ids['student1']), str(extra_id)],
            'day_of_week': self.day_b, 'start_time': '15:00',
            'batch_name': 'Weekend Batch',
            'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertIn(b'Batch scheduled with 2 students', r.data)
        with app.app_context():
            rows = Schedule.query.filter_by(batch_name='Weekend Batch').all()
            self.assertEqual(len(rows), 2)
        page = self.client.get(f'/schedule?day={self.day_b}')
        self.assertIn(b'Weekend Batch', page.data)
        self.assertIn(b'BATCH', page.data)

    def test_batch_add_rejects_foreign_students(self):
        r = self.client.post('/schedule/add', data={
            'student_ids': [str(self.ids['student2'])],  # tutor 2's student
            'day_of_week': self.day_c, 'start_time': '10:00',
            'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertIn(b'No valid students selected', r.data)
        with app.app_context():
            self.assertEqual(Schedule.query.filter_by(day_of_week=self.day_c).count(), 0)

    def test_invalid_time_rejected(self):
        r = self.client.post('/schedule/add', data={
            'student_ids': [str(self.ids['student1'])],
            'day_of_week': self.day_a, 'start_time': 'not-a-time',
            'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertIn(b'Invalid start time format', r.data)

    def test_mark_attendance(self):
        r = self.client.post(f"/schedule/{self.ids['schedule1']}/attendance", data={
            'attendance_status': 'completed', 'csrf_token': self.token,
        }, follow_redirects=True)
        self.assertIn(b'Attendance marked', r.data)
        with app.app_context():
            row = Attendance.query.filter_by(
                schedule_id=self.ids['schedule1'], date=date.today()).first()
            self.assertIsNotNone(row)
            self.assertEqual(row.status, 'completed')


# ─────────────────────────────────────────────────────────────
# Fees & reports
# ─────────────────────────────────────────────────────────────
class TestFees(BaseCase):
    def setUp(self):
        super().setUp()
        login(self.client)
        self.token = get_csrf(self.client)

    def test_fees_page(self):
        r = self.client.get('/fees')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Payments', r.data)

    def test_mark_paid_and_unpaid(self):
        pid = self.ids['payment1']
        r = self.client.post(f'/fees/{pid}/mark-paid', data={'csrf_token': self.token},
                             follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        with app.app_context():
            self.assertEqual(Payment.query.get(pid).status, 'paid')
        self.client.post(f'/fees/{pid}/mark-unpaid', data={'csrf_token': self.token})
        with app.app_context():
            self.assertEqual(Payment.query.get(pid).status, 'pending')

    def test_monthly_report_pdf(self):
        month = datetime.now().strftime('%Y-%m')
        r = self.client.get(f'/fees/report?month={month}')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b'%PDF-'))

    def test_monthly_report_invalid_month(self):
        r = self.client.get('/fees/report?month=banana', follow_redirects=True)
        self.assertIn(b'Invalid month', r.data)


# ─────────────────────────────────────────────────────────────
# Public demo booking
# ─────────────────────────────────────────────────────────────
class TestBooking(BaseCase):
    def _booking_url(self):
        with app.app_context():
            t = Tutor.query.get(self.ids['tutor1'])
            token = booking_mod.make_booking_token(t)
            return f"/book/{self.ids['tutor1']}/{token}"

    def _public_csrf(self, client, url):
        page = client.get(url).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    def test_public_page_valid_token(self):
        r = self.client.get(self._booking_url())
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Book a free demo class', r.data)

    def test_public_page_invalid_token(self):
        r = self.client.get(f"/book/{self.ids['tutor1']}/wrongtoken00000000")
        self.assertEqual(r.status_code, 404)

    def test_submit_booking(self):
        url = self._booking_url()
        token = self._public_csrf(self.client, url)
        r = self.client.post(url, data={
            'student_name': 'Demo Seeker', 'phone': '9666666660',
            'subject': 'Mathematics', 'preferred_day': 'monday',
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Request sent', r.data)
        with app.app_context():
            req = DemoRequest.query.filter_by(student_name='Demo Seeker').first()
            self.assertIsNotNone(req)
            self.assertEqual(req.tutor_id, self.ids['tutor1'])
            self.assertEqual(req.status, 'new')

    def test_submit_invalid_phone_rejected(self):
        url = self._booking_url()
        token = self._public_csrf(self.client, url)
        self.client.post(url, data={
            'student_name': 'Bad Phone', 'phone': '12', 'csrf_token': token,
        })
        with app.app_context():
            self.assertIsNone(DemoRequest.query.filter_by(student_name='Bad Phone').first())

    def test_honeypot_drops_bots(self):
        url = self._booking_url()
        token = self._public_csrf(self.client, url)
        r = self.client.post(url, data={
            'student_name': 'Bot Kid', 'phone': '9666666661',
            'website': 'http://spam.example', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Request sent', r.data)  # bot sees success…
        with app.app_context():                  # …but nothing is stored
            self.assertIsNone(DemoRequest.query.filter_by(student_name='Bot Kid').first())

    def test_booking_rate_limit(self):
        url = self._booking_url()
        token = self._public_csrf(self.client, url)
        for i in range(5):
            self.client.post(url, data={
                'student_name': f'Flood {i}', 'phone': f'966666670{i}',
                'csrf_token': token,
            })
        r = self.client.post(url, data={
            'student_name': 'Flood 6', 'phone': '9666666706', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Too many requests', r.data)

    def test_manage_requests(self):
        with app.app_context():
            req = DemoRequest(tutor_id=self.ids['tutor1'], student_name='Manage Me',
                              phone='9666666662')
            db.session.add(req)
            db.session.commit()
            rid = req.id
        login(self.client)
        token = get_csrf(self.client)
        r = self.client.get('/bookings')
        self.assertIn(b'Manage Me', r.data)
        self.client.post(f'/bookings/{rid}/status',
                         data={'status': 'contacted', 'csrf_token': token})
        with app.app_context():
            self.assertEqual(DemoRequest.query.get(rid).status, 'contacted')
        # invalid status rejected
        self.client.post(f'/bookings/{rid}/status',
                         data={'status': 'hacked', 'csrf_token': token})
        with app.app_context():
            self.assertEqual(DemoRequest.query.get(rid).status, 'contacted')

    def test_other_tutor_cannot_manage_requests(self):
        with app.app_context():
            req = DemoRequest(tutor_id=self.ids['tutor1'], student_name='Private Req',
                              phone='9666666663')
            db.session.add(req)
            db.session.commit()
            rid = req.id
        login(self.client, TUTOR2)
        token = get_csrf(self.client)
        r = self.client.post(f'/bookings/{rid}/status',
                             data={'status': 'closed', 'csrf_token': token})
        self.assertEqual(r.status_code, 404)


# ─────────────────────────────────────────────────────────────
# Parent marketplace (teacher discovery)
# ─────────────────────────────────────────────────────────────
class TestMarketplace(BaseCase):
    PARENT = {'phone': '9500000001', 'password': 'parentpass'}

    def _signup_parent(self, client=None, phone=None):
        client = client or self.client
        token = get_csrf(client)
        return client.post('/parent/signup', data={
            'name': 'Test Parent', 'phone': phone or self.PARENT['phone'],
            'password': self.PARENT['password'],
            'child_name': 'Test Kid', 'child_class': '9', 'city': 'Patna',
            'csrf_token': token,
        }, follow_redirects=True)

    def _make_discoverable(self, tutor_id):
        with app.app_context():
            t = db.session.get(Tutor, tutor_id)
            t.discoverable = True
            t.city = 'Patna'
            db.session.commit()

    def test_find_page_public(self):
        r = self.client.get('/find')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Find your perfect teacher', r.data)

    def test_only_discoverable_tutors_listed(self):
        r = self.client.get('/find')
        self.assertNotIn(b'Tutor 1', r.data)  # not opted in
        self._make_discoverable(self.ids['tutor1'])
        r = self.client.get('/find')
        self.assertIn(b'Tutor 1', r.data)
        self.assertNotIn(b'Tutor 2', r.data)  # still not opted in

    def test_tutor_phone_not_exposed_in_search(self):
        self._make_discoverable(self.ids['tutor1'])
        r = self.client.get('/find')
        self.assertNotIn(TUTOR1['phone'].encode(), r.data)

    def test_search_filters(self):
        self._make_discoverable(self.ids['tutor1'])
        r = self.client.get('/find?subject=Mathematics')
        self.assertIn(b'Tutor 1', r.data)
        r = self.client.get('/find?subject=Chemistry')
        self.assertNotIn(b'Tutor 1', r.data)
        r = self.client.get('/find?city=Delhi')
        self.assertNotIn(b'Tutor 1', r.data)

    def test_parent_signup_and_login(self):
        r = self._signup_parent()
        self.assertIn(b'Welcome, Test', r.data)
        self.client.get('/parent/logout')
        token = get_csrf(self.client)
        r = self.client.post('/parent/login', data={
            'phone': self.PARENT['phone'], 'password': self.PARENT['password'],
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'My Demo Requests', r.data)

    def test_parent_login_wrong_password(self):
        self._signup_parent(phone='9500000002')
        self.client.get('/parent/logout')
        token = get_csrf(self.client)
        r = self.client.post('/parent/login', data={
            'phone': '9500000002', 'password': 'wrong', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Invalid phone number or password', r.data)

    def test_parent_home_requires_login(self):
        r = self.client.get('/parent/home')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/parent/login', r.headers['Location'])

    def test_next_param_rejects_offsite_urls(self):
        self._signup_parent(phone='9500000003')
        self.client.get('/parent/logout')
        token = get_csrf(self.client)
        r = self.client.post('/parent/login?next=https://evil.example', data={
            'phone': '9500000003', 'password': self.PARENT['password'],
            'csrf_token': token,
        })
        self.assertNotIn('evil.example', r.headers.get('Location', ''))

    def test_request_demo_requires_account(self):
        self._make_discoverable(self.ids['tutor1'])
        token = get_csrf(self.client)
        r = self.client.post(f"/find/request/{self.ids['tutor1']}",
                             data={'csrf_token': token})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/parent/signup', r.headers['Location'])

    def test_request_demo_flow(self):
        self._make_discoverable(self.ids['tutor1'])
        self._signup_parent(phone='9500000004')
        token = get_csrf(self.client)
        r = self.client.post(f"/find/request/{self.ids['tutor1']}", data={
            'subject': 'Mathematics', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Demo request sent', r.data)
        with app.app_context():
            req = DemoRequest.query.filter_by(phone='9500000004').first()
            self.assertIsNotNone(req)
            self.assertEqual(req.tutor_id, self.ids['tutor1'])
            self.assertIsNotNone(req.parent_id)
        # Parent home shows the request and reveals tutor contact
        r = self.client.get('/parent/home')
        self.assertIn(b'Tutor 1', r.data)
        self.assertIn(b'Chat on WhatsApp', r.data)
        # Duplicate request to the same tutor is blocked
        r = self.client.post(f"/find/request/{self.ids['tutor1']}", data={
            'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'already have a request', r.data)

    def test_cannot_request_undiscoverable_tutor(self):
        self._signup_parent(phone='9500000005')
        token = get_csrf(self.client)
        r = self.client.post(f"/find/request/{self.ids['tutor2']}",
                             data={'csrf_token': token})
        self.assertEqual(r.status_code, 404)

    def test_tutor_sees_marketplace_request(self):
        self._make_discoverable(self.ids['tutor1'])
        self._signup_parent(phone='9500000006')
        token = get_csrf(self.client)
        self.client.post(f"/find/request/{self.ids['tutor1']}",
                         data={'csrf_token': token})
        tutor_client = app.test_client()
        login(tutor_client, TUTOR1)
        r = tutor_client.get('/bookings')
        self.assertIn(b'Test Kid', r.data)
        self.assertIn(b'Search', r.data)  # marketplace badge

    def test_parents_see_only_their_requests(self):
        self._make_discoverable(self.ids['tutor1'])
        self._signup_parent(phone='9500000007')
        token = get_csrf(self.client)
        self.client.post(f"/find/request/{self.ids['tutor1']}",
                         data={'csrf_token': token})
        other = app.test_client()
        tok2 = get_csrf(other)
        other.post('/parent/signup', data={
            'name': 'Other Parent', 'phone': '9500000008',
            'password': 'otherpass1', 'csrf_token': tok2,
        })
        r = other.get('/parent/home')
        self.assertNotIn(b'Test Kid', r.data)


# ─────────────────────────────────────────────────────────────
# Landing page & reviews
# ─────────────────────────────────────────────────────────────
class TestLandingAndReviews(BaseCase):
    def _parent_with_request(self, phone, status='contacted'):
        """Signup a parent and give them a demo request in the given status."""
        token = get_csrf(self.client)
        self.client.post('/parent/signup', data={
            'name': 'Review Parent', 'phone': phone, 'password': 'reviewpass',
            'child_name': 'Review Kid', 'csrf_token': token,
        })
        with app.app_context():
            t = db.session.get(Tutor, self.ids['tutor1'])
            t.discoverable = True
            parent = Parent.query.filter_by(phone=phone).first()
            req = DemoRequest(tutor_id=t.id, parent_id=parent.id,
                              student_name='Review Kid', phone=phone, status=status)
            db.session.add(req)
            db.session.commit()
            return req.id

    def test_landing_page_anonymous(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'I\'m looking for a teacher', r.data.replace(b'&#39;', b'\''))
        self.assertIn(b'Teacher login', r.data)

    def test_landing_redirects_logged_in_tutor(self):
        login(self.client)
        r = self.client.get('/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/dashboard', r.headers['Location'])

    def test_landing_redirects_logged_in_parent(self):
        token = get_csrf(self.client)
        self.client.post('/parent/signup', data={
            'name': 'Land Parent', 'phone': '9400000001', 'password': 'landpass1',
            'csrf_token': token,
        })
        r = self.client.get('/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/find', r.headers['Location'])

    def test_review_blocked_while_request_new(self):
        rid = self._parent_with_request('9400000002', status='new')
        token = get_csrf(self.client)
        r = self.client.post(f'/parent/review/{rid}', data={
            'rating': '5', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'once they have been in touch', r.data)
        with app.app_context():
            self.assertEqual(Review.query.filter_by(demo_request_id=rid).count(), 0)

    def test_review_submit_and_update(self):
        rid = self._parent_with_request('9400000003', status='contacted')
        token = get_csrf(self.client)
        r = self.client.post(f'/parent/review/{rid}', data={
            'rating': '5', 'comment': 'Great teacher!', 'csrf_token': token,
        }, follow_redirects=True)
        self.assertIn(b'Thanks for rating', r.data)
        with app.app_context():
            rv = Review.query.filter_by(demo_request_id=rid).first()
            self.assertEqual(rv.rating, 5)
        # Update instead of duplicate
        self.client.post(f'/parent/review/{rid}', data={
            'rating': '4', 'csrf_token': token,
        })
        with app.app_context():
            self.assertEqual(Review.query.filter_by(demo_request_id=rid).count(), 1)
            self.assertEqual(Review.query.filter_by(demo_request_id=rid).first().rating, 4)

    def test_review_rating_bounds(self):
        rid = self._parent_with_request('9400000004', status='closed')
        token = get_csrf(self.client)
        for bad in ('0', '6', 'abc', ''):
            self.client.post(f'/parent/review/{rid}', data={
                'rating': bad, 'csrf_token': token,
            })
        with app.app_context():
            self.assertEqual(Review.query.filter_by(demo_request_id=rid).count(), 0)

    def test_cannot_review_others_request(self):
        rid = self._parent_with_request('9400000005', status='contacted')
        other = app.test_client()
        tok = get_csrf(other)
        other.post('/parent/signup', data={
            'name': 'Sneaky', 'phone': '9400000006', 'password': 'sneakypass',
            'csrf_token': tok,
        })
        r = other.post(f'/parent/review/{rid}', data={'rating': '1', 'csrf_token': get_csrf(other)})
        self.assertEqual(r.status_code, 404)

    def test_rating_shows_on_find_page(self):
        rid = self._parent_with_request('9400000007', status='contacted')
        token = get_csrf(self.client)
        self.client.post(f'/parent/review/{rid}', data={
            'rating': '5', 'csrf_token': token,
        })
        r = self.client.get('/find')
        self.assertIn(b'fa-star', r.data)
        self.assertIn(b'5.0', r.data)

    def test_marketplace_request_with_tutor_email_does_not_crash(self):
        """Tutor 1 has an email; the notify thread must not break the request."""
        with app.app_context():
            t = db.session.get(Tutor, self.ids['tutor1'])
            t.discoverable = True
            db.session.commit()
        token = get_csrf(self.client)
        self.client.post('/parent/signup', data={
            'name': 'Notify Parent', 'phone': '9400000008', 'password': 'notifypass',
            'csrf_token': token,
        })
        r = self.client.post(f"/find/request/{self.ids['tutor1']}", data={
            'csrf_token': get_csrf(self.client),
        }, follow_redirects=True)
        self.assertIn(b'Demo request sent', r.data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
