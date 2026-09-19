from fastapi import FastAPI,HTTPException,Depends,Header
from fastapi.responses import HTMLResponse
from .db import init_db,get_db
from .schemas import *
from .security import *
from .config import *
import hashlib,json,secrets
app=FastAPI(title='AgroLink Angola v11',version='11.0.0');TOKENS={}
@app.on_event('startup')
def startup():init_db()
def auth(authorization:str=Header(default='')):
    if not authorization.startswith('Bearer '):raise HTTPException(401,'Autenticação necessária')
    uid=TOKENS.get(authorization[7:]);db=get_db();u=db.execute("SELECT * FROM users WHERE id=? AND status='active'",(uid,)).fetchone() if uid else None;db.close()
    if not u:raise HTTPException(401,'Sessão inválida')
    return dict(u)
def role(*roles):
    def dep(u=Depends(auth)):
        if u['role'] not in roles:raise HTTPException(403,'Permissão insuficiente')
        return u
    return dep
def audit(db,uid,action,typ=None,eid=None,meta=None):db.execute('INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,metadata) VALUES(?,?,?,?,?)',(uid,action,typ,eid,json.dumps(meta or {},ensure_ascii=False)))
@app.get('/',response_class=HTMLResponse)
def home():return '''<html><meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:system-ui;max-width:900px;margin:40px auto;padding:20px"><h1 style="font-size:44px;color:#23823d">AGRO-LINK <span style="color:#df781e">ANGOLA</span></h1><h3>Conectamos Produtores &amp; Consumidores</h3><p>v11 — Marketplace • Transporte • Rastreamento • Pagamento protegido • Chat • Admin • Offline-first</p><p><a href="/docs">Documentação da API</a></p><hr><b>© 2026 Nuvem JM – Prestação de Serviços e Tecnologias de Informação, Limitada. Todos os direitos reservados.</b></body></html>'''
@app.post('/api/auth/register')
def register(x:Register):
    db=get_db();phone=normalize_phone(x.phone)
    if db.execute('SELECT id FROM users WHERE phone=?',(phone,)).fetchone():db.close();raise HTTPException(409,'Telefone já registado')
    bih=blind_hash(x.bi_number) if x.bi_number else None;bie=('PROTECTED:'+hashlib.sha256((x.bi_number or '').encode()).hexdigest()) if x.bi_number else None
    c=db.execute('INSERT INTO users(full_name,phone,password_hash,role,province,address,bi_number_encrypted,bi_blind_hash) VALUES(?,?,?,?,?,?,?,?)',(x.full_name,phone,hash_password(x.password),x.role,x.province,x.address,bie,bih));uid=c.lastrowid
    if x.role=='seller':db.execute('INSERT INTO producers(user_id,company_name,farm_name,province) VALUES(?,?,?,?)',(uid,x.company_name,x.farm_name,x.province))
    audit(db,uid,'USER_REGISTERED','users',uid,{'role':x.role});db.commit();db.close();return {'ok':True,'user_id':uid}
@app.post('/api/auth/login')
def login(x:Login):
    db=get_db();u=db.execute('SELECT * FROM users WHERE phone=?',(normalize_phone(x.phone),)).fetchone()
    if not u or not verify_password(x.password,u['password_hash']):db.close();raise HTTPException(401,'Credenciais inválidas')
    t=secrets.token_urlsafe(32);TOKENS[t]=u['id'];db.close();return {'access_token':t,'token_type':'bearer','role':u['role'],'full_name':u['full_name']}
@app.get('/api/products')
def products(q:str='',category_id:int|None=None):
    db=get_db();sql="SELECT p.*,u.full_name seller_name,pr.company_name,pr.farm_name FROM products p JOIN users u ON u.id=p.seller_id LEFT JOIN producers pr ON pr.user_id=u.id WHERE p.active=1";args=[]
    if q:sql+=' AND (p.name LIKE ? OR p.description LIKE ?)';args += [f'%{q}%',f'%{q}%']
    if category_id:sql+=' AND p.category_id=?';args.append(category_id)
    sql+=' ORDER BY p.created_at DESC';r=[dict(x) for x in db.execute(sql,args).fetchall()];db.close();return r
@app.post('/api/products')
def create_product(x:Product,u=Depends(role('seller'))):
    db=get_db();c=db.execute('INSERT INTO products(seller_id,category_id,name,description,price_kz,quantity,unit,photo,location) VALUES(?,?,?,?,?,?,?,?,?)',(u['id'],x.category_id,x.name,x.description,x.price_kz,x.quantity,x.unit,x.photo,x.location));audit(db,u['id'],'PRODUCT_CREATED','products',c.lastrowid);db.commit();db.close();return {'id':c.lastrowid}
