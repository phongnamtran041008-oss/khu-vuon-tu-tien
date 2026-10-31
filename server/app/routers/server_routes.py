"""Server status (spec 15.5, stage 10): /server/info for the client and for people.

The game asks for JSON; a browser (Accept: text/html) gets a small status page with the
download link, so the same address can be shared with players. /healthz is for hosting
health checks: it never touches the database, so Neon's free compute is not kept awake.
"""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import clock, server_state
from ..config import GAME_VERSION, PROTOCOL_VERSION, settings

router = APIRouter()


def info() -> dict:
    from ..realtime.world import world
    now = clock.now()
    return {"name": "Khu Vườn Tu Tiên", "version": GAME_VERSION, "protocol_version": PROTOCOL_VERSION,
            "server_time": now.isoformat() + "Z", "local_date": clock.local_date(now),
            "time_scale": settings.time_scale, "env": settings.env,
            "maintenance_message": server_state.maintenance_message or None,
            "announcement": server_state.announcement or None,
            "online": len(world.sessions), "uptime_seconds": server_state.uptime_seconds(),
            "latest_client_version": settings.latest_client_version,
            "client_download_url": settings.client_download_url or None,
            "auth": "firebase" if settings.firebase_api_key else "local",
            "local_accounts": settings.local_accounts,
            "world_name": settings.lan_world_name if settings.lan_beacon else None}


def _wants_html(request: Request) -> bool:
    fmt = request.query_params.get("format")
    if fmt:
        return fmt == "html"
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept


def _uptime(seconds: int) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    return (f"{d} ngày " if d else "") + f"{h} giờ {rem // 60} phút"


def _page(i: dict) -> str:
    rows = [("Phiên bản máy chủ", i["version"]), ("Giao thức", str(i["protocol_version"])),
            ("Đang online", str(i["online"])), ("Đã chạy", _uptime(i["uptime_seconds"])),
            ("Giờ máy chủ (UTC)", i["server_time"][:19].replace("T", " "))]
    if i["env"] == "dev":
        rows.append(("Môi trường", f"dev, TIME_SCALE = {i['time_scale']:g}"))
    table = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in rows)
    notices = ""
    if i["maintenance_message"]:
        notices += f'<p class="warn">🛠 {escape(i["maintenance_message"])}</p>'
    if i["announcement"]:
        notices += f'<p class="note">📣 {escape(i["announcement"])}</p>'
    download = ""
    if i["client_download_url"]:
        download = (f'<p><a class="btn" href="{escape(i["client_download_url"], quote=True)}">'
                    f'Tải game (bản {escape(i["latest_client_version"])})</a></p>')
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Khu Vườn Tu Tiên · máy chủ</title>
<style>
:root {{ --paper:#F4EBD9; --ink:#2B2B2B; --bamboo:#6A994E; --cinnabar:#BC4749; --gold:#E9C46A; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 system-ui, sans-serif; }}
main {{ max-width:560px; margin:0 auto; padding:24px 16px; }}
h1 {{ margin:0 0 4px; font-size:26px; }} .sub {{ margin:0 0 20px; color:#5A5A5A; }}
.ok {{ display:inline-block; padding:2px 10px; border-radius:12px; background:var(--bamboo); color:#fff; }}
table {{ width:100%; border-collapse:collapse; margin:16px 0; }}
th, td {{ text-align:left; padding:6px 4px; border-bottom:1px solid #d9ccb0; }} th {{ font-weight:600; width:45%; }}
.warn {{ background:#f6d7d7; border-left:4px solid var(--cinnabar); padding:8px 12px; }}
.note {{ background:#f8ecc4; border-left:4px solid var(--gold); padding:8px 12px; }}
.btn {{ display:inline-block; padding:10px 18px; background:var(--ink); color:var(--paper); text-decoration:none;
        border-radius:6px; }}
small {{ color:#5A5A5A; }}
</style></head>
<body><main>
<h1>Khu Vườn Tu Tiên · 字园仙途</h1>
<p class="sub"><span class="ok">Máy chủ đang chạy</span></p>
{notices}
<table>{table}</table>
{download}
<p><small>Trong game: Cài đặt → Máy chủ → dán địa chỉ trang này (bỏ phần /server/info).
Dữ liệu cho máy: <a href="/server/info?format=json">/server/info?format=json</a></small></p>
</main></body></html>"""


@router.get("/server/info")
async def server_info(request: Request):
    i = info()
    if _wants_html(request):
        return HTMLResponse(_page(i))
    return i


@router.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/server/info")


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


@router.get("/server/stats")
async def server_stats():
    """Counts and tick timings of the world loop (no personal data); used by tools/load_bots.py."""
    from ..realtime.world import world
    return world.status()
