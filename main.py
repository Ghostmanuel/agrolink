import hashlib,hmac,json,secrets,os,urllib.request,urllib.parse,base64,uuid,math,mimetypes
from pathlib import Path
import jwt
from datetime import datetime,timezone,timedelta
from fastapi import FastAPI,HTTPException,Depends,Header,WebSocket,WebSocketDisconnect,Request
from fastapi.responses import HTMLResponse,FileResponse
from fastapi.middleware.cors import CORSMiddleware
from db import init_db,get_db
from schemas import *
from security import *
from config import *

app=FastAPI(title=APP_NAME,version=APP_VERSION)
TOKENS={}
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def issue_token(uid):
    now=datetime.now(timezone.utc)
    payload={"sub":str(uid),"iat":now,"exp":now+timedelta(minutes=JWT_EXPIRE_MINUTES)}
    return jwt.encode(payload,SECRET_KEY,algorithm=JWT_ALGORITHM)

def auth(authorization:str=Header(default="")):
    if not authorization.startswith("Bearer "): raise HTTPException(401,"Autenticação necessária")
    token=authorization[7:]
    try:
        payload=jwt.decode(token,SECRET_KEY,algorithms=[JWT_ALGORITHM])
        uid=int(payload.get("sub"))
    except (jwt.ExpiredSignatureError,jwt.InvalidTokenError,TypeError,ValueError):
        raise HTTPException(401,"Sessão inválida ou expirada")
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

def _route_url(coords):
    return f"{ROUTING_BASE_URL.rstrip('/')}/route/v1/driving/{coords[0][1]},{coords[0][0]};{coords[1][1]},{coords[1][0]}?overview=false&steps=false"

def geocode_address(address):
    if not address: return None
    try:
        q=urllib.parse.urlencode({"q":address+", Angola","format":"json","limit":1})
        req=urllib.request.Request(f"{GEOCODING_BASE_URL.rstrip('/')}/search?{q}",headers={"User-Agent":"EPYALINK/1.6"})
        with urllib.request.urlopen(req,timeout=8) as r: data=json.loads(r.read().decode())
        if data: return float(data[0]["lat"]),float(data[0]["lon"])
    except Exception:
        return None
    return None

def road_route(origin_lat,origin_lon,dest_lat,dest_lon):
    try:
        url=_route_url([(origin_lat,origin_lon),(dest_lat,dest_lon)])
        req=urllib.request.Request(url,headers={"User-Agent":"EPYALINK/1.6"})
        with urllib.request.urlopen(req,timeout=12) as r: data=json.loads(r.read().decode())
        route=(data.get("routes") or [None])[0]
        if route: return round(route["distance"]/1000,2),round(route["duration"]/60)
    except Exception:
        pass
    return None

def haversine_km(a_lat,a_lon,b_lat,b_lon):
    r=6371.0088; p1=math.radians(a_lat); p2=math.radians(b_lat); dp=math.radians(b_lat-a_lat); dl=math.radians(b_lon-a_lon)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2*r*math.asin(math.sqrt(h)),2)

def storage_root():
    root=Path(FILE_STORAGE_DIR); root.mkdir(parents=True,exist_ok=True); return root

def _validate_private_file(raw,filename,content_type):
    if len(raw)>MAX_UPLOAD_BYTES: raise HTTPException(413,"Ficheiro demasiado grande")
    allowed={"image/jpeg","image/png","image/webp","application/pdf"}
    if content_type not in allowed: raise HTTPException(415,"Tipo de ficheiro não permitido")

def store_private_file_db(db,raw,filename,content_type,owner_id,purpose,entity_id=None):
    """Grava o ficheiro usando a mesma ligação/transação já aberta pelo pedido."""
    _validate_private_file(raw,filename,content_type)
    ext=Path(filename).suffix.lower() or mimetypes.guess_extension(content_type) or ""
    fid=uuid.uuid4().hex; key=fid+ext
    (storage_root()/key).write_bytes(raw)
    db.execute("INSERT INTO stored_files(id,owner_id,entity_type,entity_id,filename,content_type,size_bytes,storage_key,private) VALUES(?,?,?,?,?,?,?,?,1)",(fid,owner_id,purpose,entity_id,Path(filename).name,content_type,len(raw),key))
    return fid

def store_private_file(raw,filename,content_type,owner_id,purpose,entity_id=None):
    db=get_db()
    try:
        fid=store_private_file_db(db,raw,filename,content_type,owner_id,purpose,entity_id)
        db.commit()
        return fid
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

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
def logo_legacy(): return FileResponse("LogoAgrolink.jpeg",media_type="image/jpeg",headers={"Cache-Control":"no-store"})

@app.get("/LogoEpyalink.png")
def logo_epyalink(): return FileResponse("LogoEpyalink.png",media_type="image/png",headers={"Cache-Control":"no-store"})

@app.get("/login-bg.jpg")
def login_bg(): return FileResponse("login-bg.jpg",media_type="image/jpeg",headers={"Cache-Control":"no-store"})

@app.get("/icon-192.png")
def icon_192(): return FileResponse("icon-192.png",media_type="image/png",headers={"Cache-Control":"no-store"})

@app.get("/icon-512.png")
def icon_512(): return FileResponse("icon-512.png",media_type="image/png",headers={"Cache-Control":"no-store"})

@app.get("/api/public-config")
def public_config():
    return {"turnstile_site_key": TURNSTILE_SITE_KEY}

@app.post("/api/auth/register")
def register(x:Register, request:Request):
    verify_turnstile(x.__dict__.get("turnstile_token"), request)
    db=get_db(); phone=normalize_phone(x.phone)
    if db.execute("SELECT id FROM users WHERE phone=?",(phone,)).fetchone():
        db.close(); raise HTTPException(409,"Telefone já registado")
    if not x.profile_photo_data_base64 and not x.profile_photo_file_id:
        db.close(); raise HTTPException(422,"Fotografia de perfil é obrigatória")
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
        if x.profile_photo_file_id:
            f=db.execute("SELECT id,owner_id FROM stored_files WHERE id=?",(x.profile_photo_file_id,)).fetchone()
            if not f or f["owner_id"]!=uid: raise HTTPException(400,"Fotografia de perfil inválida")
            db.execute("UPDATE users SET profile_photo=? WHERE id=?",(f"/api/files/{x.profile_photo_file_id}",uid))
            db.execute("UPDATE stored_files SET entity_type='profile',entity_id=? WHERE id=?",(uid,x.profile_photo_file_id))
        elif x.profile_photo_data_base64:
            try:
                raw=base64.b64decode(x.profile_photo_data_base64,validate=True)
            except Exception:
                raise HTTPException(400,"Fotografia de perfil inválida")
            if not x.profile_photo_content_type or x.profile_photo_content_type not in ("image/jpeg","image/png","image/webp"):
                raise HTTPException(415,"A fotografia deve ser JPG, PNG ou WebP")
            if not x.profile_photo_filename:
                raise HTTPException(400,"Nome da fotografia inválido")
            # Importante: usar a mesma ligação SQLite do cadastro.
            # Isto evita o erro de bloqueio que acontecia quando a fotografia
            # abria uma segunda ligação enquanto o INSERT do utilizador estava em transação.
            fid=store_private_file_db(db,raw,x.profile_photo_filename or "perfil.jpg",x.profile_photo_content_type,uid,"profile",uid)
            db.execute("UPDATE users SET profile_photo=? WHERE id=?",(f"/api/files/{fid}",uid))
        audit(db,uid,"USER_REGISTERED","users",uid,{"role":x.role}); db.commit()
    except HTTPException:
        db.rollback(); db.close(); raise
    except Exception:
        db.rollback(); db.close(); raise HTTPException(500,"Não foi possível concluir o cadastro. Verifique os dados e tente novamente.")
    db.close(); return {"ok":True,"user_id":uid}

