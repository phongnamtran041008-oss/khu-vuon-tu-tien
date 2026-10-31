#!/bin/sh
# Daily database backup, keeping the newest 7 (spec 15.2, stage 10). POSIX sh: runs in
# the postgres:16-alpine container of deploy/docker-compose.yml, on a Linux VM, or in
# Git Bash on Windows.
#
#   DATABASE_URL=postgresql://user:pass@host/db BACKUP_DIR=./backups sh tools/backup_db.sh
#   sh tools/backup_db.sh --loop        # forever: one now, then every day at BACKUP_HOUR_UTC
#
# PostgreSQL -> khuvuon-YYYYmmdd-HHMMSS.sql.gz (pg_dump, plain SQL; restore with psql)
# SQLite     -> khuvuon-YYYYmmdd-HHMMSS.db     (a consistent copy, safe while the server runs)
#
# Settings: DATABASE_URL (default sqlite server/dev.db), BACKUP_DIR (default ./backups),
#           BACKUP_KEEP (default 7), BACKUP_HOUR_UTC (default 20 = 03:00 in Việt Nam).
set -eu

BACKUP_DIR=${BACKUP_DIR:-./backups}
KEEP=${BACKUP_KEEP:-7}
HOUR=${BACKUP_HOUR_UTC:-20}

log() { echo "[backup $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

backup_once() {
    mkdir -p "$BACKUP_DIR"
    stamp=$(date -u +%Y%m%d-%H%M%S)
    url=${DATABASE_URL:-sqlite+aiosqlite:///server/dev.db}
    case "$url" in
        postgres*)
            # SQLAlchemy/asyncpg spellings -> what libpq (pg_dump) understands
            pgurl=$(printf '%s' "$url" | sed -e 's#^postgresql+asyncpg://#postgresql://#' \
                -e 's#^postgres://#postgresql://#' -e 's#\([?&]\)ssl=#\1sslmode=#')
            out="$BACKUP_DIR/khuvuon-$stamp.sql.gz"
            pg_dump --no-owner --no-privileges "$pgurl" > "$out.sql.tmp"
            gzip -9 -c "$out.sql.tmp" > "$out.tmp"
            rm -f "$out.sql.tmp"
            mv "$out.tmp" "$out"
            ;;
        sqlite*)
            path=${url#*:///}
            [ -f "$path" ] || { log "không thấy file SQLite: $path"; return 1; }
            out="$BACKUP_DIR/khuvuon-$stamp.db"
            if command -v sqlite3 >/dev/null 2>&1; then
                sqlite3 "$path" ".backup '$out.tmp'"
            else
                py=$(command -v python3 || command -v python)
                "$py" - "$path" "$out.tmp" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PY
            fi
            mv "$out.tmp" "$out"
            ;;
        *)
            log "DATABASE_URL không phải PostgreSQL hay SQLite: $url"
            return 1
            ;;
    esac
    log "đã lưu $out ($(wc -c < "$out" | tr -d ' ') byte)"
    # keep the newest $KEEP (names sort by time); paths may contain spaces
    ls -1 "$BACKUP_DIR"/khuvuon-* 2>/dev/null | grep -v '\.tmp$' | sort -r | tail -n +$((KEEP + 1)) |
        while IFS= read -r old; do
            rm -f "$old"
            log "xóa bản cũ $old"
        done
}

seconds_until_hour() {
    h=$(date -u +%H); m=$(date -u +%M); s=$(date -u +%S)
    now=$(( ${h#0} * 3600 + ${m#0} * 60 + ${s#0} ))
    wait=$(( (HOUR * 3600 - now + 86400) % 86400 ))
    [ "$wait" -gt 60 ] || wait=$((wait + 86400))
    echo "$wait"
}

if [ "${1:-}" = "--loop" ]; then
    log "sao lưu mỗi ngày lúc ${HOUR}:00 UTC, giữ $KEEP bản trong $BACKUP_DIR"
    while true; do
        backup_once || log "sao lưu thất bại, thử lại lần sau"
        sleep "$(seconds_until_hour)"
    done
else
    backup_once
fi
