#!/bin/sh
set -e

python3 -m alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