@app.post("/api/auth/login")
def login(x:Login, request:Request):
    verify_turnstile(x.turnstile_token, request)
    db=get_db(); u=db.execute("SELECT * FROM users WHERE phone=?",(normalize_phone(x.phone),)).fetchone(); db.close()
    if not u or not verify_password(x.password,u["password_hash"]): raise HTTPException(401,"Telefone ou palavra-passe inválidos")
    if u["status"]!="active": raise HTTPException(403,"Conta suspensa")
    t=issue_token(u["id"])
    return {"access_token":t,"token_type":"bearer","role":u["role"],"full_name":u["full_name"],"expires_in":JWT_EXPIRE_MINUTES*60}

@app.post("/api/auth/logout")
def logout(u=Depends(auth)):
    # JWT is stateless; logout is handled client-side by discarding the token.
    return {"ok":True,"message":"Sessão encerrada neste dispositivo."}

@app.post("/api/files/upload")
def upload_file(x:FileUpload,u=Depends(auth)):
    try: raw=base64.b64decode(x.data_base64,validate=True)
    except Exception: raise HTTPException(400,"Ficheiro inválido")
    fid=store_private_file(raw,x.filename,x.content_type,u["id"],x.purpose,x.entity_id)
    audit_db=get_db(); audit(audit_db,u["id"],"FILE_UPLOADED","stored_files",None,{"file_id":fid,"purpose":x.purpose}); audit_db.commit(); audit_db.close()
    return {"file_id":fid,"url":f"/api/files/{fid}","private":True}

@app.get("/api/files/{file_id}")
def get_private_file(file_id:str,u=Depends(auth)):
    db=get_db(); f=db.execute("SELECT * FROM stored_files WHERE id=?",(file_id,)).fetchone()
    if not f: db.close(); raise HTTPException(404,"Ficheiro não encontrado")
    allowed=(f["owner_id"]==u["id"] or u["role"]=="admin")
    if not allowed and f["entity_type"]=="driver":
        allowed=bool(db.execute("SELECT 1 FROM drivers WHERE id=? AND company_user_id=?",(f["entity_id"],u["id"])).fetchone())
    if not allowed: db.close(); raise HTTPException(403,"Sem acesso ao ficheiro")
    path=storage_root()/f["storage_key"]; db.close()
    if not path.exists(): raise HTTPException(404,"Ficheiro não disponível")
    return FileResponse(path,media_type=f["content_type"],filename=f["filename"],headers={"Cache-Control":"private, no-store"})

def _kamba_phone(phone):
    return "+244" + normalize_phone(phone)

def _kamba_request(path, payload, api_key=None, timeout=10):
    headers={"Content-Type":"application/json"}
    if api_key:
        headers["X-API-Key"]=api_key
    req=urllib.request.Request(f"{KAMBASMS_BASE_URL}{path}",data=json.dumps(payload).encode(),headers=headers,method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except Exception as exc:
        raise HTTPException(503,"Não foi possível contactar o serviço de SMS. Tente novamente mais tarde.") from exc

def _send_password_otp(phone, code=None):
    provider=(PASSWORD_RESET_SMS_PROVIDER or "").lower()
    if provider=="kambasms" and KAMBASMS_API_KEY:
        result=_kamba_request("/otp/send", {"phone":_kamba_phone(phone)}, KAMBASMS_API_KEY)
        if result.get("success") is not True:
            raise HTTPException(503,"Não foi possível enviar o código por SMS. Tente novamente.")
        return "kambasms", int(result.get("expires_in") or PASSWORD_RESET_TTL_MINUTES*60)
    if PASSWORD_RESET_DEMO:
        return "local", PASSWORD_RESET_TTL_MINUTES*60
    raise HTTPException(503,"Recuperação por SMS ainda não está configurada no servidor.")

def _verify_password_otp(provider, phone, code, token_hash):
    if provider=="kambasms":
        # A KambaSMS /otp/verify é público segundo a documentação oficial;
        # não enviamos a API key do servidor nesta chamada.
        result=_kamba_request("/otp/verify", {"phone":_kamba_phone(phone),"code":code})
        return bool(result.get("success"))
    return hmac.compare_digest(token_hash,reset_token_hash(code))

@app.post("/api/auth/forgot-password")
def forgot_password(x:ForgotPassword, request:Request):
    verify_turnstile(x.turnstile_token, request)
    phone=normalize_phone(x.phone); db=get_db(); u=db.execute("SELECT id FROM users WHERE phone=? AND status='active'",(phone,)).fetchone()
    message="Se o número estiver registado, um código de recuperação foi enviado."
    if not u:
        db.close(); return {"ok":True,"message":message}
    # Local anti-abuse: max N successful/reset-code requests per hour and one every 60s.
    recent=db.execute("SELECT COUNT(*) c FROM password_reset_tokens WHERE user_id=? AND created_at>=datetime('now','-1 hour')",(u["id"],)).fetchone()["c"]
    last=db.execute("SELECT created_at FROM password_reset_tokens WHERE user_id=? ORDER BY id DESC LIMIT 1",(u["id"],)).fetchone()
    if recent>=PASSWORD_RESET_RATE_LIMIT_PER_HOUR:
        db.close(); raise HTTPException(429,"Foram solicitados demasiados códigos. Tente novamente mais tarde.")
    if last:
        try:
            last_dt=datetime.fromisoformat(last["created_at"].replace("Z","+00:00")).replace(tzinfo=timezone.utc) if "+" not in last["created_at"] else datetime.fromisoformat(last["created_at"])
            if (datetime.now(timezone.utc)-last_dt).total_seconds()<60:
                db.close(); raise HTTPException(429,"Aguarde um minuto antes de solicitar outro código.")
        except HTTPException: raise
        except Exception: pass
    provider, ttl=_send_password_otp(phone)
    # KambaSMS informa a validade real no response (normalmente 300s).
    # Nunca deixamos o token local viver mais tempo do que o OTP do provedor.
    ttl=max(60, min(int(ttl), PASSWORD_RESET_TTL_MINUTES*60))
    code=reset_code() if provider=="local" else "KAMBA_PROVIDER"
    expires=(datetime.now(timezone.utc)+timedelta(seconds=ttl)).isoformat()
    db.execute("UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND used_at IS NULL",(u["id"],))
    db.execute("INSERT INTO password_reset_tokens(user_id,token_hash,expires_at,attempts,provider) VALUES(?,?,?,?,?)",(u["id"],reset_token_hash(code),expires,0,provider))
    db.commit(); db.close()
    out={"ok":True,"message":message}
    if provider=="local" and PASSWORD_RESET_DEMO: out["demo_code"]=code
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
    provider=token["provider"] if "provider" in token.keys() else "local"
    if provider not in ("local","kambasms"):
        db.close(); raise HTTPException(400,"Código inválido")
    if not _verify_password_otp(provider, phone, x.code, token["token_hash"]):
        db.execute("UPDATE password_reset_tokens SET attempts=attempts+1 WHERE id=?",(token["id"],)); db.commit(); db.close(); raise HTTPException(400,"Código inválido")
    db.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(x.new_password),u["id"]))
    db.execute("UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE id=?",(token["id"],))
    db.execute("UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND used_at IS NULL AND id<>?",(u["id"],token["id"]))
    audit(db,u["id"],"PASSWORD_RESET","users",u["id"])
    db.commit(); db.close()
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
def products(q:str="",category_id:int|None=None,province:str="",min_price:float|None=None,max_price:float|None=None,unit:str="",available_only:bool=True):
    db=get_db(); sql="""SELECT p.*,u.full_name seller_name,pr.company_name,pr.farm_name,c.name category_name FROM products p JOIN users u ON u.id=p.seller_id LEFT JOIN producers pr ON pr.user_id=u.id LEFT JOIN categories c ON c.id=p.category_id WHERE p.active=1"""; args=[]
    if q: sql+=" AND (p.name LIKE ? OR p.description LIKE ? OR pr.company_name LIKE ? OR pr.farm_name LIKE ? OR p.location LIKE ?)"; args += [f"%{q}%"]*5
    if category_id: sql+=" AND p.category_id=?"; args.append(category_id)
    if province: sql+=" AND (p.location LIKE ? OR u.province LIKE ? OR pr.province LIKE ?)"; args += [f"%{province}%"]*3
    if min_price is not None: sql+=" AND p.price_kz>=?"; args.append(min_price)
    if max_price is not None: sql+=" AND p.price_kz<=?"; args.append(max_price)
    if unit: sql+=" AND p.unit=?"; args.append(unit)
    if available_only: sql+=" AND p.quantity>0"
    sql+=" ORDER BY p.created_at DESC"; rows=[dict(x) for x in db.execute(sql,args).fetchall()]; db.close(); return rows

