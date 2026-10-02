#!/bin/sh
set -e

python - <<'PY'
import os
import time

from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
last_error = None
for _ in range(30):
    try:
        engine = create_engine(url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        time.sleep(1)
else:
    raise SystemExit(f"database not ready: {last_error}")
PY

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
