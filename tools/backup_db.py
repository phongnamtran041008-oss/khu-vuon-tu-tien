#!/usr/bin/env python3
"""Database backup for Windows (or anywhere with Python), keeping the newest 7 (stage 10).
Same files as tools/backup_db.sh, which the Docker setup uses.

    python tools/backup_db.py                     # the DATABASE_URL of server/.env (default server/dev.db)
    python tools/backup_db.py --keep 14 --dir D:/sao-luu
    python tools/backup_db.py --database-url "postgresql://user:pass@host/db?sslmode=require"

SQLite: a consistent copy through SQLite's backup API (safe while the server runs).
PostgreSQL: needs `pg_dump` on PATH (PostgreSQL client tools), output gzip-compressed.
Run it every day with Windows Task Scheduler (docs/DEPLOY.md, "Sao lưu").
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"


def default_url() -> str:
    """DATABASE_URL from the environment or server/.env, like the server reads it."""
    url = os.environ.get("DATABASE_URL")
    env = SERVER / ".env"
    if not url and env.exists():
        for line in env.read_text("utf-8").splitlines():
            k, _, v = line.strip().partition("=")
            if k.strip() == "DATABASE_URL" and v.strip():
                url = v.strip().strip('"').strip("'")
    return url or f"sqlite+aiosqlite:///{SERVER / 'dev.db'}"


def sqlite_path(url: str) -> Path:
    p = Path(url.split(":///", 1)[1])
    return p if p.is_absolute() else (SERVER / p).resolve()   # relative paths are from server/, like the server


def libpq_url(url: str) -> str:
    url = re.sub(r"^postgres(ql)?(\+asyncpg)?://", "postgresql://", url)
    return re.sub(r"([?&])ssl=", r"\1sslmode=", url)


def backup(url: str, out_dir: Path, keep: int, now: dt.datetime | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%d-%H%M%S")
    if url.startswith("sqlite"):
        src_path = sqlite_path(url)
        if not src_path.exists():
            raise SystemExit(f"Không thấy file SQLite: {src_path}")
        out = out_dir / f"khuvuon-{stamp}.db"
        tmp = out.with_suffix(".db.tmp")
        src, dst = sqlite3.connect(src_path), sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        tmp.replace(out)
    elif url.startswith("postgres"):
        if not shutil.which("pg_dump"):
            raise SystemExit("Cần pg_dump (cài PostgreSQL client tools) để sao lưu PostgreSQL.")
        out = out_dir / f"khuvuon-{stamp}.sql.gz"
        tmp = out.with_suffix(".gz.tmp")
        dump = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", libpq_url(url)],
                              capture_output=True, check=False)
        if dump.returncode != 0:
            raise SystemExit("pg_dump lỗi: " + dump.stderr.decode("utf-8", "replace")[-500:])
        with gzip.open(tmp, "wb", compresslevel=9) as f:
            f.write(dump.stdout)
        tmp.replace(out)
    else:
        raise SystemExit(f"DATABASE_URL không phải PostgreSQL hay SQLite: {url}")
    old = sorted((p for p in out_dir.glob("khuvuon-*") if not p.name.endswith(".tmp")), reverse=True)[keep:]
    for p in old:
        p.unlink()
    return out


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--dir", default=str(ROOT / "backups"))
    ap.add_argument("--keep", type=int, default=int(os.environ.get("BACKUP_KEEP", "7")))
    args = ap.parse_args(argv)
    out = backup(args.database_url or default_url(), Path(args.dir), max(1, args.keep))
    print(f"Đã sao lưu: {out} ({out.stat().st_size:,} byte). Giữ {args.keep} bản mới nhất trong {out.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
