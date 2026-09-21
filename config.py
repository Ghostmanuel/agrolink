import os
import base64
import hashlib
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "EPYALINK")
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
SECRET_KEY = os.getenv("SECRET_KEY", "agrolink-development-only-secret-change-before-production-2026").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrolink_v11.db")
SELLER_COMMISSION_RATE = float(os.getenv("SELLER_COMMISSION_RATE", "0.04"))
TRANSPORTER_COMMISSION_RATE = float(os.getenv("TRANSPORTER_COMMISSION_RATE", "0.01"))
BASE_DELIVERY_FEE = float(os.getenv("BASE_DELIVERY_FEE", "0"))
DELIVERY_RATE_PER_KM = float(os.getenv("DELIVERY_RATE_PER_KM", "150"))
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrador EPYALINK")
ADMIN_PROVINCE = os.getenv("ADMIN_PROVINCE", "Luanda")
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS", "Luanda, Angola")
# BI_ENCRYPTION_KEY: em produção, se não for fornecida (ou estiver com o placeholder
# antigo do .env), derivamos uma chave estável de 32 bytes a partir da SECRET_KEY.
# Isto evita que um deploy legítimo caia apenas porque o operador não definiu
# a variável secundária. Se a SECRET_KEY de produção continuar no valor de
# desenvolvimento, o arranque é bloqueado para não criar uma chave previsível.
if APP_ENV == "production" and SECRET_KEY == "agrolink-development-only-secret-change-before-production-2026":
    raise RuntimeError("SECRET_KEY de produção não configurada")
_raw_bi_key = os.getenv("BI_ENCRYPTION_KEY", "").strip()
if not _raw_bi_key or _raw_bi_key in {"CHANGE_ME_BASE64URL_32_BYTES", "CHANGE_ME"}:
    BI_ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode().rstrip("=")
else:
    BI_ENCRYPTION_KEY = _raw_bi_key
try:
    padded = BI_ENCRYPTION_KEY + "=" * (-len(BI_ENCRYPTION_KEY) % 4)
    if len(base64.urlsafe_b64decode(padded.encode())) != 32:
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
PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "5"))
# SMS OTP provider (KambaSMS). Keep credentials only in Render/environment variables.
PASSWORD_RESET_SMS_PROVIDER = os.getenv("PASSWORD_RESET_SMS_PROVIDER", "kambasms").strip().lower()
KAMBASMS_API_KEY = os.getenv("KAMBASMS_API_KEY", "").strip()
KAMBASMS_BASE_URL = os.getenv("KAMBASMS_BASE_URL", "https://api.kambasms.ao").strip().rstrip("/")
PASSWORD_RESET_RATE_LIMIT_PER_HOUR = int(os.getenv("PASSWORD_RESET_RATE_LIMIT_PER_HOUR", "3"))

# v15 services
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
ROUTING_BASE_URL = os.getenv("ROUTING_BASE_URL", "https://router.project-osrm.org")
GEOCODING_BASE_URL = os.getenv("GEOCODING_BASE_URL", "https://nominatim.openstreetmap.org")
FILE_STORAGE_DIR = os.getenv("FILE_STORAGE_DIR", "private_uploads")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5*1024*1024)))
