"""
Parent/student marketplace: search opted-in tutors and book demo classes fast.

Parents get their own lightweight session auth (session['parent_id']),
deliberately separate from the tutors' Flask-Login setup so no tutor route
can ever be reached with a parent identity.

Privacy rules:
- Only tutors with discoverable=True appear in search.
- A tutor's phone number is revealed to a parent only AFTER that parent
  has submitted a demo request to them (no scraping the directory).
"""
import time
from functools import wraps
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Tutor, Parent, DemoRequest

parents_bp = Blueprint('parents', __name__)

# Per-IP limiter for parent login attempts and demo requests
_attempts = {}
_MAX_ATTEMPTS = 8
_WINDOW_SECONDS = 600


def _is_limited(ip, bucket):
    now = time.time()
    key = (ip, bucket)
    hits = [t for t in _attempts.get(key, []) if now - t < _WINDOW_SECONDS]
    _attempts[key] = hits
    return len(hits) >= _MAX_ATTEMPTS


def _record(ip, bucket):
    _attempts.setdefault((ip, bucket), []).append(time.time())


def current_parent():
    pid = session.get('parent_id')
    return db.session.get(Parent, pid) if pid else None


def parent_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        parent = current_parent()
        if not parent:
            nxt = request.path if request.path.startswith('/') and not request.path.startswith('//') else None
            return redirect(url_for('parents.parent_login', next=nxt))
        return f(parent, *args, **kwargs)
    return wrapper


def _safe_next(default='/parent/home'):
    nxt = request.args.get('next') or request.form.get('next') or ''
    # Only same-site relative paths — never absolute URLs
    if nxt.startswith('/') and not nxt.startswith('//'):
        return nxt
    return default


# ─────────────────────────────────────────────────────────────
# Teacher discovery (public)
# ─────────────────────────────────────────────────────────────
@parents_bp.route('/find')
def find_teachers():
    subject = request.args.get('subject', '').strip()
    class_grade = request.args.get('class_grade', '').strip()
    city = request.args.get('city', '').strip()
    mode = request.args.get('mode', '').strip()

    query = Tutor.query.filter_by(discoverable=True)
    if subject:
        query = query.filter(Tutor.subjects.ilike(f'%{subject}%'))
    if class_grade:
        query = query.filter(Tutor.classes_taught.ilike(f'%{class_grade}%'))
    if city:
        query = query.filter(Tutor.city.ilike(f'%{city}%'))
    if mode in ('online', 'offline'):
        query = query.filter(Tutor.teaching_mode.in_([mode, 'both']))

    tutors = query.order_by(Tutor.experience_years.desc()).limit(50).all()

    parent = current_parent()
    # Which of these tutors has this parent already requested?
    requested_ids = set()
    if parent:
        requested_ids = {r.tutor_id for r in DemoRequest.query.filter_by(parent_id=parent.id).all()}

    # Popular subject chips for one-tap filtering
    subjects_set = []
    for t in Tutor.query.filter_by(discoverable=True).limit(200).all():
        for s in (t.subjects or '').split(','):
            s = s.strip()
            if s and s not in subjects_set:
                subjects_set.append(s)

    return render_template('parents/find.html',
        tutors=tutors, parent=parent, requested_ids=requested_ids,
        subject=subject, class_grade=class_grade, city=city, mode=mode,
        popular_subjects=subjects_set[:8])


@parents_bp.route('/find/request/<int:tutor_id>', methods=['POST'])
def request_demo(tutor_id):
    parent = current_parent()
    if not parent:
        flash('Create a free account to book demo classes.', 'info')
        return redirect(url_for('parents.parent_signup', next='/find'))

    client_ip = request.remote_addr or '0.0.0.0'
    if _is_limited(client_ip, 'demo'):
        flash('Too many requests. Please try again later.', 'error')
        return redirect(url_for('parents.find_teachers'))

    tutor = Tutor.query.filter_by(id=tutor_id, discoverable=True).first_or_404()

    # One open request per tutor per parent
    existing = DemoRequest.query.filter_by(parent_id=parent.id, tutor_id=tutor.id).first()
    if existing:
        flash(f'You already have a request with {tutor.name}. Check My Requests.', 'info')
        return redirect(url_for('parents.parent_home'))

    subject = request.form.get('subject', '').strip()[:100]
    db.session.add(DemoRequest(
        tutor_id=tutor.id,
        parent_id=parent.id,
        student_name=parent.child_name or parent.name,
        parent_name=parent.name,
        phone=parent.phone,
        class_grade=parent.child_class,
        subject=subject or (tutor.subjects or '').split(',')[0].strip(),
        note=request.form.get('note', '').strip()[:500],
    ))
    db.session.commit()
    _record(client_ip, 'demo')
    flash(f'Demo request sent to {tutor.name}! You can chat with them right away.', 'success')
    return redirect(url_for('parents.parent_home'))


