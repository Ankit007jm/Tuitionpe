"""
TuitionPe – Daily Schedule Email Reminder
- Sends every tutor a morning email listing their classes for the day.
- Each class has a one-click "Add to Google Calendar" link (no login/OAuth needed).
- Also sends a 30-min-before email for each upcoming class.
- Uses only Python built-in modules (threading) — NO extra pip installs.
"""

import smtplib
import urllib.parse
import threading
import time as _time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_greeting():
    """Return time-appropriate greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    elif hour < 17:
        return "Good Afternoon"
    elif hour < 21:
        return "Good Evening"
    else:
        return "Hello"


def make_gcal_link(title, date_obj, start_time_str, end_time_str, details='', location=''):
    """
    Build a Google Calendar one-click link.
    e.g. https://calendar.google.com/calendar/render?action=TEMPLATE&...
    No API key or OAuth required — works for anyone with a Google account.
    """
    try:
        sh, sm = map(int, start_time_str.split(':'))
        start_dt = datetime(date_obj.year, date_obj.month, date_obj.day, sh, sm)

        if end_time_str:
            eh, em = map(int, end_time_str.split(':'))
            end_dt = datetime(date_obj.year, date_obj.month, date_obj.day, eh, em)
        else:
            end_dt = start_dt + timedelta(hours=1)

        fmt = '%Y%m%dT%H%M%S'
        dates = f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}"

        params = {
            'action': 'TEMPLATE',
            'text': title,
            'dates': dates,
            'details': details,
        }
        if location:
            params['location'] = location

        return 'https://calendar.google.com/calendar/render?' + urllib.parse.urlencode(params)
    except Exception:
        return ''


def send_email(app, to_email, subject, html_body):
    """Send an HTML email using the app's SMTP config."""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = app.config.get('MAIL_DEFAULT_SENDER', 'TuitionPe')
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP(
            app.config.get('MAIL_SERVER', 'smtp.gmail.com'),
            app.config.get('MAIL_PORT', 587)
        )
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[TuitionPe Reminder] Email send failed: {e}")
        return False


# ─────────────────────────────────────────────
# Email HTML builders (mobile-first card layout)
# ─────────────────────────────────────────────

def build_daily_email(tutor_name, classes, today=None):
    """Build the daily schedule summary email — mobile-friendly card layout with Google Calendar buttons."""
    if today is None:
        today = date.today()

    date_str = today.strftime('%A, %B %d, %Y')
    count = len(classes)
    greeting = _get_greeting()

    if count == 0:
        class_cards = '''
        <div style="padding:32px 24px;text-align:center;">
          <p style="font-size:32px;margin:0 0 8px;">&#127881;</p>
          <p style="color:#9ca3af;font-size:14px;margin:0;">No classes scheduled today. Enjoy your day!</p>
        </div>'''
    else:
        cards = []
        for cls in classes:
            time_str = cls['start_time']
            if cls.get('end_time'):
                time_str += f" - {cls['end_time']}"

            gcal = cls.get('gcal_link', '')
            gcal_btn = ''
            if gcal:
                gcal_btn = f'''
                <div style="text-align:center;margin-top:12px;">
                  <a href="{gcal}" target="_blank"
                     style="display:inline-block;background:#4285f4;color:white;
                            border-radius:8px;padding:10px 20px;font-size:13px;font-weight:600;
                            text-decoration:none;">
                    &#128197; Add to Google Calendar
                  </a>
                </div>'''

            type_label = cls.get('class_type', 'offline').capitalize()

            cards.append(f'''
            <div style="background:#111;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:16px;margin:0 16px 10px;">
              <table style="width:100%;border-collapse:collapse;"><tr>
                <td style="vertical-align:top;">
                  <p style="color:white;font-size:15px;font-weight:600;margin:0;">{cls['student_name']}</p>
                  <p style="color:#9ca3af;font-size:12px;margin:4px 0 0;">{cls.get('subject','Tuition')}</p>
                </td>
                <td style="vertical-align:top;text-align:right;">
                  <span style="background:rgba(16,185,129,0.12);color:#10b981;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:700;">{type_label}</span>
                </td>
              </tr></table>
              <div style="margin-top:10px;background:rgba(16,185,129,0.08);border-radius:8px;padding:8px 12px;display:inline-block;">
                <span style="color:#10b981;font-size:15px;font-weight:700;">&#128336; {time_str}</span>
              </div>
              {gcal_btn}
            </div>''')
        class_cards = ''.join(cards)

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#050505;font-family:'Segoe UI',Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:24px 12px;">

    <div style="text-align:center;margin-bottom:24px;">
      <span style="color:#10b981;font-size:18px;font-weight:800;letter-spacing:5px;">TUITIONPE</span>
    </div>

    <div style="background:linear-gradient(135deg,#10b981,#059669);border-radius:16px 16px 0 0;padding:28px 20px;text-align:center;">
      <p style="color:rgba(255,255,255,0.85);margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:2px;">Daily Schedule</p>
      <h2 style="color:white;margin:0;font-size:22px;font-weight:700;">{greeting}, {tutor_name.split()[0]}!</h2>
      <p style="color:rgba(255,255,255,0.8);margin:8px 0 0;font-size:14px;">{date_str}</p>
    </div>

    <div style="background:#0a0a0a;border:1px solid rgba(255,255,255,0.07);border-top:0;border-radius:0 0 16px 16px;overflow:hidden;">

      <div style="padding:14px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
        <span style="background:rgba(16,185,129,0.15);color:#10b981;padding:6px 18px;border-radius:20px;font-size:13px;font-weight:600;">
          {count} class{'es' if count != 1 else ''} today
        </span>
      </div>

      {class_cards}

      <div style="padding:16px;text-align:center;border-top:1px solid rgba(255,255,255,0.05);">
        <p style="color:#4b5563;font-size:12px;margin:0;">
          Have a great teaching day! &#128640;<br>
          <span style="font-size:11px;">To change reminder time or turn off, go to Profile &gt; Reminder Settings</span>
        </p>
      </div>
    </div>

    <div style="text-align:center;margin-top:20px;">
      <span style="color:#10b981;font-size:11px;font-weight:800;letter-spacing:3px;">TUITIONPE</span>
      <p style="color:#374151;font-size:10px;margin:4px 0 0;">Smart Tuition Management for Modern Teachers</p>
    </div>
  </div>
