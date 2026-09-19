import os, sqlite3, shutil, tempfile
DB=os.getenv("DATABASE_URL","sqlite:///./agrolink.db")
if not DB.startswith("sqlite:///"):
    print("Migration script: DATABASE_URL is not SQLite; SQLAlchemy app migrations will run on startup.")
    raise SystemExit(0)
path=DB.replace("sqlite:///","")
con=sqlite3.connect(path)
cur=con.cursor()
def cols(table): return {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}
def add(table,name,typ):
    if name not in cols(table):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
# additive columns
for t,items in {
"users":[("photo_data","TEXT"),("company_name","VARCHAR(160)"),("address","VARCHAR(240)"),("latitude","FLOAT"),("longitude","FLOAT"),("updated_at","TIMESTAMP")],
"vehicles":[("photo_data","TEXT"),("status","VARCHAR(20)"),("latitude","FLOAT"),("longitude","FLOAT"),("location_at","TIMESTAMP")],
"products":[("photo_data","TEXT")],
"orders":[("seller_id","INTEGER"),("delivery_address","VARCHAR(240)"),("buyer_reviewed","BOOLEAN"),("seller_reviewed","BOOLEAN"),("driver_reviewed","BOOLEAN"),("review_confirmed_at","TIMESTAMP")],
"conversations":[("driver_id","INTEGER"),("order_id","INTEGER")],
"payments":[("provider","VARCHAR(40)"),("entity","VARCHAR(40)"),("reference_number","VARCHAR(80)"),("gateway_reference","VARCHAR(120)"),("gateway_status","VARCHAR(50)"),("beneficiary_name","VARCHAR(160)"),("beneficiary_bank","VARCHAR(120)"),("beneficiary_iban","VARCHAR(40)"),("beneficiary_phone","VARCHAR(30)"),("expires_at","TIMESTAMP"),("confirmed_at","TIMESTAMP")]
}.items():
    for n,ty in items: add(t,n,ty)
# Rebuild vehicles if the legacy table still has UNIQUE(driver_id), allowing multiple vehicles per transport provider.
idx=list(cur.execute("PRAGMA index_list(vehicles)"))
unique_driver=False
for row in idx:
    # row: seq,name,unique,origin,partial
    if row[2]:
        cols_idx=[r[2] for r in cur.execute(f"PRAGMA index_info({row[1]})")]
        if cols_idx==["driver_id"]: unique_driver=True
if unique_driver:
    cur.execute("ALTER TABLE vehicles RENAME TO vehicles_legacy")
    cur.execute("""CREATE TABLE vehicles (
      id INTEGER NOT NULL PRIMARY KEY,
      driver_id INTEGER NOT NULL,
      plate VARCHAR(20) NOT NULL,
      model VARCHAR(80) NOT NULL DEFAULT '',
      vehicle_type VARCHAR(40) NOT NULL DEFAULT 'camião',
      capacity_kg FLOAT NOT NULL DEFAULT 0,
      photo_data TEXT,
      status VARCHAR(20) DEFAULT 'livre',
      latitude FLOAT, longitude FLOAT, location_at TIMESTAMP,
      FOREIGN KEY(driver_id) REFERENCES users(id)
    )""")
    oldcols=cols('vehicles_legacy')
    select_photo='photo_data' if 'photo_data' in oldcols else 'NULL'
    select_status='status' if 'status' in oldcols else "'livre'"
    select_lat='latitude' if 'latitude' in oldcols else 'NULL'
    select_lon='longitude' if 'longitude' in oldcols else 'NULL'
    select_at='location_at' if 'location_at' in oldcols else 'NULL'
    cur.execute(f"""INSERT INTO vehicles(id,driver_id,plate,model,vehicle_type,capacity_kg,photo_data,status,latitude,longitude,location_at)
      SELECT id,driver_id,plate,model,vehicle_type,capacity_kg,{select_photo},{select_status},{select_lat},{select_lon},{select_at} FROM vehicles_legacy""")
    cur.execute("DROP TABLE vehicles_legacy")
cur.execute("""CREATE TABLE IF NOT EXISTS payment_events (id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL, event_type VARCHAR(60) NOT NULL, gateway_event_id VARCHAR(120), payload TEXT, created_at TIMESTAMP)""")
con.commit(); con.close(); print("AgroLink DB migration concluída:",path)
