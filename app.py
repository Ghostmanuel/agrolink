import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import create_engine, String, Float, Integer, ForeignKey, DateTime, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrolink.db")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET")
ALGORITHM = "HS256"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="buyer")
    province: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    verified: Mapped[bool] = mapped_column(default=False)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    province: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="active")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    quantity: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="AgroLink Angola API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()

def token_for(user):
    payload = {"sub": str(user.id), "role": user.role,
               "exp": datetime.utcnow() + timedelta(hours=12)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def current_user(authorization: Optional[str] = Header(None), s: Session = Depends(db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Autenticação necessária.")
    try:
        data = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        user = s.get(User, int(data["sub"]))
        if not user:
            raise HTTPException(401, "Utilizador inválido.")
        return user
    except (JWTError, ValueError):
        raise HTTPException(401, "Token inválido.")

class Register(BaseModel):
    name: str
    phone: str
    password: str = Field(min_length=6)
    role: str = "buyer"
    province: Optional[str] = None

class Login(BaseModel):
    phone: str
    password: str

class ProductIn(BaseModel):
    name: str
    category: str
    price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    unit: str
    province: str
    description: str = ""

class OrderIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)

@app.get("/health")
def health():
    return {"status": "ok", "app": "AgroLink Angola"}

@app.post("/api/v1/auth/register")
def register(x: Register, s: Session = Depends(db)):
    if s.scalar(select(User).where(User.phone == x.phone)):
        raise HTTPException(409, "Telefone já registado.")
    if x.role not in {"buyer", "farmer", "driver"}:
        raise HTTPException(400, "Perfil inválido.")
    u = User(name=x.name, phone=x.phone, password_hash=pwd.hash(x.password),
             role=x.role, province=x.province)
    s.add(u); s.commit(); s.refresh(u)
    return {"access_token": token_for(u), "user": {"id": u.id, "name": u.name, "role": u.role}}

@app.post("/api/v1/auth/login")
def login(x: Login, s: Session = Depends(db)):
    u = s.scalar(select(User).where(User.phone == x.phone))
    if not u or not pwd.verify(x.password, u.password_hash):
        raise HTTPException(401, "Credenciais inválidas.")
    return {"access_token": token_for(u), "user": {"id": u.id, "name": u.name, "role": u.role}}

@app.get("/api/v1/products")
def products(province: Optional[str] = None, category: Optional[str] = None,
             q: Optional[str] = None, s: Session = Depends(db)):
    stmt = select(Product).where(Product.status == "active")
    if province: stmt = stmt.where(Product.province == province)
    if category: stmt = stmt.where(Product.category == category)
    rows = s.scalars(stmt).all()
    if q: rows = [r for r in rows if q.lower() in r.name.lower()]
    return [{"id": r.id, "name": r.name, "category": r.category, "price": r.price,
             "quantity": r.quantity, "unit": r.unit, "province": r.province,
             "producer_id": r.producer_id, "description": r.description} for r in rows]

@app.post("/api/v1/products")
def create_product(x: ProductIn, u: User = Depends(current_user), s: Session = Depends(db)):
    if u.role != "farmer":
        raise HTTPException(403, "Apenas agricultores podem publicar produtos.")
    p = Product(producer_id=u.id, **x.model_dump())
    s.add(p); s.commit(); s.refresh(p)
    return {"id": p.id, "message": "Produto publicado."}

@app.post("/api/v1/orders")
def create_order(x: OrderIn, u: User = Depends(current_user), s: Session = Depends(db)):
    if u.role != "buyer":
        raise HTTPException(403, "Apenas compradores podem criar pedidos.")
    p = s.get(Product, x.product_id)
    if not p or p.status != "active": raise HTTPException(404, "Produto não encontrado.")
    if p.quantity < x.quantity: raise HTTPException(400, "Quantidade indisponível.")
    total = p.price * x.quantity
    p.quantity -= x.quantity
    o = Order(product_id=p.id, buyer_id=u.id, quantity=x.quantity, total=total)
    s.add(o); s.commit(); s.refresh(o)
    return {"id": o.id, "total": total, "status": o.status}

@app.get("/api/v1/orders")
def orders(u: User = Depends(current_user), s: Session = Depends(db)):
    stmt = select(Order)
    if u.role == "buyer": stmt = stmt.where(Order.buyer_id == u.id)
    rows = s.scalars(stmt.order_by(Order.id.desc())).all()
    return [{"id": r.id, "product_id": r.product_id, "quantity": r.quantity,
             "total": r.total, "status": r.status, "created_at": r.created_at.isoformat()}
            for r in rows]

@app.get("/api/v1/admin/summary")
def admin_summary(u: User = Depends(current_user), s: Session = Depends(db)):
    if u.role != "admin": raise HTTPException(403, "Acesso reservado.")
    return {
        "users": s.query(User).count(),
        "products": s.query(Product).count(),
        "orders": s.query(Order).count(),
        "sales_value": sum(x.total for x in s.scalars(select(Order)).all())
    }
