import hashlib,hmac,secrets
from passlib.hash import pbkdf2_sha256
from .config import SECRET_KEY

def hash_password(p): return pbkdf2_sha256.hash(p)
def verify_password(p,h):
    try:return pbkdf2_sha256.verify(p,h)
    except:return False
def normalize_phone(v):return ''.join(c for c in v if c.isdigit())
def blind_hash(v):return hmac.new(SECRET_KEY.encode(),v.strip().upper().encode(),hashlib.sha256).hexdigest()
def delivery_hash(v):return blind_hash('DELIVERY:'+v)
def delivery_code():return f'{secrets.randbelow(1000000):06d}'
