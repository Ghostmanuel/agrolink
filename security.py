import hashlib
import hmac
import secrets
from passlib.hash import pbkdf2_sha256
from config import SECRET_KEY

def hash_password(password):
    return pbkdf2_sha256.hash(password)

def verify_password(password,password_hash):
    try: return pbkdf2_sha256.verify(password,password_hash)
    except Exception: return False

def normalize_phone(value):
    d="".join(c for c in value if c.isdigit())
    if d.startswith("244") and len(d)==12: d=d[3:]
    return d

def blind_hash(value):
    if not SECRET_KEY: raise RuntimeError("SECRET_KEY não configurada")
    return hmac.new(SECRET_KEY.encode(),value.strip().upper().encode(),hashlib.sha256).hexdigest()

def delivery_hash(value): return blind_hash("DELIVERY:"+value)
def delivery_code(): return f"{secrets.randbelow(1000000):06d}"