@app.post('/api/orders')
def create_order(x:Order,u=Depends(role('buyer'))):
    db=get_db();p=db.execute('SELECT * FROM products WHERE id=? AND active=1',(x.product_id,)).fetchone()
    if not p:db.close();raise HTTPException(404,'Produto não encontrado')
    if x.quantity>p['quantity']:db.close();raise HTTPException(400,'Quantidade indisponível')
    total=round(x.quantity*p['price_kz'],2);c=db.execute('INSERT INTO orders(buyer_id,seller_id,product_id,quantity,delivery_address,transport_mode,product_total_kz,total_kz) VALUES(?,?,?,?,?,?,?,?)',(u['id'],p['seller_id'],p['id'],x.quantity,x.delivery_address,x.transport_mode,total,total));oid=c.lastrowid;db.execute('INSERT INTO conversations(order_id) VALUES(?)',(oid,));db.execute('INSERT INTO notifications(user_id,title,body) VALUES(?,?,?)',(p['seller_id'],'Novo pedido',f'Pedido #{oid}'));audit(db,u['id'],'ORDER_CREATED','orders',oid,{'transport_mode':x.transport_mode});db.commit();db.close();return {'order_id':oid,'status':'PENDING_SELLER'}
@app.post('/api/orders/{oid}/seller-review')
def review(oid:int,x:Review,u=Depends(role('seller'))):
    db=get_db();o=db.execute('SELECT * FROM orders WHERE id=? AND seller_id=?',(oid,u['id'])).fetchone()
    if not o:db.close();raise HTTPException(404,'Pedido não encontrado')
    st='SELLER_ACCEPTED' if x.accepted else 'SELLER_REJECTED';db.execute('UPDATE orders SET status=? WHERE id=?',(st,oid));db.execute('INSERT INTO notifications(user_id,title,body) VALUES(?,?,?)',(o['buyer_id'],'Pedido atualizado',f'Pedido #{oid}: {st}'));audit(db,u['id'],'SELLER_REVIEW','orders',oid,{'accepted':x.accepted});db.commit();db.close();return {'status':st}
@app.post('/api/orders/{oid}/payment')
def payment(oid:int,x:Payment,u=Depends(role('buyer'))):
    db=get_db();o=db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?',(oid,u['id'])).fetchone()
    if not o:db.close();raise HTTPException(404,'Pedido não encontrado')
    if round(x.amount_kz,2)!=round(o['total_kz'],2):db.close();raise HTTPException(400,'Valor incorreto')
    if db.execute('SELECT id FROM payments WHERE idempotency_key=?',(x.idempotency_key,)).fetchone():db.close();raise HTTPException(409,'Pagamento duplicado')
    c=db.execute('INSERT INTO payments(order_id,method,transaction_id,reference,amount_kz,status,idempotency_key) VALUES(?,?,?,?,?,?,?)',(oid,x.method,x.transaction_id,x.reference,x.amount_kz,'PENDING',x.idempotency_key));db.execute("UPDATE orders SET payment_status='PENDING' WHERE id=?",(oid,));db.commit();r=dict(db.execute('SELECT * FROM payments WHERE id=?',(c.lastrowid,)).fetchone());db.close();return r
@app.post('/api/payments/{pid}/webhook')
def webhook(pid:int,payload:dict):
    db=get_db();p=db.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
    if not p:db.close();raise HTTPException(404,'Pagamento não encontrado')
    st=payload.get('status')
    if st not in ('CONFIRMED','FAILED','EXPIRED','CANCELLED'):db.close();raise HTTPException(400,'Estado inválido')
    ph=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();db.execute('UPDATE payments SET status=?,provider_payload_hash=? WHERE id=?',(st,ph,pid));db.execute('UPDATE orders SET payment_status=? WHERE id=?',('PAID' if st=='CONFIRMED' else 'PAYMENT_FAILED',p['order_id']));db.commit();db.close();return {'ok':True}
@app.post('/api/deliveries/{did}/confirm')
def confirm_delivery(did:int,x:Code,u=Depends(role('buyer'))):
    db=get_db();d=db.execute('SELECT * FROM deliveries WHERE id=?',(did,)).fetchone()
    if not d:db.close();raise HTTPException(404,'Entrega não encontrada')
    o=db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?',(d['order_id'],u['id'])).fetchone()
    if not o:db.close();raise HTTPException(403,'Sem acesso')
    if o['delivery_code_hash'] and o['delivery_code_hash']!=delivery_hash(x.code):db.close();raise HTTPException(400,'Código inválido')
    db.execute("UPDATE deliveries SET status='DELIVERED',delivered_at=CURRENT_TIMESTAMP WHERE id=?",(did,));db.execute("UPDATE orders SET delivery_status='DELIVERED',status='DELIVERED',payment_status='READY_FOR_SETTLEMENT' WHERE id=?",(o['id'],));audit(db,u['id'],'DELIVERY_CONFIRMED','deliveries',did);db.commit();db.close();return {'status':'DELIVERED','payment_status':'READY_FOR_SETTLEMENT'}
