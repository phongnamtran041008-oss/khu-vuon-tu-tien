"""Read-only game data: items, equipment, pills, skills, quests, monsters, bees, fish, rods,
baits, recipes, pets (server/data)."""
from __future__ import annotations

import json
from functools import lru_cache

from ..config import DATA_DIR


def _load(rel: str) -> dict:
    data = json.loads((DATA_DIR / rel).read_text("utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def equipment() -> dict:
    return _load("items/equipment.json")


@lru_cache(maxsize=1)
def pills() -> dict:
    return _load("items/pills.json")


@lru_cache(maxsize=1)
def materials() -> dict:
    return _load("items/materials.json")


@lru_cache(maxsize=1)
def skills() -> dict:
    return _load("skills.json")


@lru_cache(maxsize=1)
def quests() -> dict:
    return _load("quests.json")


@lru_cache(maxsize=1)
def monsters() -> dict:
    return _load("creatures/monsters.json")


@lru_cache(maxsize=1)
def bees() -> dict:
    """Linh Phong species (built and verified by tools/build_bees.py)."""
    return _load("creatures/bees.json")


@lru_cache(maxsize=1)
def fish() -> dict:
    """Fish species (built and verified by tools/build_fish.py)."""
    return _load("creatures/fish.json")


@lru_cache(maxsize=1)
def rods() -> dict:
    return _load("items/rods.json")


@lru_cache(maxsize=1)
def baits() -> dict:
    return _load("items/baits.json")


@lru_cache(maxsize=1)
def recipes() -> dict:
    """Đan phương (stage 8): recipe id (= the pill it makes) -> ingredients, yield, name chars."""
    return _load("recipes.json")["recipes"]


@lru_cache(maxsize=1)
def pets() -> dict:
    """Linh Thú: the 12 zodiac pets (stage 8)."""
    return _load("creatures/pets.json")


@lru_cache(maxsize=1)
def realms() -> list[dict]:
    return _load("realms_cultivation.json")["realms"]


def stack_item(item_id: str) -> dict | None:
    """Stackable things in inventory_items: pills, materials (incl. manuals), fishing rods,
    baits and caught fish (`fish_<species>`)."""
    if item_id in pills():
        return {"kind": "pill", **pills()[item_id]}
    if item_id in materials():
        return materials()[item_id]
    if item_id in rods():
        r = rods()[item_id]
        return {"kind": "rod", "name_vi": r["name_vi"], "desc_vi": r["desc_vi"], "rarity": r["rarity"]}
    if item_id in baits():
        b = baits()[item_id]
        return {"kind": "bait", "name_vi": b["name_vi"], "desc_vi": b["desc_vi"], "sell_price": b["sell_price"]}
    if item_id.startswith("fish_") and item_id[5:] in fish():
        f = fish()[item_id[5:]]
        return {"kind": "fish", "name_vi": f["name_vi"], "rarity": f["rarity"], "sell_price": f["sell_price"],
                "desc_vi": f"{f['hanzi']} ({f['pinyin']}). {f['desc_vi']}"}
    return None


def item_name(item_id: str) -> str:
    info = stack_item(item_id) or equipment()["items"].get(item_id)
    return info["name_vi"] if info else item_id


def skill_for_word(hanzi: str) -> str | None:
    return next((sid for sid, s in skills()["skills"].items() if s["hanzi"] == hanzi), None)
