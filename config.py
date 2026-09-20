import os
import base64
import hashlib
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "AgroLink Angola")
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
SECRET_KEY = os.getenv("SECRET_KEY", "agrolink-development-only-secret-change-before-production-2026").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrolink_v11.db")
SELLER_COMMISSION_RATE = float(os.getenv("SELLER_COMMISSION_RATE", "0.04"))
TRANSPORTER_COMMISSION_RATE = float(os.getenv("TRANSPORTER_COMMISSION_RATE", "0.01"))
BASE_DELIVERY_FEE = float(os.getenv("BASE_DELIVERY_FEE", "0"))
DELIVERY_RATE_PER_KM = float(os.getenv("DELIVERY_RATE_PER_KM", "150"))
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrador AgroLink")
ADMIN_PROVINCE = os.getenv("ADMIN_PROVINCE", "Luanda")
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS", "Luanda, Angola")
BI_ENCRYPTION_KEY = os.getenv("BI_ENCRYPTION_KEY", base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()).strip()
try:
    if len(base64.urlsafe_b64decode(BI_ENCRYPTION_KEY.encode())) != 32:
        raise ValueError
except Exception:
    raise RuntimeError("BI_ENCRYPTION_KEY deve ser uma chave base64url de 32 bytes")

# Cloudflare Turnstile. Use the official test keys only for development/demo.
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "1x00000000000000000000AA" if APP_ENV != "production" else "").strip()
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "1x0000000000000000000000000000000AA" if APP_ENV != "production" else "").strip()
TURNSTILE_REQUIRED = os.getenv("TURNSTILE_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}

# Password recovery: demo mode returns the OTP in the API response for testing only.
# Production should use an SMS/WhatsApp provider and set this to false.
PASSWORD_RESET_DEMO = os.getenv("PASSWORD_RESET_DEMO", "true" if APP_ENV != "production" else "false").strip().lower() in {"1", "true", "yes", "on"}
PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "10"))
