"""Character creation and abode position (spec 7.2). Everyone starts identical:
Phàm Nhân, Áo Vải Phàm Nhân, no weapon. Only hair and body shape are chosen."""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance
from ..moderation import contains_banned
from ..models import Character, User

NAME_RE = re.compile(r"^[^\W_]+( [^\W_]+)*$")  # letters/digits (any script), single spaces


class CharacterError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("character")


def view(c: Character) -> dict:
    return {"display_name": c.display_name, "realm": c.realm, "realm_stage": c.realm_stage,
            "cultivation_xp": c.cultivation_xp, "hp": c.hp, "max_hp": c.max_hp, "qi": c.qi,
            "zone_id": c.zone_id, "x": c.x, "y": c.y, "facing": c.facing,
            "appearance": c.appearance, "outfit": cfg()["starting_outfit"]}


async def create(db: AsyncSession, user: User, display_name: str, appearance: dict) -> dict:
    if await db.get(Character, user.id):
        raise CharacterError(409, "has_character", "Bạn đã có nhân vật rồi.")
    c = cfg()
    name = unicodedata.normalize("NFC", (display_name or "").strip())
    name = re.sub(r"\s+", " ", name)
    if not (c["display_name_min"] <= len(name) <= c["display_name_max"]) or not NAME_RE.match(name):
        raise CharacterError(400, "bad_name",
                             f"Tên nhân vật dài {c['display_name_min']}–{c['display_name_max']} ký tự, "
                             "chỉ gồm chữ, số và khoảng trắng.")
    if contains_banned(name):
        raise CharacterError(400, "banned_name", "Tên này không phù hợp, hãy chọn tên khác.")
    taken = (await db.execute(select(Character.user_id).where(
        func.lower(Character.display_name) == name.lower()))).first()
    if taken:
        raise CharacterError(409, "name_taken", "Tên này đã có người dùng.")
    app = appearance or {}
    hair_color = app.get("hair_color", c["hair_colors"][0])
    hair_style = app.get("hair_style", c["hair_styles"][0])
    body = app.get("body", c["bodies"][0])
    if hair_color not in c["hair_colors"] or hair_style not in c["hair_styles"] or body not in c["bodies"]:
        raise CharacterError(400, "bad_appearance", "Lựa chọn ngoại hình không hợp lệ.")
    spawn = c["abode_spawn"]
    ch = Character(user_id=user.id, display_name=name, realm="pham_nhan", realm_stage=0,
                   cultivation_xp=0, hp=100, max_hp=100, qi=50,
                   stats={"atk": 5, "def": 5, "spd": 5, "crit": 0, "ink_res": 0},
                   zone_id="abode", x=spawn["x"], y=spawn["y"], facing="down",
                   appearance={"hair_color": hair_color, "hair_style": hair_style, "body": body},
                   hotbar={})
    db.add(ch)
    await db.flush()
    return view(ch)


async def save_position(db: AsyncSession, user: User, zone_id: str, x: float, y: float, facing: str) -> dict:
    ch = await db.get(Character, user.id)
    if ch is None:
        raise CharacterError(404, "no_character", "Bạn chưa tạo nhân vật.")
    if zone_id != "abode":  # the shared world moves through the WebSocket server (stage 3)
        raise CharacterError(400, "bad_zone", "Chỉ lưu vị trí trong động phủ.")
    from ..realtime.world import world
    if world.in_world(user.id):  # a late save from the abode must not pull the character back
        return {"ok": False, "ignored": "in_world"}
    if not (0 <= x <= 2000 and 0 <= y <= 2000) or facing not in ("up", "down", "left", "right"):
        raise CharacterError(400, "bad_position", "Vị trí không hợp lệ.")
    ch.zone_id, ch.x, ch.y, ch.facing = zone_id, float(x), float(y), facing
    return {"ok": True}
