import sqlite3
from pathlib import Path
from config import DATABASE_URL

def get_db():
    if not DATABASE_URL.startswith("sqlite:///"): raise RuntimeError("DATABASE_URL não-SQLite requer adaptador PostgreSQL")
    p=Path(DATABASE_URL.replace("sqlite:///","",1)); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c

SCHEMA="""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,full_name TEXT NOT NULL,phone TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,province TEXT,address TEXT,profile_photo TEXT,bi_number_encrypted TEXT,bi_blind_hash TEXT,status TEXT DEFAULT 'active',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS producers(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL,company_name TEXT,farm_name TEXT,description TEXT,location TEXT,province TEXT,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,category_id INTEGER,name TEXT NOT NULL,description TEXT,price_kz REAL NOT NULL,quantity REAL NOT NULL,unit TEXT DEFAULT 'kg',photo TEXT,location TEXT,active INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(seller_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS transport_companies(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL,company_name TEXT NOT NULL,registration_number TEXT,location TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS drivers(id INTEGER PRIMARY KEY AUTOINCREMENT,company_user_id INTEGER NOT NULL,full_name TEXT NOT NULL,phone TEXT,bi_number_encrypted TEXT,bi_blind_hash TEXT,license_number_encrypted TEXT,photo TEXT,status TEXT DEFAULT 'active',created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(company_user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY AUTOINCREMENT,transporter_id INTEGER NOT NULL,company_id INTEGER,driver_id INTEGER,plate TEXT UNIQUE NOT NULL,model TEXT,capacity_kg REAL,vehicle_type TEXT,photo TEXT,status TEXT DEFAULT 'FREE',latitude REAL,longitude REAL,last_ping_at TEXT,FOREIGN KEY(transporter_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,buyer_id INTEGER NOT NULL,seller_id INTEGER NOT NULL,product_id INTEGER NOT NULL,quantity REAL NOT NULL,delivery_address TEXT NOT NULL,transport_mode TEXT NOT NULL DEFAULT 'pending',delivery_distance_km REAL DEFAULT 0,delivery_fee_kz REAL DEFAULT 0,product_total_kz REAL NOT NULL,total_kz REAL NOT NULL,status TEXT DEFAULT 'PENDING_SELLER',payment_status TEXT DEFAULT 'NOT_STARTED',delivery_status TEXT DEFAULT 'NOT_REQUESTED',delivery_code_hash TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER UNIQUE NOT NULL,transporter_id INTEGER,vehicle_id INTEGER,origin TEXT,destination TEXT,distance_km REAL,eta_minutes INTEGER,status TEXT DEFAULT 'REQUESTED',delivered_at TEXT,proof_photo TEXT,proof_latitude REAL,proof_longitude REAL,proof_timestamp TEXT);
CREATE TABLE IF NOT EXISTS location_pings(id INTEGER PRIMARY KEY AUTOINCREMENT,delivery_id INTEGER,latitude REAL,longitude REAL,speed REAL,heading REAL,captured_at TEXT);
CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER UNIQUE);
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id INTEGER,sender_id INTEGER,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER,method TEXT,transaction_id TEXT UNIQUE,reference TEXT,amount_kz REAL,status TEXT DEFAULT 'PENDING',idempotency_key TEXT UNIQUE,provider_payload_hash TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS commissions(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER,beneficiary_type TEXT,rate REAL,base_amount_kz REAL,commission_kz REAL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT,body TEXT,read_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id INTEGER,action TEXT,entity_type TEXT,entity_id INTEGER,metadata TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sync_queue(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,device_id TEXT,event_type TEXT,payload TEXT,synced INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS password_reset_tokens(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,token_hash TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT,attempts INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS stored_files(id TEXT PRIMARY KEY,owner_id INTEGER,entity_type TEXT,entity_id INTEGER,filename TEXT,content_type TEXT,size_bytes INTEGER,storage_key TEXT NOT NULL,private INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(owner_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS settlements(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,beneficiary_user_id INTEGER NOT NULL,beneficiary_type TEXT NOT NULL,gross_amount_kz REAL NOT NULL,commission_kz REAL NOT NULL,net_amount_kz REAL NOT NULL,status TEXT DEFAULT 'PENDING',payment_reference TEXT,paid_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(order_id,beneficiary_type),FOREIGN KEY(order_id) REFERENCES orders(id),FOREIGN KEY(beneficiary_user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS favorites(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,product_id INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,product_id),FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(product_id) REFERENCES products(id));
CREATE TABLE IF NOT EXISTS ratings(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,rater_id INTEGER NOT NULL,target_id INTEGER NOT NULL,target_role TEXT NOT NULL,score INTEGER NOT NULL,comment TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(order_id,rater_id,target_id),FOREIGN KEY(order_id) REFERENCES orders(id),FOREIGN KEY(rater_id) REFERENCES users(id),FOREIGN KEY(target_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS disputes(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,opened_by INTEGER NOT NULL,reason TEXT NOT NULL,description TEXT,status TEXT DEFAULT 'OPEN',resolution TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,resolved_at TEXT,FOREIGN KEY(order_id) REFERENCES orders(id),FOREIGN KEY(opened_by) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS profile_verifications(user_id INTEGER PRIMARY KEY,verified INTEGER DEFAULT 0,verified_at TEXT,verified_by INTEGER,FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(verified_by) REFERENCES users(id));
"""

