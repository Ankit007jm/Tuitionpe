"""
TuitionPe -- PDF Receipt Generator & Email Sender

Generates professional payment receipts as PDF and sends via email.
Uses fpdf2 if available, otherwise falls back to a pure-Python minimal PDF generator.
Also provides a downloadable PDF link for WhatsApp sharing.
"""

import os
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, date

# Try importing fpdf2; if not available we use a minimal fallback
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False


# ────────────────────────────────────────────────────────────
# PDF Generation using fpdf2
# ────────────────────────────────────────────────────────────

class ReceiptPDF(FPDF if HAS_FPDF else object):
    """Professional receipt PDF using fpdf2."""

    def __init__(self, tutor, student, payment):
        if not HAS_FPDF:
            raise ImportError("fpdf2 not installed")
        super().__init__()
        self.tutor = tutor
        self.student = student
        self.payment = payment
        self._receipt_no = f"TP-{payment.id:06d}"
        self._paid_date = payment.paid_date.strftime('%d %B %Y') if payment.paid_date else date.today().strftime('%d %B %Y')
        try:
            self._month_display = datetime.strptime(payment.month_year[:7], '%Y-%m').strftime('%B %Y')
        except Exception:
            self._month_display = payment.month_year

    def header(self):
        # Green header bar
        self.set_fill_color(16, 185, 129)
        self.rect(0, 0, 210, 38, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 22)
        self.set_y(8)
        self.cell(0, 10, 'TUITIONPE', align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_font('Helvetica', '', 10)
        self.cell(0, 7, 'Payment Receipt', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(10)

    def footer(self):
        self.set_y(-30)
        # Green line
        self.set_draw_color(16, 185, 129)
        self.set_line_width(0.8)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(5)
        self.set_text_color(107, 114, 128)
        self.set_font('Helvetica', '', 7)
        self.cell(0, 4, 'This is a computer-generated receipt from TuitionPe. Thank you for your payment!', align='C', new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 4, 'TuitionPe -- Smart Tuition Management for Modern Teachers', align='C', new_x="LMARGIN", new_y="NEXT")

    def _section_title(self, title):
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(16, 185, 129)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(229, 231, 235)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(3)

    def _label_value(self, label, value, value_bold=False):
        self.set_font('Helvetica', '', 9)
        self.set_text_color(107, 114, 128)
        x = self.get_x()
        self.cell(55, 6, label)
        if value_bold:
            self.set_font('Helvetica', 'B', 10)
        else:
            self.set_font('Helvetica', '', 10)
        self.set_text_color(17, 24, 39)
        self.cell(0, 6, str(value), new_x="LMARGIN", new_y="NEXT")

    def build(self):
        self.add_page()
        self.set_auto_page_break(auto=True, margin=35)

        # Receipt info row
        self.set_y(45)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(107, 114, 128)
        self.cell(85, 5, 'Receipt No.')
        self.cell(0, 5, 'Payment Date', align='R', new_x="LMARGIN", new_y="NEXT")
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(17, 24, 39)
        self.cell(85, 7, self._receipt_no)
        self.cell(0, 7, self._paid_date, align='R', new_x="LMARGIN", new_y="NEXT")
        self.ln(8)

        # FROM section
        self._section_title('FROM (Teacher)')
        self._label_value('Name', self.tutor.name, value_bold=True)
        self._label_value('Phone', self.tutor.phone)
        if self.tutor.subjects:
            self._label_value('Subjects', self.tutor.subjects)
        self.ln(5)

        # TO section
        self._section_title('TO (Student)')
        self._label_value('Student', self.student.student_name, value_bold=True)
        if self.student.parent_name:
            self._label_value('Parent', self.student.parent_name)
        self._label_value('Phone', self.student.parent_phone)
        if self.student.class_grade:
            self._label_value('Class', self.student.class_grade)
        if self.student.subject:
            self._label_value('Subject', self.student.subject)
        self.ln(5)

        # Payment details table
        self._section_title('PAYMENT DETAILS')
        self.ln(2)

        # Table header
        self.set_fill_color(16, 185, 129)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 10)
        self.cell(80, 9, '  Description', fill=True)
        self.cell(90, 9, 'Details', align='R', fill=True, new_x="LMARGIN", new_y="NEXT")

        # Table rows
        rows = [
            ('Tuition Fee', f'Rs. {int(self.payment.amount)}'),
            ('Month', self._month_display),
            ('Payment Cycle', (self.student.payment_cycle or 'Monthly').capitalize()),
            ('Status', 'PAID'),
            ('Paid On', self._paid_date),
        ]
        for i, (desc, val) in enumerate(rows):
            if i % 2 == 0:
                self.set_fill_color(249, 250, 251)
            else:
                self.set_fill_color(255, 255, 255)

            self.set_font('Helvetica', '', 9)
            self.set_text_color(107, 114, 128)
            self.cell(80, 8, f'  {desc}', fill=True)

            if desc == 'Status':
                self.set_text_color(16, 185, 129)
                self.set_font('Helvetica', 'B', 10)
            else:
                self.set_text_color(17, 24, 39)
                self.set_font('Helvetica', 'B', 10)
            self.cell(90, 8, val, align='R', fill=True, new_x="LMARGIN", new_y="NEXT")

        # Border around table
        table_x = 20
        table_y = self.get_y() - (len(rows) + 1) * 8 - 9
        self.set_draw_color(229, 231, 235)
        self.rect(table_x, table_y, 170, (len(rows) + 1) * 8 + 1)

        self.ln(12)

        # Total amount - big green center
        self.set_font('Helvetica', '', 10)
        self.set_text_color(107, 114, 128)
        self.cell(0, 6, 'TOTAL AMOUNT', align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_font('Helvetica', 'B', 28)
        self.set_text_color(16, 185, 129)
        self.cell(0, 14, f'Rs. {int(self.payment.amount)}', align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_font('Helvetica', 'B', 14)
        self.cell(0, 8, 'PAID', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(6)

        # UPI / Bank details
        if self.tutor.upi_id or self.tutor.bank_account:
            self._section_title('PAYMENT METHOD')
            if self.tutor.upi_id:
                self._label_value('UPI', self.tutor.upi_id, value_bold=True)
            if self.tutor.bank_account:
                bank = self.tutor.bank_account
                if self.tutor.ifsc_code:
                    bank += f' (IFSC: {self.tutor.ifsc_code})'
                self._label_value('Bank', bank, value_bold=True)


# ────────────────────────────────────────────────────────────
# Fallback: Minimal PDF without any external library
# ────────────────────────────────────────────────────────────

def _generate_minimal_pdf(tutor, student, payment):
    """
    Generate a basic but readable PDF receipt using raw PDF commands.
    No external libraries needed. Works on any Python installation.
    """
    receipt_no = f"TP-{payment.id:06d}"
    paid_date_str = payment.paid_date.strftime('%d %B %Y') if payment.paid_date else date.today().strftime('%d %B %Y')
    try:
        month_display = datetime.strptime(payment.month_year[:7], '%Y-%m').strftime('%B %Y')
    except Exception:
        month_display = payment.month_year

    # Build text content for a simple structured receipt
    lines = [
        "=" * 50,
        "                   TUITIONPE",
        "              Payment Receipt",
        "=" * 50,
        "",
        f"Receipt No:    {receipt_no}",
        f"Payment Date:  {paid_date_str}",
        "",
        "-" * 50,
        "FROM (Teacher)",
        "-" * 50,
        f"Name:     {tutor.name}",
        f"Phone:    {tutor.phone}",
    ]
    if tutor.subjects:
        lines.append(f"Subjects: {tutor.subjects}")

    lines += [
        "",
        "-" * 50,
        "TO (Student)",
        "-" * 50,
        f"Student:  {student.student_name}",
    ]
    if student.parent_name:
        lines.append(f"Parent:   {student.parent_name}")
    lines.append(f"Phone:    {student.parent_phone}")
    if student.class_grade:
        lines.append(f"Class:    {student.class_grade}")
    if student.subject:
        lines.append(f"Subject:  {student.subject}")

    lines += [
        "",
        "-" * 50,
        "PAYMENT DETAILS",
        "-" * 50,
        f"Amount:        Rs. {int(payment.amount)}",
        f"Month:         {month_display}",
        f"Cycle:         {(student.payment_cycle or 'Monthly').capitalize()}",
        f"Status:        PAID",
        f"Paid On:       {paid_date_str}",
        "",
        "=" * 50,
        f"     TOTAL:  Rs. {int(payment.amount)}  -  PAID",
        "=" * 50,
    ]
    if tutor.upi_id:
        lines.append(f"\nUPI: {tutor.upi_id}")
    if tutor.bank_account:
        bank = tutor.bank_account
        if tutor.ifsc_code:
            bank += f" (IFSC: {tutor.ifsc_code})"
        lines.append(f"Bank: {bank}")

    lines += [
        "",
        "This is a computer-generated receipt.",
        "Thank you for your payment!",
        "",
        "TuitionPe - Smart Tuition Management",
    ]

    text = "\n".join(lines)

    # Build raw PDF
    # Objects: catalog, pages, page, font, content stream
    objs = []

    def add_obj(content):
        objs.append(content)
        return len(objs)

    # 1: Catalog
    add_obj("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    # 2: Pages
    add_obj("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
    # 4: Font
    add_obj("4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj")

    # Build content stream
    content_lines = ["BT", "/F1 10 Tf"]
    y = 780
    for line in text.split("\n"):
        if y < 50:
            break
        # Escape special PDF chars
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"1 0 0 1 50 {y} Tm")
        content_lines.append(f"({safe}) Tj")
        y -= 14
    content_lines.append("ET")
    stream = "\n".join(content_lines)

    # 5: Content stream
    add_obj(f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj")

    # 3: Page (insert at position 2, shift others)
    page_obj = ("3 0 obj\n<< /Type /Page /Parent 2 0 R "
                "/MediaBox [0 0 595 842] "
                "/Contents 5 0 R "
                "/Resources << /Font << /F1 4 0 R >> >> >>\nendobj")
    objs.insert(2, page_obj)  # Insert page as 3rd object

    # Build PDF file
    pdf_lines = ["%PDF-1.4"]
    offsets = []
    for i, obj_str in enumerate(objs):
        offsets.append(len("\n".join(pdf_lines)) + 1)
        pdf_lines.append(obj_str)

    xref_offset = len("\n".join(pdf_lines)) + 1
    pdf_lines.append("xref")
    pdf_lines.append(f"0 {len(objs) + 1}")
    pdf_lines.append("0000000000 65535 f ")
    for off in offsets:
        pdf_lines.append(f"{off:010d} 00000 n ")
    pdf_lines.append("trailer")
    pdf_lines.append(f"<< /Size {len(objs) + 1} /Root 1 0 R >>")
    pdf_lines.append("startxref")
    pdf_lines.append(str(xref_offset))
    pdf_lines.append("%%EOF")

    return "\n".join(pdf_lines).encode('latin-1')


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────

def generate_receipt_pdf(tutor, student, payment):
    """
    Generate a payment receipt PDF. Uses fpdf2 if available, else minimal fallback.
    Returns bytes of the PDF file.
    """
    if HAS_FPDF:
        pdf = ReceiptPDF(tutor, student, payment)
        pdf.build()
        return bytes(pdf.output())  # fpdf2 returns bytearray; gunicorn needs bytes
    else:
        return _generate_minimal_pdf(tutor, student, payment)


def save_receipt_pdf(tutor, student, payment, upload_folder):
    """Generate and save receipt PDF to disk. Returns the relative path."""
    pdf_bytes = generate_receipt_pdf(tutor, student, payment)

    receipts_dir = os.path.join(upload_folder, 'receipts')
    os.makedirs(receipts_dir, exist_ok=True)

    safe_name = student.student_name.replace(' ', '_')
    month_str = payment.month_year.replace('-', '_')
    filename = f"Receipt_{safe_name}_{month_str}_{payment.id}.pdf"
    filepath = os.path.join(receipts_dir, filename)

    with open(filepath, 'wb') as f:
        f.write(pdf_bytes)

    return f"uploads/receipts/{filename}"


def send_receipt_email(app, tutor, student, payment):
    """
    Send a beautiful HTML email with the PDF receipt attached.
    Sent FROM TuitionPe email TO the tutor's email.
    Returns (success: bool, message: str).
    """
    cfg = app.config
    if not cfg.get('MAIL_USERNAME') or not cfg.get('MAIL_PASSWORD'):
        return False, 'Email not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env'

    if not tutor.email:
        return False, 'Your email address is not set. Please update it in Profile.'

    pdf_bytes = generate_receipt_pdf(tutor, student, payment)

    try:
        month_display = datetime.strptime(payment.month_year[:7], '%Y-%m').strftime('%B %Y')
    except Exception:
        month_display = payment.month_year

    paid_date_str = payment.paid_date.strftime('%d %B %Y') if payment.paid_date else date.today().strftime('%d %B %Y')
    receipt_no = f"TP-{payment.id:06d}"

    html_body = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:'Segoe UI',Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;padding:24px 12px;">
    <div style="background:linear-gradient(135deg,#10b981,#059669);border-radius:16px 16px 0 0;padding:28px 24px;text-align:center;">
      <h1 style="margin:0;font-size:22px;font-weight:800;color:#fff;letter-spacing:3px;">TUITIONPE</h1>
      <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:13px;">Payment Receipt</p>
    </div>
    <div style="background:#ffffff;padding:28px 24px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
      <p style="color:#374151;font-size:15px;margin:0 0 20px;">
        Hello <strong>{tutor.name.split()[0]}</strong>,
      </p>
      <p style="color:#6b7280;font-size:14px;margin:0 0 24px;line-height:1.6;">
        Payment has been recorded for <strong style="color:#111;">{student.student_name}</strong>.
        The receipt is attached as a PDF. Here is a quick summary:
      </p>
      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:24px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Receipt No.</td>
              <td style="padding:6px 0;text-align:right;font-weight:600;color:#111;font-size:13px;">{receipt_no}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Student</td>
              <td style="padding:6px 0;text-align:right;font-weight:600;color:#111;font-size:13px;">{student.student_name}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Month</td>
              <td style="padding:6px 0;text-align:right;font-weight:600;color:#111;font-size:13px;">{month_display}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Amount</td>
              <td style="padding:6px 0;text-align:right;font-weight:700;color:#10b981;font-size:16px;">Rs. {int(payment.amount)}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Status</td>
              <td style="padding:6px 0;text-align:right;">
                <span style="background:#d1fae5;color:#065f46;padding:3px 12px;border-radius:20px;font-size:12px;font-weight:600;">PAID</span>
              </td></tr>
          <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Paid Date</td>
              <td style="padding:6px 0;text-align:right;font-weight:600;color:#111;font-size:13px;">{paid_date_str}</td></tr>
        </table>
      </div>
      <p style="color:#6b7280;font-size:13px;margin:0;line-height:1.5;">
        The PDF receipt is attached to this email. You can share it with the parent if needed.
      </p>
    </div>
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 16px 16px;padding:20px 24px;text-align:center;">
      <p style="color:#10b981;font-size:11px;font-weight:800;letter-spacing:3px;margin:0 0 4px;">TUITIONPE</p>
      <p style="color:#9ca3af;font-size:10px;margin:0;">Smart Tuition Management for Modern Teachers</p>
    </div>
  </div>
</body>
</html>'''

    msg = MIMEMultipart('mixed')
    msg['Subject'] = f'Payment Receipt - {student.student_name} ({month_display})'
    msg['From'] = cfg['MAIL_DEFAULT_SENDER']
    msg['To'] = tutor.email

    html_part = MIMEMultipart('alternative')
    html_part.attach(MIMEText(html_body, 'html'))
    msg.attach(html_part)

    safe_name = student.student_name.replace(' ', '_')
    pdf_filename = f"Receipt_{safe_name}_{payment.month_year}.pdf"
    attachment = MIMEBase('application', 'pdf')
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', f'attachment; filename="{pdf_filename}"')
    msg.attach(attachment)

    try:
        server = smtplib.SMTP(cfg['MAIL_SERVER'], cfg['MAIL_PORT'], timeout=20)
        server.ehlo()
        server.starttls()
        server.login(cfg['MAIL_USERNAME'], cfg['MAIL_PASSWORD'])
        server.sendmail(cfg['MAIL_USERNAME'], tutor.email, msg.as_string())
        server.quit()
        return True, f'Receipt sent to {tutor.email}'
    except Exception as e:
        return False, f'Failed to send email: {str(e)}'
