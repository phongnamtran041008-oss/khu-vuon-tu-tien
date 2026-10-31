"""Cached access to the code-built sprites."""
from __future__ import annotations

from functools import lru_cache

import pygame

from ..art import build as B


@lru_cache(maxsize=4096)
def prop(name: str, variant: int = 0, frame: int = 0) -> pygame.Surface:
    if name == "bamboo":
        return B.bamboo(variant % 7)
    if name == "hut":
        return B.hut()
    if name == "shrine":
        return B.shrine(frame)
    if name == "tablet":
        return B.tablet()
    if name == "table":
        return B.table()
    if name == "gate":
        return B.gate()
    if name == "mat":
        return B.mat()
    if name == "rock":
        return B.rock(variant)
    if name == "house":
        return B.house(variant)
    if name == "pavilion":
        return B.pavilion(frame)
    if name == "library":
        return B.library()
    if name == "stall":
        return B.stall(variant)
    if name == "furnace":
        return B.furnace(frame)
    if name == "anvil":
        return B.anvil()
    if name == "board":
        return B.board()
    if name == "well":
        return B.well()
    if name == "lantern":
        return B.lantern(frame)
    if name == "tree":
        return B.tree(variant)
    if name == "ink_tree":
        return B.tree(variant, inked=True)
    if name == "portal":
        return B.portal(frame)
    if name == "td_gate":
        return B.td_gate(frame)
    if name == "sign":
        return B.sign()
    if name == "hive":
        return B.hive(frame)
    if name == "realm_gate":
        from ..art import realm_art
        return realm_art.realm_gate(frame)
    raise KeyError(name)


ANIMATED_PROPS = {"shrine", "pavilion", "furnace", "lantern", "portal", "td_gate", "hive", "realm_gate"}


@lru_cache(maxsize=256)
def realm(name: str, *args) -> pygame.Surface:
    """Bí cảnh props (stage 9): realm('pillar', 3, False), realm('rift', frame)..."""
    from ..art import realm_art
    return getattr(realm_art, name)(*args)

DEFAULT_BEE_LOOK = {"body": "#E9C46A", "stripe": "#2B2B2B", "wing": "#F0F8FF", "eye": "#2B2B2B"}


@lru_cache(maxsize=128)
def _bee(body: str, stripe: str, wing: str, eye: str) -> tuple:
    frames = B.bee_frames({"body": body, "stripe": stripe, "wing": wing, "eye": eye})
    left = [pygame.transform.flip(f, True, False) for f in frames]
    return tuple(frames), tuple(left)


def bee(look: dict | None, frame: int, facing_left: bool = False) -> pygame.Surface:
    lk = {**DEFAULT_BEE_LOOK, **(look or {})}
    right, left = _bee(lk["body"], lk["stripe"], lk["wing"], lk["eye"])
    return (left if facing_left else right)[frame % 2]


@lru_cache(maxsize=16)
def egg(color: str) -> list[pygame.Surface]:
    return B.egg_frames(color)


@lru_cache(maxsize=32)
def decoration(name: str, frame: int = 0) -> pygame.Surface:
    return B.decoration(name, frame)


@lru_cache(maxsize=32)
def _char(hair_color: str, hair_style: str, body: str) -> dict:
    return B.character_frames({"hair_color": hair_color, "hair_style": hair_style, "body": body})


def character(appearance: dict) -> dict:
    return _char(appearance.get("hair_color", "#2B2B2B"), appearance.get("hair_style", "ngan"),
                 appearance.get("body", "nam"))


@lru_cache(maxsize=8)
def monster(kind: str) -> list[pygame.Surface]:
    return B.monster_frames(kind)


NPC_LOOKS = {  # villagers of Trúc Lâm Thôn: (appearance, robe colours)
    "shopkeeper": ({"hair_color": "#5C3A21", "hair_style": "ngan", "body": "nam"}, {"c": "#C9B48A", "C": "#A8946A"}),
    "alchemist": ({"hair_color": "#8E8E8E", "hair_style": "buoi", "body": "nam"}, {"c": "#A8C6E0", "C": "#7FA3C4"}),
    "smith": ({"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}, {"c": "#8C8C8C", "C": "#5A5A5A"}),
    "librarian": ({"hair_color": "#2B2B2B", "hair_style": "dai", "body": "nu"}, {"c": "#E89AB0", "C": "#BC4749"}),
    "guide": ({"hair_color": "#A0522D", "hair_style": "buoi", "body": "nu"}, {"c": "#B5D67A", "C": "#8DB360"}),
    "fisher": ({"hair_color": "#D8D2C4", "hair_style": "buoi", "body": "nam"}, {"c": "#B89B5E", "C": "#7E6A3E"}),
}


@lru_cache(maxsize=16)
def npc(kind: str) -> dict:
    app, cols = NPC_LOOKS.get(kind, NPC_LOOKS["guide"])
    return B.character_frames(app, cols)


@lru_cache(maxsize=1)
def truc_lao() -> list[pygame.Surface]:
    return B.truc_lao_frames()


@lru_cache(maxsize=1)
def horse() -> list[pygame.Surface]:
    return B.horse_frames()


@lru_cache(maxsize=8)
def villager() -> dict:
    return B.character_frames({"hair_color": "#8E8E8E", "hair_style": "buoi", "body": "nu"},
                              {"c": "#A8C6E0", "C": "#7FA3C4"})


@lru_cache(maxsize=16)
def seeds(rarity: str) -> list[pygame.Surface]:
    return B.seed_frames(rarity)


@lru_cache(maxsize=16)
def icon(name: str, rarity: str | None = None) -> pygame.Surface:
    return B.icon(name, rarity)


@lru_cache(maxsize=512)
def plant(stage: int, rarity: str, key: str, frame: int, wither_bucket: int) -> pygame.Surface:
    p = B.plant(stage, rarity, key, frame)
    return B.withered(p, wither_bucket * 10) if wither_bucket >= 3 else p


@lru_cache(maxsize=4)
def bed(locked: bool) -> pygame.Surface:
    return B.plot_bed(locked)


@lru_cache(maxsize=2)
def tag() -> pygame.Surface:
    return B.tag()


_PET_LOOKS: dict[str, dict] = {}


def set_pet_looks(looks: dict[str, dict]) -> None:
    """The looks of every Linh Thú species (from /pets), so other players' pets can be drawn."""
    if looks and any(_PET_LOOKS.get(k) != v for k, v in looks.items()):
        _PET_LOOKS.update(looks)
        _pet.cache_clear()          # a pet drawn before the looks arrived was a placeholder


@lru_cache(maxsize=32)
def _pet(kind: str) -> tuple:
    frames = B.pet_frames(_PET_LOOKS.get(kind) or {"plan": "quad", "body": "#C9B48A"})
    return tuple(frames), tuple(pygame.transform.flip(f, True, False) for f in frames)


def pet(kind: str, frame: int, facing_left: bool = False) -> pygame.Surface:
    right, left = _pet(kind)
    return (left if facing_left else right)[frame % 2]


def pet_known(kind: str) -> bool:
    return kind in _PET_LOOKS
