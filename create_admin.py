"""Create an admin account (or promote an existing user).  Run:  python create_admin.py"""
from getpass import getpass
from sqlalchemy import select
from app.database import SessionLocal, Base, engine
from app import models
from app.models import User
from app.security import hash_password

Base.metadata.create_all(bind=engine)
email = input("Admin email: ").strip().lower()
db = SessionLocal()
user = db.scalar(select(User).where(User.email == email))
if user:
    user.role = "admin"
    print("Existing user promoted to admin.")
else:
    name = input("Full name: ").strip()
    pw = getpass("Password (min 8 characters): ")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    db.add(User(full_name=name, email=email, password_hash=hash_password(pw), role="admin"))
    print("Admin created.")
db.commit()
