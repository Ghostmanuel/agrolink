import hashlib,hmac,json,secrets,os,urllib.request,urllib.parse
from datetime import datetime,timezone,timedelta
from fastapi import FastAPI,HTTPException,Depends,Header,WebSocket,WebSocketDisconnect,Request
from fastapi.responses import HTMLResponse,FileResponse
from fastapi.middleware.cors import CORSMiddleware
from db import init_db,get_db
from schemas import *
from security import *
from config import *

app=FastAPI(title=APP_NAME,version="14.0.0")
TOKENS={}
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

def _client_ip(request:Request):
    return request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")

def verify_turnstile(token, request:Request):
    if not TURNSTILE_REQUIRED:
        return True
    if not TURNSTILE_SECRET_KEY or not TURNSTILE_SITE_KEY:
        raise HTTPException(503, "Verificação anti-robô não configurada no servidor")
    if not token:
        raise HTTPException(400, "Confirme a verificação anti-robô")
    data=json.dumps({"secret":TURNSTILE_SECRET_KEY,"response":token,"remoteip":_client_ip(request),"idempotency_key":secrets.token_hex(16)}).encode()
    req=urllib.request.Request("https://challenges.cloudflare.com/turnstile/v0/siteverify",data=data,headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=8) as resp:
            result=json.loads(resp.read().decode())
    except Exception:
        raise HTTPException(503,"Não foi possível validar a verificação anti-robô. Tente novamente.")
    if not result.get("success"):
        raise HTTPException(400,"Verificação anti-robô inválida ou expirada. Tente novamente.")
    return True


@app.on_event("startup")
def startup():
    if not SECRET_KEY: raise RuntimeError("SECRET_KEY é obrigatória")
    init_db(); bootstrap_admin()

def bootstrap_admin():
    if not ADMIN_PHONE or not ADMIN_PASSWORD: return
    db=get_db(); phone=normalize_phone(ADMIN_PHONE)
    u=db.execute("SELECT id FROM users WHERE phone=?",(phone,)).fetchone()
    if not u:
        db.execute("INSERT INTO users(full_name,phone,password_hash,role,province,address) VALUES(?,?,?,?,?,?)",(ADMIN_NAME,phone,hash_password(ADMIN_PASSWORD),"admin",ADMIN_PROVINCE,ADMIN_ADDRESS))
    else:
        db.execute("UPDATE users SET full_name=?,password_hash=?,role='admin',province=?,address=?,status='active' WHERE id=?",(ADMIN_NAME,hash_password(ADMIN_PASSWORD),ADMIN_PROVINCE,ADMIN_ADDRESS,u["id"]))
    db.commit(); db.close()

def auth(authorization:str=Header(default="")):
    if not authorization.startswith("Bearer "): raise HTTPException(401,"Autenticação necessária")
    token=authorization[7:]; uid=TOKENS.get(token)
    if not uid: raise HTTPException(401,"Sessão inválida")
    db=get_db(); u=db.execute("SELECT * FROM users WHERE id=? AND status='active'",(uid,)).fetchone(); db.close()
    if not u: raise HTTPException(401,"Sessão inválida")
    return dict(u)

def role(*roles):
    def dep(u=Depends(auth)):
        if u["role"] not in roles: raise HTTPException(403,"Permissão insuficiente")
        return u
    return dep

def audit(db,uid,action,typ=None,eid=None,meta=None):
    db.execute("INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,metadata) VALUES(?,?,?,?,?)",(uid,action,typ,eid,json.dumps(meta or {},ensure_ascii=False)))

def notify(db,uid,title,body): db.execute("INSERT INTO notifications(user_id,title,body) VALUES(?,?,?)",(uid,title,body))
def order_access(db,oid,uid):
    o=db.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
    if not o: raise HTTPException(404,"Pedido não encontrado")
    d=db.execute("SELECT transporter_id FROM deliveries WHERE order_id=?",(oid,)).fetchone()
    if uid not in (o["buyer_id"],o["seller_id"]) and not (d and d["transporter_id"]==uid): raise HTTPException(403,"Sem acesso")
    return o

def calc_fee(distance): return round(BASE_DELIVERY_FEE + max(0,float(distance))*DELIVERY_RATE_PER_KM,2)

def recalc_total(db,oid,distance,fee):
    o=db.execute("SELECT product_total_kz FROM orders WHERE id=?",(oid,)).fetchone(); total=round(o["product_total_kz"]+fee,2)
    db.execute("UPDATE orders SET delivery_distance_km=?,delivery_fee_kz=?,total_kz=? WHERE id=?",(distance,fee,total,oid)); return total

@app.get("/",response_class=HTMLResponse)
def home(): return FileResponse("index.html",media_type="text/html")
@app.get("/index.html",response_class=HTMLResponse)
def index(): return FileResponse("index.html",media_type="text/html")
@app.get("/manifest.json")
def manifest(): return FileResponse("manifest.json",media_type="application/manifest+json")
@app.get("/sw.js")
def sw(): return FileResponse("sw.js",media_type="application/javascript")
@app.get("/LogoAgrolink.jpeg")
def logo(): return FileResponse("LogoAgrolink.jpeg",media_type="image/jpeg")

@app.get("/api/public-config")
def public_config():
    return {"turnstile_site_key": TURNSTILE_SITE_KEY}

@app.post("/api/auth/register")
def register(x:Register, request:Request):
    verify_turnstile(x.__dict__.get("turnstile_token"), request)
    db=get_db(); phone=normalize_phone(x.phone)
    if db.execute("SELECT id FROM users WHERE phone=?",(phone,)).fetchone():
        db.close(); raise HTTPException(409,"Telefone já registado")
    if x.role=="seller" and not (x.company_name or x.farm_name):
        db.close(); raise HTTPException(422,"Indique empresa ou fazenda")
    if x.role in ("private_transporter","transporter") and not x.bi_number:
        db.close(); raise HTTPException(422,"BI é obrigatório para transportador particular")
    if x.role=="transport_company" and not x.company_name:
        db.close(); raise HTTPException(422,"Indique o nome da empresa transportadora")
    bih=blind_hash(x.bi_number) if x.bi_number else None
    bie=encrypt_sensitive(x.bi_number) if x.bi_number else None
    try:
        c=db.execute("INSERT INTO users(full_name,phone,password_hash,role,province,address,bi_number_encrypted,bi_blind_hash) VALUES(?,?,?,?,?,?,?,?)",(x.full_name.strip(),phone,hash_password(x.password),x.role,x.province.strip(),x.address.strip(),bie,bih)); uid=c.lastrowid
        if x.role=="seller": db.execute("INSERT INTO producers(user_id,company_name,farm_name,province) VALUES(?,?,?,?)",(uid,x.company_name,x.farm_name,x.province))
        if x.role=="transport_company": db.execute("INSERT INTO transport_companies(user_id,company_name,location) VALUES(?,?,?)",(uid,x.company_name,x.address))
        audit(db,uid,"USER_REGISTERED","users",uid,{"role":x.role}); db.commit()
    except Exception:
        db.rollback(); db.close(); raise HTTPException(500,"Não foi possível concluir o cadastro. Verifique os dados e tente novamente.")
    db.close(); return {"ok":True,"user_id":uid}

@app.post("/api/auth/login")
def login(x:Login, request:Request):
    verify_turnstile(x.turnstile_token, request)
    db=get_db(); u=db.execute("SELECT * FROM users WHERE phone=?",(normalize_phone(x.phone),)).fetchone(); db.close()
    if not u or not verify_password(x.password,u["password_hash"]): raise HTTPException(401,"Telefone ou palavra-passe inválidos")
    if u["status"]!="active": raise HTTPException(403,"Conta suspensa")
    t=secrets.token_urlsafe(32); TOKENS[t]=u["id"]
    return {"access_token":t,"token_type":"bearer","role":u["role"],"full_name":u["full_name"]}

@app.post("/api/auth/forgot-password")
def forgot_password(x:ForgotPassword, request:Request):
    verify_turnstile(x.turnstile_token, request)
    phone=normalize_phone(x.phone); db=get_db(); u=db.execute("SELECT id FROM users WHERE phone=? AND status='active'",(phone,)).fetchone()
    # Always return the same public message to avoid account enumeration.
    message="Se o número estiver registado, um código de recuperação foi gerado."
    if not u:
        db.close(); return {"ok":True,"message":message.strip()}
    code=reset_code(); expires=(datetime.now(timezone.utc)+timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)).isoformat()
    db.execute("UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND used_at IS NULL",(u["id"],))
    db.execute("INSERT INTO password_reset_tokens(user_id,token_hash,expires_at,attempts) VALUES(?,?,?,0)",(u["id"],reset_token_hash(code),expires))
    db.commit(); db.close()
    out={"ok":True,"message":message.strip()}
    if PASSWORD_RESET_DEMO: out["demo_code"]=code
    return out

@app.post("/api/auth/reset-password")
def reset_password(x:ResetPassword, request:Request):
    verify_turnstile(x.turnstile_token, request)
    phone=normalize_phone(x.phone); db=get_db(); u=db.execute("SELECT id FROM users WHERE phone=? AND status='active'",(phone,)).fetchone()
    if not u: db.close(); raise HTTPException(400,"Código ou dados inválidos")
    token=db.execute("SELECT * FROM password_reset_tokens WHERE user_id=? AND used_at IS NULL ORDER BY id DESC LIMIT 1",(u["id"],)).fetchone()
    if not token: db.close(); raise HTTPException(400,"Código expirado ou inválido")
    if token["attempts"]>=5: db.close(); raise HTTPException(429,"Muitas tentativas. Solicite um novo código.")
    try: expired=datetime.fromisoformat(token["expires_at"].replace("Z","+00:00")) <= datetime.now(timezone.utc)
    except Exception: expired=True
    if expired:
        db.close(); raise HTTPException(400,"Código expirado. Solicite um novo código.")
    if not hmac.compare_digest(token["token_hash"],reset_token_hash(x.code)):
        db.execute("UPDATE password_reset_tokens SET attempts=attempts+1 WHERE id=?",(token["id"],)); db.commit(); db.close(); raise HTTPException(400,"Código inválido")
    db.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(x.new_password),u["id"]))
    db.execute("UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE id=?",(token["id"],)); db.commit(); db.close()
    return {"ok":True,"message":"Palavra-passe alterada com sucesso."}

@app.get("/api/me")
def me(u=Depends(auth)):
    db=get_db(); p=db.execute("SELECT * FROM producers WHERE user_id=?",(u["id"],)).fetchone(); v=db.execute("SELECT * FROM vehicles WHERE transporter_id=?",(u["id"],)).fetchall()
    out=dict(u); out.pop("password_hash",None); out.pop("bi_number_encrypted",None); out["bi_masked"]=("***********"+str((decrypt_sensitive(u.get("bi_number_encrypted")) or "")[-3:])) if u.get("bi_number_encrypted") else None; out["producer"]=dict(p) if p else None; out["vehicles"]=[dict(x) for x in v];
    if u["role"]=="transport_company":
        c=db.execute("SELECT * FROM transport_companies WHERE user_id=?",(u["id"],)).fetchone(); out["transport_company"]=dict(c) if c else None
        out["drivers_count"]=db.execute("SELECT COUNT(*) c FROM drivers WHERE company_user_id=?",(u["id"],)).fetchone()["c"]
    db.close(); return out

@app.get("/api/categories")
def categories():
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT * FROM categories ORDER BY name").fetchall()]; db.close(); return rows

@app.get("/api/products")
def products(q:str="",category_id:int|None=None):
    db=get_db(); sql="""SELECT p.*,u.full_name seller_name,pr.company_name,pr.farm_name,c.name category_name FROM products p JOIN users u ON u.id=p.seller_id LEFT JOIN producers pr ON pr.user_id=u.id LEFT JOIN categories c ON c.id=p.category_id WHERE p.active=1"""; args=[]
    if q: sql+=" AND (p.name LIKE ? OR p.description LIKE ? OR pr.company_name LIKE ? OR pr.farm_name LIKE ? OR p.location LIKE ?)"; args += [f"%{q}%"]*5
    if category_id: sql+=" AND p.category_id=?"; args.append(category_id)
    sql+=" ORDER BY p.created_at DESC"; rows=[dict(x) for x in db.execute(sql,args).fetchall()]; db.close(); return rows

@app.post("/api/products")
def create_product(x:Product,u=Depends(role("seller"))):
    db=get_db();
    if x.category_id and not db.execute("SELECT id FROM categories WHERE id=?",(x.category_id,)).fetchone(): db.close(); raise HTTPException(400,"Categoria inválida")
    c=db.execute("INSERT INTO products(seller_id,category_id,name,description,price_kz,quantity,unit,photo,location) VALUES(?,?,?,?,?,?,?,?,?)",(u["id"],x.category_id,x.name.strip(),x.description.strip(),x.price_kz,x.quantity,x.unit,x.photo,x.location.strip())); audit(db,u["id"],"PRODUCT_CREATED","products",c.lastrowid); db.commit(); db.close(); return {"id":c.lastrowid}

@app.get("/api/orders")
def orders(u=Depends(auth)):
    db=get_db(); sql="""SELECT o.*,p.name product_name,p.photo product_photo,b.full_name buyer_name,s.full_name seller_name,pr.company_name seller_company,d.id delivery_id,d.transporter_id,d.vehicle_id,d.status delivery_current_status FROM orders o JOIN products p ON p.id=o.product_id JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id LEFT JOIN producers pr ON pr.user_id=o.seller_id LEFT JOIN deliveries d ON d.order_id=o.id WHERE o.buyer_id=? OR o.seller_id=? OR d.transporter_id=? ORDER BY o.created_at DESC"""; rows=[dict(x) for x in db.execute(sql,(u["id"],u["id"],u["id"])).fetchall()]; db.close(); return rows

@app.post("/api/orders")
def create_order(x:Order,u=Depends(role("buyer"))):
    db=get_db()
    try:
        p=db.execute("SELECT * FROM products WHERE id=? AND active=1",(x.product_id,)).fetchone()
        if not p: raise HTTPException(404,"Produto não encontrado")
        if x.quantity>p["quantity"]: raise HTTPException(400,"Quantidade indisponível")
        if p["seller_id"]==u["id"]: raise HTTPException(400,"Não pode comprar o próprio produto")
        total=round(x.quantity*p["price_kz"],2)
        c=db.execute("INSERT INTO orders(buyer_id,seller_id,product_id,quantity,delivery_address,transport_mode,delivery_distance_km,delivery_fee_kz,product_total_kz,total_kz,status,payment_status,delivery_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(u["id"],p["seller_id"],p["id"],x.quantity,x.delivery_address.strip(),"pending",0,0,total,total,"PENDING_SELLER","NOT_STARTED","NOT_REQUESTED"))
        oid=c.lastrowid
        db.execute("INSERT OR IGNORE INTO conversations(order_id) VALUES(?)",(oid,))
        notify(db,p["seller_id"],"Novo pedido",f"Pedido #{oid} aguarda análise.")
        audit(db,u["id"],"ORDER_CREATED","orders",oid)
        db.commit()
    except HTTPException:
        db.rollback(); db.close(); raise
    except Exception as exc:
        db.rollback(); db.close(); print(f"ORDER_CREATE_ERROR: {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(500,"Não foi possível criar o pedido. Tente novamente.")
    db.close(); return {"order_id":oid,"status":"PENDING_SELLER"}

@app.get("/api/orders/{oid}")
def order_detail(oid:int,u=Depends(auth)):
    db=get_db(); o=order_access(db,oid,u["id"]); d=db.execute("SELECT d.*,v.plate,v.model,v.capacity_kg,tu.full_name transporter_name FROM deliveries d LEFT JOIN vehicles v ON v.id=d.vehicle_id LEFT JOIN users tu ON tu.id=d.transporter_id WHERE d.order_id=?",(oid,)).fetchone(); p=db.execute("SELECT p.*,u.full_name seller_name,pr.company_name,pr.farm_name FROM products p JOIN users u ON u.id=p.seller_id LEFT JOIN producers pr ON pr.user_id=u.id WHERE p.id=?",(o["product_id"],)).fetchone(); db.close(); return {"order":dict(o),"delivery":dict(d) if d else None,"product":dict(p) if p else None}

@app.post("/api/orders/{oid}/seller-review")
def review(oid:int,x:Review,u=Depends(role("seller"))):
    db=get_db(); o=db.execute("SELECT * FROM orders WHERE id=? AND seller_id=?",(oid,u["id"])).fetchone()
    if not o: db.close(); raise HTTPException(404,"Pedido não encontrado")
    if o["status"]!="PENDING_SELLER": db.close(); raise HTTPException(409,"Pedido já analisado")
    st="SELLER_ACCEPTED" if x.accepted else "SELLER_REJECTED"; db.execute("UPDATE orders SET status=? WHERE id=?",(st,oid)); notify(db,o["buyer_id"],"Pedido atualizado",f"Pedido #{oid}: {'aceite' if x.accepted else 'rejeitado'}."); audit(db,u["id"],"SELLER_REVIEW","orders",oid,{"accepted":x.accepted,"note":x.note}); db.commit(); db.close(); return {"status":st}

@app.post("/api/orders/{oid}/transport-choice")
def transport_choice(oid:int,x:TransportChoice,u=Depends(auth)):
    db=get_db(); o=order_access(db,oid,u["id"])
    if u["id"] not in (o["buyer_id"],o["seller_id"]): db.close(); raise HTTPException(403,"Apenas comprador ou vendedor")
    if o["status"]!="SELLER_ACCEPTED": db.close(); raise HTTPException(409,"O vendedor ainda não aceitou o pedido")
    if x.mode=="agrolink":
        db.execute("UPDATE orders SET transport_mode='agrolink',delivery_status='REQUESTED' WHERE id=?",(oid,)); db.execute("INSERT OR IGNORE INTO deliveries(order_id,status,destination) VALUES(?,?,?)",(oid,"REQUESTED",o["delivery_address"])); notify(db,o["seller_id"] if u["id"]==o["buyer_id"] else o["buyer_id"],"Transporte AgroLink",f"Pedido #{oid} aguarda seleção de transportador.")
    elif x.mode=="buyer":
        db.execute("UPDATE orders SET transport_mode='buyer',delivery_status='NOT_REQUIRED',delivery_distance_km=0,delivery_fee_kz=0,total_kz=product_total_kz WHERE id=?",(oid,)); db.execute("DELETE FROM deliveries WHERE order_id=?",(oid,))
    else:
        db.execute("UPDATE orders SET transport_mode='seller',delivery_status='SELLER_DELIVERY',delivery_distance_km=0,delivery_fee_kz=0,total_kz=product_total_kz WHERE id=?",(oid,)); db.execute("DELETE FROM deliveries WHERE order_id=?",(oid,))
    db.commit(); db.close(); return {"mode":x.mode}

@app.post("/api/orders/{oid}/delivery-quote")
def delivery_quote(oid:int,x:DeliveryQuote,u=Depends(auth)):
    db=get_db(); o=order_access(db,oid,u["id"])
    if o["transport_mode"] not in ("seller","agrolink"): db.close(); raise HTTPException(409,"Este pedido não usa transporte pago")
    fee=calc_fee(x.distance_km); total=recalc_total(db,oid,x.distance_km,fee); db.execute("UPDATE orders SET delivery_address=? WHERE id=?",(x.destination or o["delivery_address"],oid))
    if o["transport_mode"]=="agrolink": db.execute("UPDATE deliveries SET origin=?,destination=?,distance_km=?,eta_minutes=? WHERE order_id=?",(x.origin,x.destination or o["delivery_address"],x.distance_km,round(x.distance_km/40*60),oid))
    db.commit(); db.close(); return {"distance_km":x.distance_km,"delivery_fee_kz":fee,"product_total_kz":o["product_total_kz"],"total_kz":total}

@app.get("/api/transporters/available")
def available_transporters(u=Depends(auth)):
    if u["role"] not in ("buyer","seller","admin","transport_company","private_transporter","transporter"): raise HTTPException(403,"Sem acesso")
    db=get_db(); rows=[dict(x) for x in db.execute("""SELECT u.id transporter_id,u.full_name,v.id vehicle_id,v.plate,v.model,v.capacity_kg,v.vehicle_type,v.photo,v.status,v.latitude,v.longitude,v.last_ping_at FROM users u JOIN vehicles v ON v.transporter_id=u.id WHERE u.role IN ('transport_company','private_transporter','transporter') AND u.status='active' AND v.status='FREE' ORDER BY u.full_name""").fetchall()]; db.close(); return rows

@app.post("/api/vehicles")
def save_vehicle(x:Vehicle,u=Depends(role("transport_company","private_transporter","transporter"))):
    db=get_db(); exists=db.execute("SELECT id FROM vehicles WHERE plate=?",(x.plate.strip().upper(),)).fetchone()
    if exists: db.close(); raise HTTPException(409,"Matrícula já registada")
    company_id=None; driver_id=x.driver_id
    if u["role"]=="transport_company":
        company_id=db.execute("SELECT id FROM transport_companies WHERE user_id=?",(u["id"],)).fetchone()
        company_id=company_id["id"] if company_id else None
        if driver_id is not None and not db.execute("SELECT id FROM drivers WHERE id=? AND company_user_id=? AND status='active'",(driver_id,u["id"])).fetchone():
            db.close(); raise HTTPException(400,"Motorista inválido para esta empresa")
    c=db.execute("INSERT INTO vehicles(transporter_id,company_id,driver_id,plate,model,capacity_kg,vehicle_type,photo,status) VALUES(?,?,?,?,?,?,?,?,?)",(u["id"],company_id,driver_id,x.plate.strip().upper(),x.model,x.capacity_kg,x.vehicle_type,x.photo,"FREE")); audit(db,u["id"],"VEHICLE_CREATED","vehicles",c.lastrowid); db.commit(); db.close(); return {"id":c.lastrowid}

@app.get("/api/vehicles/mine")
def my_vehicles(u=Depends(role("transport_company","private_transporter","transporter"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT * FROM vehicles WHERE transporter_id=? ORDER BY id DESC",(u["id"],)).fetchall()]; db.close(); return rows

@app.post("/api/orders/{oid}/assign-transporter")
def assign_transporter(oid:int,x:AssignTransporter,u=Depends(auth)):
    db=get_db(); o=order_access(db,oid,u["id"])
    if u["id"] not in (o["buyer_id"],o["seller_id"]): db.close(); raise HTTPException(403,"Sem acesso")
    if o["transport_mode"]!="agrolink": db.close(); raise HTTPException(409,"Transporte AgroLink não foi escolhido")
    v=db.execute("SELECT * FROM vehicles WHERE transporter_id=? AND status='FREE' AND id=COALESCE(?,id) ORDER BY id DESC LIMIT 1",(x.transporter_id,x.vehicle_id)).fetchone()
    if not v: db.close(); raise HTTPException(409,"Transportador/veículo indisponível")
    code=delivery_code(); existing=db.execute("SELECT id FROM deliveries WHERE order_id=?",(oid,)).fetchone()
    if existing: db.execute("UPDATE deliveries SET transporter_id=?,vehicle_id=?,origin=?,destination=?,status='REQUESTED' WHERE order_id=?",(x.transporter_id,v["id"],x.origin,o["delivery_address"],oid)); did=existing["id"]
    else: did=db.execute("INSERT INTO deliveries(order_id,transporter_id,vehicle_id,origin,destination,status) VALUES(?,?,?,?,?,?)",(oid,x.transporter_id,v["id"],x.origin,o["delivery_address"],"REQUESTED")).lastrowid
    db.execute("UPDATE orders SET delivery_status='REQUESTED',delivery_code_hash=? WHERE id=?",(delivery_hash(code),oid)); db.execute("UPDATE vehicles SET status='RESERVED' WHERE id=?",(v["id"],)); notify(db,x.transporter_id,"Nova solicitação de transporte",f"Pedido #{oid}. Aceite ou rejeite no AgroLink."); audit(db,u["id"],"TRANSPORT_REQUESTED","deliveries",did,{"transporter_id":x.transporter_id}); db.commit(); db.close()
    # The delivery code is returned only to the buyer/seller who initiated the assignment; transporter never receives it.
    return {"delivery_id":did,"status":"REQUESTED","delivery_code_for_buyer":"%s"%code}

@app.post("/api/deliveries/{did}/accept")
def accept_delivery(did:int,u=Depends(role("transport_company","private_transporter","transporter"))):
    db=get_db(); d=db.execute("SELECT * FROM deliveries WHERE id=? AND transporter_id=?",(did,u["id"])).fetchone()
    if not d: db.close(); raise HTTPException(404,"Solicitação não encontrada")
    if d["status"]!="REQUESTED": db.close(); raise HTTPException(409,"Solicitação já processada")
    db.execute("UPDATE deliveries SET status='ACCEPTED' WHERE id=?",(did,)); db.execute("UPDATE orders SET delivery_status='ACCEPTED' WHERE id=?",(d["order_id"],)); notify(db,(db.execute("SELECT buyer_id FROM orders WHERE id=?",(d["order_id"],)).fetchone())["buyer_id"],"Transporte aceite",f"O transportador aceitou o pedido #{d['order_id']}."); db.commit(); db.close(); return {"status":"ACCEPTED"}

@app.post("/api/deliveries/{did}/reject")
def reject_delivery(did:int,u=Depends(role("transport_company","private_transporter","transporter"))):
    db=get_db(); d=db.execute("SELECT * FROM deliveries WHERE id=? AND transporter_id=?",(did,u["id"])).fetchone()
    if not d: db.close(); raise HTTPException(404,"Solicitação não encontrada")
    db.execute("UPDATE deliveries SET status='REJECTED' WHERE id=?",(did,)); db.execute("UPDATE orders SET delivery_status='REJECTED' WHERE id=?",(d["order_id"],)); db.execute("UPDATE vehicles SET status='FREE' WHERE id=?",(d["vehicle_id"],)); db.commit(); db.close(); return {"status":"REJECTED"}

@app.post("/api/deliveries/{did}/status")
def delivery_status(did:int,status:str,u=Depends(role("transport_company","private_transporter","transporter"))):
    allowed={"ARRIVED_PICKUP","CARGO_COLLECTED","IN_TRANSIT","ARRIVED_DESTINATION"}
    if status not in allowed: raise HTTPException(400,"Estado inválido")
    db=get_db(); d=db.execute("SELECT * FROM deliveries WHERE id=? AND transporter_id=?",(did,u["id"])).fetchone()
    if not d: db.close(); raise HTTPException(404,"Entrega não encontrada")
    db.execute("UPDATE deliveries SET status=? WHERE id=?",(status,did)); db.execute("UPDATE orders SET delivery_status=? WHERE id=?",(status,d["order_id"])); db.commit(); db.close(); return {"status":status}

@app.post("/api/deliveries/{did}/confirm")
def confirm_delivery(did:int,x:Code,u=Depends(role("buyer"))):
    db=get_db(); d=db.execute("SELECT * FROM deliveries WHERE id=?",(did,)).fetchone()
    if not d: db.close(); raise HTTPException(404,"Entrega não encontrada")
    o=db.execute("SELECT * FROM orders WHERE id=? AND buyer_id=?",(d["order_id"],u["id"])).fetchone()
    if not o: db.close(); raise HTTPException(403,"Sem acesso")
    if not o["delivery_code_hash"] or o["delivery_code_hash"]!=delivery_hash(x.code): db.close(); raise HTTPException(400,"Código inválido")
    db.execute("UPDATE deliveries SET status='DELIVERED',delivered_at=CURRENT_TIMESTAMP WHERE id=?",(did,)); db.execute("UPDATE vehicles SET status='FREE' WHERE id=?",(d["vehicle_id"],)); db.execute("UPDATE orders SET delivery_status='DELIVERED',status='DELIVERED',payment_status=CASE WHEN payment_status='PAID' THEN 'READY_FOR_SETTLEMENT' ELSE payment_status END WHERE id=?",(o["id"],)); notify(db,d["transporter_id"],"Entrega confirmada",f"O pedido #{o['id']} foi confirmado pelo comprador."); audit(db,u["id"],"DELIVERY_CONFIRMED","deliveries",did); db.commit(); db.close(); return {"status":"DELIVERED"}

@app.post("/api/deliveries/{did}/location")
def location(did:int,x:Location,u=Depends(role("transport_company","private_transporter","transporter"))):
    db=get_db(); d=db.execute("SELECT * FROM deliveries WHERE id=? AND transporter_id=?",(did,u["id"])).fetchone()
    if not d: db.close(); raise HTTPException(403,"Sem acesso")
    db.execute("INSERT INTO location_pings(delivery_id,latitude,longitude,speed,heading,captured_at) VALUES(?,?,?,?,?,?)",(did,x.latitude,x.longitude,x.speed,x.heading,x.captured_at)); db.execute("UPDATE vehicles SET latitude=?,longitude=?,last_ping_at=? WHERE id=?",(x.latitude,x.longitude,x.captured_at,d["vehicle_id"])); db.commit(); db.close(); return {"ok":True}

@app.get("/api/orders/{oid}/location")
def latest_location(oid:int,u=Depends(auth)):
    db=get_db(); o=order_access(db,oid,u["id"]); d=db.execute("SELECT id FROM deliveries WHERE order_id=?",(oid,)).fetchone()
    if not d: db.close(); return None
    p=db.execute("SELECT * FROM location_pings WHERE delivery_id=? ORDER BY id DESC LIMIT 1",(d["id"],)).fetchone(); db.close(); return dict(p) if p else None

@app.post("/api/orders/{oid}/payment")
def payment(oid:int,x:Payment,u=Depends(role("buyer"))):
    db=get_db(); o=db.execute("SELECT * FROM orders WHERE id=? AND buyer_id=?",(oid,u["id"])).fetchone()
    if not o: db.close(); raise HTTPException(404,"Pedido não encontrado")
    if o["status"]!="SELLER_ACCEPTED": db.close(); raise HTTPException(409,"O vendedor ainda não aceitou o pedido")
    if o["transport_mode"]=="pending": db.close(); raise HTTPException(409,"Defina a modalidade de entrega antes do pagamento")
    if round(x.amount_kz,2)!=round(o["total_kz"],2): db.close(); raise HTTPException(400,"Valor incorreto")
    if db.execute("SELECT id FROM payments WHERE idempotency_key=?",(x.idempotency_key,)).fetchone(): db.close(); raise HTTPException(409,"Pagamento duplicado")
    c=db.execute("INSERT INTO payments(order_id,method,transaction_id,reference,amount_kz,status,idempotency_key) VALUES(?,?,?,?,?,?,?)",(oid,x.method,x.transaction_id,x.reference,x.amount_kz,"PENDING",x.idempotency_key)); db.execute("UPDATE orders SET payment_status='PENDING' WHERE id=?",(oid,)); audit(db,u["id"],"PAYMENT_SUBMITTED","payments",c.lastrowid,{"method":x.method}); db.commit(); r=dict(db.execute("SELECT * FROM payments WHERE id=?",(c.lastrowid,)).fetchone()); db.close(); return r

@app.post("/api/payments/{pid}/webhook")
def webhook(pid:int,payload:dict, x_agrolink_webhook: str = Header(default="")):
    if not x_agrolink_webhook or not SECRET_KEY or not hmac.compare_digest(x_agrolink_webhook, SECRET_KEY):
        raise HTTPException(401,"Webhook não autorizado")
    # MVP placeholder: production PSP webhook must validate provider signature, amount, reference and event id before confirming.
    db=get_db(); p=db.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone()
    if not p: db.close(); raise HTTPException(404,"Pagamento não encontrado")
    st=payload.get("status")
    if st not in ("CONFIRMED","FAILED","EXPIRED","CANCELLED"): db.close(); raise HTTPException(400,"Estado inválido")
    if "amount_kz" in payload and round(float(payload["amount_kz"]),2)!=round(p["amount_kz"],2): db.close(); raise HTTPException(400,"Valor do gateway não corresponde")
    ph=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(); db.execute("UPDATE payments SET status=?,provider_payload_hash=? WHERE id=?",(st,ph,pid)); db.execute("UPDATE orders SET payment_status=? WHERE id=?",("PAID" if st=="CONFIRMED" else "PAYMENT_FAILED",p["order_id"])); db.commit(); db.close(); return {"ok":True}

@app.get("/api/orders/{oid}/chat")
def chat_list(oid:int,u=Depends(auth)):
    db=get_db(); order_access(db,oid,u["id"]); c=db.execute("SELECT id FROM conversations WHERE order_id=?",(oid,)).fetchone();
    rows=[] if not c else [dict(x) for x in db.execute("SELECT m.*,u.full_name sender_name FROM chat_messages m JOIN users u ON u.id=m.sender_id WHERE conversation_id=? ORDER BY m.id",(c["id"],)).fetchall()]; db.close(); return rows
@app.post("/api/orders/{oid}/chat")
def chat_send(oid:int,x:Chat,u=Depends(auth)):
    db=get_db(); order_access(db,oid,u["id"]); c=db.execute("SELECT id FROM conversations WHERE order_id=?",(oid,)).fetchone(); cid=c["id"] if c else db.execute("INSERT INTO conversations(order_id) VALUES(?)",(oid,)).lastrowid; mid=db.execute("INSERT INTO chat_messages(conversation_id,sender_id,body) VALUES(?,?,?)",(cid,u["id"],x.body)).lastrowid
    o=db.execute("SELECT buyer_id,seller_id FROM orders WHERE id=?",(oid,)).fetchone(); recipients={o["buyer_id"],o["seller_id"]}; d=db.execute("SELECT transporter_id FROM deliveries WHERE order_id=?",(oid,)).fetchone();
    if d and d["transporter_id"]: recipients.add(d["transporter_id"])
    for rid in recipients-{u["id"]}: notify(db,rid,"Nova mensagem",f"Nova mensagem no pedido #{oid}.")
    db.commit(); db.close(); return {"message_id":mid}

@app.get("/api/notifications")
def notifications(u=Depends(auth)):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100",(u["id"],)).fetchall()]; db.close(); return rows
@app.post("/api/notifications/{nid}/read")
def notification_read(nid:int,u=Depends(auth)):
    db=get_db(); db.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",(nid,u["id"])); db.commit(); db.close(); return {"ok":True}

@app.post("/api/sync")
def sync(x:Offline,u=Depends(auth)):
    db=get_db(); c=db.execute("INSERT INTO sync_queue(user_id,device_id,event_type,payload) VALUES(?,?,?,?)",(u["id"],x.device_id,x.event_type,json.dumps(x.payload,ensure_ascii=False))); db.commit(); db.close(); return {"queued_event_id":c.lastrowid}

@app.get("/api/transport/company")
def transport_company(u=Depends(role("transport_company"))):
    db=get_db(); c=db.execute("SELECT * FROM transport_companies WHERE user_id=?",(u["id"],)).fetchone(); db.close(); return dict(c) if c else None

@app.post("/api/transport/company/drivers")
def create_driver(x:DriverCreate,u=Depends(role("transport_company"))):
    db=get_db();
    if x.phone:
        ph=normalize_phone(x.phone)
        if len(ph)!=9 or not ph.startswith("9"): db.close(); raise HTTPException(422,"Telefone angolano inválido")
    c=db.execute("INSERT INTO drivers(company_user_id,full_name,phone,bi_number_encrypted,bi_blind_hash,license_number_encrypted,photo) VALUES(?,?,?,?,?,?,?)",(u["id"],x.full_name.strip(),ph if x.phone else None,encrypt_sensitive(x.bi_number),blind_hash(x.bi_number),encrypt_sensitive(x.license_number) if x.license_number else None,x.photo)); audit(db,u["id"],"DRIVER_CREATED","drivers",c.lastrowid); db.commit(); db.close(); return {"id":c.lastrowid,"full_name":x.full_name,"status":"active"}

@app.get("/api/transport/company/drivers")
def company_drivers(u=Depends(role("transport_company"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT id,full_name,phone,photo,status,created_at FROM drivers WHERE company_user_id=? ORDER BY id DESC",(u["id"],)).fetchall()]; db.close(); return rows

@app.get("/api/transport/company/drivers/{driver_id}/documents")
def driver_documents(driver_id:int,u=Depends(role("transport_company","admin"))):
    db=get_db(); d=db.execute("SELECT * FROM drivers WHERE id=?",(driver_id,)).fetchone();
    if not d: db.close(); raise HTTPException(404,"Motorista não encontrado")
    if u["role"]=="transport_company" and d["company_user_id"]!=u["id"]: db.close(); raise HTTPException(403,"Sem acesso")
    audit(db,u["id"],"DRIVER_DOCUMENTS_ACCESSED","drivers",driver_id); db.commit(); db.close(); return {"id":d["id"],"full_name":d["full_name"],"bi_number":decrypt_sensitive(d["bi_number_encrypted"]),"license_number":decrypt_sensitive(d["license_number_encrypted"])}

@app.get("/api/admin/dashboard")
def dashboard(u=Depends(role("admin"))):
    db=get_db(); out={}
    for k,t in [("users","users"),("producers","producers"),("transporters","users"),("vehicles","vehicles"),("products","products"),("orders","orders"),("payments","payments"),("commissions","commissions"),("notifications","notifications")]:
        where="role IN ('transport_company','private_transporter','transporter')" if k=="transporters" else "1=1"; out[k]=db.execute(f"SELECT COUNT(*) c FROM {t} WHERE {where}").fetchone()["c"]
    out["sales_this_month"]=db.execute("SELECT COALESCE(SUM(product_total_kz),0) v FROM orders WHERE status='DELIVERED' AND created_at>=date('now','start of month')").fetchone()["v"]
    out["active_transports"]=db.execute("SELECT COUNT(*) c FROM deliveries WHERE status IN ('REQUESTED','ACCEPTED','ARRIVED_PICKUP','CARGO_COLLECTED','IN_TRANSIT','ARRIVED_DESTINATION')").fetchone()["c"]
    db.close(); return out
@app.get("/api/admin/users")
def admin_users(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT id,full_name,phone,role,province,address,status,created_at FROM users ORDER BY id DESC").fetchall()]; db.close(); return rows
@app.get("/api/admin/users/{user_id}/bi")
def admin_user_bi(user_id:int,u=Depends(role("admin"))):
    db=get_db(); target=db.execute("SELECT id,full_name,phone,role,bi_number_encrypted FROM users WHERE id=?",(user_id,)).fetchone()
    if not target: db.close(); raise HTTPException(404,"Utilizador não encontrado")
    value=decrypt_sensitive(target["bi_number_encrypted"])
    audit(db,u["id"],"USER_BI_ACCESSED","users",user_id)
    db.commit(); db.close(); return {"id":target["id"],"full_name":target["full_name"],"phone":target["phone"],"role":target["role"],"bi_number":value}

@app.get("/api/admin/orders")
def admin_orders(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT o.*,b.full_name buyer_name,s.full_name seller_name,p.name product_name FROM orders o JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id JOIN products p ON p.id=o.product_id ORDER BY o.id DESC").fetchall()]; db.close(); return rows
@app.get("/api/admin/payments")
def admin_payments(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT p.*,o.buyer_id,o.seller_id FROM payments p JOIN orders o ON o.id=p.order_id ORDER BY p.id DESC").fetchall()]; db.close(); return rows
@app.get("/api/admin/commissions")
def admin_commissions(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT * FROM commissions ORDER BY id DESC").fetchall()]; db.close(); return rows
@app.get("/api/admin/producers")
def admin_producers(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT p.*,u.full_name,u.phone FROM producers p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC").fetchall()]; db.close(); return rows
@app.get("/api/admin/transporters")
def admin_transporters(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT u.id,u.full_name,u.phone,u.province,u.status,u.role,v.id vehicle_id,v.plate,v.model,v.capacity_kg,v.status vehicle_status FROM users u LEFT JOIN vehicles v ON v.transporter_id=u.id WHERE u.role IN ('transport_company','private_transporter','transporter') ORDER BY u.id DESC").fetchall()]; db.close(); return rows
@app.get("/api/admin/vehicles")
def admin_vehicles(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT v.*,u.full_name transporter_name FROM vehicles v JOIN users u ON u.id=v.transporter_id ORDER BY v.id DESC").fetchall()]; db.close(); return rows
@app.get("/api/admin/products")
def admin_products(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT p.*,u.full_name seller_name,c.name category_name FROM products p JOIN users u ON u.id=p.seller_id LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.id DESC").fetchall()]; db.close(); return rows
@app.post("/api/admin/orders/{oid}/release")
def release(oid:int,u=Depends(role("admin"))):
    db=get_db(); o=db.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
    if not o: db.close(); raise HTTPException(404,"Pedido não encontrado")
    if o["delivery_status"]!="DELIVERED" or o["payment_status"] not in ("PAID","READY_FOR_SETTLEMENT"): db.close(); raise HTTPException(400,"Condições de liquidação não cumpridas")
    if db.execute("SELECT id FROM commissions WHERE order_id=?",(oid,)).fetchone(): db.close(); raise HTTPException(409,"Liquidação já processada")
    sc=round(o["product_total_kz"]*SELLER_COMMISSION_RATE,2); db.execute("INSERT INTO commissions(order_id,beneficiary_type,rate,base_amount_kz,commission_kz) VALUES(?,?,?,?,?)",(oid,"seller",SELLER_COMMISSION_RATE,o["product_total_kz"],sc)); tc=0
    if o["delivery_fee_kz"]>0: tc=round(o["delivery_fee_kz"]*TRANSPORTER_COMMISSION_RATE,2); db.execute("INSERT INTO commissions(order_id,beneficiary_type,rate,base_amount_kz,commission_kz) VALUES(?,?,?,?,?)",(oid,"transporter",TRANSPORTER_COMMISSION_RATE,o["delivery_fee_kz"],tc))
    db.execute("UPDATE orders SET payment_status='SETTLEMENT_RELEASED' WHERE id=?",(oid,)); audit(db,u["id"],"SETTLEMENT_RELEASED","orders",oid); db.commit(); db.close(); return {"status":"SETTLEMENT_RELEASED","seller_commission":sc,"transporter_commission":tc}

@app.websocket("/ws/chat/{oid}")
async def ws_chat(ws:WebSocket,oid:int):
    await ws.accept(); await ws.send_json({"type":"info","message":"Chat em tempo real disponível; mensagens também podem usar /api/orders/{id}/chat."})
    try:
        while True:
            msg=await ws.receive_text(); await ws.send_json({"type":"echo","message":msg})
    except WebSocketDisconnect: pass

@app.websocket("/ws/location/{oid}")
async def ws_location(ws:WebSocket,oid:int):
    await ws.accept(); await ws.send_json({"type":"info","message":"Canal de localização conectado."})
    try:
        while True:
            msg=await ws.receive_text(); await ws.send_text(msg)
    except WebSocketDisconnect: pass