def _ensure_columns(c, table, columns):
    existing = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

def init_db():
    c=get_db()
    c.executescript(SCHEMA)
    for n in ["Cereais","Hortícolas","Frutas","Tubérculos","Leguminosas","Pecuária","Avicultura","Outros"]:
        c.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)",(n,))

    # Compatibility migration: older v10/v11 databases may have fewer columns.
    _ensure_columns(c, "users", {
        "profile_photo":"TEXT", "bi_number_encrypted":"TEXT", "bi_blind_hash":"TEXT",
        "status":"TEXT DEFAULT 'active'", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"
    })
    _ensure_columns(c, "producers", {
        "company_name":"TEXT", "farm_name":"TEXT", "description":"TEXT", "location":"TEXT", "province":"TEXT"
    })
    _ensure_columns(c, "products", {
        "category_id":"INTEGER", "description":"TEXT", "price_kz":"REAL NOT NULL DEFAULT 0",
        "quantity":"REAL NOT NULL DEFAULT 0", "unit":"TEXT DEFAULT 'kg'", "photo":"TEXT",
        "location":"TEXT", "active":"INTEGER DEFAULT 1", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"
    })
    _ensure_columns(c, "transport_companies", {"company_name":"TEXT", "registration_number":"TEXT", "location":"TEXT", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"})
    _ensure_columns(c, "drivers", {"company_user_id":"INTEGER", "phone":"TEXT", "bi_number_encrypted":"TEXT", "bi_blind_hash":"TEXT", "license_number_encrypted":"TEXT", "photo":"TEXT", "status":"TEXT DEFAULT 'active'", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"})
    _ensure_columns(c, "vehicles", {
        "model":"TEXT", "capacity_kg":"REAL", "vehicle_type":"TEXT", "photo":"TEXT",
        "status":"TEXT DEFAULT 'FREE'", "latitude":"REAL", "longitude":"REAL", "last_ping_at":"TEXT", "company_id":"INTEGER", "driver_id":"INTEGER"
    })
    _ensure_columns(c, "orders", {
        "transport_mode":"TEXT NOT NULL DEFAULT 'pending'", "delivery_distance_km":"REAL DEFAULT 0",
        "delivery_fee_kz":"REAL DEFAULT 0", "product_total_kz":"REAL NOT NULL DEFAULT 0",
        "total_kz":"REAL NOT NULL DEFAULT 0", "status":"TEXT DEFAULT 'PENDING_SELLER'",
        "payment_status":"TEXT DEFAULT 'NOT_STARTED'", "delivery_status":"TEXT DEFAULT 'NOT_REQUESTED'",
        "delivery_code_hash":"TEXT", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"
    })
    _ensure_columns(c, "deliveries", {
        "transporter_id":"INTEGER", "vehicle_id":"INTEGER", "origin":"TEXT", "destination":"TEXT",
        "distance_km":"REAL", "eta_minutes":"INTEGER", "status":"TEXT DEFAULT 'REQUESTED'",
        "delivered_at":"TEXT", "proof_photo":"TEXT", "proof_latitude":"REAL",
        "proof_longitude":"REAL", "proof_timestamp":"TEXT"
    })
    _ensure_columns(c, "location_pings", {
        "delivery_id":"INTEGER", "latitude":"REAL", "longitude":"REAL", "speed":"REAL", "heading":"REAL", "captured_at":"TEXT"
    })
    _ensure_columns(c, "conversations", {"order_id":"INTEGER"})
    _ensure_columns(c, "chat_messages", {"conversation_id":"INTEGER", "sender_id":"INTEGER", "body":"TEXT", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP", "attachment_file_id":"TEXT"})
    _ensure_columns(c, "notifications", {"user_id":"INTEGER", "title":"TEXT", "body":"TEXT", "read_at":"TEXT", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"})
    _ensure_columns(c, "audit_logs", {"actor_id":"INTEGER", "action":"TEXT", "entity_type":"TEXT", "entity_id":"INTEGER", "metadata":"TEXT", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"})
    _ensure_columns(c, "sync_queue", {"user_id":"INTEGER", "device_id":"TEXT", "event_type":"TEXT", "payload":"TEXT", "synced":"INTEGER DEFAULT 0", "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"})
    _ensure_columns(c, "payments", {
        "method":"TEXT", "transaction_id":"TEXT", "reference":"TEXT", "amount_kz":"REAL",
        "status":"TEXT DEFAULT 'PENDING'", "idempotency_key":"TEXT", "provider_payload_hash":"TEXT",
        "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"
    })
    _ensure_columns(c, "commissions", {
        "beneficiary_type":"TEXT", "rate":"REAL", "base_amount_kz":"REAL", "commission_kz":"REAL",
        "created_at":"TEXT DEFAULT CURRENT_TIMESTAMP"
    })
    c.execute("CREATE INDEX IF NOT EXISTS idx_reset_tokens_user ON password_reset_tokens(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_seller ON orders(seller_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ratings_target ON ratings(target_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_disputes_order ON disputes(order_id)")
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ("delivery_base_fee","0"))
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ("delivery_rate_per_km","150"))
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ("delivery_default_capacity_kg","5000"))
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ("maintenance_mode","false"))
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ("support_email","nuvemjv69@gmail.com"))
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ("support_phone_1","+244 929 715 406"))
    c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", ("support_phone_2","+244 934 678 932"))
    c.commit(); c.close()
