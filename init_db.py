"""
init_db.py  —  Run once to create and seed the database.
Usage:  python init_db.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from server import app
from models import db, User, StudentPerformance
import random


def init_database():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("🔄  Generating users: Teachers → Students → Parents …")

        # ── Teachers ────────────────────────────────────────────
        teachers = [
            ('t01', 'A', 'Mr. Amit Kumar'),
            ('t02', 'B', 'Ms. Priya Sharma'),
            ('t03', 'C', 'Mr. John Das'),
            ('t04', 'D', 'Ms. Sara Patel'),
            ('t05', 'E', 'Mr. David Singh'),
        ]
        for uname, section, name in teachers:
            db.session.add(User(
                username=uname, password='password123',
                role='teacher', name=name, section=section
            ))

        # ── Students & Parents ───────────────────────────────────
        for i in range(1, 201):
            roll = f"24cse{str(i).zfill(3)}"

            # Assign section
            if   i <= 40:  sec = 'A'
            elif i <= 80:  sec = 'B'
            elif i <= 120: sec = 'C'
            elif i <= 160: sec = 'D'
            else:          sec = 'E'

            # Special demo student
            if i == 1:
                p_email = "niteshnemalpuri17@gmail.com"
                s_name  = "Rahul Sharma"
                m, p, c, cs, e, pe = 95, 88, 92, 98, 85, 96
                pres   = 52   # out of 60 → 86.7%
            else:
                p_email = f"parent.{roll}@giet.ac.in"
                s_name  = f"Student {i}"
                m   = random.randint(55, 98)
                p   = random.randint(55, 98)
                c   = random.randint(55, 98)
                cs  = random.randint(60, 99)
                e   = random.randint(60, 98)
                pe  = random.randint(70, 99)
                pres = random.randint(28, 58)

            # Student user
            student = User(
                username=roll, password='password123',
                role='student', name=s_name,
                class_name='B.Tech CSE', section=sec,
                parent_email=p_email, parent_phone='9876543210'
            )
            db.session.add(student)

            # Parent user (linked by child_roll)
            parent = User(
                username=f"p_{roll}",
                password='password123',
                role='parent',
                name=f"Parent of {s_name}",
                child_roll=roll
            )
            db.session.add(parent)

            # Performance record
            avg     = round((m + p + c + cs + e + pe) / 6, 2)
            att_pct = round((pres / 60) * 100, 1)

            db.session.add(StudentPerformance(
                student=student,
                math_marks=m, physics_marks=p, chemistry_marks=c,
                cs_marks=cs, english_marks=e, pe_marks=pe,
                total_classes=60, present_classes=pres,
                attendance=att_pct, avg_marks=avg
            ))

        db.session.commit()

        print("\n✅  Database ready!")
        print("─" * 45)
        print("  Demo Student  →  24cse001  / password123")
        print("  Demo Teacher  →  t01       / password123")
        print("  Demo Parent   →  p_24cse001 / password123")
        print("─" * 45)


if __name__ == '__main__':
    init_database()