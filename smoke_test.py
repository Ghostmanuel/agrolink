from fastapi.testclient import TestClient
from app import app

client=TestClient(app)

def login(phone,password):
    r=client.post('/api/v1/auth/login',json={'phone':phone,'password':password})
    assert r.status_code==200, r.text
    return r.json()['access_token']

def auth(token): return {'Authorization':f'Bearer {token}'}

# Requires seed_demo.py first.
b=login('900000001','Demo1234')
f=login('900000002','Demo1234')
d=login('900000003','Demo1234')
a=login('900000000','Admin1234')

products=client.get('/api/v1/products').json(); assert products
order=client.post('/api/v1/orders',headers=auth(b),json={'product_id':products[0]['id'],'quantity':2,'delivery_address':'Talatona, Luanda'}); assert order.status_code==200,order.text
o=order.json(); oid=o['id']

available=client.get(f'/api/v1/orders/{oid}/available-drivers',headers=auth(b)); assert available.status_code==200 and available.json()
did=available.json()[0]['driver_id']
assert client.post(f'/api/v1/orders/{oid}/assign-driver',headers=auth(b),json={'driver_id':did}).status_code==200
assert client.post(f'/api/v1/orders/{oid}/review',headers=auth(b),json={'confirm':True,'delivery_address':'Talatona, Luanda'}).status_code==200
assert client.post(f'/api/v1/orders/{oid}/review',headers=auth(f),json={'confirm':True}).status_code==200
assert client.post(f'/api/v1/orders/{oid}/review',headers=auth(d),json={'confirm':True}).status_code==200
p=client.post('/api/v1/payments',headers=auth(b),json={'order_id':oid,'method':'gpo'}); assert p.status_code==200,p.text
assert p.json()['commission_amount']==round(o['total']*0.04,2)
admin=client.post(f"/api/v1/payments/{p.json()['id']}/confirm",headers=auth(a)); assert admin.status_code==200,admin.text
assert client.post(f'/api/v1/orders/{oid}/status',headers=auth(d),json={'status':'a_caminho'}).status_code==200
assert client.post(f'/api/v1/orders/{oid}/status',headers=auth(d),json={'status':'entregue'}).status_code==200
print('SMOKE TEST OK')