@app.post('/api/deliveries/{did}/location')
def location(did:int,x:Location,u=Depends(role('transporter'))):
    db=get_db();d=db.execute('SELECT * FROM deliveries WHERE id=? AND transporter_id=?',(did,u['id'])).fetchone()
    if not d:db.close();raise HTTPException(403,'Sem acesso')
    db.execute('INSERT INTO location_pings(delivery_id,latitude,longitude,speed,heading,captured_at) VALUES(?,?,?,?,?,?)',(did,x.latitude,x.longitude,x.speed,x.heading,x.captured_at));db.commit();db.close();return {'ok':True}
@app.post('/api/sync')
def sync(x:Offline,u=Depends(auth)):
    db=get_db();c=db.execute('INSERT INTO sync_queue(user_id,device_id,event_type,payload) VALUES(?,?,?,?)',(u['id'],x.device_id,x.event_type,json.dumps(x.payload,ensure_ascii=False)));db.commit();db.close();return {'queued_event_id':c.lastrowid}
@app.post('/api/orders/{oid}/chat')
def chat(oid:int,x:Chat,u=Depends(auth)):
    db=get_db();o=db.execute('SELECT buyer_id,seller_id FROM orders WHERE id=?',(oid,)).fetchone()
    if not o:db.close();raise HTTPException(404,'Pedido não encontrado')
    allowed=u['id'] in (o['buyer_id'],o['seller_id']);d=db.execute('SELECT transporter_id FROM deliveries WHERE order_id=?',(oid,)).fetchone();allowed=allowed or (d and d['transporter_id']==u['id'])
    if not allowed:db.close();raise HTTPException(403,'Sem acesso')
    c=db.execute('SELECT id FROM conversations WHERE order_id=?',(oid,)).fetchone();cid=c['id'] if c else db.execute('INSERT INTO conversations(order_id) VALUES(?)',(oid,)).lastrowid;mid=db.execute('INSERT INTO chat_messages(conversation_id,sender_id,body) VALUES(?,?,?)',(cid,u['id'],x.body)).lastrowid;db.commit();db.close();return {'message_id':mid}
@app.get('/api/admin/dashboard')
def dashboard(u=Depends(role('admin'))):
    db=get_db();out={};
    for k,t in [('users','users'),('producers','producers'),('transporters','users'),('vehicles','vehicles'),('products','products'),('orders','orders'),('payments','payments'),('commissions','commissions'),('notifications','notifications')]:
        where="role='transporter'" if k=='transporters' else '1=1';out[k]=db.execute(f'SELECT COUNT(*) c FROM {t} WHERE {where}').fetchone()['c']
    db.close();return out
@app.post('/api/admin/orders/{oid}/release')
def release(oid:int,u=Depends(role('admin'))):
    db=get_db();o=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if not o:db.close();raise HTTPException(404,'Pedido não encontrado')
    if o['delivery_status']!='DELIVERED' or o['payment_status'] not in ('PAID','READY_FOR_SETTLEMENT'):db.close();raise HTTPException(400,'Condições de liquidação não cumpridas')
    sc=round(o['product_total_kz']*SELLER_COMMISSION_RATE,2);db.execute('INSERT INTO commissions(order_id,beneficiary_type,rate,base_amount_kz,commission_kz) VALUES(?,?,?,?,?)',(oid,'seller',SELLER_COMMISSION_RATE,o['product_total_kz'],sc));
    if o['delivery_fee_kz']>0:tc=round(o['delivery_fee_kz']*TRANSPORTER_COMMISSION_RATE,2);db.execute('INSERT INTO commissions(order_id,beneficiary_type,rate,base_amount_kz,commission_kz) VALUES(?,?,?,?,?)',(oid,'transporter',TRANSPORTER_COMMISSION_RATE,o['delivery_fee_kz'],tc))
    db.execute("UPDATE orders SET payment_status='SETTLEMENT_RELEASED' WHERE id=?",(oid,));audit(db,u['id'],'SETTLEMENT_RELEASED','orders',oid);db.commit();db.close();return {'status':'SETTLEMENT_RELEASED','seller_commission':sc}
