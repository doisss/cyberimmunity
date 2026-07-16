import os
from cryptography.fernet import Fernet
from django.conf import settings

KEY_FILE = settings.BASE_DIR / "log.key"
LOG_FILE = settings.BASE_DIR / "secure_audit.log"

def _load_key():
    if not KEY_FILE.exists():
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
    return KEY_FILE.read_bytes()

fernet = Fernet(_load_key())

def log_event(message: str):
    encrypted = fernet.encrypt(message.encode())
    with open(LOG_FILE, "ab") as f:
        f.write(encrypted + b"\n")

def read_log():
    lines = []
    with open(LOG_FILE, "rb") as f:
        for enc in f.readlines():
            lines.append(fernet.decrypt(enc).decode())
    return lines