@app.post("/api/products")
def create_product(x:Product,u=Depends(role("seller"))):
    db=get_db();
    if x.category_id and not db.execute("SELECT id FROM categories WHERE id=?",(x.category_id,)).fetchone(): db.close(); raise HTTPException(400,"Categoria inválida")
    c=db.execute("INSERT INTO products(seller_id,category_id,name,description,price_kz,quantity,unit,photo,location) VALUES(?,?,?,?,?,?,?,?,?)",(u["id"],x.category_id,x.name.strip(),x.description.strip(),x.price_kz,x.quantity,x.unit,x.photo,x.location.strip())); audit(db,u["id"],"PRODUCT_CREATED","products",c.lastrowid); db.commit(); db.close(); return {"id":c.lastrowid}


@app.post("/api/products/{pid}/photo")
def product_photo(pid:int,file_id:str,u=Depends(auth)):
    db=get_db(); pr=db.execute("SELECT id,seller_id FROM products WHERE id=?",(pid,)).fetchone()
    f=db.execute("SELECT id,owner_id FROM stored_files WHERE id=?",(file_id,)).fetchone()
    if not pr or pr["seller_id"]!=u["id"]: db.close(); raise HTTPException(403,"Sem acesso ao produto")
    if not f or f["owner_id"]!=u["id"]: db.close(); raise HTTPException(403,"Ficheiro inválido")
    db.execute("UPDATE stored_files SET entity_type='product',entity_id=? WHERE id=?",(pid,file_id)); db.execute("UPDATE products SET photo=? WHERE id=?",(f"/api/products/{pid}/photo",pid)); audit(db,u["id"],"PRODUCT_PHOTO_ATTACHED","products",pid); db.commit(); db.close(); return {"url":f"/api/products/{pid}/photo"}

@app.get("/api/products/{pid}/photo")
def product_photo_get(pid:int):
    db=get_db(); f=db.execute("SELECT sf.* FROM stored_files sf JOIN products p ON p.photo=? WHERE sf.entity_type='product' AND sf.entity_id=? ORDER BY sf.created_at DESC LIMIT 1",(f"/api/products/{pid}/photo",pid)).fetchone(); db.close()
    if not f: raise HTTPException(404,"Fotografia não encontrada")
    path=storage_root()/f["storage_key"]
    if not path.exists(): raise HTTPException(404,"Fotografia não disponível")
    return FileResponse(path,media_type=f["content_type"],headers={"Cache-Control":"public, max-age=3600"})

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
        stock_update=db.execute("UPDATE products SET quantity=quantity-? WHERE id=? AND quantity>=?",(x.quantity,p["id"],x.quantity))
        if stock_update.rowcount < 1: raise HTTPException(409,"Quantidade deixou de estar disponível")
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
    st="SELLER_ACCEPTED" if x.accepted else "SELLER_REJECTED";
    if not x.accepted: db.execute("UPDATE products SET quantity=quantity+(SELECT quantity FROM orders WHERE id=?) WHERE id=(SELECT product_id FROM orders WHERE id=?)",(oid,oid))
    db.execute("UPDATE orders SET status=? WHERE id=?",(st,oid)); notify(db,o["buyer_id"],"Pedido atualizado",f"Pedido #{oid}: {'aceite' if x.accepted else 'rejeitado'}."); audit(db,u["id"],"SELLER_REVIEW","orders",oid,{"accepted":x.accepted,"note":x.note}); db.commit(); db.close(); return {"status":st}

