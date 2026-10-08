import getpass
import secrets
import sys
from pathlib import Path

from app.security import hash_password

path = Path(".env")
if path.exists():
    sys.exit(".env already exists. Delete it first if you want to make a new one.")

username = input("Admin username [admin]: ").strip() or "admin"
password = getpass.getpass("Admin password (at least 8 characters): ")
if len(password) < 8:
    sys.exit("Password is too short.")
if password != getpass.getpass("Repeat the password: "):
    sys.exit("Passwords do not match.")

lines = [
    "DATABASE_URL=sqlite:///./booking.db",
    f"SECRET_KEY={secrets.token_hex(32)}",
    f"ADMIN_USERNAME={username}",
    f"ADMIN_PASSWORD_HASH={hash_password(password)}",
    "COOKIE_SECURE=false",
]
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Created .env")
