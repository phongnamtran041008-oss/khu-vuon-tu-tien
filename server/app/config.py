"""Server configuration from environment variables (.env supported, no extra deps)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = SERVER_DIR / "data"
PROTOCOL_VERSION = 5   # 2: stage 3 WebSocket world; 3: stage 4 combat (hp/shield in snapshots); 4: stage 5 guard bees; 5: stage 9 parties and bí cảnh
GAME_VERSION = "1.1.1"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(SERVER_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(url: str) -> str:
    """Accept the URLs hosts hand out and turn them into what SQLAlchemy + asyncpg take.
    Neon gives `postgresql://...?sslmode=require&channel_binding=require`; asyncpg knows
    neither parameter (it wants `ssl=require`), so they are translated or dropped."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
    if not url.startswith("postgresql+asyncpg://") or "?" not in url:
        return url
    base, query = url.split("?", 1)
    params = []
    for pair in query.split("&"):
        key, _, value = pair.partition("=")
        if key == "sslmode":
            if value != "disable":
                params.append(f"ssl={value}")
        elif key and key != "channel_binding":
            params.append(pair)
    return base + ("?" + "&".join(params) if params else "")


@dataclass
class Settings:
    env: str = field(default_factory=lambda: os.environ.get("ENV", "dev"))
    database_url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL", f"sqlite+aiosqlite:///{SERVER_DIR / 'dev.db'}"))
    jwt_secret: str = field(default_factory=lambda: os.environ.get("JWT_SECRET", "dev-secret-change-me-0123456789abcdef"))
    # Divides every SRS wait (spec 6.2): 1440 makes one day pass in one minute.
    time_scale: float = field(default_factory=lambda: float(os.environ.get("TIME_SCALE", "1")))
    # Unreviewed AI-written sentences/examples may be used only when this is on (spec 8.2).
    allow_unreviewed: bool = field(default_factory=lambda: _bool("ALLOW_UNREVIEWED", os.environ.get("ENV", "dev") == "dev"))
    auto_migrate: bool = field(default_factory=lambda: _bool("AUTO_MIGRATE", True))
    db_pool_size: int = field(default_factory=lambda: int(os.environ.get("DB_POOL_SIZE", "3")))
    # Stage 10: close pooled Postgres connections after this long without a query, so a free
    # Neon database can suspend (and stop counting compute hours) while nobody plays. 0 = never.
    db_idle_close_seconds: int = field(default_factory=lambda: int(os.environ.get("DB_IDLE_CLOSE_SECONDS") or "300"))
    maintenance_message: str = field(default_factory=lambda: os.environ.get("MAINTENANCE_MESSAGE", ""))
    trust_proxy_headers: bool = field(default_factory=lambda: _bool("TRUST_PROXY_HEADERS", False))
    rate_limit_enabled: bool = field(default_factory=lambda: _bool("RATE_LIMIT", True))
    # Merge server/data/balance/<profile>/*.json over the real numbers (dev only), e.g. "dev".
    balance_profile: str = field(default_factory=lambda: os.environ.get("BALANCE_PROFILE", "").strip())
    # Overrides balance economy.max_accounts_per_ip_per_day, e.g. for tools/load_bots.py on a dev server.
    accounts_per_ip: int | None = field(default_factory=lambda: int(os.environ["ACCOUNTS_PER_IP"])
                                        if os.environ.get("ACCOUNTS_PER_IP") else None)
    # Stage 10: these usernames get is_admin at startup and on registration (no shell needed
    # on hosts like Render). Comma separated; removing a name does not revoke anything.
    admin_usernames: list[str] = field(default_factory=lambda: [
        u.strip().casefold() for u in os.environ.get("ADMIN_USERNAMES", "").split(",") if u.strip()])
    # LAN worlds (Minecraft style): accounts come from Firebase Authentication. The Web API key
    # is the public one from the Firebase console; the server only uses it to check ID tokens.
    firebase_api_key: str = field(default_factory=lambda: os.environ.get("FIREBASE_API_KEY", "").strip())
    # The player who opened this world (their Firebase uid) is its admin.
    host_firebase_uid: str = field(default_factory=lambda: os.environ.get("HOST_FIREBASE_UID", "").strip())
    # Username + password accounts kept on this server (/auth/register, /auth/login). A world
    # opened from the game turns them off so every player is a Firebase account.
    local_accounts: bool = field(default_factory=lambda: _bool("LOCAL_ACCOUNTS", True))
    # Announce this server on the LAN so "Tham gia" lists it (UDP broadcast).
    lan_beacon: bool = field(default_factory=lambda: _bool("LAN_BEACON", False))
    lan_world_name: str = field(default_factory=lambda: os.environ.get("LAN_WORLD_NAME", "Khu Vườn").strip()[:40])
    lan_host_name: str = field(default_factory=lambda: os.environ.get("LAN_HOST_NAME", "").strip()[:40])
    lan_port: int = field(default_factory=lambda: int(os.environ.get("PORT") or "8000"))
    # Shown by /server/info so an old client can point players at the new exe.
    client_download_url: str = field(default_factory=lambda: os.environ.get("CLIENT_DOWNLOAD_URL", "").strip())
    latest_client_version: str = field(default_factory=lambda: os.environ.get("LATEST_CLIENT_VERSION", "").strip()
                                       or GAME_VERSION)

    def __post_init__(self):
        self.database_url = normalize_database_url(self.database_url)
        if self.env != "dev" and (self.jwt_secret == "dev-secret-change-me-0123456789abcdef"
                                  or len(self.jwt_secret) < 32):
            raise RuntimeError("JWT_SECRET must be set outside dev (at least 32 random characters)")
        if self.time_scale <= 0:
            raise RuntimeError("TIME_SCALE must be > 0")
        if self.env != "dev" and self.balance_profile:
            raise RuntimeError("BALANCE_PROFILE can only be used in dev")
        if self.env != "dev" and self.time_scale != 1:
            raise RuntimeError("TIME_SCALE can only be changed in dev")


settings = Settings()
