import os, secrets, hashlib, json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import create_engine, String, Float, Integer, Boolean, ForeignKey, DateTime, Text, select, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrolink.db")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_IN_PRODUCTION")
ALGORITHM = "HS256"
COMMISSION_RATE = float(os.getenv("COMMISSION_RATE", "0.04"))
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "sandbox")
PROXYPAY_BASE_URL = os.getenv("PROXYPAY_BASE_URL", "")
PROXYPAY_API_KEY = os.getenv("PROXYPAY_API_KEY", "")
PROXYPAY_ACCOUNT = os.getenv("PROXYPAY_ACCOUNT", "")
MULTICAIXA_ENTITY = os.getenv("MULTICAIXA_ENTITY", "")
PAYMENT_REFERENCE_DAYS = int(os.getenv("PAYMENT_REFERENCE_DAYS", "2"))
AGROLINK_BENEFICIARY_NAME = os.getenv("AGROLINK_BENEFICIARY_NAME", "Agro-Link Angola")
AGROLINK_BANK = os.getenv("AGROLINK_BANK", "")
AGROLINK_IBAN = os.getenv("AGROLINK_IBAN", "")
AGROLINK_KWIK_PHONE = os.getenv("AGROLINK_KWIK_PHONE", "")
RESET_DEV_MODE = os.getenv("RESET_DEV_MODE", "true").lower() == "true"
security = HTTPBearer(auto_error=True)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    name: Mapped[str]=mapped_column(String(120))
    phone: Mapped[str]=mapped_column(String(30), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(30), default="buyer")
    province: Mapped[Optional[str]]=mapped_column(String(80), nullable=True)
    verified: Mapped[bool]=mapped_column(Boolean, default=False)
    active: Mapped[bool]=mapped_column(Boolean, default=True, index=True)
    iban: Mapped[Optional[str]]=mapped_column(String(40), nullable=True)
    express_phone: Mapped[Optional[str]]=mapped_column(String(30), nullable=True)
    photo_data: Mapped[Optional[str]]=mapped_column(Text, nullable=True)
    company_name: Mapped[Optional[str]]=mapped_column(String(160), nullable=True)
    address: Mapped[Optional[str]]=mapped_column(String(240), nullable=True)
    latitude: Mapped[Optional[float]]=mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]]=mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Vehicle(Base):
    __tablename__="vehicles"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    plate: Mapped[str]=mapped_column(String(20))
    model: Mapped[str]=mapped_column(String(80), default="")
    vehicle_type: Mapped[str]=mapped_column(String(40), default="camião")
    capacity_kg: Mapped[float]=mapped_column(Float, default=0)
    photo_data: Mapped[Optional[str]]=mapped_column(Text, nullable=True)
    status: Mapped[str]=mapped_column(String(20), default="livre")
    latitude: Mapped[Optional[float]]=mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]]=mapped_column(Float, nullable=True)
    location_at: Mapped[Optional[datetime]]=mapped_column(DateTime, nullable=True)

class Product(Base):
    __tablename__="products"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    producer_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str]=mapped_column(String(120), index=True)
    category: Mapped[str]=mapped_column(String(60), index=True)
    price: Mapped[float]=mapped_column(Float)
    quantity: Mapped[float]=mapped_column(Float)
    unit: Mapped[str]=mapped_column(String(20))
    province: Mapped[str]=mapped_column(String(80), index=True)
    description: Mapped[str]=mapped_column(String(500), default="")
    status: Mapped[str]=mapped_column(String(30), default="active")
    photo_data: Mapped[Optional[str]]=mapped_column(Text, nullable=True)

class Order(Base):
    __tablename__="orders"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    product_id: Mapped[int]=mapped_column(ForeignKey("products.id"))
    buyer_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    seller_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    driver_id: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"), nullable=True)
    quantity: Mapped[float]=mapped_column(Float)
    total: Mapped[float]=mapped_column(Float)
    delivery_address: Mapped[Optional[str]]=mapped_column(String(240), nullable=True)
    status: Mapped[str]=mapped_column(String(40), default="pending")
    buyer_reviewed: Mapped[bool]=mapped_column(Boolean, default=False)
    seller_reviewed: Mapped[bool]=mapped_column(Boolean, default=False)
    driver_reviewed: Mapped[bool]=mapped_column(Boolean, default=False)
    review_confirmed_at: Mapped[Optional[datetime]]=mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class LocationPing(Base):
    __tablename__="location_pings"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    order_id: Mapped[int]=mapped_column(ForeignKey("orders.id"), index=True)
    driver_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    latitude: Mapped[float]=mapped_column(Float)
    longitude: Mapped[float]=mapped_column(Float)
    speed_kmh: Mapped[Optional[float]]=mapped_column(Float, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class Conversation(Base):
    __tablename__="conversations"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    buyer_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    seller_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    driver_id: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"), nullable=True)
    product_id: Mapped[Optional[int]]=mapped_column(ForeignKey("products.id"), nullable=True)
    order_id: Mapped[Optional[int]]=mapped_column(ForeignKey("orders.id"), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class ChatMessage(Base):
    __tablename__="chat_messages"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int]=mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    content: Mapped[str]=mapped_column(String(1000))
    proposed_price: Mapped[Optional[float]]=mapped_column(Float, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class Payment(Base):
    __tablename__="payments"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    order_id: Mapped[int]=mapped_column(ForeignKey("orders.id"), unique=True)
    method: Mapped[str]=mapped_column(String(40))
    provider: Mapped[str]=mapped_column(String(40), default="sandbox")
    reference: Mapped[str]=mapped_column(String(120))
    entity: Mapped[Optional[str]]=mapped_column(String(40), nullable=True)
    reference_number: Mapped[Optional[str]]=mapped_column(String(80), nullable=True)
    amount: Mapped[float]=mapped_column(Float)
    commission_amount: Mapped[float]=mapped_column(Float)
    net_to_seller: Mapped[float]=mapped_column(Float)
    status: Mapped[str]=mapped_column(String(30), default="aguardando")
    gateway_reference: Mapped[Optional[str]]=mapped_column(String(120), nullable=True)
    gateway_status: Mapped[Optional[str]]=mapped_column(String(50), nullable=True)
    beneficiary_name: Mapped[Optional[str]]=mapped_column(String(160), nullable=True)
    beneficiary_bank: Mapped[Optional[str]]=mapped_column(String(120), nullable=True)
    beneficiary_iban: Mapped[Optional[str]]=mapped_column(String(40), nullable=True)
    beneficiary_phone: Mapped[Optional[str]]=mapped_column(String(30), nullable=True)
    expires_at: Mapped[Optional[datetime]]=mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]]=mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class PaymentEvent(Base):
    __tablename__="payment_events"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int]=mapped_column(ForeignKey("payments.id"), index=True)
    event_type: Mapped[str]=mapped_column(String(60))
    gateway_event_id: Mapped[Optional[str]]=mapped_column(String(120), nullable=True)
    payload: Mapped[Optional[str]]=mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__="notifications"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str]=mapped_column(String(120))
    body: Mapped[str]=mapped_column(String(500))
    kind: Mapped[str]=mapped_column(String(40), default="info")
    read: Mapped[bool]=mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class PasswordReset(Base):
    __tablename__="password_resets"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str]=mapped_column(String(64))
    expires_at: Mapped[datetime]=mapped_column(DateTime)
    used: Mapped[bool]=mapped_column(Boolean, default=False)

