import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from fastapi.responses import FileResponse
from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import (
    create_engine, String, Float, Integer, Boolean, ForeignKey, DateTime, select
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session


# Config de segurança para autenticação via token JWT
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrolink.db")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET")
ALGORITHM = "HS256"

#Ativa o esquema bearer para o botao authorize no swagger
security = HTTPBearer()

#Inicializa da aplicação 
app = FastAPI(title="AgroLink Angola API", version="1.0.0", description="API doo ecosistema AgroLink Angola")



# Comissão da plataforma. Moderada por defeito (4%). Configurável via env var.
COMMISSION_RATE = float(os.getenv("COMMISSION_RATE", "0.04"))  # 4%

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # buyer | farmer | driver | admin
    role: Mapped[str] = mapped_column(String(30), default="buyer")
    province: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # dados de pagamento do utilizador (para receber, ex: agricultor/transportador)
    iban: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    express_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    plate: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80), default="")
    vehicle_type: Mapped[str] = mapped_column(String(30), default="camião")
    capacity_kg: Mapped[float] = mapped_column(Float, default=0)


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
    driver_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    # pending | confirmed | a_caminho | entregue | cancelado
    status: Mapped[str] = mapped_column(String(40), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LocationPing(Base):
    """Última posição (e histórico) do veículo/transportador em movimento."""
    __tablename__ = "location_pings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    """Uma conversa entre comprador e agricultor (opcionalmente ligada a um produto/pedido)."""
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(String(1000))
    proposed_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    # multicaixa_express | iban
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(80))  # nº telefone Express ou IBAN
    amount: Mapped[float] = mapped_column(Float)
    commission_amount: Mapped[float] = mapped_column(Float)
    net_to_seller: Mapped[float] = mapped_column(Float)
    # pendente | pago | falhou
    status: Mapped[str] = mapped_column(String(30), default="pendente")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="AgroLink Angola API", version="2.0.0")

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


def current_user(credentials: HTTPAuthorizationCredentials = Depends(security), s: Session = Depends(db)):
    try:
        data = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user = s.get(User, int(data["sub"]))
        if not user:
            raise HTTPException(401, "Utilizador inválido.")
        return user
    except (JWTError, ValueError):
        raise HTTPException(401, "Token inválido.")


def user_from_token(token: str, s: Session) -> Optional[User]:
    """Versão para WebSockets (o token vem por query string, não por header)."""
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return s.get(User, int(data["sub"]))
    except (JWTError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class Register(BaseModel):
    name: str
    phone: str
    password: str = Field(min_length=6)
    role: str = "buyer"          # buyer | farmer | driver
    province: Optional[str] = None
    iban: Optional[str] = None
    express_phone: Optional[str] = None


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


class AssignDriver(BaseModel):
    driver_id: int


class VehicleIn(BaseModel):
    plate: str
    model: str = ""
    vehicle_type: str = "camião"
    capacity_kg: float = 0


class ConversationIn(BaseModel):
    seller_id: int
    product_id: Optional[int] = None


class MessageIn(BaseModel):
    content: str
    proposed_price: Optional[float] = None


class PaymentIn(BaseModel):
    order_id: int
    method: str  # "multicaixa_express" | "iban"
    reference: str


# ---------------------------------------------------------------------------
# Auth & Users
# ---------------------------------------------------------------------------
@app.get("/",response_class=FileResponse)
def read_index():
    #Serve a página web do frontend (index.html)."""
    return FileResponse("index.html")
@app.get("/health")
def health():
    return {"status": "ok", "app": "AgroLink Angola", "commission_rate": COMMISSION_RATE}


@app.post("/api/v1/auth/register")
def register(x: Register, s: Session = Depends(db)):
    if s.scalar(select(User).where(User.phone == x.phone)):
        raise HTTPException(409, "Telefone já registado.")
    if x.role not in {"buyer", "farmer", "driver"}:
        raise HTTPException(400, "Perfil inválido.")
    u = User(name=x.name, phone=x.phone, password_hash=pwd.hash(x.password),
              role=x.role, province=x.province, iban=x.iban, express_phone=x.express_phone)
    s.add(u); s.commit(); s.refresh(u)
    return {"access_token": token_for(u), "user": {"id": u.id, "name": u.name, "role": u.role}}


@app.post("/api/v1/auth/login")
def login(x: Login, s: Session = Depends(db)):
    u = s.scalar(select(User).where(User.phone == x.phone))
    if not u or not pwd.verify(x.password, u.password_hash):
        raise HTTPException(401, "Credenciais inválidas.")
    return {"access_token": token_for(u), "user": {"id": u.id, "name": u.name, "role": u.role}}


@app.get("/api/v1/drivers")
def list_drivers(province: Optional[str] = None, s: Session = Depends(db)):
    stmt = select(User).where(User.role == "driver")
    if province:
        stmt = stmt.where(User.province == province)
    rows = s.scalars(stmt).all()
    return [{"id": r.id, "name": r.name, "province": r.province} for r in rows]


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------
@app.post("/api/v1/vehicles")
def register_vehicle(x: VehicleIn, u: User = Depends(current_user), s: Session = Depends(db)):
    if u.role != "driver":
        raise HTTPException(403, "Apenas transportadores podem registar veículos.")
    existing = s.scalar(select(Vehicle).where(Vehicle.driver_id == u.id))
    if existing:
        raise HTTPException(409, "Já tem um veículo registado.")
    v = Vehicle(driver_id=u.id, **x.model_dump())
    s.add(v); s.commit(); s.refresh(v)
    return {"id": v.id, "message": "Veículo registado."}


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Orders + Delivery assignment
# ---------------------------------------------------------------------------
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


@app.post("/api/v1/orders/{order_id}/assign-driver")
def assign_driver(order_id: int, x: AssignDriver, u: User = Depends(current_user), s: Session = Depends(db)):
    o = s.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Pedido não encontrado.")
    driver = s.get(User, x.driver_id)
    if not driver or driver.role != "driver":
        raise HTTPException(400, "Transportador inválido.")
    o.driver_id = driver.id
    o.status = "confirmado"
    s.commit()
    return {"id": o.id, "driver_id": o.driver_id, "status": o.status}


@app.get("/api/v1/orders")
def orders(u: User = Depends(current_user), s: Session = Depends(db)):
    stmt = select(Order)
    if u.role == "buyer": stmt = stmt.where(Order.buyer_id == u.id)
    if u.role == "driver": stmt = stmt.where(Order.driver_id == u.id)
    rows = s.scalars(stmt.order_by(Order.id.desc())).all()
    return [{"id": r.id, "product_id": r.product_id, "quantity": r.quantity,
             "total": r.total, "status": r.status, "driver_id": r.driver_id,
             "created_at": r.created_at.isoformat()} for r in rows]


# ---------------------------------------------------------------------------
# Real-time location (WebSocket)
# ---------------------------------------------------------------------------
class LocationHub:
    """Mantém as ligações WebSocket que acompanham cada pedido (order_id)."""
    def __init__(self):
        self.rooms: Dict[int, List[WebSocket]] = {}

    async def connect(self, order_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms.setdefault(order_id, []).append(ws)

    def disconnect(self, order_id: int, ws: WebSocket):
        if order_id in self.rooms and ws in self.rooms[order_id]:
            self.rooms[order_id].remove(ws)

    async def broadcast(self, order_id: int, message: dict):
        for ws in list(self.rooms.get(order_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(order_id, ws)


location_hub = LocationHub()


@app.websocket("/ws/location/{order_id}")
async def ws_location(websocket: WebSocket, order_id: int, token: str):
    """
    O transportador liga-se a este socket e envia:
        {"latitude": -8.83, "longitude": 13.23, "speed_kmh": 42}
    Todos os outros ligados ao mesmo pedido (comprador, agricultor) recebem
    a posição em tempo real. As posições também ficam gravadas na BD.
    """
    s = SessionLocal()
    user = user_from_token(token, s)
    order = s.get(Order, order_id)
    if not user or not order:
        await websocket.close(code=4401)
        s.close()
        return

    await location_hub.connect(order_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if user.role == "driver":
                ping = LocationPing(
                    order_id=order_id, driver_id=user.id,
                    latitude=data["latitude"], longitude=data["longitude"],
                    speed_kmh=data.get("speed_kmh"),
                )
                s.add(ping); s.commit()
            await location_hub.broadcast(order_id, {
                "order_id": order_id,
                "latitude": data["latitude"],
                "longitude": data["longitude"],
                "speed_kmh": data.get("speed_kmh"),
                "timestamp": datetime.utcnow().isoformat(),
            })
    except WebSocketDisconnect:
        location_hub.disconnect(order_id, websocket)
    finally:
        s.close()


@app.get("/api/v1/orders/{order_id}/location")
def last_location(order_id: int, u: User = Depends(current_user), s: Session = Depends(db)):
    ping = s.scalar(
        select(LocationPing).where(LocationPing.order_id == order_id)
        .order_by(LocationPing.id.desc())
    )
    if not ping:
        raise HTTPException(404, "Ainda sem localização para este pedido.")
    return {"latitude": ping.latitude, "longitude": ping.longitude,
            "speed_kmh": ping.speed_kmh, "timestamp": ping.created_at.isoformat()}


# ---------------------------------------------------------------------------
# Chat (negociação de preços)
# ---------------------------------------------------------------------------
class ChatHub:
    def __init__(self):
        self.rooms: Dict[int, List[WebSocket]] = {}

    async def connect(self, conv_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms.setdefault(conv_id, []).append(ws)

    def disconnect(self, conv_id: int, ws: WebSocket):
        if conv_id in self.rooms and ws in self.rooms[conv_id]:
            self.rooms[conv_id].remove(ws)

    async def broadcast(self, conv_id: int, message: dict):
        for ws in list(self.rooms.get(conv_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(conv_id, ws)


chat_hub = ChatHub()


@app.post("/api/v1/conversations")
def create_conversation(x: ConversationIn, u: User = Depends(current_user), s: Session = Depends(db)):
    existing = s.scalar(
        select(Conversation).where(
            Conversation.buyer_id == u.id, Conversation.seller_id == x.seller_id,
            Conversation.product_id == x.product_id,
        )
    )
    if existing:
        return {"id": existing.id}
    c = Conversation(buyer_id=u.id, seller_id=x.seller_id, product_id=x.product_id)
    s.add(c); s.commit(); s.refresh(c)
    return {"id": c.id}


@app.get("/api/v1/conversations/{conv_id}/messages")
def get_messages(conv_id: int, u: User = Depends(current_user), s: Session = Depends(db)):
    rows = s.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.id.asc())
    ).all()
    return [{"id": r.id, "sender_id": r.sender_id, "content": r.content,
             "proposed_price": r.proposed_price, "created_at": r.created_at.isoformat()}
            for r in rows]


@app.websocket("/ws/chat/{conversation_id}")
async def ws_chat(websocket: WebSocket, conversation_id: int, token: str):
    s = SessionLocal()
    user = user_from_token(token, s)
    conv = s.get(Conversation, conversation_id)
    if not user or not conv:
        await websocket.close(code=4401)
        s.close()
        return

    await chat_hub.connect(conversation_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg = ChatMessage(
                conversation_id=conversation_id, sender_id=user.id,
                content=data.get("content", ""), proposed_price=data.get("proposed_price"),
            )
            s.add(msg); s.commit(); s.refresh(msg)
            await chat_hub.broadcast(conversation_id, {
                "id": msg.id, "sender_id": user.id, "content": msg.content,
                "proposed_price": msg.proposed_price,
                "created_at": msg.created_at.isoformat(),
            })
    except WebSocketDisconnect:
        chat_hub.disconnect(conversation_id, websocket)
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Payments (Multicaixa Express / IBAN) + Comissão da plataforma
# ---------------------------------------------------------------------------
@app.post("/api/v1/payments")
def create_payment(x: PaymentIn, u: User = Depends(current_user), s: Session = Depends(db)):
    if x.method not in {"multicaixa_express", "iban"}:
        raise HTTPException(400, "Método de pagamento inválido.")
    order = s.get(Order, x.order_id)
    if not order or order.buyer_id != u.id:
        raise HTTPException(404, "Pedido não encontrado.")
    if s.scalar(select(Payment).where(Payment.order_id == order.id)):
        raise HTTPException(409, "Este pedido já tem um pagamento registado.")

    commission = round(order.total * COMMISSION_RATE, 2)
    net = round(order.total - commission, 2)

    payment = Payment(
        order_id=order.id, method=x.method, reference=x.reference,
        amount=order.total, commission_amount=commission, net_to_seller=net,
        status="pendente",
    )
    s.add(payment)
    order.status = "pago"
    s.commit(); s.refresh(payment)

    return {
        "id": payment.id,
        "method": payment.method,
        "amount": payment.amount,
        "commission_amount": payment.commission_amount,
        "commission_rate": COMMISSION_RATE,
        "net_to_seller": payment.net_to_seller,
        "status": payment.status,
        "instructions": (
            f"Confirme o pagamento de Kz {payment.amount:,.0f} via Multicaixa Express "
            f"para o número {payment.reference}."
            if x.method == "multicaixa_express"
            else f"Transfira Kz {payment.amount:,.0f} por IBAN para {payment.reference}."
        ),
    }


@app.post("/api/v1/payments/{payment_id}/confirm")
def confirm_payment(payment_id: int, u: User = Depends(current_user), s: Session = Depends(db)):
    """Simula a confirmação vinda do gateway (webhook em produção)."""
    if u.role != "admin":
        raise HTTPException(403, "Apenas o administrador pode confirmar pagamentos manualmente.")
    payment = s.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Pagamento não encontrado.")
    payment.status = "pago"
    s.commit()
    return {"id": payment.id, "status": payment.status}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@app.get("/api/v1/admin/summary")
def admin_summary(u: User = Depends(current_user), s: Session = Depends(db)):
    if u.role != "admin": raise HTTPException(403, "Acesso reservado.")
    payments = s.scalars(select(Payment)).all()
    return {
        "users": s.query(User).count(),
        "products": s.query(Product).count(),
        "orders": s.query(Order).count(),
        "sales_value": sum(x.total for x in s.scalars(select(Order)).all()),
        "commission_rate": COMMISSION_RATE,
        "commission_earned": round(sum(p.commission_amount for p in payments if p.status == "pago"), 2),
        "pending_payments": len([p for p in payments if p.status == "pendente"]),
    }
#Meu Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwicm9sZSI6ImJ1eWVyIiwiZXhwIjoxNzg5Nzk5NzcwfQ.zpB9uTCkv4TGqElYOF9y_1HPQO3S5IroFlM8v4qOhBs