</body>
</html>'''
    return html


def build_class_reminder_email(tutor_name, cls, minutes_before=30, today=None):
    """Build an HTML email for a single upcoming class reminder, with Google Calendar link."""
    if today is None:
        today = date.today()

    greeting = _get_greeting()
    time_str = cls['start_time']
    if cls.get('end_time'):
        time_str += f" - {cls['end_time']}"

    gcal = cls.get('gcal_link', '')
    gcal_btn = ''
    if gcal:
        gcal_btn = f'''
        <div style="text-align:center;margin-top:16px;">
          <a href="{gcal}" target="_blank"
             style="display:inline-block;background:#4285f4;color:white;
                    border-radius:10px;padding:12px 24px;font-size:14px;font-weight:600;
                    text-decoration:none;">
            &#128197; Add to Google Calendar
          </a>
        </div>'''

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#050505;font-family:'Segoe UI',Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:24px 12px;">
    <div style="text-align:center;margin-bottom:24px;">
      <span style="color:#10b981;font-size:16px;font-weight:800;letter-spacing:5px;">TUITIONPE</span>
    </div>
    <div style="background:#0a0a0a;border:1px solid rgba(255,255,255,0.07);border-radius:16px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#f97316,#ea580c);padding:22px;text-align:center;">
        <p style="color:rgba(255,255,255,0.85);margin:0 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:2px;">Class Starting Soon</p>
        <h2 style="color:white;margin:0;font-size:22px;font-weight:700;">&#9200; {minutes_before} minutes to go!</h2>
      </div>
      <div style="padding:24px;text-align:center;">
        <p style="color:white;font-size:17px;font-weight:700;margin:0 0 4px;">{cls['student_name']}</p>
        <p style="color:#9ca3af;font-size:14px;margin:0 0 20px;">{cls.get('subject','Tuition')} &bull; {cls.get('class_type','Offline').capitalize()}</p>
        <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);border-radius:12px;padding:14px 24px;display:inline-block;">
          <span style="color:#10b981;font-size:22px;font-weight:800;">{time_str}</span>
        </div>
        {gcal_btn}
      </div>
    </div>
    <div style="text-align:center;margin-top:20px;">
      <span style="color:#10b981;font-size:11px;font-weight:800;letter-spacing:3px;">TUITIONPE</span>
      <p style="color:#374151;font-size:10px;margin:4px 0 0;">Smart Tuition Management for Modern Teachers</p>
    </div>
  </div>
</body>
</html>'''
    return html


# ─────────────────────────────────────────────
# Core jobs
# ─────────────────────────────────────────────

def _get_classes_for_tutor(tutor_id, day_name, today=None):
    """Return a list of class dicts for a tutor on a given day, with gcal_link included."""
    from models import Student, Schedule
    if today is None:
        today = date.today()

    schedules = Schedule.query.filter_by(
        tutor_id=tutor_id, day_of_week=day_name, status='active'
    ).order_by(Schedule.start_time).all()

    classes = []
    for s in schedules:
        student = Student.query.get(s.student_id)
        if not student:
            continue
        details = f"{student.subject or 'Tuition'} class ({s.class_type})"
        gcal = make_gcal_link(
            title=f"{student.student_name} - {student.subject or 'Tuition'}",
            date_obj=today,
            start_time_str=s.start_time,
            end_time_str=s.end_time or '',
            details=details,
            location=s.location or ''
        )
        classes.append({
            'schedule_id': s.id,
            'student_name': student.student_name,
            'subject': student.subject or '',
            'start_time': s.start_time,
            'end_time': s.end_time or '',
            'class_type': s.class_type,
            'gcal_link': gcal,
        })
    return classes


