from flask import Flask, request, jsonify, send_from_directory, send_file, make_response
from flask_cors import CORS
from models import db, User, Attendance, StudentPerformance, Message
from notifier import send_absent_email, send_absent_sms, send_payment_receipt
from datetime import date, datetime
import io
import base64
import numpy as np
import cv2
import os
import sys
import pytesseract
from PIL import Image
import re
from werkzeug.utils import secure_filename
from predictor import predict_score
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import yagmail


# ─────────────────────────────────────────────
# 1. APP CONFIGURATION
# ─────────────────────────────────────────────
app = Flask(__name__, static_folder='frontend', static_url_path='')

CORS(app, resources={r"/*": {"origins": "*"}})

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'super_secret_giet_2026'

UPLOAD_FOLDER = 'uploads/payments'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db.init_app(app)


# ─────────────────────────────────────────────
# 2. OCR SETUP
# ─────────────────────────────────────────────
try:
    if sys.platform == 'win32':
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    else:
        pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False
# ─────────────────────────────────────────────
# 3. OPENCV FACE RECOGNITION SETUP (No dlib required)
# ─────────────────────────────────────────────
# This uses LBPH which is compatible with Python 3.14
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
recognizer = cv2.face.LBPHFaceRecognizer_create()
USER_MAP = {} # Maps numeric IDs to Usernames (e.g., {0: "24cse001"})

def train_ai():
    global USER_MAP
    print("🧠 AI Training (OpenCV LBPH Mode)...")
    
    # Matches your folder structure: backend/faces/
    base_face_dir = os.path.join(os.getcwd(), "backend", "faces")
    if not os.path.exists(base_face_dir):
        print(f"⚠️ Directory NOT found: {base_face_dir}")
        return

    face_samples = []
    ids = []

    for idx, user_folder in enumerate(os.listdir(base_face_dir)):
        user_path = os.path.join(base_face_dir, user_folder)
        if os.path.isdir(user_path):
            USER_MAP[idx] = user_folder
            for filename in os.listdir(user_path):
                if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                    img_path = os.path.join(user_path, filename)
                    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                    if img is None: continue
                    
                    faces = face_cascade.detectMultiScale(img, 1.3, 5)
                    for (x, y, w, h) in faces:
                        # Crop and resize face to standard size
                        face_roi = cv2.resize(img[y:y+h, x:x+w], (200, 200))
                        face_samples.append(face_roi)
                        ids.append(idx)
                        print(f"✅ Training image: {user_folder}/{filename}")

    if face_samples:
        recognizer.train(face_samples, np.array(ids))
        print(f"🚀 AI Ready. Registered users: {list(USER_MAP.values())}")
    else:
        print("❌ No face images found to train.")
# ─────────────────────────────────────────────
# 4. HELPER: compute rank for a student
# ─────────────────────────────────────────────
def compute_rank(student_username, section):
    """Returns the rank (1-based) of the student within their section."""
    peers = (
        User.query
        .join(StudentPerformance, User.id == StudentPerformance.user_id)
        .filter(User.role == 'student', User.section == section)
        .order_by(StudentPerformance.avg_marks.desc())
        .all()
    )
    for idx, peer in enumerate(peers, start=1):
        if peer.username == student_username:
            return idx, len(peers)
    return None, len(peers)


def compute_class_averages(section):
    """Returns average marks per subject for all students in a section."""
    students = (
        User.query
        .join(StudentPerformance, User.id == StudentPerformance.user_id)
        .filter(User.role == 'student', User.section == section)
        .all()
    )
    if not students:
        return {}
    perfs = [s.performance for s in students if s.performance]
    n = len(perfs)
    if n == 0:
        return {}
    return {
        'math':  round(sum(p.math_marks     for p in perfs) / n, 1),
        'phy':   round(sum(p.physics_marks  for p in perfs) / n, 1),
        'chem':  round(sum(p.chemistry_marks for p in perfs) / n, 1),
        'cs':    round(sum(p.cs_marks        for p in perfs) / n, 1),
        'eng':   round(sum(p.english_marks   for p in perfs) / n, 1),
        'pe':    round(sum(p.pe_marks        for p in perfs) / n, 1),
    }