@app.post("/api/orders/{oid}/transport-choice")
def transport_choice(oid:int,x:TransportChoice,u=Depends(auth)):
    db=get_db(); o=order_access(db,oid,u["id"])
    if u["id"] not in (o["buyer_id"],o["seller_id"]): db.close(); raise HTTPException(403,"Apenas comprador ou vendedor")
    if o["status"]!="SELLER_ACCEPTED": db.close(); raise HTTPException(409,"O vendedor ainda não aceitou o pedido")
    if x.mode in ("epyalink","agrolink"):
        db.execute("UPDATE orders SET transport_mode='epyalink',delivery_status='REQUESTED' WHERE id=?",(oid,)); db.execute("INSERT OR IGNORE INTO deliveries(order_id,status,destination) VALUES(?,?,?)",(oid,"REQUESTED",o["delivery_address"])); notify(db,o["seller_id"] if u["id"]==o["buyer_id"] else o["buyer_id"],"Transporte EPYALINK",f"Pedido #{oid} aguarda seleção de transportador.")
    elif x.mode=="buyer":
        db.execute("UPDATE orders SET transport_mode='buyer',delivery_status='NOT_REQUIRED',delivery_distance_km=0,delivery_fee_kz=0,total_kz=product_total_kz WHERE id=?",(oid,)); db.execute("DELETE FROM deliveries WHERE order_id=?",(oid,))
    else:
        # Seller delivery: the seller defines the fee; EPYALINK only records/displays it.
        if x.seller_delivery_fee_kz is None:
            db.close(); raise HTTPException(422,"Informe o preço de entrega definido pelo vendedor")
        fee=round(float(x.seller_delivery_fee_kz),2)
        total=round(o["product_total_kz"]+fee,2)
        db.execute("UPDATE orders SET transport_mode='seller',delivery_status='SELLER_DELIVERY',delivery_distance_km=0,delivery_fee_kz=?,total_kz=? WHERE id=?",(fee,total,oid)); db.execute("DELETE FROM deliveries WHERE order_id=?",(oid,))
    db.commit(); db.close(); return {"mode":x.mode}

@app.post("/api/orders/{oid}/delivery-quote")
def delivery_quote(oid:int,x:DeliveryQuote,u=Depends(auth)):
    db=get_db(); o=order_access(db,oid,u["id"])
    if o["transport_mode"] not in ("epyalink","agrolink"): db.close(); raise HTTPException(409,"A cotação EPYALINK só existe quando o comprador escolhe um transportador EPYALINK")
    origin_text=x.origin
    if not origin_text:
        origin_row=db.execute("SELECT COALESCE(NULLIF(p.location,''),NULLIF(pr.location,''),u.address) AS origin FROM products p JOIN users u ON u.id=p.seller_id LEFT JOIN producers pr ON pr.user_id=u.id WHERE p.id=?",(o["product_id"],)).fetchone()
        origin_text=origin_row["origin"] if origin_row else None
    destination_text=x.destination or o["delivery_address"]
    origin=(x.origin_lat,x.origin_lon) if x.origin_lat is not None and x.origin_lon is not None else geocode_address(origin_text or "")
    destination=(x.destination_lat,x.destination_lon) if x.destination_lat is not None and x.destination_lon is not None else geocode_address(destination_text)
    road=None
    if origin and destination: road=road_route(origin[0],origin[1],destination[0],destination[1])
    if road:
        distance_km,eta=road
        source="road_router"
    elif x.distance_km is not None:
        distance_km=float(x.distance_km); eta=round(distance_km/40*60); source="manual_fallback"
    elif origin and destination:
        distance_km=haversine_km(origin[0],origin[1],destination[0],destination[1]); eta=round(distance_km/35*60); source="geodesic_fallback"
    else:
        db.close(); raise HTTPException(422,"Forneça origem/destino com coordenadas ou um endereço que possa ser localizado")
    cargo_kg=x.cargo_kg
    if cargo_kg is None:
        conv={"kg":1,"tonne":1000,"t":1000,"ton":1000,"sack":50,"saco":50,"unit":1,"unidade":1}
        cargo_kg=float(o["quantity"])*conv.get(str(db.execute("SELECT unit FROM products WHERE id=?",(o["product_id"],)).fetchone()["unit"]).lower(),1)
    capacity=x.vehicle_capacity_kg or float(db.execute("SELECT value FROM app_settings WHERE key='delivery_default_capacity_kg'").fetchone()["value"] or 5000)
    base=float(db.execute("SELECT value FROM app_settings WHERE key='delivery_base_fee'").fetchone()["value"] or 0)
    rate=float(db.execute("SELECT value FROM app_settings WHERE key='delivery_rate_per_km'").fetchone()["value"] or DELIVERY_RATE_PER_KM)
    load_factor=max(1.0,cargo_kg/capacity)
    fee=round(base + distance_km*rate*load_factor,2)
    total=recalc_total(db,oid,distance_km,fee); db.execute("UPDATE orders SET delivery_address=? WHERE id=?",(destination_text,oid))
    if o["transport_mode"] in ("epyalink","agrolink"): db.execute("UPDATE deliveries SET origin=?,destination=?,distance_km=?,eta_minutes=? WHERE order_id=?",(origin_text,destination_text,distance_km,eta,oid))
    audit(db,u["id"],"ROUTE_QUOTED","orders",oid,{"distance_km":distance_km,"eta_minutes":eta,"source":source}); db.commit(); db.close()
    return {"distance_km":distance_km,"eta_minutes":eta,"delivery_fee_kz":fee,"product_total_kz":o["product_total_kz"],"total_kz":total,"source":source,"origin":origin,"destination":destination,"cargo_kg":round(cargo_kg,2),"vehicle_capacity_kg":capacity,"load_factor":round(load_factor,2)}

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
    if o["transport_mode"] not in ("epyalink","agrolink"): db.close(); raise HTTPException(409,"Transporte EPYALINK não foi escolhido")
    v=db.execute("SELECT * FROM vehicles WHERE transporter_id=? AND status='FREE' AND id=COALESCE(?,id) ORDER BY id DESC LIMIT 1",(x.transporter_id,x.vehicle_id)).fetchone()
    if not v: db.close(); raise HTTPException(409,"Transportador/veículo indisponível")
    code=delivery_code(); existing=db.execute("SELECT id FROM deliveries WHERE order_id=?",(oid,)).fetchone()
    if existing: db.execute("UPDATE deliveries SET transporter_id=?,vehicle_id=?,origin=?,destination=?,status='REQUESTED' WHERE order_id=?",(x.transporter_id,v["id"],x.origin,o["delivery_address"],oid)); did=existing["id"]
    else: did=db.execute("INSERT INTO deliveries(order_id,transporter_id,vehicle_id,origin,destination,status) VALUES(?,?,?,?,?,?)",(oid,x.transporter_id,v["id"],x.origin,o["delivery_address"],"REQUESTED")).lastrowid
    db.execute("UPDATE orders SET delivery_status='REQUESTED',delivery_code_hash=? WHERE id=?",(delivery_hash(code),oid)); db.execute("UPDATE vehicles SET status='RESERVED' WHERE id=?",(v["id"],)); notify(db,x.transporter_id,"Nova solicitação de transporte",f"Pedido #{oid}. Aceite ou rejeite no EPYALINK."); audit(db,u["id"],"TRANSPORT_REQUESTED","deliveries",did,{"transporter_id":x.transporter_id}); db.commit(); db.close()
    # The delivery code is returned only to the buyer/seller who initiated the assignment; transporter never receives it.
    return {"delivery_id":did,"status":"REQUESTED","message":"Solicitação enviada. O código de confirmação é reservado para a confirmação da entrega pelo comprador."}

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
def webhook(pid:int,payload:dict, x_epyalink_webhook: str = Header(default="", alias="X-EPYALINK-Webhook"), x_agrolink_webhook: str = Header(default="", alias="X-AgroLink-Webhook")):
    webhook_secret=x_epyalink_webhook or x_agrolink_webhook
    if not webhook_secret or not SECRET_KEY or not hmac.compare_digest(webhook_secret, SECRET_KEY):
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
    rows=[] if not c else [dict(x) for x in db.execute("SELECT m.*,u.full_name sender_name,u.role sender_role,u.province sender_province,u.profile_photo sender_profile_photo FROM chat_messages m JOIN users u ON u.id=m.sender_id WHERE conversation_id=? ORDER BY m.id",(c["id"],)).fetchall()]
    for r in rows:
        if r.get("attachment_file_id"): r["attachment_url"]=f"/api/files/{r['attachment_file_id']}"
    db.close(); return rows
