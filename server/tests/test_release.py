"""Stage 10: database URLs from hosting providers, backups, and the deployment files."""
import datetime as dt
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import normalize_database_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import backup_db  # noqa: E402


def test_database_urls_from_hosts():
    neon = "postgresql://u:p@ep-cool-1.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert normalize_database_url(neon) == \
        "postgresql+asyncpg://u:p@ep-cool-1.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
    assert normalize_database_url("postgres://u:p@db:5432/khuvuon") == "postgresql+asyncpg://u:p@db:5432/khuvuon"
    assert normalize_database_url("postgresql://u:p@h/d?sslmode=disable&application_name=kv") == \
        "postgresql+asyncpg://u:p@h/d?application_name=kv"
    assert normalize_database_url("sqlite+aiosqlite:///./dev.db") == "sqlite+aiosqlite:///./dev.db"
    assert backup_db.libpq_url("postgresql+asyncpg://u:p@h/d?ssl=require") == "postgresql://u:p@h/d?sslmode=require"


def _sqlite_with_row(path: Path, value: str) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    con.execute("INSERT INTO t VALUES (?)", (value,))
    con.commit()
    con.close()


def test_python_backup_copies_and_keeps_seven(tmp_path):
    db = tmp_path / "live.db"
    _sqlite_with_row(db, "Linh Thạch")
    out_dir = tmp_path / "backups"
    start = dt.datetime(2026, 11, 1, 20, 0, tzinfo=dt.timezone.utc)
    for day in range(10):
        out = backup_db.backup(f"sqlite+aiosqlite:///{db}", out_dir, keep=7, now=start + dt.timedelta(days=day))
    files = sorted(p.name for p in out_dir.iterdir())
    assert len(files) == 7 and files[0] == "khuvuon-20261104-200000.db" and out.name == files[-1]
    assert sqlite3.connect(out).execute("SELECT v FROM t").fetchone() == ("Linh Thạch",)


def _bash() -> str | None:
    if sys.platform != "win32":
        return shutil.which("sh")
    git = shutil.which("git")   # Git for Windows: <git>/cmd/git.exe (or deeper) beside <git>/bin/bash.exe
    roots = list(Path(git).resolve().parents)[:3] if git else []
    roots += [Path(r"C:\Program Files\Git")]
    for root in roots:
        for p in (root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"):
            if p.exists():
                return str(p)
    return None


@pytest.mark.skipif(_bash() is None, reason="no POSIX shell")
def test_shell_backup_postgres_and_rotation(tmp_path):
    """tools/backup_db.sh, as the Docker backup service runs it, with a stand-in pg_dump."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "pg_dump").write_text('#!/bin/sh\necho "-- dump of $3"\necho "CREATE TABLE users ();"\n',
                                      newline="\n")
    (fake_bin / "pg_dump").chmod(0o755)
    out_dir = tmp_path / "sao luu"              # a folder name with a space, like "khu vườn tu tiên"
    out_dir.mkdir()
    for i in range(9):                           # older backups already there
        (out_dir / f"khuvuon-2026010{i}-000000.sql.gz").write_bytes(b"old")
    env = dict(os.environ, BACKUP_DIR=str(out_dir), BACKUP_KEEP="7",
               DATABASE_URL="postgresql+asyncpg://khuvuon:pw@db:5432/khuvuon?ssl=require",
               PATH=str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([_bash(), str(ROOT / "tools" / "backup_db.sh")], env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    files = sorted(p.name for p in out_dir.iterdir())
    assert len(files) == 7 and "khuvuon-20260100-000000.sql.gz" not in files
    import gzip
    newest = out_dir / files[-1]
    text = gzip.decompress(newest.read_bytes()).decode()
    assert "postgresql://khuvuon:pw@db:5432/khuvuon?sslmode=require" in text and "CREATE TABLE users" in text


def test_deploy_files_fit_together():
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text("utf-8"))
    svc = compose["services"]
    assert set(svc) == {"db", "server", "caddy", "backup"}
    assert svc["server"]["build"] == "../server" and svc["caddy"]["profiles"] == ["https"]
    assert svc["server"]["ports"] == ["127.0.0.1:8000:8000"]          # never public without the proxy
    assert svc["backup"]["entrypoint"][-1] == "--loop"
    render = yaml.safe_load((ROOT / "render.yaml").read_text("utf-8"))["services"][0]
    assert render["plan"] == "free" and render["healthCheckPath"] == "/healthz"
    keys = {e["key"]: e for e in render["envVars"]}
    assert keys["DATABASE_URL"]["sync"] is False and keys["JWT_SECRET"]["generateValue"] is True
    docker = (ROOT / "server" / "Dockerfile").read_text("utf-8")
    assert "FROM python:3.12-slim" in docker and "requirements-postgres.txt" in docker and "${PORT" in docker
    for name in ("alembic", "app", "data", "maps"):
        assert f"COPY {name} ./{name}" in docker
    env_example = (ROOT / "deploy" / ".env.example").read_text("utf-8")
    for key in ("POSTGRES_PASSWORD", "JWT_SECRET", "DOMAIN", "ADMIN_USERNAMES", "CLIENT_DOWNLOAD_URL"):
        assert f"\n{key}=" in env_example


def test_prod_settings_refuse_a_weak_secret(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("TIME_SCALE", "1")
    monkeypatch.setenv("BALANCE_PROFILE", "")
    for bad in ("", "short", "dev-secret-change-me-0123456789abcdef"):
        monkeypatch.setenv("JWT_SECRET", bad)
        with pytest.raises(RuntimeError):
            Settings()
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    assert Settings().env == "prod"