# =================================================================
# 🛡️  AUTH ROUTES
# =================================================================

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'login.html')


@app.route('/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    data = request.json or {}
    user = User.query.filter_by(username=data.get('username', '')).first()
    if user and user.password == data.get('password', ''):
        return jsonify({
            'success': True,
            'role': user.role,
            'username': user.username,
            'name': user.name,
            'section': user.section or ''
        })
    return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
@app.route('/auth/face_login', methods=['POST'])
def face_login():
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({'success': False, 'message': 'No image data'}), 400

        # 1. Decode base64 to image
        img_str = data['image'].split(",")[1]
        image_bytes = base64.b64decode(img_str)
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE) # Gray is needed for LBPH

        # 2. Detect face in the live frame
        faces = face_cascade.detectMultiScale(frame, 1.3, 5)
        
        if len(faces) == 0:
            return jsonify({'success': False, 'message': 'No face detected in camera'})

        for (x, y, w, h) in faces:
            # 3. Prepare the face for prediction
            face_roi = cv2.resize(frame[y:y+h, x:x+w], (200, 200))
            
            # 4. Use the recognizer we trained at startup
            label_id, confidence = recognizer.predict(face_roi)
            
            print(f"🔍 Scan Match: ID {label_id} with Confidence {confidence}")

            # Confidence < 80 is usually a solid match for LBPH
            if confidence < 80:
                username = USER_MAP.get(label_id)
                user = User.query.filter_by(username=username).first()
                if user:
                    return jsonify({
                        'success': True,
                        'name': user.name,
                        'role': user.role,
                        'username': user.username
                    })

        return jsonify({'success': False, 'message': 'Identity not recognized.'})

    except Exception as e:
        print(f"🔥 FACE LOGIN ERROR: {e}")
        return jsonify({'success': False, 'message': f'Server Error: {str(e)}'}), 500
# =================================================================
# 🏫  STUDENT ROUTES
# =================================================================

@app.route('/api/students/<username>', methods=['GET'])
def get_student_data(username):
    user = User.query.filter_by(username=username).first()
    if not user or not user.performance:
        return jsonify({'error': 'Student not found'}), 404

    p = user.performance
    rank, total_students = compute_rank(username, user.section)
    class_avgs = compute_class_averages(user.section)

    return jsonify({
        'name':             user.name,
        'roll':             user.username,
        'section':          user.section or 'A',
        'attendance':       round(p.attendance, 1),
        'avg_marks':        round(p.avg_marks, 1),
        'rank':             rank,
        'total_students':   total_students,
        'math_marks':       p.math_marks,
        'physics_marks':    p.physics_marks,
        'chemistry_marks':  p.chemistry_marks,
        'cs_marks':         p.cs_marks,
        'english_marks':    p.english_marks,
        'pe_marks':         p.pe_marks,
        'class_averages':   class_avgs,
    })


@app.route('/api/predict/<username>', methods=['GET'])
def predict_student(username):
    """AI prediction: predicted final semester score."""
    user = User.query.filter_by(username=username).first()
    if not user or not user.performance:
        return jsonify({'error': 'Student not found'}), 404

    p = user.performance
    predicted = predict_score(
        p.math_marks, p.physics_marks, p.chemistry_marks,
        p.cs_marks, p.english_marks, p.pe_marks, p.attendance
    )
    return jsonify({
        'predicted_final_score': round(predicted, 1),
        'current_avg':           round(p.avg_marks, 1),
        'current_attendance':    round(p.attendance, 1),
    })


# =================================================================
# 👨‍👩‍👧  PARENT ROUTES
# =================================================================