Base.metadata.create_all(engine)

# Small additive migration for databases created by the previous prototype.
def ensure_columns():
    needed = {
      "users": [("active","BOOLEAN"),("photo_data","TEXT"),("company_name","VARCHAR(160)"),("address","VARCHAR(240)"),("latitude","FLOAT"),("longitude","FLOAT"),("updated_at","TIMESTAMP")],
      "vehicles": [("photo_data","TEXT"),("status","VARCHAR(20)"),("latitude","FLOAT"),("longitude","FLOAT"),("location_at","TIMESTAMP")],
      "products": [("photo_data","TEXT")],
      "orders": [("seller_id","INTEGER"),("delivery_address","VARCHAR(240)"),("buyer_reviewed","BOOLEAN"),("seller_reviewed","BOOLEAN"),("driver_reviewed","BOOLEAN"),("review_confirmed_at","TIMESTAMP")],
      "conversations": [("driver_id","INTEGER"),("order_id","INTEGER")],
      "payments": [("provider","VARCHAR(40)"),("entity","VARCHAR(40)"),("reference_number","VARCHAR(80)"),("gateway_reference","VARCHAR(120)"),("gateway_status","VARCHAR(50)"),("beneficiary_name","VARCHAR(160)"),("beneficiary_bank","VARCHAR(120)"),("beneficiary_iban","VARCHAR(40)"),("beneficiary_phone","VARCHAR(30)"),("expires_at","TIMESTAMP"),("confirmed_at","TIMESTAMP")]
    }
    insp=inspect(engine)
    for table, cols in needed.items():
        existing={c["name"] for c in insp.get_columns(table)}
        for name, typ in cols:
            if name not in existing:
                try:
                    with engine.begin() as c: c.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {typ}"))
                except Exception:
                    pass
ensure_columns()

pwd=CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    # PBKDF2 is available in the Python standard library and avoids deployment
    # failures caused by incompatible passlib/bcrypt package versions.
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
    return "pbkdf2_sha256$310000$"+salt.hex()+"$"+digest.hex()

def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        try:
            scheme,rounds,salt_hex,digest_hex=stored.split("$",3)
            if scheme!="pbkdf2_sha256": return False
            candidate=hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
            return secrets.compare_digest(candidate.hex(), digest_hex)
        except Exception:
            return False
    try:
        return pwd.verify(password, stored)
    except Exception:
        return False
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

def bootstrap_admin():
    # Optional production-safe bootstrap: only runs when both env vars are explicitly configured.
    if not ADMIN_PHONE or not ADMIN_PASSWORD or len(ADMIN_PASSWORD) < 8:
        return
    import re
    phone = re.sub(r"[\s-]", "", ADMIN_PHONE)
    if phone.startswith("+244"): phone = phone[4:]
    if not re.fullmatch(r"9\d{8}", phone):
        return
    s = SessionLocal()
    try:
        u = s.scalar(select(User).where(User.phone == phone))
        if not u:
            u = User(name=os.getenv("ADMIN_NAME", "Administrador AgroLink"), phone=phone,
                     password_hash=hash_password(ADMIN_PASSWORD), role="admin",
                     province=os.getenv("ADMIN_PROVINCE", "Luanda"),
                     company_name=os.getenv("ADMIN_COMPANY", "Agro-Link Angola"),
                     address=os.getenv("ADMIN_ADDRESS", "Luanda, Angola"), verified=True, active=True)
            s.add(u)
        else:
            u.role = "admin"; u.active = True; u.verified = True
        s.commit()
    finally:
        s.close()

app=FastAPI(title="AgroLink Angola API", version="10.0.0",
            description="Marketplace agrícola com mercado, transporte, chat, notificações e fluxo de pagamento preparado para integração EMIS/MULTICAIXA.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
bootstrap_admin()

def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()

def token_for(user):
    return jwt.encode({"sub":str(user.id),"role":user.role,"exp":datetime.utcnow()+timedelta(hours=12)}, SECRET_KEY, algorithm=ALGORITHM)

def current_user(credentials: HTTPAuthorizationCredentials=Depends(security), s:Session=Depends(db)):
    try:
        data=jwt.decode(credentials.credentials,SECRET_KEY,algorithms=[ALGORITHM])
        u=s.get(User,int(data["sub"]))
        if not u: raise HTTPException(401,"Utilizador inválido.")
        if not getattr(u,"active",True): raise HTTPException(403,"Conta desativada. Contacte o administrador.")
        return u
    except (JWTError,ValueError): raise HTTPException(401,"Token inválido.")

def user_from_token(token,s):
    try: return s.get(User,int(jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])["sub"]))
    except Exception: return None

def notify(s,user_id,title,body,kind="info"):
    if user_id: s.add(Notification(user_id=user_id,title=title,body=body,kind=kind))

def user_json(u):
    return {"id":u.id,"name":u.name,"phone":u.phone,"role":u.role,"province":u.province,"verified":u.verified,"active":getattr(u,"active",True),
            "express_phone":u.express_phone,"iban":u.iban,"photo_data":u.photo_data,"company_name":u.company_name,
            "address":u.address,"latitude":u.latitude,"longitude":u.longitude}

class Register(BaseModel):
    name:str; phone:str; password:str=Field(min_length=6); role:str="buyer"; province:Optional[str]=None
    iban:Optional[str]=None; express_phone:Optional[str]=None; company_name:Optional[str]=None; address:Optional[str]=None
    photo_data:Optional[str]=None
    model_config=ConfigDict(extra="forbid")
class Login(BaseModel):
    phone:str; password:str
    model_config=ConfigDict(extra="forbid")
class ProfileIn(BaseModel):
    name:str; phone:str; province:Optional[str]=None; iban:Optional[str]=None; express_phone:Optional[str]=None
    company_name:Optional[str]=None; address:Optional[str]=None; photo_data:Optional[str]=None
    latitude:Optional[float]=None; longitude:Optional[float]=None
    model_config=ConfigDict(extra="forbid")
class ProductIn(BaseModel):
    name:str; category:str; price:float=Field(gt=0); quantity:float=Field(gt=0); unit:str; province:str
    description:str=""; photo_data:Optional[str]=None
    model_config=ConfigDict(extra="forbid")
class OrderIn(BaseModel):
    product_id:int; quantity:float=Field(gt=0); delivery_address:Optional[str]=None
    model_config=ConfigDict(extra="forbid")
class AssignDriver(BaseModel):
    driver_id:int
    model_config=ConfigDict(extra="forbid")
class VehicleIn(BaseModel):
    plate:str; model:str=""; vehicle_type:str="camião"; capacity_kg:float=Field(gt=0); photo_data:Optional[str]=None
    model_config=ConfigDict(extra="forbid")
class ConversationIn(BaseModel):
    seller_id:int; product_id:Optional[int]=None; order_id:Optional[int]=None; driver_id:Optional[int]=None
    model_config=ConfigDict(extra="forbid")
class MessageIn(BaseModel):
    content:str; proposed_price:Optional[float]=None
    model_config=ConfigDict(extra="forbid")
class ReviewIn(BaseModel):
    delivery_address:Optional[str]=None; confirm:bool
    model_config=ConfigDict(extra="forbid")
class PaymentIn(BaseModel):
    order_id:int; method:str
    model_config=ConfigDict(extra="forbid")

