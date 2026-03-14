from server import app
from models import User, db

with app.app_context():
    users = User.query.all()
    print("\n--- 🔍 CURRENT USERS IN DB ---")
    if not users:
        print("❌ The Database is EMPTY. Seeding failed.")
    for u in users:
        print(f"✅ User: {u.username} | Role: {u.role} | Password: {u.password}")
    print("------------------------------\n")