@app.route('/api/parent/child', methods=['POST'])
def get_child_data():
    """Return the linked child's data for a parent account."""
    data = request.json or {}
    parent = User.query.filter_by(username=data.get('username', '')).first()

    if not parent or parent.role != 'parent':
        return jsonify({'error': 'Parent not found'}), 404

    child_roll = parent.child_roll
    if not child_roll:
        return jsonify({'error': 'No child linked to this account'}), 404

    child = User.query.filter_by(username=child_roll).first()
    if not child or not child.performance:
        return jsonify({'error': 'Child data not found'}), 404

    p = child.performance
    return jsonify({
        'child_name':  child.name,
        'roll':        child.username,
        'section':     child.section or 'A',
        'attendance':  round(p.attendance, 1),
        'avg':         round(p.avg_marks, 1),
        'math':        p.math_marks,
        'phy':         p.physics_marks,
        'chem':        p.chemistry_marks,
        'cs':          p.cs_marks,
        'eng':         p.english_marks,
        'pe':          p.pe_marks,
    })


# =================================================================
# 🧑‍🏫  TEACHER ROUTES
# =================================================================

@app.route('/api/teacher/students', methods=['POST'])
def get_teacher_students():
    data = request.json or {}
    teacher = User.query.filter_by(username=data.get('username', '')).first()
    if not teacher or teacher.role != 'teacher':
        return jsonify({'error': 'Unauthorised'}), 401

    students = User.query.filter_by(role='student', section=teacher.section).all()

    result = []
    for s in students:
        p = s.performance
        result.append({
            'roll':             s.username,
            'name':             s.name,
            'attendance':       round(p.attendance, 1) if p else 0,
            'avg_marks':        round(p.avg_marks, 1)  if p else 0,
            'math_marks':       p.math_marks            if p else 0,
            'physics_marks':    p.physics_marks         if p else 0,
            'chemistry_marks':  p.chemistry_marks       if p else 0,
            'cs_marks':         p.cs_marks              if p else 0,
            'english_marks':    p.english_marks         if p else 0,
            'pe_marks':         p.pe_marks              if p else 0,
        })

    return jsonify({'section': teacher.section, 'students': result})


@app.route('/api/attendance/bulk', methods=['POST'])
def bulk_att():
    data = request.json or {}
    notified = []
    for item in data.get('attendance', []):
        student = User.query.filter_by(username=item['roll']).first()
        if student and student.performance:
            p = student.performance
            if item['present']:
                p.attendance = min(100, p.attendance + 0.5)
            else:
                p.attendance = max(0, p.attendance - 1.5)
                # Notify parent if below 75%
                if p.attendance < 75 and student.parent_email:
                    try:
                        send_absent_email(student.name, student.parent_email, date.today())
                        notified.append(student.name)
                    except Exception:
                        pass

    db.session.commit()
    msg = f"✅ Attendance saved. Parent notifications sent for: {', '.join(notified)}" if notified else "✅ Attendance saved successfully!"
    return jsonify({'success': True, 'message': msg})


# =================================================================
# 💬  CHAT ROUTES
# =================================================================

@app.route('/api/chat/history', methods=['POST'])
def get_chat_history():
    data = request.json or {}
    u1, u2 = data.get('user1', ''), data.get('user2', '')
    msgs = (
        Message.query
        .filter(
            ((Message.sender == u1) & (Message.receiver == u2)) |
            ((Message.sender == u2) & (Message.receiver == u1))
        )
        .order_by(Message.timestamp.asc())
        .all()
    )
    return jsonify([{'sender': m.sender, 'content': m.content, 'time': m.timestamp.strftime('%H:%M')} for m in msgs])


@app.route('/api/chat/send', methods=['POST'])
def send_chat():
    data = request.json or {}
    sender   = data.get('sender', '')
    receiver = data.get('receiver', '')
    content  = data.get('content', '').strip()

    if not sender or not receiver or not content:
        return jsonify({'success': False, 'message': 'Missing fields'}), 400

    msg = Message(sender=sender, receiver=receiver, content=content)
    db.session.add(msg)
    db.session.commit()
    return jsonify({'success': True})