class PaymentWebhook(BaseModel):
    payment_id:Optional[int]=None; reference:Optional[str]=None; gateway_reference:Optional[str]=None
    status:str; amount:Optional[float]=None; event_id:Optional[str]=None
    model_config=ConfigDict(extra="allow")

@app.get("/health")
def health(): return {"status":"ok","app":"AgroLink Angola","version":"9.0.0","commission_rate":COMMISSION_RATE,"database":DATABASE_URL.split(":",1)[0],"tables":inspect(engine).get_table_names()}

@app.get("/")
def root():
    return FileResponse("index.html") if os.path.exists("index.html") else {"status":"ok"}
@app.get("/manifest.json")
def manifest(): return FileResponse("manifest.json") if os.path.exists("manifest.json") else {}
@app.get("/LogoAgrolink.jpeg")
def logo(): return FileResponse("LogoAgrolink.jpeg") if os.path.exists("LogoAgrolink.jpeg") else {"error":"logo não encontrado"}
@app.get("/sw.js")
def sw(): return FileResponse("sw.js") if os.path.exists("sw.js") else {}

@app.post("/api/v1/auth/register")
def register(x:Register,s:Session=Depends(db)):
    # Server-side validation is authoritative; browser required fields alone are not enough.
    name=(x.name or "").strip(); phone=(x.phone or "").strip(); province=(x.province or "").strip(); address=(x.address or "").strip()
    company=(x.company_name or "").strip()
    import re
    if len(name)<3: raise HTTPException(422,"Informe o nome completo.")
    if not re.fullmatch(r"(?:\+244)?9\d{8}", re.sub(r"[\s-]", "", phone)): raise HTTPException(422,"Informe um número de telefone angolano válido (9XXXXXXXX ou +2449XXXXXXXX).")
    if len(x.password)<8: raise HTTPException(422,"A palavra-passe deve ter pelo menos 8 caracteres.")
    if not province: raise HTTPException(422,"Selecione/informe a província.")
    if not address: raise HTTPException(422,"Informe a morada.")
    if x.role not in {"buyer","farmer","driver"}: raise HTTPException(400,"Perfil inválido.")
    if x.role in {"farmer","driver"} and len(company)<2: raise HTTPException(422,"Para este perfil, informe a empresa/fazenda ou nome do proprietário.")
    phone=re.sub(r"[\s-]", "", phone)
    if phone.startswith("+244"): phone=phone[4:]
    if s.scalar(select(User).where(User.phone==phone)): raise HTTPException(409,"Telefone já registado.")
    u=User(name=name,phone=phone,password_hash=hash_password(x.password),role=x.role,province=province,
           iban=x.iban,express_phone=x.express_phone,company_name=company or None,address=address,photo_data=x.photo_data,active=True)
    s.add(u)
    try:
        s.commit(); s.refresh(u)
    except IntegrityError:
        s.rollback()
        raise HTTPException(409,"Não foi possível criar a conta. Verifique se o telefone já está registado e tente novamente.")
    except Exception as e:
        s.rollback()
        raise HTTPException(500,"Falha ao guardar o cadastro no servidor. Verifique a configuração da base de dados.")
    if x.role=="farmer": notify(s,u.id,"Conta criada","O seu perfil de produtor está pronto.","account")
    elif x.role=="driver": notify(s,u.id,"Conta criada","Registe o seu veículo para aparecer no Transportes.","account")
    else: notify(s,u.id,"Conta criada","Bem-vindo ao AgroLink Angola.","account")
    s.commit()
    return {"access_token":token_for(u),"user":user_json(u)}

@app.post("/api/v1/auth/login")
def login(x:Login,s:Session=Depends(db)):
    import re
    phone=re.sub(r"[\s-]", "", x.phone.strip())
    if phone.startswith("+244"): phone=phone[4:]
    u=s.scalar(select(User).where(User.phone==phone))
    if not u or not verify_password(x.password,u.password_hash): raise HTTPException(401,"Credenciais inválidas.")
    return {"access_token":token_for(u),"user":user_json(u)}

@app.post("/api/v1/auth/forgot-password")
def forgot_password(phone:str,s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.phone==phone))
    # Do not reveal whether a phone exists in production.
    response={"message":"Se o número estiver registado, será enviado um código de recuperação."}
    if not u: return response
    code=f"{secrets.randbelow(1000000):06d}"
    s.add(PasswordReset(user_id=u.id,code_hash=hashlib.sha256(code.encode()).hexdigest(),
                        expires_at=datetime.utcnow()+timedelta(minutes=10)))
    s.commit()
    if RESET_DEV_MODE: response["dev_code"]=code
    return response

@app.post("/api/v1/auth/reset-password")
def reset_password(phone:str,code:str,new_password:str,s:Session=Depends(db)):
    if len(new_password)<8: raise HTTPException(400,"A nova senha deve ter pelo menos 8 caracteres.")
    u=s.scalar(select(User).where(User.phone==phone))
    if not u: raise HTTPException(400,"Código inválido ou expirado.")
    h=hashlib.sha256(code.encode()).hexdigest()
    r=s.scalar(select(PasswordReset).where(PasswordReset.user_id==u.id,PasswordReset.code_hash==h,
                                         PasswordReset.used==False).order_by(PasswordReset.id.desc()))
    if not r or r.expires_at<datetime.utcnow(): raise HTTPException(400,"Código inválido ou expirado.")
    u.password_hash=hash_password(new_password); r.used=True
    for old in s.scalars(select(PasswordReset).where(PasswordReset.user_id==u.id,PasswordReset.used==False)).all():
        old.used=True
    s.commit()
    return {"message":"Senha alterada com sucesso."}

@app.get("/api/v1/me")
def me(u:User=Depends(current_user)): return user_json(u)

@app.put("/api/v1/me")
def update_me(x:ProfileIn,u:User=Depends(current_user),s:Session=Depends(db)):
    import re
    name=(x.name or "").strip(); phone=re.sub(r"[\s-]", "", (x.phone or "").strip()); province=(x.province or "").strip(); address=(x.address or "").strip(); company=(x.company_name or "").strip()
    if len(name)<3: raise HTTPException(422,"Informe o nome completo.")
    if not re.fullmatch(r"(?:\+244)?9\d{8}", phone): raise HTTPException(422,"Número de telefone angolano inválido.")
    if phone.startswith("+244"): phone=phone[4:]
    if not province or not address: raise HTTPException(422,"Província e morada são obrigatórias.")
    if u.role in {"farmer","driver"} and len(company)<2: raise HTTPException(422,"Empresa/fazenda é obrigatória para este perfil.")
    other=s.scalar(select(User).where(User.phone==phone,User.id!=u.id))
    if other: raise HTTPException(409,"Este telefone já pertence a outra conta.")
    data=x.model_dump(); data.update({"name":name,"phone":phone,"province":province,"address":address,"company_name":company or None})
    for k,v in data.items(): setattr(u,k,v)
    s.commit(); s.refresh(u); notify(s,u.id,"Perfil atualizado","Os seus dados foram atualizados.","account"); s.commit()
    return user_json(u)

