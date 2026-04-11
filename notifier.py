import os
import io
import yagmail
from datetime import date
from dotenv import load_dotenv

# ── 1. LOAD ENVIRONMENT VARIABLES ──────────────────────────
load_dotenv()

try:
    from twilio.rest import Client as TwilioClient
    _TWILIO_OK = True
except ImportError:
    TwilioClient = None
    _TWILIO_OK = False

# ── 2. CONFIGURATION ──────────────────────────────────────
SENDER_EMAIL    = os.getenv("EMAIL_USER", "")
SENDER_PASSWORD = os.getenv("EMAIL_PASS", "")

TWILIO_SID   = os.getenv("TWILIO_SID",   "")
TWILIO_AUTH  = os.getenv("TWILIO_AUTH",  "")
TWILIO_PHONE = os.getenv("TWILIO_PHONE", "+15550000000")

# Global instances for reuse
yag_instance = None
sms_client   = None

def _get_yag():
    global yag_instance
    if yag_instance is None:
        if SENDER_EMAIL and SENDER_PASSWORD:
            try:
                # Use the 16-character App Password from your .env
                yag_instance = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)
                print(f"✅ Mailer initialized for: {SENDER_EMAIL}")
            except Exception as e:
                print(f"❌ Email initialization failed: {e}")
        else:
            print("⚠️ EMAIL_USER or EMAIL_PASS missing in .env")
    return yag_instance

def _get_sms():
    global sms_client
    if sms_client is None and _TWILIO_OK and TWILIO_SID and TWILIO_AUTH:
        try:
            sms_client = TwilioClient(TWILIO_SID, TWILIO_AUTH)
        except Exception as e:
            print(f"❌ SMS initialization failed: {e}")
    return sms_client

# ── 3. PUBLIC FUNCTIONS ───────────────────────────────────

def send_absent_email(student_name, parent_email, date_absent):
    mailer = _get_yag()
    if not mailer: return
    try:
        subject = f"Attendance Alert: {student_name} Absent"
        body = (
            f"Dear Parent,\n\n"
            f"{student_name} was marked ABSENT on {date_absent}.\n"
            f"Please contact the GIET University office for any queries.\n\n"
            f"Regards,\nAttendance System"
        )
        mailer.send(to=parent_email, subject=subject, contents=body)
        print(f"📧 Absent email sent to {parent_email}")
    except Exception as e:
        print(f"❌ Absent email failed: {e}")

def send_absent_sms(student_name, parent_phone):
    client = _get_sms()
    if not client: return
    try:
        msg = f"GIETU ALERT: {student_name} is ABSENT today ({date.today()})."
        client.messages.create(body=msg, from_=TWILIO_PHONE, to=parent_phone)
        print(f"📱 SMS sent to {parent_phone}")
    except Exception as e:
        print(f"❌ SMS failed: {e}")

def send_payment_receipt(student_name, parent_email, filename, pdf_buffer):
    """
    Sends the payment receipt as a properly named PDF attachment.
    Saves to a temp file briefly to ensure the filename is preserved.
    """
    mailer = _get_yag()
    if not mailer:
        print("❌ Receipt skipped: Mailer not configured.")
        return False
    
    temp_path = f"temp_{filename}"
    if not temp_path.lower().endswith(".pdf"):
        temp_path += ".pdf"

    try:
        # 1. Write the buffer to a physical temp file
        pdf_buffer.seek(0)
        with open(temp_path, "wb") as f:
            f.write(pdf_buffer.read())

        # 2. Prepare email content
        subject = f"Fee Payment Receipt - {student_name}"
        body = (
            f"Dear Parent,\n\n"
            f"The fee payment for {student_name} has been successfully verified.\n"
            f"Please find the attached official receipt for your records.\n\n"
            f"Regards,\nAccounts Department, GIET University"
        )

        # 3. Send using the file path (guarantees the PDF name and extension)
        mailer.send(
            to=parent_email,
            subject=subject,
            contents=body,
            attachments=temp_path
        )
        
        print(f"🚀 Receipt PDF successfully emailed to {parent_email}")
        
        # 4. Clean up the temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return True

    except Exception as e:
        print(f"❌ Receipt email failed: {e}")
        # Final cleanup attempt
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False