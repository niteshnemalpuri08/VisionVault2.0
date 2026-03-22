import os
from datetime import date

# ── Optional imports ──────────────────────────────────────
try:
    import yagmail
    _YAGMAIL_OK = True
except ImportError:
    yagmail = None
    _YAGMAIL_OK = False

try:
    from twilio.rest import Client as TwilioClient
    _TWILIO_OK = True
except ImportError:
    TwilioClient = None
    _TWILIO_OK = False

# ── Configuration (reads from Render environment variables) ──
SENDER_EMAIL    = os.getenv("EMAIL_USER", "")
SENDER_PASSWORD = os.getenv("EMAIL_PASS", "")

TWILIO_SID   = os.getenv("TWILIO_SID",   "")
TWILIO_AUTH  = os.getenv("TWILIO_AUTH",  "")
TWILIO_PHONE = os.getenv("TWILIO_PHONE", "+15550000000")

yag        = None
sms_client = None

def _get_yag():
    global yag
    if yag is None and _YAGMAIL_OK and SENDER_EMAIL and SENDER_PASSWORD:
        try:
            yag = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)
        except Exception as e:
            print(f"Email init failed: {e}")
    return yag

def _get_sms():
    global sms_client
    if sms_client is None and _TWILIO_OK and TWILIO_SID and TWILIO_AUTH:
        try:
            sms_client = TwilioClient(TWILIO_SID, TWILIO_AUTH)
        except Exception as e:
            print(f"SMS init failed: {e}")
    return sms_client

# ── Public Functions ──────────────────────────────────────

def send_absent_email(student_name, parent_email, date_absent):
    mailer = _get_yag()
    if not mailer:
        print("Email skipped - not configured.")
        return
    try:
        subject = f"Alert: {student_name} Absent Today"
        body    = (
            f"Dear Parent,\n\n"
            f"{student_name} was marked ABSENT on {date_absent}.\n"
            f"Please contact the class teacher if this is an error.\n\n"
            f"Regards,\nGIET University"
        )
        mailer.send(to=parent_email, subject=subject, contents=body)
        print(f"Absent email sent to {parent_email}")
    except Exception as e:
        print(f"Absent email failed: {e}")


def send_absent_sms(student_name, parent_phone):
    client = _get_sms()
    if not client:
        print("SMS skipped - not configured.")
        return
    try:
        msg = f"GIETU ALERT: {student_name} is ABSENT today ({date.today()})."
        client.messages.create(body=msg, from_=TWILIO_PHONE, to=parent_phone)
        print(f"SMS sent to {parent_phone}")
    except Exception as e:
        print(f"SMS failed: {e}")


def send_payment_receipt(student_name, parent_email, filename, pdf_buffer):
    mailer = _get_yag()
    if not mailer:
        print("Receipt email skipped - not configured.")
        return False
    try:
        subject = f"Fee Receipt: {student_name}"
        body    = (
            f"Dear Parent,\n\n"
            f"Payment for {student_name} has been received and verified.\n"
            f"Please find the official receipt attached.\n\n"
            f"Regards,\nGIET University"
        )
        pdf_buffer.seek(0)
        mailer.send(
            to=parent_email,
            subject=subject,
            contents=body,
            attachments=pdf_buffer
        )
        print(f"Receipt sent to {parent_email}")
        return True
    except Exception as e:
        print(f"Receipt email failed: {e}")
        return False