@app.post("/api/orders/{oid}/chat")
def chat_send(oid:int,x:Chat,u=Depends(auth)):
    if not x.body.strip() and not x.attachment_file_id: raise HTTPException(422,"Envie uma mensagem ou fotografia")
    db=get_db(); order_access(db,oid,u["id"])
    if x.attachment_file_id:
        f=db.execute("SELECT id,owner_id FROM stored_files WHERE id=?",(x.attachment_file_id,)).fetchone()
        if not f or f["owner_id"]!=u["id"]: db.close(); raise HTTPException(403,"Anexo inválido")
    c=db.execute("SELECT id FROM conversations WHERE order_id=?",(oid,)).fetchone(); cid=c["id"] if c else db.execute("INSERT INTO conversations(order_id) VALUES(?)",(oid,)).lastrowid
    mid=db.execute("INSERT INTO chat_messages(conversation_id,sender_id,body,attachment_file_id) VALUES(?,?,?,?)",(cid,u["id"],x.body.strip(),x.attachment_file_id)).lastrowid
    o=db.execute("SELECT buyer_id,seller_id FROM orders WHERE id=?",(oid,)).fetchone(); recipients={o["buyer_id"],o["seller_id"]}; d=db.execute("SELECT transporter_id FROM deliveries WHERE order_id=?",(oid,)).fetchone();
    if d and d["transporter_id"]: recipients.add(d["transporter_id"])
    for rid in recipients-{u["id"]}: notify(db,rid,"Nova mensagem",f"Nova mensagem no pedido #{oid}.")
    audit(db,u["id"],"CHAT_MESSAGE_SENT","orders",oid,{"has_attachment":bool(x.attachment_file_id)})
    db.commit(); db.close(); return {"message_id":mid}

@app.get("/api/admin/audit")
def admin_audit(limit:int=100,offset:int=0,action:str="",entity_type:str="",u=Depends(role("admin"))):
    limit=max(1,min(limit,500)); db=get_db(); where=[]; args=[]
    if action: where.append("a.action LIKE ?"); args.append(f"%{action}%")
    if entity_type: where.append("a.entity_type=?"); args.append(entity_type)
    w=(" WHERE "+" AND ".join(where)) if where else ""
    rows=[dict(x) for x in db.execute(f"SELECT a.*,u.full_name actor_name,u.phone actor_phone FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id{w} ORDER BY a.id DESC LIMIT ? OFFSET ?",(*args,limit,offset)).fetchall()]
    total=db.execute(f"SELECT COUNT(*) c FROM audit_logs a{w}",args).fetchone()["c"]; audit(db,u["id"],"AUDIT_VIEWED","audit_logs",None,{"limit":limit,"offset":offset}); db.commit(); db.close(); return {"items":rows,"total":total}

@app.get("/api/admin/reports")
def admin_reports(u=Depends(role("admin"))):
    db=get_db(); r={}
    r["sales_total_kz"]=db.execute("SELECT COALESCE(SUM(product_total_kz),0) v FROM orders WHERE status='DELIVERED'").fetchone()["v"]
    r["transport_total_kz"]=db.execute("SELECT COALESCE(SUM(delivery_fee_kz),0) v FROM orders WHERE delivery_status='DELIVERED'").fetchone()["v"]
    r["agrolink_commissions_kz"]=db.execute("SELECT COALESCE(SUM(commission_kz),0) v FROM commissions").fetchone()["v"]
    r["orders_total"]=db.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    r["delivered_orders"]=db.execute("SELECT COUNT(*) c FROM orders WHERE delivery_status='DELIVERED'").fetchone()["c"]
    r["active_users"]=db.execute("SELECT COUNT(*) c FROM users WHERE status='active'").fetchone()["c"]
    r["products_active"]=db.execute("SELECT COUNT(*) c FROM products WHERE active=1").fetchone()["c"]
    r["pending_payments_kz"]=db.execute("SELECT COALESCE(SUM(amount_kz),0) v FROM payments WHERE status='PENDING'").fetchone()["v"]
    r["pending_settlements_kz"]=db.execute("SELECT COALESCE(SUM(net_amount_kz),0) v FROM settlements WHERE status='PENDING'").fetchone()["v"]
    r["users_by_role"]=[dict(x) for x in db.execute("SELECT role,COUNT(*) count FROM users GROUP BY role ORDER BY count DESC").fetchall()]
    r["orders_by_status"]=[dict(x) for x in db.execute("SELECT status,COUNT(*) count FROM orders GROUP BY status ORDER BY count DESC").fetchall()]
    audit(db,u["id"],"REPORTS_VIEWED","reports",None); db.commit(); db.close(); return r

