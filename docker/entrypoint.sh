#!/bin/sh
set -e

# Wait for PostgreSQL database connection if configured
if [ -n "$DATABASE_URL" ]; then
    echo "Checking database connection..."
    python << 'EOF'
import os
import sys
import time
import socket
from urllib.parse import urlparse

db_url = os.environ.get("DATABASE_URL", "")
if "postgres" in db_url:
    parsed = urlparse(db_url)
    host = parsed.hostname or "db"
    port = parsed.port or 5432
    print(f"Waiting for PostgreSQL on {host}:{port}...")
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=2):
                print("PostgreSQL is ready!")
                break
        except OSError:
            if time.time() - start_time > 45:
                print("Timed out waiting for PostgreSQL.")
                sys.exit(1)
            time.sleep(1)
EOF
fi

# Execute migrations if requested via env var
if [ "$AUTO_MIGRATE" = "true" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput
fi

# Execute passed container command
exec "$@"
