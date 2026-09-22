import hashlib
import hmac
import secrets
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from passlib.hash import pbkdf2_sha256
from config import SECRET_KEY, BI_ENCRYPTION_KEY


def hash_password(password):
    return pbkdf2_sha256.hash(password)


def verify_password(password, password_hash):
    try:
        return pbkdf2_sha256.verify(password, password_hash)
    except Exception:
        return False


def normalize_phone(value):
    digits = "".join(c for c in str(value) if c.isdigit())
    if digits.startswith("244"):
        digits = digits[3:]
    return digits


def blind_hash(value):
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY não configurada")
    return hmac.new(SECRET_KEY.encode(), value.strip().upper().encode(), hashlib.sha256).hexdigest()


def delivery_hash(value):
    return blind_hash("DELIVERY:" + value)


def reset_token_hash(value):
    return blind_hash("RESET:" + value)


def delivery_code():
    return f"{secrets.randbelow(1000000):06d}"


def reset_code():
    return f"{secrets.randbelow(1000000):06d}"


def encrypt_sensitive(value):
    if value is None or value == "":
        return None
    key = base64.urlsafe_b64decode(BI_ENCRYPTION_KEY + "=" * (-len(BI_ENCRYPTION_KEY) % 4))
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode(), None)
    return "AESGCM1:" + base64.urlsafe_b64encode(nonce + ciphertext).decode()

def decrypt_sensitive(value):
    if not value or not value.startswith("AESGCM1:"):
        return None
    try:
        raw = base64.urlsafe_b64decode(value.split(":",1)[1].encode())
        return AESGCM(base64.urlsafe_b64decode(BI_ENCRYPTION_KEY + "=" * (-len(BI_ENCRYPTION_KEY) % 4))).decrypt(raw[:12], raw[12:], None).decode()
    except Exception:
        return None