@app.get("/api/admin/settings")
def admin_settings(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT key,value,updated_at FROM app_settings ORDER BY key").fetchall()]; db.close(); return rows
@app.put("/api/admin/settings/{key}")
def admin_setting(key:str,x:AdminSetting,u=Depends(role("admin"))):
    allowed={"maintenance_mode","support_email","support_phone_1","support_phone_2","support_address","company_name"}
    if key not in allowed: raise HTTPException(400,"Configuração não permitida")
    db=get_db(); db.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",(key,x.value.strip())); audit(db,u["id"],"SETTING_CHANGED","app_settings",None,{"key":key}); db.commit(); db.close(); return {"key":key,"value":x.value.strip()}

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


@app.get("/api/profiles/{user_id}")
def public_profile(user_id:int,u=Depends(auth)):
    db=get_db(); target=db.execute("SELECT id,full_name,role,province,profile_photo,status FROM users WHERE id=?",(user_id,)).fetchone()
    if not target: db.close(); raise HTTPException(404,"Perfil não encontrado")
    out=dict(target)
    if out["role"]=="seller":
        p=db.execute("SELECT company_name,farm_name,description,location,province FROM producers WHERE user_id=?",(user_id,)).fetchone(); out["producer"]=dict(p) if p else None
    if out["role"]=="transport_company":
        c=db.execute("SELECT company_name,registration_number,location FROM transport_companies WHERE user_id=?",(user_id,)).fetchone(); out["transport_company"]=dict(c) if c else None
        out["drivers_count"]=db.execute("SELECT COUNT(*) c FROM drivers WHERE company_user_id=?",(user_id,)).fetchone()["c"]
        out["vehicles_count"]=db.execute("SELECT COUNT(*) c FROM vehicles WHERE transporter_id=?",(user_id,)).fetchone()["c"]
    out["products"]= [dict(r) for r in db.execute("SELECT id,name,price_kz,quantity,unit,photo,location FROM products WHERE seller_id=? AND active=1 ORDER BY created_at DESC",(user_id,)).fetchall()]
    rating=db.execute("SELECT COALESCE(AVG(score),0) avg_score,COUNT(*) count FROM ratings WHERE target_id=?",(user_id,)).fetchone(); out["rating"]=round(float(rating["avg_score"]),2); out["ratings_count"]=rating["count"]
    ver=db.execute("SELECT verified FROM profile_verifications WHERE user_id=?",(user_id,)).fetchone(); out["verified"]=bool(ver and ver["verified"])
    db.close(); return out

@app.get("/api/profiles/{user_id}/photo")
def profile_photo_get(user_id:int,u=Depends(auth)):
    db=get_db(); target=db.execute("SELECT profile_photo FROM users WHERE id=?",(user_id,)).fetchone()
    if not target or not target["profile_photo"]: db.close(); raise HTTPException(404,"Fotografia de perfil não encontrada")
    ref=str(target["profile_photo"]).rsplit("/",1)[-1]; f=db.execute("SELECT * FROM stored_files WHERE id=? AND entity_type='profile' AND entity_id=?",(ref,user_id)).fetchone(); db.close()
    if not f: raise HTTPException(404,"Fotografia não encontrada")
    path=storage_root()/f["storage_key"]
    if not path.exists(): raise HTTPException(404,"Fotografia não disponível")
    return FileResponse(path,media_type=f["content_type"],headers={"Cache-Control":"private, no-store"})

@app.put("/api/profile")
def update_profile(x:ProfileUpdate,u=Depends(auth)):
    db=get_db(); vals=[]; args=[]
    for key in ("full_name","province","address"):
        v=getattr(x,key)
        if v is not None: vals.append(f"{key}=?"); args.append(v.strip())
    if x.profile_photo_file_id:
        f=db.execute("SELECT id,owner_id FROM stored_files WHERE id=?",(x.profile_photo_file_id,)).fetchone()
        if not f or f["owner_id"]!=u["id"]: db.close(); raise HTTPException(400,"Fotografia inválida")
        vals.append("profile_photo=?"); args.append(f"/api/files/{x.profile_photo_file_id}"); db.execute("UPDATE stored_files SET entity_type='profile',entity_id=? WHERE id=?",(u["id"],x.profile_photo_file_id))
    if vals: db.execute("UPDATE users SET "+",".join(vals)+" WHERE id=?",args+[u["id"]])
    if u["role"]=="seller":
        vals=[]; args=[]
        for key in ("company_name","farm_name","description"):
            v=getattr(x,key)
            if v is not None: vals.append(f"{key}=?"); args.append(v.strip())
        if x.province is not None: vals.append("province=?"); args.append(x.province.strip())
        if vals: db.execute("UPDATE producers SET "+",".join(vals)+" WHERE user_id=?",args+[u["id"]])
    audit(db,u["id"],"PROFILE_UPDATED","users",u["id"]); db.commit(); db.close(); return {"ok":True}

@app.post("/api/favorites/{product_id}")
def add_favorite(product_id:int,u=Depends(auth)):
    db=get_db(); p=db.execute("SELECT id FROM products WHERE id=? AND active=1",(product_id,)).fetchone()
    if not p: db.close(); raise HTTPException(404,"Produto não encontrado")
    db.execute("INSERT OR IGNORE INTO favorites(user_id,product_id) VALUES(?,?)",(u["id"],product_id)); db.commit(); db.close(); return {"ok":True}

@app.delete("/api/favorites/{product_id}")
def remove_favorite(product_id:int,u=Depends(auth)):
    db=get_db(); db.execute("DELETE FROM favorites WHERE user_id=? AND product_id=?",(u["id"],product_id)); db.commit(); db.close(); return {"ok":True}

@app.get("/api/favorites")
def favorites(u=Depends(auth)):
    db=get_db(); rows=[dict(r) for r in db.execute("SELECT p.*,u.full_name seller_name,pr.company_name,pr.farm_name FROM favorites f JOIN products p ON p.id=f.product_id JOIN users u ON u.id=p.seller_id LEFT JOIN producers pr ON pr.user_id=u.id WHERE f.user_id=? ORDER BY f.created_at DESC",(u["id"],)).fetchall()]; db.close(); return rows

@app.post("/api/ratings")
def add_rating(x:RatingCreate,u=Depends(auth)):
    db=get_db(); o=db.execute("SELECT * FROM orders WHERE id=?",(x.order_id,)).fetchone()
    if not o or o["status"]!="DELIVERED": db.close(); raise HTTPException(409,"A avaliação só pode ser feita após a entrega concluída")
    if u["id"] not in (o["buyer_id"],o["seller_id"]) and not db.execute("SELECT 1 FROM deliveries WHERE order_id=? AND transporter_id=?",(x.order_id,u["id"])).fetchone(): db.close(); raise HTTPException(403,"Sem acesso a esta avaliação")
    allowed={"buyer":o["buyer_id"],"seller":o["seller_id"]}
    d=db.execute("SELECT transporter_id FROM deliveries WHERE order_id=?",(x.order_id,)).fetchone();
    if d and d["transporter_id"]: allowed["transporter"]=d["transporter_id"]
    if allowed.get(x.target_role)!=x.target_id or x.target_id==u["id"]: db.close(); raise HTTPException(400,"Destinatário da avaliação inválido")
    try: db.execute("INSERT INTO ratings(order_id,rater_id,target_id,target_role,score,comment) VALUES(?,?,?,?,?,?)",(x.order_id,u["id"],x.target_id,x.target_role,x.score,x.comment));
    except Exception: db.close(); raise HTTPException(409,"Já avaliou este utilizador neste pedido")
    notify(db,x.target_id,"Nova avaliação",f"Recebeu uma avaliação de {x.score}/5 no pedido #{x.order_id}."); audit(db,u["id"],"RATING_CREATED","ratings",None,{"order_id":x.order_id,"target_id":x.target_id,"score":x.score}); db.commit(); db.close(); return {"ok":True}

@app.get("/api/orders/{oid}/ratings")
def order_ratings(oid:int,u=Depends(auth)):
    db=get_db(); order_access(db,oid,u["id"]); rows=[dict(r) for r in db.execute("SELECT r.*,u.full_name rater_name FROM ratings r JOIN users u ON u.id=r.rater_id WHERE r.order_id=? ORDER BY r.created_at DESC",(oid,)).fetchall()]; db.close(); return rows

@app.post("/api/disputes")
def create_dispute(x:DisputeCreate,u=Depends(auth)):
    db=get_db(); o=order_access(db,x.order_id,u["id"]); existing=db.execute("SELECT id FROM disputes WHERE order_id=? AND status='OPEN'",(x.order_id,)).fetchone()
    if existing: db.close(); raise HTTPException(409,"Já existe uma disputa aberta para este pedido")
    c=db.execute("INSERT INTO disputes(order_id,opened_by,reason,description) VALUES(?,?,?,?)",(x.order_id,u["id"],x.reason,x.description)); notify(db,o["seller_id"] if u["id"]==o["buyer_id"] else o["buyer_id"],"Disputa aberta",f"Foi aberta uma disputa no pedido #{x.order_id}."); audit(db,u["id"],"DISPUTE_OPENED","orders",x.order_id,{"reason":x.reason}); db.commit(); db.close(); return {"id":c.lastrowid,"status":"OPEN"}

@app.get("/api/disputes/mine")
def my_disputes(u=Depends(auth)):
    db=get_db(); rows=[dict(r) for r in db.execute("SELECT d.*,u.full_name opened_by_name FROM disputes d JOIN users u ON u.id=d.opened_by WHERE d.opened_by=? OR d.order_id IN (SELECT id FROM orders WHERE buyer_id=? OR seller_id=?) ORDER BY d.created_at DESC",(u["id"],u["id"],u["id"])).fetchall()]; db.close(); return rows

@app.post("/api/deliveries/{did}/proof")
def delivery_proof(did:int,file_id:str,latitude:float|None=None,longitude:float|None=None,u=Depends(role("transport_company","private_transporter","transporter"))):
    db=get_db(); d=db.execute("SELECT * FROM deliveries WHERE id=? AND transporter_id=?",(did,u["id"])).fetchone(); f=db.execute("SELECT id,owner_id FROM stored_files WHERE id=?",(file_id,)).fetchone()
    if not d or not f or f["owner_id"]!=u["id"]: db.close(); raise HTTPException(403,"Prova de entrega inválida")
    db.execute("UPDATE deliveries SET proof_photo=?,proof_latitude=?,proof_longitude=?,proof_timestamp=CURRENT_TIMESTAMP WHERE id=?",(file_id,latitude,longitude,did)); audit(db,u["id"],"DELIVERY_PROOF_ATTACHED","deliveries",did); db.commit(); db.close(); return {"ok":True}

@app.get("/api/dashboard/mine")
def my_dashboard(u=Depends(auth)):
    db=get_db();
    out={"role":u["role"],"orders":db.execute("SELECT COUNT(*) c FROM orders WHERE buyer_id=? OR seller_id=?",(u["id"],u["id"])).fetchone()["c"],"delivered":db.execute("SELECT COUNT(*) c FROM orders WHERE (buyer_id=? OR seller_id=?) AND status='DELIVERED'",(u["id"],u["id"])).fetchone()["c"],"unread_notifications":db.execute("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND read_at IS NULL",(u["id"],)).fetchone()["c"]}
    if u["role"]=="seller": out.update({"active_products":db.execute("SELECT COUNT(*) c FROM products WHERE seller_id=? AND active=1",(u["id"],)).fetchone()["c"],"sales_value":db.execute("SELECT COALESCE(SUM(product_total_kz),0) v FROM orders WHERE seller_id=? AND status='DELIVERED'",(u["id"],)).fetchone()["v"]})
    if u["role"] in ("transport_company","private_transporter","transporter"): out["transports_completed"]=db.execute("SELECT COUNT(*) c FROM deliveries WHERE transporter_id=? AND status='DELIVERED'",(u["id"],)).fetchone()["c"]
    if u["role"]=="buyer": out["purchases_value"]=db.execute("SELECT COALESCE(SUM(product_total_kz),0) v FROM orders WHERE buyer_id=? AND status='DELIVERED'",(u["id"],)).fetchone()["v"]
    db.close(); return out

@app.get("/api/admin/disputes")
def admin_disputes(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(r) for r in db.execute("SELECT d.*,o.buyer_id,o.seller_id,ou.full_name opened_by_name FROM disputes d JOIN orders o ON o.id=d.order_id JOIN users ou ON ou.id=d.opened_by ORDER BY d.created_at DESC").fetchall()]; db.close(); return rows

@app.post("/api/admin/disputes/{did}/resolve")
def admin_resolve_dispute(did:int,x:DisputeResolve,u=Depends(role("admin"))):
    db=get_db(); d=db.execute("SELECT * FROM disputes WHERE id=?",(did,)).fetchone()
    if not d: db.close(); raise HTTPException(404,"Disputa não encontrada")
    db.execute("UPDATE disputes SET status=?,resolution=?,resolved_at=CURRENT_TIMESTAMP WHERE id=?",(x.status,x.resolution,did)); notify(db,d["opened_by"],"Disputa atualizada",f"A disputa #{did} foi atualizada para {x.status}."); audit(db,u["id"],"DISPUTE_RESOLVED","disputes",did,{"status":x.status}); db.commit(); db.close(); return {"ok":True}

@app.post("/api/admin/users/{user_id}/verify")
def verify_profile(user_id:int,u=Depends(role("admin"))):
    db=get_db(); target=db.execute("SELECT id FROM users WHERE id=?",(user_id,)).fetchone()
    if not target: db.close(); raise HTTPException(404,"Utilizador não encontrado")
    db.execute("INSERT INTO profile_verifications(user_id,verified,verified_at,verified_by) VALUES(?,1,CURRENT_TIMESTAMP,?) ON CONFLICT(user_id) DO UPDATE SET verified=1,verified_at=CURRENT_TIMESTAMP,verified_by=excluded.verified_by",(user_id,u["id"])); audit(db,u["id"],"PROFILE_VERIFIED","users",user_id); db.commit(); db.close(); return {"ok":True,"verified":True}


@app.get("/api/market-insights")
def market_insights(u=Depends(auth)):
    db=get_db()
    top=[dict(r) for r in db.execute("SELECT p.name,p.unit,COUNT(o.id) orders_count,COALESCE(SUM(o.quantity),0) quantity_sold FROM orders o JOIN products p ON p.id=o.product_id WHERE o.status='DELIVERED' GROUP BY p.id ORDER BY orders_count DESC,quantity_sold DESC LIMIT 10").fetchall()]
    provinces=[dict(r) for r in db.execute("SELECT u.province,COUNT(o.id) orders_count FROM orders o JOIN users u ON u.id=o.buyer_id WHERE u.province IS NOT NULL AND u.province<>'' GROUP BY u.province ORDER BY orders_count DESC LIMIT 10").fetchall()]
    low=[dict(r) for r in db.execute("SELECT id,name,quantity,unit,price_kz FROM products WHERE active=1 AND quantity>0 ORDER BY quantity ASC LIMIT 10").fetchall()]
    searches=[dict(r) for r in db.execute("SELECT name,COUNT(*) c FROM products GROUP BY name ORDER BY c DESC LIMIT 10").fetchall()]
    db.close(); return {"top_sold_products":top,"buyer_regions":provinces,"low_stock":low,"market_catalogue":searches,"note":"Insights baseiam-se nos dados internos disponíveis e não constituem previsão garantida de procura."}

@app.get("/api/admin/dashboard")
def dashboard(u=Depends(role("admin"))):
    db=get_db(); out={}
    for k,t in [("users","users"),("producers","producers"),("transporters","users"),("vehicles","vehicles"),("products","products"),("orders","orders"),("payments","payments"),("commissions","commissions"),("notifications","notifications"),("settlements","settlements")]:
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

@app.post("/api/admin/users/{user_id}/status")
def admin_user_status(user_id:int,x:AdminUserStatus,u=Depends(role("admin"))):
    if user_id==u["id"] and x.status=="suspended": raise HTTPException(400,"Não pode suspender a própria conta administrativa")
    db=get_db(); target=db.execute("SELECT id FROM users WHERE id=?",(user_id,)).fetchone()
    if not target: db.close(); raise HTTPException(404,"Utilizador não encontrado")
    db.execute("UPDATE users SET status=? WHERE id=?",(x.status,user_id)); audit(db,u["id"],"USER_STATUS_CHANGED","users",user_id,{"status":x.status}); db.commit(); db.close(); return {"ok":True,"status":x.status}

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
    if db.execute("SELECT id FROM settlements WHERE order_id=?",(oid,)).fetchone(): db.close(); raise HTTPException(409,"Liquidação já processada")
    sc=round(o["product_total_kz"]*SELLER_COMMISSION_RATE,2); seller_net=round(o["product_total_kz"]-sc,2)
    db.execute("INSERT INTO commissions(order_id,beneficiary_type,rate,base_amount_kz,commission_kz) VALUES(?,?,?,?,?)",(oid,"seller",SELLER_COMMISSION_RATE,o["product_total_kz"],sc))
    db.execute("INSERT INTO settlements(order_id,beneficiary_user_id,beneficiary_type,gross_amount_kz,commission_kz,net_amount_kz) VALUES(?,?,?,?,?,?)",(oid,o["seller_id"],"seller",o["product_total_kz"],sc,seller_net))
    tc=0; transporter_net=0
    if o["delivery_fee_kz"]>0:
        tc=round(o["delivery_fee_kz"]*TRANSPORTER_COMMISSION_RATE,2); transporter_net=round(o["delivery_fee_kz"]-tc,2)
        d=db.execute("SELECT transporter_id FROM deliveries WHERE order_id=?",(oid,)).fetchone()
        if d and d["transporter_id"]:
            db.execute("INSERT INTO commissions(order_id,beneficiary_type,rate,base_amount_kz,commission_kz) VALUES(?,?,?,?,?)",(oid,"transporter",TRANSPORTER_COMMISSION_RATE,o["delivery_fee_kz"],tc))
            db.execute("INSERT INTO settlements(order_id,beneficiary_user_id,beneficiary_type,gross_amount_kz,commission_kz,net_amount_kz) VALUES(?,?,?,?,?,?)",(oid,d["transporter_id"],"transporter",o["delivery_fee_kz"],tc,transporter_net))
            notify(db,d["transporter_id"],"Liquidação disponível",f"A liquidação do transporte do pedido #{oid} foi criada.")
    db.execute("UPDATE orders SET payment_status='SETTLEMENT_RELEASED' WHERE id=?",(oid,)); notify(db,o["seller_id"],"Liquidação disponível",f"A liquidação da venda do pedido #{oid} foi criada."); audit(db,u["id"],"SETTLEMENT_CREATED","orders",oid); db.commit(); db.close(); return {"status":"SETTLEMENT_RELEASED","seller_net":seller_net,"transporter_net":transporter_net,"agrolink_commission":round(sc+tc,2)}

@app.get("/api/settlements/mine")
def my_settlements(u=Depends(auth)):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT * FROM settlements WHERE beneficiary_user_id=? ORDER BY id DESC",(u["id"],)).fetchall()]; db.close(); return rows

@app.get("/api/admin/settlements")
def admin_settlements(u=Depends(role("admin"))):
    db=get_db(); rows=[dict(x) for x in db.execute("SELECT s.*,u.full_name,u.phone FROM settlements s JOIN users u ON u.id=s.beneficiary_user_id ORDER BY s.id DESC").fetchall()]; db.close(); return rows

@app.post("/api/admin/settlements/{sid}/mark-paid")
def mark_settlement_paid(sid:int,x:SettlementPayment,u=Depends(role("admin"))):
    db=get_db(); st=db.execute("SELECT * FROM settlements WHERE id=?",(sid,)).fetchone()
    if not st: db.close(); raise HTTPException(404,"Liquidação não encontrada")
    if st["status"]=="PAID": db.close(); raise HTTPException(409,"Liquidação já marcada como paga")
    db.execute("UPDATE settlements SET status='PAID',payment_reference=?,paid_at=CURRENT_TIMESTAMP WHERE id=?",(x.payment_reference.strip(),sid)); notify(db,st["beneficiary_user_id"],"Pagamento de liquidação",f"A liquidação #{sid} foi marcada como paga."); audit(db,u["id"],"SETTLEMENT_PAID","settlements",sid,{"reference":x.payment_reference}); db.commit(); db.close(); return {"ok":True,"status":"PAID"}

def _ws_user(token: str):
    if not token:
        return None
    try:
        payload=jwt.decode(token,SECRET_KEY,algorithms=[JWT_ALGORITHM])
        uid=int(payload.get("sub"))
    except (jwt.ExpiredSignatureError,jwt.InvalidTokenError,TypeError,ValueError):
        return None
    db=get_db()
    try:
        row=db.execute("SELECT id,full_name,role,status FROM users WHERE id=? AND status='active'",(uid,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()

@app.websocket("/ws/chat/{oid}")
async def ws_chat(ws:WebSocket,oid:int,token:str=""):
    user=_ws_user(token)
    if not user:
        await ws.close(code=4001,reason="Sessão inválida ou expirada")
        return
    db=get_db()
    try:
        order_access(db,oid,user["id"])
    except HTTPException:
        db.close()
        await ws.close(code=4003,reason="Sem acesso ao chat")
        return
    db.close()
    await ws.accept()
    await ws.send_json({"type":"ready","order_id":oid,"message":"Canal de chat conectado. Use a API de mensagens para persistência."})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass

@app.websocket("/ws/location/{oid}")
async def ws_location(ws:WebSocket,oid:int,token:str=""):
    user=_ws_user(token)
    if not user or user["role"] not in ("transport_company","private_transporter","transporter"):
        await ws.close(code=4001,reason="Sessão ou permissão inválida")
        return
    db=get_db()
    try:
        order_access(db,oid,user["id"])
    except HTTPException:
        db.close()
        await ws.close(code=4003,reason="Sem acesso à entrega")
        return
    db.close()
    await ws.accept()
    await ws.send_json({"type":"ready","order_id":oid,"message":"Canal de localização conectado. Use a API de localização para persistência."})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass

