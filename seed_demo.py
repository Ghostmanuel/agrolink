import os, base64
from app import SessionLocal, User, Vehicle, Product, hash_password

def main():
    s=SessionLocal()
    try:
        # Demo-only: wipe application data in the selected demo database.
        from app import ChatMessage, Conversation, LocationPing, Payment, Notification, Order, PasswordReset
        for model in [ChatMessage,Conversation,LocationPing,Payment,Notification,Order,Product,Vehicle,PasswordReset,User]: s.query(model).delete()
        s.commit()
        ph=None
        try: ph='data:image/jpeg;base64,'+base64.b64encode(open('LogoAgrolink.jpeg','rb').read()).decode()
        except Exception: pass
        users=[
          User(name='Cliente Demonstração',phone='900000001',password_hash=hash_password('Demo1234'),role='buyer',province='Luanda',company_name='AgroLink Cliente',address='Talatona, Luanda',photo_data=ph,verified=True),
          User(name='Fazenda Esperança',phone='900000002',password_hash=hash_password('Demo1234'),role='farmer',province='Huambo',company_name='Fazenda Esperança',address='Huambo, Angola',photo_data=ph,verified=True),
          User(name='Motorista Agro Transporte',phone='900000003',password_hash=hash_password('Demo1234'),role='driver',province='Huambo',company_name='Agro Transporte, Lda.',address='Huambo, Angola',photo_data=ph,verified=True),
          User(name='Administrador AgroLink',phone='900000000',password_hash=hash_password('Admin1234'),role='admin',province='Luanda',company_name='Agro-Link Angola',address='Luanda, Angola',photo_data=ph,verified=True),
        ]
        s.add_all(users); s.flush(); farmer,driver=users[1],users[2]
        s.add(Vehicle(driver_id=driver.id,plate='LD-24-26-HU',model='Toyota Dyna',vehicle_type='Camião',capacity_kg=5000,photo_data=ph,status='livre',latitude=-12.7766,longitude=15.7392))
        s.add_all([
          Product(producer_id=farmer.id,name='Milho amarelo',category='Grãos',price=850,quantity=5000,unit='kg',province='Huambo',description='Milho produzido localmente pela Fazenda Esperança.',photo_data=ph),
          Product(producer_id=farmer.id,name='Tomate fresco',category='Hortícolas',price=1200,quantity=1200,unit='kg',province='Huambo',description='Tomate fresco para revenda e consumo.',photo_data=ph)
        ])
        s.commit()
        print('Demo criada.')
        print('Comprador: 900000001 / Demo1234')
        print('Agricultor: 900000002 / Demo1234')
        print('Transportador: 900000003 / Demo1234')
        print('Admin: 900000000 / Admin1234')
    finally: s.close()
if __name__=='__main__': main()
