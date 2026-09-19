#!/bin/sh
set -e
python migrate_db.py
exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
