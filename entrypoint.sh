#!/bin/sh
set -e

echo "Waiting for database..."
python -c "
import time, os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'carpool_system.settings')
django.setup()
from django.db import connections
for _ in range(30):
    try:
        connections['default'].ensure_connection()
        print('Database ready.')
        break
    except Exception:
        print('Waiting...')
        time.sleep(1)
"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"