@app.route('/api/payment/upload_proof', methods=['POST'])
def upload_payment_proof():
    try:
        import threading
        username = request.form.get('username', '')
        txn_id   = request.form.get('txn_id', '').strip()
        amount   = request.form.get('amount', '0')
        file     = request.files.get('screenshot')

        if not file:
            return jsonify({'success': False, 'message': 'No screenshot uploaded.'}), 400
        if not txn_id:
            return jsonify({'success': False, 'message': 'Transaction ID required.'}), 400
        if not username:
            return jsonify({'success': False, 'message': 'Username missing.'}), 400

        # ── Save file ─────────────────────────────────────
        try:
            ext       = os.path.splitext(file.filename)[1] or '.png'
            filename  = secure_filename(f"{username}_{txn_id}{ext}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            print(f"File saved: {file_path}")
        except Exception as e:
            print(f"File save error: {e}")
            return jsonify({'success': False, 'message': f'File save failed: {str(e)}'}), 500

        # ── OCR verification ──────────────────────────────
        ocr_passed = True
        ocr_done   = False
        try:
            if OCR_AVAILABLE and file_path and os.path.exists(file_path):
                img = cv2.imread(file_path)
                if img is not None:
                    gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    proc   = cv2.threshold(gray, 0, 255,
                                 cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
                    text   = pytesseract.image_to_string(proc)
                    ocr_done = True
                    print(f"OCR extracted: {text[:80]}")
                    if not re.search(re.escape(txn_id), text, re.IGNORECASE):
                        ocr_passed = False
                        print(f"OCR mismatch: {txn_id} not found")
                    else:
                        print(f"OCR match confirmed: {txn_id}")
        except Exception as e:
            print(f"OCR error (skipped): {e}")
            ocr_passed = True

        if ocr_done and not ocr_passed:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            return jsonify({
                'success': False,
                'message': f'Transaction ID "{txn_id}" not found in screenshot.'
            }), 400

        # ── Generate PDF ──────────────────────────────────
        buffer = None
        try:
            buffer = io.BytesIO()
            c      = rl_canvas.Canvas(buffer, pagesize=letter)
            w, h   = letter

            c.setFillColorRGB(0.36, 0.47, 0.96)
            c.rect(0, h-80, w, 80, fill=True, stroke=False)
            c.setFillColorRGB(1, 1, 1)
            c.setFont('Helvetica-Bold', 20)
            c.drawString(40, h-52, 'GIET University - Fee Receipt')

            c.setFillColorRGB(0.1, 0.1, 0.1)
            rows = [
                ('Student ID',     str(username)),
                ('Transaction ID', str(txn_id)),
                ('Amount Paid',    'Rs. ' + str(amount)),
                ('Date',           date.today().strftime('%d %B %Y')),
                ('Status',         'PAYMENT VERIFIED'),
            ]
            y = h - 130
            for label, value in rows:
                c.setFont('Helvetica-Bold', 12)
                c.drawString(60, y, label + ':')
                c.setFont('Helvetica', 12)
                c.drawString(220, y, value)
                y -= 32

            c.setFont('Helvetica-Oblique', 9)
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.drawString(60, 36,
                'GIET University | AI Student Portal | Auto-generated Receipt')
            c.save()
            buffer.seek(0)
            print("PDF generated OK")
        except Exception as e:
            print(f"PDF error: {e}")
            buffer = None

        # ── Send email in background thread ───────────────
        # Does NOT block the response - returns immediately
        # ── Send email in background thread ───────────────
FALLBACK_EMAIL = "niteshnemalpuri17@gmail.com"

def send_email_bg(sname, pemail, fname, pdf_bytes):
    try:
        buf = io.BytesIO(pdf_bytes)
        send_payment_receipt(sname, pemail, fname, buf)
        print(f"Background email sent to {pemail}")
    except Exception as e:
        print(f"Background email error: {e}")

try:
    student    = User.query.filter_by(username=username).first()
    # Use parent email if set, otherwise fall back to default email
    to_email   = (student.parent_email
                  if student and student.parent_email
                  else FALLBACK_EMAIL)
    sname      = student.name if student else username

    if buffer:
        pdf_bytes = buffer.getvalue()
        t = threading.Thread(
            target=send_email_bg,
            args=(sname, to_email, filename, pdf_bytes),
            daemon=True
        )
        t.start()
        print(f"Email thread started → sending to {to_email}")
except Exception as e:
    print(f"Email thread setup error: {e}")

# =================================================================
# 📄  REPORT DOWNLOAD
# =================================================================

@app.route('/api/report/download', methods=['POST'])
def download_report():
    data     = request.json or {}
    username = data.get('username', '')

    user = User.query.filter_by(username=username).first()
    if not user or not user.performance:
        return jsonify({'error': 'Student not found'}), 404

    p = user.performance
    rank, total = compute_rank(username, user.section)

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=letter)
    page_w, page_h = letter

    # ── Header ──
    c.setFillColorRGB(0.4, 0.49, 0.92)
    c.rect(0, page_h - 90, page_w, 90, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.setFont('Helvetica-Bold', 20)
    c.drawString(40, page_h - 45, 'GIET University — Student Performance Report')
    c.setFont('Helvetica', 11)
    c.drawString(40, page_h - 68, f'Generated: {datetime.now().strftime("%d %B %Y, %I:%M %p")}')

    # ── Student Info ──
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(40, page_h - 120, 'Student Details')
    c.setFont('Helvetica', 12)
    info_lines = [
        f'Name:         {user.name}',
        f'Roll Number:  {user.username.upper()}',
        f'Section:      {user.section or "A"}',
        f'Class Rank:   #{rank} of {total}',
        f'Attendance:   {round(p.attendance, 1)}%',
        f'Average Marks:{round(p.avg_marks, 1)}%',
    ]
    y = page_h - 145
    for line in info_lines:
        c.drawString(60, y, line)
        y -= 22

    # ── Subject Table ──
    y -= 10
    c.setFont('Helvetica-Bold', 14)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(40, y, 'Subject-wise Marks')
    y -= 25

    subjects = [
        ('Mathematics',       p.math_marks),
        ('Physics',           p.physics_marks),
        ('Chemistry',         p.chemistry_marks),
        ('Computer Science',  p.cs_marks),
        ('English',           p.english_marks),
        ('Physical Education',p.pe_marks),
    ]

    for subj, marks in subjects:
        grade = 'A+' if marks >= 90 else 'A' if marks >= 80 else 'B' if marks >= 70 else 'C' if marks >= 60 else 'D'
        # Bar background
        c.setFillColorRGB(0.93, 0.93, 0.95)
        c.rect(60, y - 5, 350, 18, fill=True, stroke=False)
        # Bar fill
        bar_w = int(350 * marks / 100)
        r, g, b = (0.24, 0.69, 0.47) if marks >= 75 else (0.96, 0.49, 0.49)
        c.setFillColorRGB(r, g, b)
        c.rect(60, y - 5, bar_w, 18, fill=True, stroke=False)
        # Text
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont('Helvetica', 11)
        c.drawString(60, y, subj)
        c.setFont('Helvetica-Bold', 11)
        c.drawString(420, y, f'{marks}  ({grade})')
        y -= 28

    # ── Footer ──
    c.setFont('Helvetica-Oblique', 9)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(40, 30, 'GIET University AI Portal · Confidential · System Generated Report')
    c.save()

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'Report_{username}.pdf',
        mimetype='application/pdf'
    )


# =================================================================
# 🛠️  UTILITY ROUTES
# =================================================================

@app.route('/repair_data')
def repair_data():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='t01').first():
            db.session.add(User(username='t01', password='password123', role='teacher', name='Mr. Amit', section='A'))
            db.session.commit()
    return jsonify({'status': 'repaired'})


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)


# =================================================================
# 🚀  ENTRY POINT
# =================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        train_ai()
    app.run(host='0.0.0.0', port=5000, debug=False)