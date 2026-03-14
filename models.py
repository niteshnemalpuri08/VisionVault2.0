from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(80), unique=True, nullable=False)
    password     = db.Column(db.String(120), nullable=False)
    role         = db.Column(db.String(20),  nullable=False)  # student | teacher | parent
    name         = db.Column(db.String(100), nullable=False)

    # Teacher
    section      = db.Column(db.String(10),  nullable=True)

    # Parent
    child_roll   = db.Column(db.String(80),  nullable=True)

    # Student
    class_name   = db.Column(db.String(50),  nullable=True)
    parent_email = db.Column(db.String(120), nullable=True)
    parent_phone = db.Column(db.String(20),  nullable=True)

    performance  = db.relationship('StudentPerformance', backref='student', uselist=False)


class StudentPerformance(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    math_marks       = db.Column(db.Float, default=0)
    physics_marks    = db.Column(db.Float, default=0)
    chemistry_marks  = db.Column(db.Float, default=0)
    cs_marks         = db.Column(db.Float, default=0)
    english_marks    = db.Column(db.Float, default=0)
    pe_marks         = db.Column(db.Float, default=0)

    total_classes    = db.Column(db.Integer, default=60)
    present_classes  = db.Column(db.Integer, default=0)
    attendance       = db.Column(db.Float,   default=0)
    avg_marks        = db.Column(db.Float,   default=0)


class Attendance(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date       = db.Column(db.Date,    nullable=False)
    status     = db.Column(db.String(10), nullable=False)  # present | absent


class Message(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    sender    = db.Column(db.String(80), nullable=False)
    receiver  = db.Column(db.String(80), nullable=False)
    content   = db.Column(db.Text,       nullable=False)
    timestamp = db.Column(db.DateTime,   default=datetime.utcnow)


class Notification(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_type    = db.Column(db.String(20),  nullable=False)   # student | teacher | parent
    student_roll = db.Column(db.String(80),  nullable=True)    # for student-specific notifications
    title        = db.Column(db.String(200), nullable=False)
    content      = db.Column(db.Text,        nullable=False)
    type         = db.Column(db.String(50),  default='general')
    priority     = db.Column(db.String(20),  default='medium')
    icon         = db.Column(db.String(10),  default='🔔')
    read         = db.Column(db.Boolean,     default=False)
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)

    @property
    def time_ago(self):
        diff = datetime.utcnow() - self.created_at
        if diff.days >= 1:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        hours = diff.seconds // 3600
        if hours >= 1:
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"