@app.get("/api/v1/products")
def products(province:Optional[str]=None,category:Optional[str]=None,q:Optional[str]=None,s:Session=Depends(db)):
    stmt=select(Product).where(Product.status=="active")
    if province: stmt=stmt.where(Product.province==province)
    if category: stmt=stmt.where(Product.category==category)
    rows=s.scalars(stmt.order_by(Product.id.desc())).all()
    if q: rows=[r for r in rows if q.lower() in r.name.lower() or q.lower() in (r.description or "").lower()]
    out=[]
    for p in rows:
        farmer=s.get(User,p.producer_id)
        out.append({"id":p.id,"name":p.name,"category":p.category,"price":p.price,"quantity":p.quantity,"unit":p.unit,
                    "province":p.province,"producer_id":p.producer_id,"producer":user_json(farmer) if farmer else None,
                    "description":p.description,"photo_data":p.photo_data})
    return out

@app.post("/api/v1/products")
def create_product(x:ProductIn,u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="farmer": raise HTTPException(403,"Apenas agricultores podem publicar produtos.")
    p=Product(producer_id=u.id,**x.model_dump()); s.add(p); s.flush()
    buyers=s.scalars(select(User).where(User.role=="buyer")).all()
    for b in buyers: notify(s,b.id,"Novo produto no Mercado",f"{u.name} publicou {p.name}.","product")
    s.commit()
    return {"id":p.id,"message":"Produto publicado."}

@app.get("/api/v1/transport")
def transport(province:Optional[str]=None,s:Session=Depends(db)):
    stmt=select(Vehicle)
    rows=s.scalars(stmt.order_by(Vehicle.id.desc())).all(); out=[]
    for v in rows:
        d=s.get(User,v.driver_id)
        if not d: continue
        if province and d.province!=province: continue
        active=s.scalar(select(Order).where(Order.driver_id==d.id,Order.status.in_(["pago","a_caminho","confirmado"])))
        status="ocupado" if active else "livre"
        v.status=status
        out.append({"id":v.id,"driver_id":d.id,"driver_name":d.name,"company_name":d.company_name or d.name,
                    "province":d.province,"plate":v.plate,"model":v.model,"vehicle_type":v.vehicle_type,
                    "capacity_kg":v.capacity_kg,"photo_data":v.photo_data,"status":status,
                    "latitude":v.latitude or d.latitude,"longitude":v.longitude or d.longitude,
                    "location_at":v.location_at.isoformat() if v.location_at else None})
    s.commit(); return {"vehicle_count":len(out),"vehicles":out}

@app.post("/api/v1/vehicles")
def save_vehicle(x:VehicleIn,u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="driver": raise HTTPException(403,"Apenas transportadores podem registar veículos.")
    v=s.scalar(select(Vehicle).where(Vehicle.driver_id==u.id,Vehicle.plate==x.plate))
    if not v:
        v=Vehicle(driver_id=u.id,**x.model_dump()); s.add(v)
    else:
        for k,val in x.model_dump().items(): setattr(v,k,val)
    s.commit(); s.refresh(v)
    notify(s,u.id,"Veículo atualizado","O veículo foi guardado no seu perfil.","transport"); s.commit()
    return {"id":v.id,"message":"Veículo guardado.","vehicle":vehicle_json(v,u)}

def vehicle_json(v,d):
    return {"id":v.id,"driver_id":d.id,"driver_name":d.name,"company_name":d.company_name or d.name,"plate":v.plate,
            "model":v.model,"vehicle_type":v.vehicle_type,"capacity_kg":v.capacity_kg,"photo_data":v.photo_data,
            "status":v.status,"latitude":v.latitude or d.latitude,"longitude":v.longitude or d.longitude,
            "location_at":v.location_at.isoformat() if v.location_at else None}

@app.get("/api/v1/vehicles/mine")
def my_vehicles(u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="driver": raise HTTPException(403,"Apenas transportadores.")
    return [vehicle_json(v,u) for v in s.scalars(select(Vehicle).where(Vehicle.driver_id==u.id)).all()]

@app.post("/api/v1/orders")
def create_order(x:OrderIn,u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="buyer": raise HTTPException(403,"Apenas compradores podem criar pedidos.")
    p=s.get(Product,x.product_id)
    if not p or p.status!="active": raise HTTPException(404,"Produto não encontrado.")
    if p.quantity<x.quantity: raise HTTPException(400,"Quantidade indisponível.")
    seller=s.get(User,p.producer_id)
    p.quantity-=x.quantity
    o=Order(product_id=p.id,buyer_id=u.id,seller_id=p.producer_id,quantity=x.quantity,total=p.price*x.quantity,delivery_address=x.delivery_address)
    s.add(o); s.flush()
    notify(s,u.id,"Novo pedido",f"Pedido #{o.id} criado. Reveja os dados antes do pagamento.","order")
    notify(s,seller.id,"Novo pedido recebido",f"O comprador criou o pedido #{o.id}.","order")
    # relevant transporters
    for d in s.scalars(select(User).where(User.role=="driver")).all():
        notify(s,d.id,"Nova solicitação de transporte",f"Há um pedido #{o.id} que precisa de transporte.","transport")
    s.commit()
    return order_json(o,s)

def order_json(o,s):
    p=s.get(Product,o.product_id); buyer=s.get(User,o.buyer_id); seller=s.get(User,o.seller_id)
    driver=s.get(User,o.driver_id) if o.driver_id else None
    vehicle=s.scalar(select(Vehicle).where(Vehicle.driver_id==o.driver_id).order_by(Vehicle.id.desc())) if o.driver_id else None
    return {"id":o.id,"product_id":o.product_id,"product_name":p.name if p else None,"quantity":o.quantity,"total":o.total,
            "status":o.status,"buyer":user_json(buyer) if buyer else None,"seller":user_json(seller) if seller else None,
            "driver":user_json(driver) if driver else None,"vehicle":{"id":vehicle.id,"plate":vehicle.plate,"model":vehicle.model,"vehicle_type":vehicle.vehicle_type,"capacity_kg":vehicle.capacity_kg,"photo_data":vehicle.photo_data,"latitude":vehicle.latitude or (driver.latitude if driver else None),"longitude":vehicle.longitude or (driver.longitude if driver else None),"location_at":vehicle.location_at.isoformat() if vehicle and vehicle.location_at else None} if vehicle else None,"delivery_address":o.delivery_address,
            "reviews":{"buyer":o.buyer_reviewed,"seller":o.seller_reviewed,"driver":o.driver_reviewed,
                       "all":o.buyer_reviewed and o.seller_reviewed and o.driver_reviewed},
            "created_at":o.created_at.isoformat()}

@app.get("/api/v1/orders/{order_id}")
def get_order(order_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    o=s.get(Order,order_id)
    if not o or u.id not in {o.buyer_id,o.seller_id,o.driver_id}: raise HTTPException(404,"Pedido não encontrado.")
    return order_json(o,s)

@app.get("/api/v1/orders")
def orders(u:User=Depends(current_user),s:Session=Depends(db)):
    stmt=select(Order)
    if u.role=="buyer": stmt=stmt.where(Order.buyer_id==u.id)
    elif u.role=="farmer": stmt=stmt.where(Order.seller_id==u.id)
    elif u.role=="driver": stmt=stmt.where(Order.driver_id==u.id)
    return [order_json(o,s) for o in s.scalars(stmt.order_by(Order.id.desc())).all()]

@app.get("/api/v1/orders/{order_id}/available-drivers")
def available_drivers(order_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    o=s.get(Order,order_id)
    if not o or u.id not in {o.buyer_id,o.seller_id}: raise HTTPException(404,"Pedido não encontrado.")
    out=[]
    for d in s.scalars(select(User).where(User.role=="driver")).all():
        vehicle=s.scalar(select(Vehicle).where(Vehicle.driver_id==d.id).order_by(Vehicle.id.desc()))
        if not vehicle: continue
        active=s.scalar(select(Order).where(Order.driver_id==d.id,Order.status.in_(["confirmado","pagamento_pendente","pago","a_caminho"])))
        if active: continue
        out.append({"driver_id":d.id,"driver_name":d.name,"company_name":d.company_name or d.name,
                    "phone":d.phone,"province":d.province,"photo_data":d.photo_data,
                    "vehicle_id":vehicle.id,"plate":vehicle.plate,"model":vehicle.model,
                    "vehicle_type":vehicle.vehicle_type,"capacity_kg":vehicle.capacity_kg,
                    "vehicle_photo_data":vehicle.photo_data,"latitude":vehicle.latitude or d.latitude,
                    "longitude":vehicle.longitude or d.longitude,"location_at":vehicle.location_at.isoformat() if vehicle.location_at else None})
    return out

@app.post("/api/v1/orders/{order_id}/assign-driver")
def assign_driver(order_id:int,x:AssignDriver,u:User=Depends(current_user),s:Session=Depends(db)):
    o=s.get(Order,order_id); d=s.get(User,x.driver_id)
    if not o or not d or d.role!="driver": raise HTTPException(400,"Pedido ou transportador inválido.")
    if u.id not in {o.buyer_id,o.seller_id} and u.role!="admin": raise HTTPException(403,"Sem permissão.")
    o.driver_id=d.id; o.driver_reviewed=False; o.status="confirmado"
    notify(s,d.id,"Transporte atribuído",f"Você foi associado ao pedido #{o.id}. Reveja e confirme os dados.","order")
    notify(s,o.buyer_id,"Transportador associado",f"{d.name} foi associado ao pedido #{o.id}.","transport")
    notify(s,o.seller_id,"Transportador associado",f"{d.name} foi associado ao pedido #{o.id}.","transport")
    s.commit(); return order_json(o,s)

@app.post("/api/v1/orders/{order_id}/review")
def review_order(order_id:int,x:ReviewIn,u:User=Depends(current_user),s:Session=Depends(db)):
    o=s.get(Order,order_id)
    if not o: raise HTTPException(404,"Pedido não encontrado.")
    if u.id==o.buyer_id: o.buyer_reviewed=x.confirm
    elif u.id==o.seller_id: o.seller_reviewed=x.confirm
    elif o.driver_id==u.id: o.driver_reviewed=x.confirm
    else: raise HTTPException(403,"Você não participa deste pedido.")
    if x.delivery_address is not None and u.id==o.buyer_id: o.delivery_address=x.delivery_address
    if not x.confirm: raise HTTPException(400,"É necessário confirmar os dados para continuar.")
    if o.buyer_reviewed and o.seller_reviewed and o.driver_reviewed:
        o.review_confirmed_at=datetime.utcnow()
        notify(s,o.buyer_id,"Pedido validado","As três partes confirmaram os dados. O pagamento está disponível.","payment")
        notify(s,o.seller_id,"Pedido validado","As três partes confirmaram os dados. O pagamento está disponível.","payment")
        if o.driver_id: notify(s,o.driver_id,"Pedido validado","As três partes confirmaram os dados. O pagamento está disponível.","payment")
    s.commit(); return order_json(o,s)

@app.get("/api/v1/orders/{order_id}/location")
def last_location(order_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    o=s.get(Order,order_id)
    if not o or u.id not in {o.buyer_id,o.seller_id,o.driver_id}: raise HTTPException(404,"Pedido não encontrado.")
    p=s.scalar(select(LocationPing).where(LocationPing.order_id==order_id).order_by(LocationPing.id.desc()))
    if not p: raise HTTPException(404,"Ainda sem localização.")
    return {"latitude":p.latitude,"longitude":p.longitude,"speed_kmh":p.speed_kmh,"timestamp":p.created_at.isoformat()}

class LocationHub:
    def __init__(self): self.rooms={}
    async def connect(self,oid,ws): await ws.accept(); self.rooms.setdefault(oid,[]).append(ws)
    def disconnect(self,oid,ws):
        if oid in self.rooms and ws in self.rooms[oid]: self.rooms[oid].remove(ws)
    async def broadcast(self,oid,msg):
        for ws in list(self.rooms.get(oid,[])):
            try: await ws.send_json(msg)
            except: self.disconnect(oid,ws)
location_hub=LocationHub()

@app.websocket("/ws/location/{order_id}")
async def ws_location(websocket:WebSocket,order_id:int,token:str):
    s=SessionLocal(); u=user_from_token(token,s); o=s.get(Order,order_id)
    if not u or not o or u.id not in {o.buyer_id,o.seller_id,o.driver_id}: await websocket.close(code=4401); s.close(); return
    await location_hub.connect(order_id,websocket)
    try:
        while True:
            d=await websocket.receive_json()
            if u.role!="driver": continue
            v=s.scalar(select(Vehicle).where(Vehicle.driver_id==u.id))
            if v:
                v.latitude=d["latitude"]; v.longitude=d["longitude"]; v.location_at=datetime.utcnow()
            ping=LocationPing(order_id=order_id,driver_id=u.id,latitude=d["latitude"],longitude=d["longitude"],speed_kmh=d.get("speed_kmh"))
            s.add(ping); s.commit()
            await location_hub.broadcast(order_id,{"order_id":order_id,"latitude":d["latitude"],"longitude":d["longitude"],"speed_kmh":d.get("speed_kmh"),"timestamp":datetime.utcnow().isoformat()})
    except WebSocketDisconnect: location_hub.disconnect(order_id,websocket)
    finally: s.close()

def participant(c,u): return u.id in {c.buyer_id,c.seller_id,c.driver_id}

class ChatHub:
    def __init__(self): self.rooms={}
    async def connect(self,cid,ws): await ws.accept(); self.rooms.setdefault(cid,[]).append(ws)
    def disconnect(self,cid,ws):
        if cid in self.rooms and ws in self.rooms[cid]: self.rooms[cid].remove(ws)
    async def broadcast(self,cid,msg):
        for ws in list(self.rooms.get(cid,[])):
            try: await ws.send_json(msg)
            except: self.disconnect(cid,ws)
chat_hub=ChatHub()

@app.post("/api/v1/conversations")
def create_conversation(x:ConversationIn,u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="buyer": raise HTTPException(403,"A conversa comercial é iniciada pelo comprador.")
    seller=s.get(User,x.seller_id)
    if not seller or seller.role!="farmer": raise HTTPException(400,"Vendedor inválido.")
    c=Conversation(buyer_id=u.id,seller_id=seller.id,driver_id=x.driver_id,product_id=x.product_id,order_id=x.order_id)
    s.add(c); s.commit(); s.refresh(c)
    for uid in [seller.id,x.driver_id]:
        if uid: notify(s,uid,"Nova conversa",f"{u.name} iniciou uma conversa.","chat")
    s.commit(); return {"id":c.id}

@app.get("/api/v1/conversations/{conv_id}/messages")
def get_messages(conv_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    c=s.get(Conversation,conv_id)
    if not c or not participant(c,u): raise HTTPException(403,"Sem acesso.")
    rows=s.scalars(select(ChatMessage).where(ChatMessage.conversation_id==conv_id).order_by(ChatMessage.id.asc())).all()
    return [{"id":r.id,"sender_id":r.sender_id,"content":r.content,"proposed_price":r.proposed_price,"created_at":r.created_at.isoformat()} for r in rows]

@app.websocket("/ws/chat/{conversation_id}")
async def ws_chat(websocket:WebSocket,conversation_id:int,token:str):
    s=SessionLocal(); u=user_from_token(token,s); c=s.get(Conversation,conversation_id)
    if not u or not c or not participant(c,u): await websocket.close(code=4401); s.close(); return
    await chat_hub.connect(conversation_id,websocket)
    try:
        while True:
            d=await websocket.receive_json(); content=(d.get("content") or "").strip()
            if not content: continue
            m=ChatMessage(conversation_id=conversation_id,sender_id=u.id,content=content,proposed_price=d.get("proposed_price"))
            s.add(m); s.commit(); s.refresh(m)
            for uid in [c.buyer_id,c.seller_id,c.driver_id]:
                if uid and uid!=u.id: notify(s,uid,"Nova mensagem",f"{u.name}: {content[:100]}","chat")
            s.commit()
            await chat_hub.broadcast(conversation_id,{"id":m.id,"sender_id":u.id,"content":m.content,"proposed_price":m.proposed_price,"created_at":m.created_at.isoformat()})
    except WebSocketDisconnect: chat_hub.disconnect(conversation_id,websocket)
    finally: s.close()

def _payment_method_label(method):
    return {"multicaixa_reference":"Referência MULTICAIXA","multicaixa_express":"MULTICAIXA Express","gpo":"MULTICAIXA / GPO","iban":"Transferência por IBAN","kwik_phone":"KWiK / telefone"}.get(method, method)

def _proxy_reference(amount, order_id):
    """Create a reference through an optional provider adapter.
    In sandbox/no credentials mode it creates a clearly labelled demo reference.
    Secrets never reach the mobile/web client.
    """
    import json, urllib.request
    expires=datetime.utcnow()+timedelta(days=PAYMENT_REFERENCE_DAYS)
    if PAYMENT_PROVIDER.lower()=="proxypay" and PROXYPAY_BASE_URL and PROXYPAY_API_KEY:
        url=PROXYPAY_BASE_URL.rstrip('/')+'/v2/references'
        payload={"amount":amount,"custom_fields":{"order_id":str(order_id),"platform":"AgroLink"}}
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+PROXYPAY_API_KEY},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=20) as r:
                data=json.loads(r.read().decode())
            return {"provider":"proxypay","entity":str(data.get("entity_id") or data.get("entity") or MULTICAIXA_ENTITY or ""),"reference_number":str(data.get("number") or data.get("reference_number") or data.get("reference") or ""),"gateway_reference":str(data.get("id") or data.get("reference_id") or ""),"expires_at":expires,"raw":data}
        except Exception as exc:
            raise HTTPException(502,"O provedor de pagamentos não respondeu. O pagamento não foi criado.") from exc
    return {"provider":"sandbox","entity":MULTICAIXA_ENTITY or "DEMO","reference_number":f"9{order_id:06d}{secrets.randbelow(100000):05d}","gateway_reference":None,"expires_at":expires,"raw":{"mode":"sandbox"}}

@app.post("/api/v1/payments")
def create_payment(x:PaymentIn,u:User=Depends(current_user),s:Session=Depends(db)):
    o=s.get(Order,x.order_id)
    if not o or o.buyer_id!=u.id: raise HTTPException(404,"Pedido não encontrado.")
    if not (o.buyer_reviewed and o.seller_reviewed and o.driver_reviewed):
        raise HTTPException(409,"Pagamento bloqueado: comprador, vendedor e transportador devem confirmar os dados primeiro.")
    if s.scalar(select(Payment).where(Payment.order_id==o.id)): raise HTTPException(409,"Pagamento já iniciado.")
    allowed={"multicaixa_reference","multicaixa_express","gpo","iban","kwik_phone"}
    if x.method not in allowed: raise HTTPException(400,"Método de pagamento inválido.")
    seller=s.get(User,o.seller_id)
    # Para preservar a comissão e o controlo da plataforma, IBAN/KWiK são pagos para a conta/identidade de recebimento do AgroLink, nunca diretamente para o vendedor.
    if x.method=="iban" and not AGROLINK_IBAN: raise HTTPException(503,"O IBAN de recebimento do AgroLink ainda não está configurado.")
    if x.method=="kwik_phone" and not AGROLINK_KWIK_PHONE: raise HTTPException(503,"O telefone KWiK de recebimento do AgroLink ainda não está configurado.")
    commission=round(o.total*COMMISSION_RATE,2); net=round(o.total-commission,2)
    reference=f"AGL-{o.id}-{secrets.token_hex(5).upper()}"
    data={"provider":"manual","entity":None,"reference_number":None,"gateway_reference":None,"expires_at":None,"raw":{}}
    if x.method in {"multicaixa_reference","gpo","multicaixa_express"}:
        data=_proxy_reference(o.total,o.id)
    p=Payment(order_id=o.id,method=x.method,provider=data["provider"],reference=reference,entity=data["entity"],reference_number=data["reference_number"],amount=o.total,commission_amount=commission,net_to_seller=net,status="aguardando",gateway_reference=data["gateway_reference"],beneficiary_name=AGROLINK_BENEFICIARY_NAME if x.method in {"iban","kwik_phone"} else seller.name,beneficiary_bank=AGROLINK_BANK if x.method=="iban" else None,beneficiary_iban=AGROLINK_IBAN if x.method=="iban" else None,beneficiary_phone=AGROLINK_KWIK_PHONE if x.method=="kwik_phone" else seller.express_phone or seller.phone,expires_at=data["expires_at"])
    s.add(p); s.flush()
    s.add(PaymentEvent(payment_id=p.id,event_type="payment_created",payload=json.dumps(data.get("raw",{}),ensure_ascii=False)))
    o.status="pagamento_pendente"; s.commit(); s.refresh(p)
    return {"id":p.id,"status":p.status,"method":p.method,"method_label":_payment_method_label(p.method),"provider":p.provider,"amount":p.amount,"commission_amount":p.commission_amount,"commission_rate":COMMISSION_RATE,"net_to_seller":p.net_to_seller,"reference":p.reference,"entity":p.entity,"reference_number":p.reference_number,"beneficiary_name":p.beneficiary_name,"beneficiary_iban":p.beneficiary_iban,"beneficiary_phone":p.beneficiary_phone,"expires_at":p.expires_at.isoformat() if p.expires_at else None,"message":"Pagamento criado. A confirmação depende do retorno do provedor para pagamentos eletrónicos; IBAN/KWiK ficam pendentes até confirmação."}

@app.post("/api/v1/payments/webhook")
def payment_webhook(x:PaymentWebhook, x_webhook_token:Optional[str]=Header(default=None, alias="X-Webhook-Token"), s:Session=Depends(db)):
    # In production configure PAYMENT_WEBHOOK_TOKEN and send it from the PSP.
    webhook_token=os.getenv("PAYMENT_WEBHOOK_TOKEN","")
    if webhook_token and not secrets.compare_digest(x_webhook_token or "", webhook_token):
        raise HTTPException(401,"Webhook não autorizado.")
    p=None
    if x.payment_id: p=s.get(Payment,x.payment_id)
    if not p and x.reference: p=s.scalar(select(Payment).where(Payment.reference==x.reference))
    if not p and x.gateway_reference: p=s.scalar(select(Payment).where(Payment.gateway_reference==x.gateway_reference))
    if not p: raise HTTPException(404,"Pagamento não encontrado.")
    if x.event_id and s.scalar(select(PaymentEvent).where(PaymentEvent.gateway_event_id==x.event_id)): return {"ok":True,"duplicate":True,"status":p.status}
    if x.amount is not None and abs(float(x.amount)-float(p.amount))>0.01: raise HTTPException(409,"Valor recebido não corresponde ao valor do pedido.")
    status=x.status.lower()
    p.gateway_status=status
    if x.gateway_reference: p.gateway_reference=x.gateway_reference
    if status in {"paid","pago","confirmed","confirmed_paid","success"}:
        p.status="pago"; p.confirmed_at=datetime.utcnow(); o=s.get(Order,p.order_id); o.status="pago"
        for uid in [o.buyer_id,o.seller_id,o.driver_id]:
            if uid: notify(s,uid,"Pagamento confirmado",f"O pagamento do pedido #{o.id} foi confirmado.","payment")
    elif status in {"failed","falhou","cancelled","cancelado","expired","expirado"}:
        p.status="falhou" if status not in {"expired","expirado"} else "expirado"
        o=s.get(Order,p.order_id); o.status="confirmado"
    s.add(PaymentEvent(payment_id=p.id,event_type="gateway_webhook",gateway_event_id=x.event_id,payload=x.model_dump_json()))
    s.commit()
    return {"ok":True,"status":p.status}

@app.post("/api/v1/payments/{payment_id}/confirm")
def confirm_payment(payment_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="admin": raise HTTPException(403,"Apenas administrador.")
    p=s.get(Payment,payment_id)
    if not p: raise HTTPException(404,"Pagamento não encontrado.")
    if p.status=="pago": return {"id":p.id,"status":p.status,"duplicate":True}
    p.status="pago"; p.gateway_status="admin_confirmed"; p.confirmed_at=datetime.utcnow(); o=s.get(Order,p.order_id); o.status="pago"
    s.add(PaymentEvent(payment_id=p.id,event_type="admin_confirmed",payload=json.dumps({"admin_id":u.id})))
    for uid in [o.buyer_id,o.seller_id,o.driver_id]:
        if uid: notify(s,uid,"Pagamento confirmado",f"O pagamento do pedido #{o.id} foi confirmado.","payment")
    s.commit(); return {"id":p.id,"status":p.status}

@app.get("/api/v1/notifications")
def notifications(u:User=Depends(current_user),s:Session=Depends(db)):
    rows=s.scalars(select(Notification).where(Notification.user_id==u.id).order_by(Notification.id.desc()).limit(50)).all()
    return [{"id":n.id,"title":n.title,"body":n.body,"kind":n.kind,"read":n.read,"created_at":n.created_at.isoformat()} for n in rows]

@app.post("/api/v1/notifications/{nid}/read")
def notification_read(nid:int,u:User=Depends(current_user),s:Session=Depends(db)):
    n=s.get(Notification,nid)
    if not n or n.user_id!=u.id: raise HTTPException(404,"Notificação não encontrada.")
    n.read=True; s.commit(); return {"ok":True}

@app.get("/api/v1/admin/summary")
def admin_summary(u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="admin": raise HTTPException(403,"Acesso reservado.")
    payments=s.scalars(select(Payment)).all()
    return {"users":s.query(User).count(),"products":s.query(Product).count(),"orders":s.query(Order).count(),
            "vehicles":s.query(Vehicle).count(),"sales_value":sum(o.total for o in s.scalars(select(Order)).all()),
            "commission_rate":COMMISSION_RATE,"commission_earned":round(sum(p.commission_amount for p in payments if p.status=="pago"),2),
            "pending_payments":sum(p.status=="aguardando" for p in payments)}



# --- IA AgroLink: publicidade e insights ---
def _ai_local_insights(s:Session,u:User):
    products=s.scalars(select(Product).where(Product.status=="active").order_by(Product.id.desc())).all()
    orders=s.scalars(select(Order).order_by(Order.id.desc())).all()
    paid=[o for o in orders if o.status in {"pago","a_caminho","entregue"}]
    if products:
        counts={}
        for p in products: counts[p.category]=counts.get(p.category,0)+1
        top_cat=max(counts,key=counts.get)
        ad=f"🌱 AgroLink em destaque: encontre {top_cat.lower()} de produtores angolanos. Consulte disponibilidade, preço e transporte no Mercado."
    else:
        ad="🌱 AgroLink Angola: conectamos produtores, compradores e transportadores. Publique a sua produção e alcance novos clientes."
    if u.role=="farmer":
        own=[p for p in products if p.producer_id==u.id]
        insight=f"Tem {len(own)} produto(s) ativo(s)." if own else "Ainda não tem produtos publicados. Publique a sua produção para aparecer no Mercado."
    elif u.role=="driver":
        vs=s.scalars(select(Vehicle).where(Vehicle.driver_id==u.id)).all(); insight=f"Tem {len(vs)} veículo(s) registado(s). Mantenha a localização atualizada para receber solicitações."
    else:
        insight=f"Há {len(products)} produto(s) disponível(is) e {len(paid)} pedido(s) em fluxo concluído/entrega."
    return {"title":"IA AgroLink","advertising":{"headline":"Publicidade inteligente","copy":ad,"cta":"Explorar Mercado"},"insights":[insight],"mode":"local"}

@app.get("/api/v1/ai/insights")
def ai_insights(u:User=Depends(current_user),s:Session=Depends(db)):
    # Deterministic fallback works without external credentials. Optional AI providers can be wired later.
    return _ai_local_insights(s,u)

@app.get("/api/v1/admin/dashboard")
def admin_dashboard(u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="admin": raise HTTPException(403,"Acesso reservado.")
    users=s.scalars(select(User)).all(); products=s.scalars(select(Product)).all(); orders=s.scalars(select(Order)).all(); payments=s.scalars(select(Payment)).all(); vehicles=s.scalars(select(Vehicle)).all()
    by_role={r:sum(1 for x in users if x.role==r) for r in ["buyer","farmer","driver","admin"]}
    status_counts={}
    for o in orders: status_counts[o.status]=status_counts.get(o.status,0)+1
    unread=s.scalar(select(Notification).where(Notification.read==False).count()) if False else sum(1 for n in s.scalars(select(Notification)).all() if not n.read)
    return {"users_total":len(users),"active_users":sum(getattr(x,"active",True) for x in users),"by_role":by_role,"products":len(products),"vehicles":len(vehicles),"orders":len(orders),"order_status":status_counts,"payments":len(payments),"paid_amount":round(sum(p.amount for p in payments if p.status=="pago"),2),"commission":round(sum(p.commission_amount for p in payments if p.status=="pago"),2),"pending_payments":sum(p.status=="aguardando" for p in payments),"unread_notifications":unread,"commission_rate":COMMISSION_RATE}

@app.post("/api/v1/admin/users/{user_id}/verify")
def admin_verify_user(user_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="admin": raise HTTPException(403,"Acesso reservado.")
    target=s.get(User,user_id)
    if not target: raise HTTPException(404,"Utilizador não encontrado.")
    target.verified=True; notify(s,target.id,"Conta verificada","A sua conta foi verificada pelo AgroLink.","account"); s.commit()
    return user_json(target)

@app.post("/api/v1/admin/users/{user_id}/toggle")
def admin_toggle_user(user_id:int,u:User=Depends(current_user),s:Session=Depends(db)):
    if u.role!="admin": raise HTTPException(403,"Acesso reservado.")
    target=s.get(User,user_id)
    if not target: raise HTTPException(404,"Utilizador não encontrado.")
    if target.id==u.id: raise HTTPException(400,"O administrador não pode desativar a própria conta.")
    target.active=not getattr(target,"active",True); s.commit(); return user_json(target)

# --- Commercial test/demo helpers ---
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

class StatusIn(BaseModel):
    status: str

@app.post("/api/v1/orders/{order_id}/status")
def update_order_status(order_id:int, x:StatusIn, u:User=Depends(current_user), s:Session=Depends(db)):
    o=s.get(Order, order_id)
    if not o or u.id not in {o.buyer_id,o.seller_id,o.driver_id}:
        raise HTTPException(404,"Pedido não encontrado.")
    allowed={"confirmado","pagamento_pendente","pago","a_caminho","entregue","cancelado"}
    if x.status not in allowed: raise HTTPException(400,"Estado inválido.")
    if x.status in {"a_caminho","entregue"} and u.id!=o.driver_id:
        raise HTTPException(403,"Apenas o transportador pode atualizar a entrega.")
    if x.status=="pago" and u.id!=o.buyer_id:
        raise HTTPException(403,"Apenas o comprador pode iniciar esta alteração; a confirmação bancária deve vir do gateway.")
    o.status=x.status
    if o.driver_id:
        v=s.scalar(select(Vehicle).where(Vehicle.driver_id==o.driver_id).order_by(Vehicle.id.desc()))
        if v and x.status in {"a_caminho","pago","confirmado"}: v.status="ocupado"
        if v and x.status in {"entregue","cancelado"}: v.status="livre"
    labels={"a_caminho":"A caminho","entregue":"Entregue","cancelado":"Cancelado","pago":"Pagamento confirmado","confirmado":"Transportador associado","pagamento_pendente":"Pagamento pendente"}
    for uid in [o.buyer_id,o.seller_id,o.driver_id]:
        if uid: notify(s,uid,"Atualização do pedido",f"O pedido #{o.id} está: {labels[x.status]}.","order")
    s.commit(); return order_json(o,s)

@app.get("/api/v1/admin/overview")
def admin_overview(u:User=Depends(current_user), s:Session=Depends(db)):
    if u.role!="admin": raise HTTPException(403,"Acesso reservado.")
    users=s.scalars(select(User).order_by(User.id.desc())).all()
    products=s.scalars(select(Product).order_by(Product.id.desc())).all()
    orders=s.scalars(select(Order).order_by(Order.id.desc()).limit(50)).all()
    payments=s.scalars(select(Payment).order_by(Payment.id.desc()).limit(50)).all()
    vehicles=s.scalars(select(Vehicle).order_by(Vehicle.id.desc())).all()
    return {"summary":admin_summary(u,s),
            "users":[user_json(x) for x in users],
            "products":[{"id":p.id,"name":p.name,"price":p.price,"quantity":p.quantity,"province":p.province,"producer_id":p.producer_id} for p in products],
            "orders":[order_json(o,s) for o in orders],
            "payments":[{"id":p.id,"order_id":p.order_id,"method":p.method,"provider":p.provider,"reference":p.reference,"entity":p.entity,"reference_number":p.reference_number,"amount":p.amount,"commission_amount":p.commission_amount,"net_to_seller":p.net_to_seller,"status":p.status,"gateway_reference":p.gateway_reference,"gateway_status":p.gateway_status,"beneficiary_name":p.beneficiary_name,"beneficiary_iban":p.beneficiary_iban,"beneficiary_phone":p.beneficiary_phone,"expires_at":p.expires_at.isoformat() if p.expires_at else None} for p in payments],
            "vehicles":[vehicle_json(v,s.get(User,v.driver_id)) for v in vehicles if s.get(User,v.driver_id)]}

@app.post("/api/v1/demo/reset")
def demo_reset(s:Session=Depends(db)):
    if not DEMO_MODE: raise HTTPException(404,"Demo desativado.")
    # Reset only application data; intended for local/demo environments.
    for model in [ChatMessage,Conversation,LocationPing,Payment,Notification,Order,Product,Vehicle,PasswordReset,User]:
        s.query(model).delete()
    s.commit()
    def mkphoto():
        try:
            import base64
            return "data:image/jpeg;base64,"+base64.b64encode(open("LogoAgrolink.jpeg","rb").read()).decode()
        except Exception: return None
    ph=mkphoto()
    demo=[
      User(name="Cliente Demonstração",phone="900000001",password_hash=pwd.hash("Demo1234"),role="buyer",province="Luanda",company_name="AgroLink Cliente",address="Talatona, Luanda",photo_data=ph,verified=True),
      User(name="Fazenda Esperança",phone="900000002",password_hash=pwd.hash("Demo1234"),role="farmer",province="Huambo",company_name="Fazenda Esperança",address="Huambo, Angola",photo_data=ph,verified=True),
      User(name="Motorista Agro Transporte",phone="900000003",password_hash=pwd.hash("Demo1234"),role="driver",province="Huambo",company_name="Agro Transporte, Lda.",address="Huambo, Angola",photo_data=ph,verified=True),
      User(name="Administrador AgroLink",phone="900000000",password_hash=pwd.hash("Admin1234"),role="admin",province="Luanda",company_name="Agro-Link Angola",address="Luanda, Angola",photo_data=ph,verified=True),
    ]
    s.add_all(demo); s.flush()
    farmer,driver=demo[1],demo[2]
    v=Vehicle(driver_id=driver.id,plate="LD-24-26-HU",model="Toyota Dyna",vehicle_type="Camião",capacity_kg=5000,photo_data=ph,status="livre",latitude=-12.7766,longitude=15.7392,location_at=datetime.utcnow())
    s.add(v)
    p1=Product(producer_id=farmer.id,name="Milho amarelo",category="Grãos",price=850,quantity=5000,unit="kg",province="Huambo",description="Milho produzido localmente pela Fazenda Esperança.",photo_data=ph)
    p2=Product(producer_id=farmer.id,name="Tomate fresco",category="Hortícolas",price=1200,quantity=1200,unit="kg",province="Huambo",description="Tomate fresco para revenda e consumo.",photo_data=ph)
    s.add_all([p1,p2]); s.commit()
    return {"message":"Dados de demonstração criados.","accounts":[{"role":"buyer","phone":"900000001","password":"Demo1234"},{"role":"farmer","phone":"900000002","password":"Demo1234"},{"role":"driver","phone":"900000003","password":"Demo1234"},{"role":"admin","phone":"900000000","password":"Admin1234"}]}

if os.path.isdir("static"): app.mount("/static",StaticFiles(directory="static"),name="static")
if __name__=="__main__":
    import uvicorn; uvicorn.run("app:app",host="0.0.0.0",port=int(os.getenv("PORT",8000)))
