#!/bin/sh
set -eu

if [ "${DJANGO_DEBUG:-0}" != "1" ]; then
    case "${DJANGO_SECRET_KEY:-}" in
        ""|"change-me"|"dev-only-change-me")
            echo "DJANGO_SECRET_KEY doit être défini avec une valeur unique." >&2
            exit 1
            ;;
    esac
fi

if [ -n "${POSTGRES_DB:-}" ]; then
    python - <<'PY'
import os
import sys
import time

import django
from django.db import connections
from django.db.utils import OperationalError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

attempts = int(os.environ.get("DB_WAIT_ATTEMPTS", "30"))
delay = float(os.environ.get("DB_WAIT_DELAY", "2"))

for attempt in range(1, attempts + 1):
    try:
        connections["default"].ensure_connection()
        print("Base de données disponible.")
        break
    except OperationalError:
        if attempt == attempts:
            print(
                "Base de données indisponible après plusieurs tentatives.",
                file=sys.stderr,
            )
            raise
        time.sleep(delay)
PY
fi

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

if [ "$#" -eq 0 ]; then
    set -- gunicorn config.wsgi:application \
        --bind "0.0.0.0:${PORT:-8000}" \
        --workers "${GUNICORN_WORKERS:-3}" \
        --threads "${GUNICORN_THREADS:-2}" \
        --timeout "${GUNICORN_TIMEOUT:-60}" \
        --max-requests 1000 \
        --max-requests-jitter 100 \
        --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
        --access-logfile - \
        --error-logfile -
fi

exec "$@"