# ─────────────────────────────────────────────────────────────
# Parent auth (session-based, separate from tutor Flask-Login)
# ─────────────────────────────────────────────────────────────
@parents_bp.route('/parent/signup', methods=['GET', 'POST'])
def parent_signup():
    if current_parent():
        return redirect(url_for('parents.parent_home'))
    if request.method == 'POST':
        client_ip = request.remote_addr or '0.0.0.0'
        if _is_limited(client_ip, 'signup'):
            flash('Too many attempts. Please wait a few minutes.', 'error')
            return redirect(url_for('parents.parent_signup'))

        name = request.form.get('name', '').strip()[:100]
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        child_name = request.form.get('child_name', '').strip()[:100]
        child_class = request.form.get('child_class', '').strip()[:20]
        city = request.form.get('city', '').strip()[:100]

        if len(name) < 2:
            flash('Please enter your name.', 'error')
            return redirect(url_for('parents.parent_signup', next=_safe_next()))
        if len(phone) != 10 or not phone.isdigit():
            flash('Please enter a valid 10-digit phone number.', 'error')
            return redirect(url_for('parents.parent_signup', next=_safe_next()))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('parents.parent_signup', next=_safe_next()))
        if Parent.query.filter_by(phone=phone).first():
            flash('This phone number is already registered. Please log in.', 'error')
            return redirect(url_for('parents.parent_login', next=_safe_next()))

        parent = Parent(
            name=name, phone=phone,
            password_hash=generate_password_hash(password),
            child_name=child_name, child_class=child_class, city=city,
        )
        db.session.add(parent)
        db.session.commit()
        _record(client_ip, 'signup')
        session['parent_id'] = parent.id
        flash(f'Welcome, {name.split()[0]}! Find your perfect teacher below.', 'success')
        return redirect(_safe_next('/find'))
    return render_template('parents/signup.html', next=_safe_next('/find'))


@parents_bp.route('/parent/login', methods=['GET', 'POST'])
def parent_login():
    if current_parent():
        return redirect(url_for('parents.parent_home'))
    if request.method == 'POST':
        client_ip = request.remote_addr or '0.0.0.0'
        if _is_limited(client_ip, 'login'):
            flash('Too many login attempts. Please wait a few minutes.', 'error')
            return redirect(url_for('parents.parent_login'))

        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        parent = Parent.query.filter_by(phone=phone).first()
        if parent and check_password_hash(parent.password_hash, password):
            session['parent_id'] = parent.id
            return redirect(_safe_next())
        _record(client_ip, 'login')
        flash('Invalid phone number or password.', 'error')
        return redirect(url_for('parents.parent_login', next=_safe_next()))
    return render_template('parents/login.html', next=_safe_next())


@parents_bp.route('/parent/logout')
def parent_logout():
    session.pop('parent_id', None)
    flash('Logged out. See you soon!', 'success')
    return redirect(url_for('parents.find_teachers'))


# ─────────────────────────────────────────────────────────────
# Parent dashboard
# ─────────────────────────────────────────────────────────────
@parents_bp.route('/parent/home')
@parent_required
def parent_home(parent):
    reqs = DemoRequest.query.filter_by(parent_id=parent.id) \
        .order_by(DemoRequest.created_at.desc()).all()
    # Tutor contact is revealed only for tutors the parent has requested
    tutor_map = {}
    for r in reqs:
        if r.tutor_id not in tutor_map:
            tutor_map[r.tutor_id] = db.session.get(Tutor, r.tutor_id)
    return render_template('parents/home.html', parent=parent, requests=reqs, tutors=tutor_map)