def send_daily_reminders(app):
    """Send daily summary email to all tutors who have reminders enabled."""
    with app.app_context():
        from models import Tutor
        today = date.today()
        today_name = today.strftime('%A').lower()

        tutors = Tutor.query.filter(
            Tutor.email.isnot(None), Tutor.email != ''
        ).all()

        for tutor in tutors:
            if not getattr(tutor, 'daily_reminder', True):
                continue
            classes = _get_classes_for_tutor(tutor.id, today_name, today)
            html = build_daily_email(tutor.name, classes, today)
            day_str = today.strftime('%A, %b %d')
            subject = (f"Your schedule for today - {day_str} ({len(classes)} class{'es' if len(classes) != 1 else ''})"
                       if classes else f"No classes today - {day_str}")
            ok = send_email(app, tutor.email, subject, html)
            print(f"[TuitionPe] Daily email {'sent' if ok else 'FAILED'} -> {tutor.email}")


def send_class_reminders(app, minutes_before=30):
    """Check all tutors for upcoming classes and send 30-min-before reminders."""
    with app.app_context():
        from models import Tutor
        now = datetime.now()
        today = now.date()
        today_name = today.strftime('%A').lower()
        window_start = now + timedelta(minutes=minutes_before - 2)
        window_end   = now + timedelta(minutes=minutes_before + 3)

        tutors = Tutor.query.filter(
            Tutor.email.isnot(None), Tutor.email != ''
        ).all()

        for tutor in tutors:
            if not getattr(tutor, 'daily_reminder', True):
                continue
            classes = _get_classes_for_tutor(tutor.id, today_name, today)
            for cls in classes:
                try:
                    h, m = map(int, cls['start_time'].split(':'))
                    class_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if window_start <= class_dt <= window_end:
                        html = build_class_reminder_email(tutor.name, cls, minutes_before, today)
                        subject = f"Class in {minutes_before} min - {cls['student_name']} ({cls.get('subject','Tuition')})"
                        ok = send_email(app, tutor.email, subject, html)
                        print(f"[TuitionPe] Class reminder {'sent' if ok else 'FAILED'} -> {tutor.email}")
                except Exception as e:
                    print(f"[TuitionPe] Error processing class reminder: {e}")


def send_manual_daily_email(app, tutor_id):
    """Manually trigger today's schedule email for one tutor (called from profile/dashboard)."""
    with app.app_context():
        from models import Tutor
        tutor = Tutor.query.get(tutor_id)
        if not tutor or not tutor.email:
            return False, "No email address found. Please add your email in Profile."
        today = date.today()
        today_name = today.strftime('%A').lower()
        classes = _get_classes_for_tutor(tutor.id, today_name, today)
        html = build_daily_email(tutor.name, classes, today)
        day_str = today.strftime('%A, %b %d')
        subject = (f"Your schedule for today - {day_str} ({len(classes)} class{'es' if len(classes) != 1 else ''})"
                   if classes else f"No classes today - {day_str}")
        ok = send_email(app, tutor.email, subject, html)
        if ok:
            return True, f"Schedule sent to {tutor.email}"
        return False, "Failed to send email. Check your email settings in .env."


# ─────────────────────────────────────────────
# Background scheduler using threading.Timer
# No extra packages needed — uses only Python stdlib
# ─────────────────────────────────────────────

_stop_event = threading.Event()


def _daily_loop(app, hour, minute):
    """Background thread: waits until the target time each day, then sends daily emails."""
    while not _stop_event.is_set():
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        print(f"[TuitionPe Reminder] Next daily email in {wait_secs/3600:.1f} hours (at {target.strftime('%H:%M')})")

        # Sleep in small chunks so we can respond to stop_event
        while wait_secs > 0 and not _stop_event.is_set():
            chunk = min(wait_secs, 60)  # wake up every 60s to check stop
            _stop_event.wait(chunk)
            wait_secs -= chunk

        if _stop_event.is_set():
            break

        try:
            send_daily_reminders(app)
        except Exception as e:
            print(f"[TuitionPe Reminder] Daily job error: {e}")


def _class_alert_loop(app, interval_minutes=5):
    """Background thread: checks every 5 min for classes starting in ~30 min."""
    while not _stop_event.is_set():
        _stop_event.wait(interval_minutes * 60)
        if _stop_event.is_set():
            break
        try:
            send_class_reminders(app)
        except Exception as e:
            print(f"[TuitionPe Reminder] Class alert error: {e}")


def init_reminders(app):
    """Start background reminder threads. Call once from app.py."""
    reminder_hour   = int(app.config.get('REMINDER_HOUR', 7))
    reminder_minute = int(app.config.get('REMINDER_MINUTE', 0))

    _stop_event.clear()

    t1 = threading.Thread(target=_daily_loop, args=(app, reminder_hour, reminder_minute), daemon=True)
    t2 = threading.Thread(target=_class_alert_loop, args=(app,), daemon=True)
    t1.start()
    t2.start()

    print(f"[TuitionPe Reminder] Started — daily email at {reminder_hour:02d}:{reminder_minute:02d}, class alerts every 5 min")


def stop_reminders():
    """Gracefully stop background threads."""
    _stop_event.set()
