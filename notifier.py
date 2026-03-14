"""
notifier.py  –  Email / SMS helpers
All third-party imports are optional so the server starts even without them.
"""
from datetime import date

# =========================================================
# Optional imports
# =========================================================
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

# =========================================================
# ⚙️ CONFIGURATION  (override via environment variables)
# =========================================================
import os

SENDER_EMAIL    = os.environ.get("SENDER_EMAIL",    "niteshnemalpuri17@gmail.com")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")   # set via env, never hardcode

TWILIO_SID   = os.environ.get("TWILIO_SID",   "")
TWILIO_AUTH  = os.environ.get("TWILIO_AUTH",  "")
TWILIO_PHONE = os.environ.get("TWILIO_PHONE", "+15550000000")

# =========================================================
# Initialise clients lazily
# =========================================================
yag = None
sms_client = None

def _get_yag():
    global yag
    if yag is None and _YAGMAIL_OK and SENDER_EMAIL and SENDER_PASSWORD:
        try:
            yag = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)
        except Exception as e:
            print(f"⚠️  Email init failed: {e}")
    return yag

def _get_sms():
    global sms_client
    if sms_client is None and _TWILIO_OK and TWILIO_SID and TWILIO_AUTH:
        try:
            sms_client = TwilioClient(TWILIO_SID, TWILIO_AUTH)
        except Exception as e:
            print(f"⚠️  SMS init failed: {e}")
    return sms_client

# =========================================================
# 📧 Public functions
# =========================================================

def send_absent_email(student_name, parent_email, date_absent):
    mailer = _get_yag()
    if not mailer:
        print("⚠️  Email skipped – yagmail not configured.")
        return
    try:
        subject = f"Alert: {student_name} Absent Today"
        body = (
            f"Dear Parent,\n\n"
            f"{student_name} was marked ABSENT on {date_absent}.\n"
            f"Contact the HOD if this is a mistake.\n\n"
            f"Regards,\nGIET University"
        )
        mailer.send(to=parent_email, subject=subject, contents=body)
        print(f"📧 Absent email sent → {parent_email}")
    except Exception as e:
        print(f"❌ Email failed: {e}")


def send_absent_sms(student_name, parent_phone):
    client = _get_sms()
    if not client:
        print("⚠️  SMS skipped – Twilio not configured.")
        return
    try:
        msg = f"GIETU ALERT: {student_name} is ABSENT today ({date.today()})."
        client.messages.create(body=msg, from_=TWILIO_PHONE, to=parent_phone)
        print(f"📱 SMS sent → {parent_phone}")
    except Exception as e:
        print(f"❌ SMS failed: {e}")


def send_payment_receipt(student_name, parent_email, filename, pdf_buffer):
    mailer = _get_yag()
    if not mailer:
        print("⚠️  Receipt email skipped – yagmail not configured.")
        return False
    try:
        subject = f"✅ Fee Receipt: {student_name}"
        body = (
            f"Dear Parent,\n\n"
            f"Payment for {student_name} has been received.\n"
            f"Please find the official receipt attached.\n\n"
            f"Transaction Status: VERIFIED\n\n"
            f"Regards,\nGIET University Accounts Dept."
        )
        pdf_buffer.seek(0)
        mailer.send(to=parent_email, subject=subject,
                    contents=body, attachments=pdf_buffer)
        print(f"📧 Receipt sent → {parent_email}")
        return True
    except Exception as e:
        print(f"❌ Receipt email failed: {e}")
        return False