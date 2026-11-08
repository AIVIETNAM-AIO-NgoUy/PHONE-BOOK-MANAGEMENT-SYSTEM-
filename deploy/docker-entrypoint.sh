#!/bin/sh
set -eu

python - <<'EOF'
import os
import sys
import time
import psycopg

host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "5432"))
dbname = os.getenv("DB_NAME", "phonebook_db")
user = os.getenv("DB_USER", "postgres")
password = os.getenv("DB_PASSWORD", "")

max_attempts = 30
for attempt in range(1, max_attempts + 1):
    try:
        with psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=3,
        ):
            print("PostgreSQL is ready.", flush=True)
            sys.exit(0)
    except psycopg.Error as exc:
        print(
            f"Waiting for PostgreSQL ({attempt}/{max_attempts}): {exc}",
            file=sys.stderr,
            flush=True,
        )
        if attempt < max_attempts:
            time.sleep(2)

print("Timed out waiting for PostgreSQL.", file=sys.stderr, flush=True)
sys.exit(1)
EOF

cd /app/backend
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py seed_demo_accounts

exec gunicorn -c config/gunicorn.conf.py config.wsgi:application
