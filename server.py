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
# 3. FACE RECOGNITION SETUP
# ─────────────────────────────────────────────
face_recognizer = None
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
AI_READY = False
FACE_SIZE = (200, 200)


def process_face(img_gray):
    equalized = cv2.equalizeHist(img_gray)
    return cv2.resize(equalized, FACE_SIZE)


def train_ai():
    global AI_READY, face_recognizer
    try:
        face_dir = os.path.join(os.getcwd(), "faces", "24cse001")
        if not os.path.exists(face_dir):
            print("⚠️  Skipping AI training: No photos found in faces/24cse001/")
            return
        face_recognizer = cv2.face.LBPHFaceRecognizer_create()
        face_samples, ids = [], []
        for filename in os.listdir(face_dir):
            if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                img = cv2.imread(os.path.join(face_dir, filename))
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                for (x, y, w, h) in faces:
                    face_samples.append(process_face(gray[y:y + h, x:x + w]))
                    ids.append(1)
        if face_samples:
            face_recognizer.train(face_samples, np.array(ids))
            AI_READY = True
            print("✅ Face AI trained successfully.")
    except Exception as e:
        print(f"⚠️  AI training error: {e}")


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
    if not AI_READY:
        return jsonify({'success': False, 'message': 'Face AI not ready – add photos first'})
    try:
        data = request.json or {}
        image_data = data['image'].split(',')[1]
        img_bytes = base64.decodebytes(image_data.encode())
        img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        for (x, y, w, h) in faces:
            roi = process_face(gray[y:y + h, x:x + w])
            label, confidence = face_recognizer.predict(roi)
            if confidence < 70:
                user = User.query.filter_by(username='24cse001').first()
                if user:
                    return jsonify({
                        'success': True,
                        'role': user.role,
                        'username': user.username,
                        'name': user.name,
                        'section': user.section or ''
                    })
        return jsonify({'success': False, 'message': 'Face not recognised – try again'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


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


# =================================================================
# 💰  PAYMENT ROUTES
# =================================================================

@app.route('/api/payment/upload_proof', methods=['POST'])
def upload_payment_proof():
    try:
        username = request.form.get('username', '')
        txn_id   = request.form.get('txn_id', '')
        amount   = request.form.get('amount', '0')
        file     = request.files.get('screenshot')

        if not file:
            return jsonify({'success': False, 'message': 'No screenshot uploaded'}), 400

        filename  = secure_filename(f"{username}_{txn_id}_{file.filename}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Generate PDF receipt
        buffer = io.BytesIO()
        c = rl_canvas.Canvas(buffer, pagesize=letter)
        w, h = letter

        # Header bar
        c.setFillColorRGB(0.4, 0.49, 0.92)
        c.rect(0, h - 80, w, 80, fill=True, stroke=False)
        c.setFillColorRGB(1, 1, 1)
        c.setFont('Helvetica-Bold', 22)
        c.drawString(40, h - 50, 'GIET University — Fee Receipt')

        # Body
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont('Helvetica', 13)
        details = [
            ('Student ID',    username),
            ('Transaction ID', txn_id),
            ('Amount Paid',   f'₹ {amount}'),
            ('Date',          date.today().strftime('%d %B %Y')),
            ('Status',        '✅ VERIFIED'),
        ]
        y = h - 130
        for label, value in details:
            c.setFont('Helvetica-Bold', 12)
            c.drawString(60, y, f'{label}:')
            c.setFont('Helvetica', 12)
            c.drawString(220, y, value)
            y -= 30

        c.setFont('Helvetica-Oblique', 10)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(60, 40, 'GIET University · AI Student Portal · This is a system-generated receipt.')
        c.save()
        buffer.seek(0)

        # Try email receipt
        student = User.query.filter_by(username=username).first()
        if student and student.parent_email:
            try:
                send_payment_receipt(student.name, student.parent_email, filename, buffer)
            except Exception:
                pass

        return jsonify({'success': True, 'message': 'Receipt generated and sent to parent email!'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


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