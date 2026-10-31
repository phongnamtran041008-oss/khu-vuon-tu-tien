# Khu Vườn Tu Tiên — game server image (stage 10, spec 19).
#
# Multi-arch: python:3.12-slim and every dependency (asyncpg, uvloop, bcrypt...) ship
# wheels for linux/amd64 and linux/arm64, so the same file builds for Oracle's Ampere A1:
#   docker buildx build --platform linux/arm64,linux/amd64 -t khuvuon-server ./server
#
# Configuration is environment only (see deploy/.env.example). Render sets PORT itself.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt requirements-postgres.txt ./
RUN pip install -r requirements-postgres.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY data ./data
COPY maps ./maps

# Run as a normal user. /app/var is the only writable folder: a SQLite file goes there
# when no DATABASE_URL is given (quick tests); real deployments use PostgreSQL.
RUN useradd --create-home --uid 10001 vuon && mkdir -p /app/var && chown vuon /app/var
USER vuon

ENV ENV=prod \
    PORT=8000 \
    DATABASE_URL=sqlite+aiosqlite:////app/var/khuvuon.db

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'), timeout=4)"

# Client IPs behind a proxy are read by the app itself when TRUST_PROXY_HEADERS=1.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --ws-ping-interval 20 --ws-ping-timeout 30"]
