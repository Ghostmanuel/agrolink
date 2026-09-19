import sqlite3
from pathlib import Path
from config import DATABASE_URL

def get_db():
    if not DATABASE_URL.startswith('sqlite:///'):
        raise RuntimeError('Configure o adaptador PostgreSQL antes da produção.')
    p=Path(DATABASE_URL.replace('sqlite:///','',1)); c=sqlite3.connect(p); c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON'); return c

def init_db():
    c=get_db(); c.executescript(SCHEMA)
    for n in ['Cereais','Hortícolas','Frutas','Tubérculos','Leguminosas','Pecuária','Avicultura','Outros']:
        c.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(n,))
    c.commit(); c.close()
SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,full_name TEXT NOT NULL,phone TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,province TEXT,address TEXT,profile_photo TEXT,bi_number_encrypted TEXT,bi_blind_hash TEXT,status TEXT DEFAULT 'active',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS producers(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL,company_name TEXT,farm_name TEXT,description TEXT,location TEXT,province TEXT,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,category_id INTEGER,name TEXT NOT NULL,description TEXT,price_kz REAL NOT NULL,quantity REAL NOT NULL,unit TEXT DEFAULT 'kg',photo TEXT,location TEXT,active INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(seller_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY AUTOINCREMENT,transporter_id INTEGER NOT NULL,plate TEXT UNIQUE NOT NULL,model TEXT,capacity_kg REAL,vehicle_type TEXT,photo TEXT,status TEXT DEFAULT 'FREE',latitude REAL,longitude REAL,last_ping_at TEXT,FOREIGN KEY(transporter_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,buyer_id INTEGER NOT NULL,seller_id INTEGER NOT NULL,product_id INTEGER NOT NULL,quantity REAL NOT NULL,delivery_address TEXT NOT NULL,transport_mode TEXT NOT NULL,delivery_distance_km REAL DEFAULT 0,delivery_fee_kz REAL DEFAULT 0,product_total_kz REAL NOT NULL,total_kz REAL NOT NULL,status TEXT DEFAULT 'PENDING_SELLER',payment_status TEXT DEFAULT 'NOT_STARTED',delivery_status TEXT DEFAULT 'NOT_REQUESTED',delivery_code_hash TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER UNIQUE NOT NULL,transporter_id INTEGER,vehicle_id INTEGER,origin TEXT,destination TEXT,distance_km REAL,eta_minutes INTEGER,status TEXT DEFAULT 'REQUESTED',delivered_at TEXT,proof_photo TEXT,proof_latitude REAL,proof_longitude REAL,proof_timestamp TEXT);
CREATE TABLE IF NOT EXISTS location_pings(id INTEGER PRIMARY KEY AUTOINCREMENT,delivery_id INTEGER,latitude REAL,longitude REAL,speed REAL,heading REAL,captured_at TEXT);
CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER UNIQUE);
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id INTEGER,sender_id INTEGER,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER,method TEXT,transaction_id TEXT UNIQUE,reference TEXT,amount_kz REAL,status TEXT DEFAULT 'PENDING',idempotency_key TEXT UNIQUE,provider_payload_hash TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS commissions(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER,beneficiary_type TEXT,rate REAL,base_amount_kz REAL,commission_kz REAL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT,body TEXT,read_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,metadata TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sync_queue(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,device_id TEXT,event_type TEXT,payload TEXT,synced INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
'''
