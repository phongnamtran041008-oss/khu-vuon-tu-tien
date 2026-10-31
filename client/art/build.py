"""Turns sprite definitions into pygame Surfaces. Character grids come from
art/sprites/*.py; tiles, props and plants are drawn procedurally with the palette.
Everything is deterministic, so the same PNGs come out every time
(tools/gen_sprites.py writes them to client/assets/sprites/)."""
from __future__ import annotations

import math
import random

import pygame

from .palette import PALETTE, RARITY_COLORS, rgb, shade
from .sprites import creatures, items, people

TILE = 16
DIRS = ("down", "up", "left", "right")


# ------------------------------------------------------------------ grids
def grid(rows: list[str], colors: dict[str, str] | None = None) -> pygame.Surface:
    w = len(rows[0])
    for i, r in enumerate(rows):
        if len(r) != w:
            raise ValueError(f"sprite row {i} has length {len(r)}, expected {w}: {r!r}")
    pal = dict(PALETTE)
    if colors:
        pal.update(colors)
    surf = pygame.Surface((w, len(rows)), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                surf.set_at((x, y), (*rgb(pal[ch]), 255))
    return surf


def _overlay(base: list[str], over: list[str]) -> list[str]:
    out = list(base)
    for y, row in enumerate(over):
        if y >= len(out):
            break
        out[y] = "".join(o if o != "." else b for b, o in zip(out[y], row))
    return out


def character_frames(appearance: dict, outfit_colors: dict | None = None) -> dict[tuple[str, int], pygame.Surface]:
    """{(direction, frame): 16x24 surface}; frame 0 = standing, 1-2 = walking."""
    hair = appearance.get("hair_color", "#2B2B2B")
    style = appearance.get("hair_style", "ngan")
    nu = appearance.get("body") == "nu"
    colors = {"H": hair, "h": shade(hair, 0.65)}
    if outfit_colors:
        colors.update(outfit_colors)
    frames = {}
    for d in ("down", "up", "right"):
        head = {"down": people.HEAD_DOWN, "up": people.HEAD_UP, "right": people.HEAD_RIGHT}[d]
        torso = {"down": people.TORSO_DOWN, "up": people.TORSO_UP, "right": people.TORSO_RIGHT}[d]
        legs_set = people.LEGS_FRONT if d != "right" else [people.LEGS_SIDE[0], people.LEGS_SIDE[1], people.LEGS_SIDE[0]]
        for f, legs in enumerate(legs_set):
            body = head + torso + legs
            if nu:
                body[18] = people.SKIRT_SIDE if d == "right" else people.SKIRT_FRONT
            rows = _overlay(body, people.HAIR[style][d])
            if nu and d != "up":  # a small red ribbon
                r = list(rows[3])
                col = 11 if d == "down" else 6
                r[col] = "r"
                rows[3] = "".join(r)
            frames[(d, f)] = grid(rows, colors)
    for f in range(3):
        frames[("left", f)] = pygame.transform.flip(frames[("right", f)], True, False)
    return frames


def monster_frames(kind: str) -> list[pygame.Surface]:
    from . import realm_art
    if kind in realm_art.MONSTERS:   # stage 9: the bí cảnh monsters are drawn with shapes
        return realm_art.monster_frames(kind)
    rows = {"ink_slime": creatures.INK_SLIME, "tone_wisp": creatures.TONE_WISP, "ink_fox": creatures.INK_FOX}[kind]
    return [grid(f) for f in rows]


def truc_lao_frames() -> list[pygame.Surface]:
    return [grid(people.TRUC_LAO), grid(people.TRUC_LAO_BLINK)]


def horse_frames() -> list[pygame.Surface]:
    return [grid(f) for f in people.HORSE]


def seed_frames(rarity: str) -> list[pygame.Surface]:
    c = RARITY_COLORS[rarity]
    cols = {"o": c, "O": shade(c, 0.75)}
    return [grid(f, cols) for f in items.SEED]


def icon(name: str, rarity: str | None = None) -> pygame.Surface:
    rows = {"stone": items.STONE, "fruit": items.FRUIT, "seed": items.SEED_ICON}[name]
    cols = None
    if rarity:
        c = RARITY_COLORS[rarity]
        cols = {"o": c, "O": shade(c, 0.75)}
    return grid(rows, cols)


# ------------------------------------------------------------------ tiles
def _rng(*key) -> random.Random:
    return random.Random("|".join(map(str, key)))


def _noise_fill(surf: pygame.Surface, base: str, specks: list[tuple[str, float]], key) -> None:
    r = _rng(*key)
    surf.fill(rgb(base))
    w, h = surf.get_size()
    for color, density in specks:
        for _ in range(int(w * h * density)):
            surf.set_at((r.randrange(w), r.randrange(h)), rgb(color))


def tile(name: str, variant: int = 0, frame: int = 0) -> pygame.Surface:
    s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    if name == "grass":
        _noise_fill(s, "v", [("V", 0.10), ("l", 0.04)], ("grass", variant))
        r = _rng("tuft", variant)
        for _ in range(2):
            x, y = r.randrange(2, 14), r.randrange(3, 14)
            s.set_at((x, y), rgb("n"))
            s.set_at((x + 1, y - 1), rgb("n"))
    elif name == "flowers":
        s.blit(tile("grass", variant + 7), (0, 0))
        r = _rng("fl", variant)
        for _ in range(3):
            x, y = r.randrange(2, 14), r.randrange(2, 14)
            c = r.choice(["i", "o", "W"])
            for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1)):
                s.set_at((x + dx, y + dy), rgb(c if (dx, dy) != (0, 0) else "o"))
    elif name == "path":
        _noise_fill(s, "y", [("Y", 0.12), ("w", 0.04)], ("path", variant))
        r = _rng("pebble", variant)
        for _ in range(2):
            x, y = r.randrange(1, 14), r.randrange(1, 14)
            pygame.draw.rect(s, rgb("Y"), (x, y, 2, 1))
    elif name == "water":
        s.fill(rgb("A"))
        for y in range(0, TILE, 4):
            off = (frame * 2 + y) % 8
            pygame.draw.line(s, rgb("a"), (off, y + 1), (off + 3, y + 1))
            pygame.draw.line(s, rgb("q"), ((off + 9) % 16, y + 3), ((off + 11) % 16, y + 3))
    elif name == "bamboo_floor":
        _noise_fill(s, "n", [("V", 0.15), ("D", 0.05)], ("bf", variant))
    elif name == "stone":
        _noise_fill(s, "t", [("T", 0.15), ("W", 0.03)], ("st", variant))
        pygame.draw.line(s, rgb("T"), (0, 15), (15, 15))
        pygame.draw.line(s, rgb("T"), (15, 0), (15, 15))
    elif name == "wood":
        s.fill(rgb("B"))
        for y in (3, 7, 11, 15):
            pygame.draw.line(s, rgb("b"), (0, y), (15, y))
    elif name == "plaza":  # village square flagstones
        _noise_fill(s, "t", [("g", 0.06), ("W", 0.02)], ("plaza", variant))
        off = 8 if variant % 2 else 0
        pygame.draw.line(s, rgb("T"), (0, 7), (15, 7))
        pygame.draw.line(s, rgb("T"), (0, 15), (15, 15))
        pygame.draw.line(s, rgb("T"), (off, 0), (off, 7))
        pygame.draw.line(s, rgb("T"), ((off + 8) % 16, 8), ((off + 8) % 16, 15))
    elif name == "dirt":
        _noise_fill(s, "e", [("d", 0.14), ("y", 0.05)], ("dirt", variant))
    elif name == "dark_grass":  # Rừng Mực Loang: grass dulled by spreading ink
        _noise_fill(s, "n", [("V", 0.10), ("G", 0.05), ("K", 0.02)], ("dg", variant))
    elif name == "ink":  # a thin smear of ink soaking the grass (walkable, purely visual)
        s.blit(tile("dark_grass", variant), (0, 0))
        r = _rng("inkp", variant)
        x0, y0 = r.randrange(0, 4), r.randrange(4, 8)
        smear = pygame.Surface((14, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(smear, (*rgb("G"), 150), (0, 0, 14, 6))
        pygame.draw.ellipse(smear, (*rgb("k"), 120), (3, 1, 7, 3))
        s.blit(smear, (x0, y0))
        for _ in range(3):
            s.set_at((r.randrange(1, 15), r.randrange(1, 15)), rgb("G"))
    elif name == "realm_floor":  # bí cảnh: old slate flags stained with ink
        _noise_fill(s, "G", [("T", 0.06), ("k", 0.08)], ("rf", variant))
        pygame.draw.line(s, rgb("k"), (0, 15), (15, 15))
        pygame.draw.line(s, rgb("k"), (15 if variant % 2 else 7, 0), (15 if variant % 2 else 7, 15))
    elif name == "realm_wall":  # bí cảnh: rock soaked black with ink
        _noise_fill(s, "K", [("k", 0.25), ("G", 0.04)], ("rw", variant))
        pygame.draw.line(s, rgb("G"), (0, 0), (15, 0))
    else:
        raise KeyError(name)
    return s


TILESET = [  # tile ids used in maps (Tiled gid = index + 1)
    ("grass", 0), ("grass", 1), ("grass", 2), ("flowers", 0), ("flowers", 1),
    ("path", 0), ("path", 1), ("water", 0), ("bamboo_floor", 0), ("stone", 0), ("wood", 0),
    # stage 3 (append only: existing map gids must not move)
    ("plaza", 0), ("plaza", 1), ("dirt", 0), ("dark_grass", 0), ("dark_grass", 1), ("ink", 0), ("ink", 1),
    # stage 9: secret realms
    ("realm_floor", 0), ("realm_floor", 1), ("realm_wall", 0),
]


def tileset_surface() -> pygame.Surface:
    cols = 8
    rows = math.ceil(len(TILESET) / cols)
    sheet = pygame.Surface((cols * TILE, rows * TILE), pygame.SRCALPHA)
    for i, (n, v) in enumerate(TILESET):
        sheet.blit(tile(n, v), ((i % cols) * TILE, (i // cols) * TILE))
    return sheet


# ------------------------------------------------------------------ props
def bamboo(variant: int = 0) -> pygame.Surface:
    """16x40 bamboo clump."""
    s = pygame.Surface((16, 40), pygame.SRCALPHA)
    r = _rng("bamboo", variant)
    for i, x in enumerate((2, 7, 11)):
        top = r.randrange(0, 8)
        pygame.draw.rect(s, rgb("V"), (x, top, 3, 40 - top))
        pygame.draw.line(s, rgb("l"), (x, top), (x, 39))
        for y in range(top + 5, 40, 7):
            pygame.draw.line(s, rgb("n"), (x, y), (x + 2, y))
        for y in range(top + 2, 30, 9):
            side = -1 if (i + y) % 2 else 1
            pygame.draw.line(s, rgb("v"), (x + 1, y), (x + 1 + side * 4, y - 2))
            pygame.draw.line(s, rgb("n"), (x + 1 + side * 4, y - 2), (x + 1 + side * 6, y - 2))
    return s


def hut() -> pygame.Surface:
    """64x56 thatched hut of Trúc Lão."""
    s = pygame.Surface((64, 56), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("B"), (6, 24, 52, 30))
    for x in range(6, 58, 4):
        pygame.draw.line(s, rgb("b"), (x, 24), (x, 53))
    pygame.draw.rect(s, rgb("k"), (6, 24, 52, 30), 1)
    pygame.draw.rect(s, rgb("D"), (27, 34, 11, 20))  # door
    pygame.draw.rect(s, rgb("k"), (27, 34, 11, 20), 1)
    pygame.draw.rect(s, rgb("w"), (12, 32, 9, 8))     # paper window
    pygame.draw.line(s, rgb("b"), (16, 32), (16, 39))
    pygame.draw.rect(s, rgb("k"), (12, 32, 9, 8), 1)
    pygame.draw.polygon(s, rgb("o"), [(0, 26), (32, 2), (63, 26)])
    pygame.draw.polygon(s, rgb("O"), [(0, 26), (32, 2), (63, 26)], 2)
    for x in range(4, 60, 5):
        pygame.draw.line(s, rgb("O"), (32, 4), (x, 25))
    pygame.draw.polygon(s, rgb("k"), [(0, 26), (32, 2), (63, 26)], 1)
    pygame.draw.rect(s, rgb("r"), (40, 36, 8, 12))   # couplet
    return s


def shrine(frame: int = 0) -> pygame.Surface:
    """32x44 Thiên Cơ Đài, the gacha altar."""
    s = pygame.Surface((32, 44), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("T"), (2, 34, 28, 10))
    pygame.draw.rect(s, rgb("t"), (4, 30, 24, 6))
    pygame.draw.rect(s, rgb("r"), (8, 12, 16, 18))
    pygame.draw.rect(s, rgb("R"), (8, 12, 16, 18), 1)
    pygame.draw.polygon(s, rgb("k"), [(2, 13), (16, 3), (30, 13)])
    pygame.draw.polygon(s, rgb("G"), [(4, 12), (16, 5), (28, 12)])
    glow = [rgb("o"), rgb("W"), rgb("o"), rgb("O")][frame % 4]
    pygame.draw.circle(s, glow, (16, 21), 4)
    pygame.draw.circle(s, rgb("k"), (16, 21), 4, 1)
    pygame.draw.rect(s, rgb("k"), (2, 34, 28, 10), 1)
    return s


def tablet() -> pygame.Surface:
    """16x24 stone tablet (opens Sổ Phát Hiện)."""
    s = pygame.Surface((16, 24), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("T"), (2, 18, 12, 6))
    pygame.draw.rect(s, rgb("t"), (3, 2, 10, 17))
    pygame.draw.rect(s, rgb("k"), (3, 2, 10, 17), 1)
    for y in (6, 9, 12, 15):
        pygame.draw.line(s, rgb("G"), (6, y), (10, y))
    return s


def table() -> pygame.Surface:
    """24x16 low table with a fruit basket (opens Ghép Câu)."""
    s = pygame.Surface((24, 16), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("b"), (1, 6, 22, 5))
    pygame.draw.rect(s, rgb("k"), (1, 6, 22, 5), 1)
    pygame.draw.rect(s, rgb("b"), (3, 11, 3, 5))
    pygame.draw.rect(s, rgb("b"), (18, 11, 3, 5))
    pygame.draw.ellipse(s, rgb("B"), (6, 1, 12, 7))
    for x, c in ((8, "o"), (11, "r"), (14, "o")):
        pygame.draw.circle(s, rgb(c), (x, 3), 2)
    return s


def gate() -> pygame.Surface:
    """32x32 bamboo gate at the abode exit."""
    s = pygame.Surface((32, 32), pygame.SRCALPHA)
    for x in (1, 27):
        pygame.draw.rect(s, rgb("V"), (x, 4, 4, 28))
        pygame.draw.rect(s, rgb("n"), (x, 4, 4, 28), 1)
    pygame.draw.rect(s, rgb("b"), (0, 2, 32, 4))
    pygame.draw.rect(s, rgb("k"), (0, 2, 32, 4), 1)
    pygame.draw.rect(s, rgb("r"), (11, 6, 10, 6))
    return s


def mat() -> pygame.Surface:
    """24x16 meditation mat (bàn đả tọa, used from stage 4)."""
    s = pygame.Surface((24, 16), pygame.SRCALPHA)
    pygame.draw.ellipse(s, rgb("o"), (0, 3, 24, 12))
    pygame.draw.ellipse(s, rgb("O"), (0, 3, 24, 12), 1)
    pygame.draw.ellipse(s, rgb("r"), (7, 6, 10, 6))
    return s


def rock(variant: int = 0) -> pygame.Surface:
    s = pygame.Surface((16, 12), pygame.SRCALPHA)
    pygame.draw.ellipse(s, rgb("T"), (1, 2, 14, 10))
    pygame.draw.ellipse(s, rgb("t"), (3, 3, 7, 4))
    pygame.draw.ellipse(s, rgb("k"), (1, 2, 14, 10), 1)
    return s


# ------------------------------------------------------------------ garden
PLOT = 32


def plot_bed(locked: bool, wither: float = 0.0) -> pygame.Surface:
    s = pygame.Surface((PLOT, PLOT), pygame.SRCALPHA)
    if locked:
        _noise_fill(s, "V", [("n", 0.12), ("v", 0.1)], ("weeds",))
        for x, y in ((6, 8), (20, 18), (12, 24)):
            s.blit(rock(), (x - 4, y - 4))
        pygame.draw.rect(s, rgb("n"), (0, 0, PLOT, PLOT), 1)
        return s
    pygame.draw.rect(s, rgb("b"), (1, 1, PLOT - 2, PLOT - 2))   # wooden border
    inner = pygame.Surface((PLOT - 6, PLOT - 6))
    _noise_fill(inner, "d", [("D", 0.15), ("e", 0.06)], ("soil",))
    for y in range(4, PLOT - 6, 6):
        pygame.draw.line(inner, rgb("D"), (1, y), (PLOT - 8, y))
    s.blit(inner, (3, 3))
    pygame.draw.rect(s, rgb("k"), (1, 1, PLOT - 2, PLOT - 2), 1)
    return s


def plant(stage: int, rarity: str, key: str, frame: int = 0) -> pygame.Surface:
    """24x24 plant for garden stage 0-5; the hanzi is drawn separately by the game."""
    s = pygame.Surface((24, 24), pygame.SRCALPHA)
    r = _rng("plant", key)
    sway = (frame % 2)
    base_x, ground = 12, 21
    if stage == 0:
        pygame.draw.ellipse(s, rgb("D"), (6, 17, 12, 6))
        pygame.draw.ellipse(s, rgb("e"), (8, 17, 8, 3))
        s.set_at((12, 18), rgb("o"))
        s.set_at((13, 18), rgb("W") if frame % 2 else rgb("o"))
        return s
    height = {1: 6, 2: 11, 3: 15, 4: 16, 5: 17}[stage]
    top = ground - height
    leaf = rgb("v") if stage < 3 else rgb("V")
    pygame.draw.line(s, rgb("n"), (base_x, ground), (base_x + sway, top), 2 if stage >= 3 else 1)
    n_leaves = {1: 2, 2: 4, 3: 6, 4: 7, 5: 8}[stage]
    for i in range(n_leaves):
        y = ground - 3 - i * (height - 3) // max(1, n_leaves)
        side = -1 if i % 2 == 0 else 1
        length = 3 + (stage >= 3) + r.randrange(0, 2)
        x0 = base_x + sway * (ground - y) // max(1, height)
        pygame.draw.ellipse(s, leaf, (x0 + (1 if side > 0 else -length - 1), y - 2, length + 1, 3))
        s.set_at((x0 + side * (length // 2 + 1), y - 1), rgb("l"))
    if stage >= 4:  # leafy crown
        pygame.draw.ellipse(s, rgb("V"), (base_x - 8 + sway, top - 3, 16, 10))
        pygame.draw.ellipse(s, rgb("v"), (base_x - 6 + sway, top - 2, 9, 5))
    color = rgb(RARITY_COLORS[rarity]) if rarity != "common" else rgb("i")
    spots = [(-5, 2), (4, 0), (0, -3)] if stage >= 4 else [(-4, 1), (4, 3), (0, -2)]
    if stage == 3:
        for dx, dy in spots:
            cx, cy = base_x + dx + sway, top + 4 + dy
            for ox, oy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                s.set_at((cx + ox, cy + oy), color)
            s.set_at((cx, cy), rgb("o"))
    elif stage == 4:
        for dx, dy in spots:
            pygame.draw.circle(s, rgb("l"), (base_x + dx + sway, top + 3 + dy), 2)
    elif stage == 5:
        fruit = rgb(RARITY_COLORS[rarity]) if rarity != "common" else rgb("r")
        for dx, dy in spots:
            cx, cy = base_x + dx + sway, top + 3 + dy
            pygame.draw.circle(s, fruit, (cx, cy), 3)
            pygame.draw.circle(s, rgb("k"), (cx, cy), 3, 1)
            s.set_at((cx - 1, cy - 1), rgb("W"))
    pygame.draw.ellipse(s, rgb("D"), (7, 20, 10, 4))
    return s


def withered(surf: pygame.Surface, wither: float) -> pygame.Surface:
    """Blend toward grey ink as wither rises (spec 6.3)."""
    if wither < 30:
        return surf
    k = min(1.0, (wither - 30) / 70) * 0.85
    out = surf.copy()
    w, h = out.get_size()
    ink = rgb("G")
    for y in range(h):
        for x in range(w):
            c = out.get_at((x, y))
            if c.a:
                g = (c.r + c.g + c.b) // 3
                mix = tuple(int(cv * (1 - k) + (g * 0.6 + ic * 0.4) * k) for cv, ic in zip((c.r, c.g, c.b), ink))
                out.set_at((x, y), (*mix, c.a))
    if wither >= 30:  # ink streaks
        rr = random.Random(int(wither) // 10)
        for _ in range(int(wither / 15)):
            x, y = rr.randrange(4, 20), rr.randrange(6, 22)
            if out.get_at((x, y)).a:
                out.set_at((x, y), (*rgb("K"), 255))
    return out


def tag(size=(13, 13)) -> pygame.Surface:
    """Little paper tag the plant's character is written on."""
    s = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("w"), (0, 0, size[0], size[1] - 2))
    pygame.draw.rect(s, rgb("k"), (0, 0, size[0], size[1] - 2), 1)
    pygame.draw.line(s, rgb("b"), (size[0] // 2, size[1] - 2), (size[0] // 2, size[1] - 1))
    return s


# ------------------------------------------------------------------ village & forest (stage 3)
def house(variant: int = 0) -> pygame.Surface:
    """48x48 village house with a tiled roof; the roof colour changes per variant."""
    s = pygame.Surface((48, 48), pygame.SRCALPHA)
    roof, roof_d = [("q", "k"), ("R", "k"), ("n", "k"), ("G", "K")][variant % 4]
    pygame.draw.rect(s, rgb("w"), (5, 22, 38, 25))
    for x in (5, 42):
        pygame.draw.rect(s, rgb("b"), (x, 22, 2, 25))
    pygame.draw.rect(s, rgb("b"), (5, 22, 38, 2))
    pygame.draw.rect(s, rgb("D"), (20, 32, 9, 15))
    pygame.draw.rect(s, rgb("k"), (20, 32, 9, 15), 1)
    for wx in (9, 32):
        pygame.draw.rect(s, rgb("o") if variant % 2 else rgb("y"), (wx, 28, 7, 6))
        pygame.draw.line(s, rgb("b"), (wx + 3, 28), (wx + 3, 33))
        pygame.draw.rect(s, rgb("k"), (wx, 28, 7, 6), 1)
    pygame.draw.rect(s, rgb("k"), (5, 22, 38, 25), 1)
    pygame.draw.polygon(s, rgb(roof), [(0, 24), (6, 8), (42, 8), (47, 24)])
    for y in range(11, 24, 3):
        pygame.draw.line(s, rgb(roof_d), (3, y), (45, y))
    pygame.draw.polygon(s, rgb("k"), [(0, 24), (6, 8), (42, 8), (47, 24)], 1)
    pygame.draw.line(s, rgb("k"), (2, 8), (46, 6))
    return s


def pavilion(frame: int = 0) -> pygame.Surface:
    """64x64 Thiên Cơ Các (gacha pavilion): red pillars, two-tier golden roof, glowing orb."""
    s = pygame.Surface((64, 64), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("T"), (4, 54, 56, 10))
    pygame.draw.rect(s, rgb("k"), (4, 54, 56, 10), 1)
    for x in (10, 50):
        pygame.draw.rect(s, rgb("r"), (x, 28, 4, 26))
        pygame.draw.rect(s, rgb("k"), (x, 28, 4, 26), 1)
    pygame.draw.rect(s, rgb("R"), (14, 30, 36, 24))
    glow = [rgb("o"), rgb("W"), rgb("o"), rgb("O")][frame % 4]
    pygame.draw.circle(s, glow, (32, 42), 6)
    pygame.draw.circle(s, rgb("k"), (32, 42), 6, 1)
    pygame.draw.polygon(s, rgb("O"), [(0, 30), (10, 18), (54, 18), (63, 30)])
    pygame.draw.polygon(s, rgb("k"), [(0, 30), (10, 18), (54, 18), (63, 30)], 1)
    pygame.draw.rect(s, rgb("r"), (16, 14, 32, 5))
    pygame.draw.polygon(s, rgb("o"), [(8, 14), (18, 2), (46, 2), (56, 14)])
    pygame.draw.polygon(s, rgb("k"), [(8, 14), (18, 2), (46, 2), (56, 14)], 1)
    pygame.draw.rect(s, rgb("r"), (29, 0, 6, 3))
    return s


def library() -> pygame.Surface:
    """64x56 Tàng Thư Các: a tall grey-roofed hall with scroll shelves in the windows."""
    s = pygame.Surface((64, 56), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("t"), (6, 22, 52, 34))
    pygame.draw.rect(s, rgb("k"), (6, 22, 52, 34), 1)
    pygame.draw.rect(s, rgb("D"), (27, 38, 10, 18))
    for wx in (11, 43):
        pygame.draw.rect(s, rgb("b"), (wx, 28, 10, 14))
        for yy in (31, 35, 39):
            pygame.draw.line(s, rgb("w"), (wx + 1, yy), (wx + 8, yy))
        pygame.draw.rect(s, rgb("k"), (wx, 28, 10, 14), 1)
    pygame.draw.polygon(s, rgb("G"), [(0, 24), (8, 6), (56, 6), (63, 24)])
    for y in range(9, 24, 3):
        pygame.draw.line(s, rgb("K"), (4, y), (60, y))
    pygame.draw.polygon(s, rgb("k"), [(0, 24), (8, 6), (56, 6), (63, 24)], 1)
    pygame.draw.rect(s, rgb("w"), (22, 12, 20, 7))
    pygame.draw.rect(s, rgb("k"), (22, 12, 20, 7), 1)
    return s


def stall(variant: int = 0) -> pygame.Surface:
    """40x32 market stall with a striped awning."""
    s = pygame.Surface((40, 32), pygame.SRCALPHA)
    col = ["r", "u", "V"][variant % 3]
    pygame.draw.rect(s, rgb("b"), (3, 10, 2, 22))
    pygame.draw.rect(s, rgb("b"), (35, 10, 2, 22))
    pygame.draw.rect(s, rgb("B"), (2, 20, 36, 8))
    pygame.draw.rect(s, rgb("k"), (2, 20, 36, 8), 1)
    for i, x in enumerate(range(0, 40, 5)):
        pygame.draw.rect(s, rgb(col) if i % 2 == 0 else rgb("w"), (x, 4, 5, 8))
    pygame.draw.rect(s, rgb("k"), (0, 4, 40, 8), 1)
    for x, c in ((8, "o"), (14, "i"), (20, "l"), (27, "r"), (32, "o")):
        pygame.draw.circle(s, rgb(c), (x, 19), 2)
    return s


def furnace(frame: int = 0) -> pygame.Surface:
    """24x28 alchemy furnace (lò luyện đan), the fire flickers."""
    s = pygame.Surface((24, 28), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("T"), (3, 10, 18, 16))
    pygame.draw.ellipse(s, rgb("t"), (2, 6, 20, 8))
    pygame.draw.rect(s, rgb("k"), (3, 10, 18, 16), 1)
    pygame.draw.ellipse(s, rgb("k"), (2, 6, 20, 8), 1)
    fire = [rgb("r"), rgb("o"), rgb("R"), rgb("o")][frame % 4]
    pygame.draw.rect(s, rgb("K"), (8, 17, 8, 7))
    pygame.draw.rect(s, fire, (9, 19 - frame % 2, 6, 5))
    pygame.draw.rect(s, rgb("G"), (10, 2, 4, 5))
    return s


def anvil() -> pygame.Surface:
    """24x20 smith's anvil on a stump (lò rèn)."""
    s = pygame.Surface((24, 20), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("b"), (7, 11, 10, 9))
    pygame.draw.rect(s, rgb("k"), (7, 11, 10, 9), 1)
    pygame.draw.polygon(s, rgb("G"), [(1, 4), (23, 4), (20, 9), (16, 11), (8, 11), (4, 9)])
    pygame.draw.polygon(s, rgb("k"), [(1, 4), (23, 4), (20, 9), (16, 11), (8, 11), (4, 9)], 1)
    pygame.draw.line(s, rgb("g"), (3, 5), (21, 5))
    return s


def board() -> pygame.Surface:
    """24x28 quest board with paper notices."""
    s = pygame.Surface((24, 28), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("b"), (3, 14, 2, 14))
    pygame.draw.rect(s, rgb("b"), (19, 14, 2, 14))
    pygame.draw.rect(s, rgb("B"), (1, 2, 22, 16))
    pygame.draw.rect(s, rgb("k"), (1, 2, 22, 16), 1)
    for x, y in ((4, 5), (12, 4), (6, 11), (15, 10)):
        pygame.draw.rect(s, rgb("w"), (x, y, 6, 5))
        pygame.draw.line(s, rgb("G"), (x + 1, y + 2), (x + 4, y + 2))
    pygame.draw.circle(s, rgb("r"), (12, 4), 1)
    return s


def well() -> pygame.Surface:
    """24x24 stone well in the square."""
    s = pygame.Surface((24, 24), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("b"), (2, 2, 2, 14))
    pygame.draw.rect(s, rgb("b"), (20, 2, 2, 14))
    pygame.draw.polygon(s, rgb("R"), [(0, 4), (12, 0), (23, 4)])
    pygame.draw.ellipse(s, rgb("T"), (1, 12, 22, 12))
    pygame.draw.ellipse(s, rgb("A"), (5, 14, 14, 6))
    pygame.draw.ellipse(s, rgb("k"), (1, 12, 22, 12), 1)
    return s


def lantern(frame: int = 0) -> pygame.Surface:
    """8x24 red paper lantern on a post."""
    s = pygame.Surface((8, 24), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("b"), (3, 8, 2, 16))
    pygame.draw.ellipse(s, rgb("r") if frame % 4 else rgb("i"), (0, 0, 8, 9))
    pygame.draw.ellipse(s, rgb("k"), (0, 0, 8, 9), 1)
    s.set_at((4, 4), rgb("o"))
    return s


def tree(variant: int = 0, inked: bool = False) -> pygame.Surface:
    """32x40 round-crowned tree; `inked` trees in Rừng Mực Loang are greyed and drip ink."""
    s = pygame.Surface((32, 40), pygame.SRCALPHA)
    r = _rng("tree", variant, inked)
    pygame.draw.rect(s, rgb("b"), (14, 24, 5, 16))
    pygame.draw.rect(s, rgb("k"), (14, 24, 5, 16), 1)
    crown, light = ("G", "g") if inked else ("V", "v")
    for _ in range(6):
        cx, cy, rad = r.randrange(9, 23), r.randrange(8, 20), r.randrange(6, 10)
        pygame.draw.circle(s, rgb(crown), (cx, cy), rad)
    for _ in range(5):
        cx, cy = r.randrange(8, 24), r.randrange(5, 16)
        pygame.draw.circle(s, rgb(light), (cx, cy), 2)
    if inked:
        for _ in range(4):
            x = r.randrange(6, 26)
            pygame.draw.line(s, rgb("K"), (x, r.randrange(10, 20)), (x, r.randrange(22, 30)))
    return s


def portal(frame: int = 0) -> pygame.Surface:
    """32x40 stone arch with a shimmering curtain: the gate between zones."""
    s = pygame.Surface((32, 40), pygame.SRCALPHA)
    shimmer = pygame.Surface((20, 30), pygame.SRCALPHA)
    for y in range(30):
        a = 70 + int(50 * math.sin((y + frame * 3) * 0.6))
        pygame.draw.line(shimmer, (*rgb("a"), max(20, a)), (0, y), (19, y))
    s.blit(shimmer, (6, 8))
    for x in (1, 25):
        pygame.draw.rect(s, rgb("t"), (x, 6, 6, 34))
        pygame.draw.rect(s, rgb("k"), (x, 6, 6, 34), 1)
    pygame.draw.rect(s, rgb("T"), (0, 2, 32, 6))
    pygame.draw.rect(s, rgb("k"), (0, 2, 32, 6), 1)
    pygame.draw.rect(s, rgb("r"), (11, 0, 10, 4))
    return s


def td_gate(frame: int = 0) -> pygame.Surface:
    """40x40 Cổng Thủ Vườn: a bamboo arch overgrown with word-plants (stage 7 opens it)."""
    s = pygame.Surface((40, 40), pygame.SRCALPHA)
    for x in (2, 33):
        pygame.draw.rect(s, rgb("V"), (x, 6, 5, 34))
        pygame.draw.rect(s, rgb("n"), (x, 6, 5, 34), 1)
    pygame.draw.rect(s, rgb("b"), (0, 3, 40, 6))
    pygame.draw.rect(s, rgb("k"), (0, 3, 40, 6), 1)
    for i, (x, y) in enumerate(((4, 12), (34, 18), (6, 26), (35, 30), (20, 2))):
        pygame.draw.circle(s, rgb("l") if i % 2 else rgb("v"), (x, y), 4)
        if i == frame % 5:
            pygame.draw.circle(s, rgb("i"), (x, y), 1)
    return s


def sign() -> pygame.Surface:
    """16x20 wooden direction sign."""
    s = pygame.Surface((16, 20), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("b"), (7, 8, 2, 12))
    pygame.draw.polygon(s, rgb("B"), [(1, 2), (13, 2), (16, 6), (13, 10), (1, 10)])
    pygame.draw.polygon(s, rgb("k"), [(1, 2), (13, 2), (16, 6), (13, 10), (1, 10)], 1)
    return s


# ------------------------------------------------------------------ Linh Phong (stage 5)
BEE_FRAMES = [  # 8x8, facing right; Y body, Z stripe, U wing, E eye, k ink outline
    [
        "..UU.UU.",
        "..UUUUU.",
        "..kkkkk.",
        ".kYZYZEk",
        "kYZYZYYk",
        ".kYZYZYk",
        "..kkkkk.",
        "........",
    ],
    [
        "........",
        "........",
        "..kkkkk.",
        ".kYZYZEk",
        "kYZUUUYk",
        ".kYUUUYk",
        "..kkkkk.",
        "........",
    ],
]


def bee_frames(look: dict) -> list[pygame.Surface]:
    """Two wing-flap frames of an 8x8 spirit bee in its species' colours (spec 10.2)."""
    cols = {"Y": look.get("body", "#E9C46A"), "Z": look.get("stripe", "#2B2B2B"),
            "U": look.get("wing", "#F0F8FF"), "E": look.get("eye", "#2B2B2B")}
    return [grid(f, cols) for f in BEE_FRAMES]


def hive(frame: int = 0) -> pygame.Surface:
    """24x32 Linh Phong Sào: a honey-gold comb on a carved post."""
    s = pygame.Surface((24, 32), pygame.SRCALPHA)
    pygame.draw.rect(s, rgb("b"), (10, 18, 4, 14))
    pygame.draw.rect(s, rgb("k"), (10, 18, 4, 14), 1)
    pygame.draw.rect(s, rgb("B"), (6, 29, 12, 3))
    pygame.draw.ellipse(s, rgb("O"), (1, 1, 22, 22))
    pygame.draw.ellipse(s, rgb("o"), (3, 2, 18, 18))
    for y in (6, 10, 14, 18):                       # coils of the comb
        pygame.draw.line(s, rgb("O"), (4 + (y == 6) * 2, y), (19 - (y == 6) * 2, y))
    pygame.draw.ellipse(s, rgb("k"), (1, 1, 22, 22), 1)
    pygame.draw.ellipse(s, rgb("K"), (9, 12, 6, 5))  # the entrance
    shine = [(6, 5), (7, 5), (6, 6)]
    for p in shine:
        s.set_at(p, rgb("W"))
    if frame % 4 == 1:                               # a drop of honey now and then
        pygame.draw.rect(s, rgb("O"), (16, 21, 1, 2))
    return s


def egg_frames(color: str) -> list[pygame.Surface]:
    """12x16 bee egg in its rarity colour: whole, cracked, lid lifting off."""
    whole = pygame.Surface((12, 14), pygame.SRCALPHA)
    pygame.draw.ellipse(whole, pygame.Color(color), (1, 0, 10, 14))
    pygame.draw.ellipse(whole, pygame.Color(shade(color, 1.3)), (3, 2, 3, 4))
    pygame.draw.ellipse(whole, rgb("k"), (1, 0, 10, 14), 1)
    for x in range(3, 10, 3):                         # little hexagon marks
        whole.set_at((x, 9), pygame.Color(shade(color, 0.7)))
    cracked = whole.copy()
    pygame.draw.lines(cracked, rgb("k"), False, [(2, 6), (4, 4), (6, 7), (8, 4), (10, 6)])
    out = []
    for k, src in enumerate((whole, cracked)):
        f = pygame.Surface((12, 16), pygame.SRCALPHA)
        f.blit(src, (0, 2))
        out.append(f)
    split = pygame.Surface((12, 16), pygame.SRCALPHA)
    split.blit(cracked, (0, 8), pygame.Rect(0, 6, 12, 8))                      # bottom stays
    lid = cracked.subsurface(pygame.Rect(0, 0, 12, 6)).copy()
    split.blit(pygame.transform.rotate(lid, 18), (2, -2))                      # lid tips off
    out.append(split)
    return out


def decoration(name: str, frame: int = 0) -> pygame.Surface:
    """Hive decorations unlocked by upgrading the comb (spec 10.1)."""
    if name == "den_long":
        return lantern(frame)
    if name == "hoa_sen":
        s = pygame.Surface((14, 12), pygame.SRCALPHA)
        pygame.draw.rect(s, rgb("A"), (2, 6, 10, 6))
        pygame.draw.rect(s, rgb("k"), (2, 6, 10, 6), 1)
        pygame.draw.ellipse(s, rgb("V"), (0, 4, 14, 4))
        for x in (4, 7, 10):
            pygame.draw.ellipse(s, rgb("i"), (x - 2, 0, 4, 6))
        s.set_at((7, 2), rgb("o"))
        return s
    if name == "chuong_gio":
        s = pygame.Surface((10, 18), pygame.SRCALPHA)
        pygame.draw.line(s, rgb("b"), (5, 0), (5, 4))
        pygame.draw.rect(s, rgb("O"), (1, 4, 8, 2))
        for i, x in enumerate((2, 5, 8)):
            ln = 8 + (i + frame) % 3 * 2
            pygame.draw.line(s, rgb("g"), (x, 6), (x, 6 + ln))
            s.set_at((x, 6 + ln), rgb("o"))
        return s
    if name == "co_phuong":
        s = pygame.Surface((10, 26), pygame.SRCALPHA)
        pygame.draw.rect(s, rgb("b"), (1, 0, 2, 26))
        sway = (0, 1, 0, -1)[frame % 4]
        pygame.draw.polygon(s, rgb("r"), [(3, 2), (9, 3 + sway), (9, 16 + sway), (6, 13), (3, 16)])
        pygame.draw.polygon(s, rgb("k"), [(3, 2), (9, 3 + sway), (9, 16 + sway), (6, 13), (3, 16)], 1)
        s.set_at((6, 7), rgb("o"))
        return s
    raise KeyError(name)


# ------------------------------------------------------------------ Linh Thú (stage 8)
def pet_frames(look: dict) -> list[pygame.Surface]:
    """Two walking frames (16x14, facing right) of a zodiac pet, drawn from its look in
    server/data/creatures/pets.json: a body plan (quad, bird, snake, dragon), colours and
    parts (ears, tail, horns, mane, comb, stripes...). Original chibi designs."""
    out = []
    for f in range(2):
        s = pygame.Surface((16, 14), pygame.SRCALPHA)
        plan = look.get("plan", "quad")
        if plan == "snake":
            _pet_snake(s, look, f)
        elif plan == "dragon":
            _pet_dragon(s, look, f)
        elif plan == "bird":
            _pet_bird(s, look, f)
        else:
            _pet_quad(s, look, f)
        out.append(s)
    return out


def _c(hex_or_none, fallback="#2B2B2B") -> pygame.Color:
    return pygame.Color(hex_or_none or fallback)


def _pet_quad(s: pygame.Surface, look: dict, f: int) -> None:
    body, belly, ink = _c(look.get("body")), _c(look.get("belly")), rgb("k")
    bob = f
    # tail (behind the body)
    t = look.get("tail")
    if t == "thin":
        pygame.draw.line(s, ink, (3, 8 + bob), (0, 6 + bob))
    elif t == "long":
        pygame.draw.lines(s, body, False, [(3, 8 + bob), (1, 7 + bob), (0, 4 + bob), (1, 2 + bob)])
        s.set_at((1, 2 + bob), ink)
    elif t == "fluffy":
        pygame.draw.circle(s, body, (2, 7 + bob), 2)
        s.set_at((1, 6 + bob), _c(look.get("mane"), look.get("belly")))
    elif t == "curl":
        pygame.draw.circle(s, body, (2, 6 + bob), 2, 1)
    # legs (they swap between the two frames)
    for i, x in enumerate((4, 6, 9, 11)):
        h = 2 if (i + f) % 2 else 3
        pygame.draw.rect(s, shade(look.get("body", "#888888"), 0.75), (x, 11, 1, h))
    pygame.draw.ellipse(s, body, (3, 6 + bob, 10, 6))
    pygame.draw.ellipse(s, belly, (5, 9 + bob, 6, 3))
    pygame.draw.ellipse(s, ink, (3, 6 + bob, 10, 6), 1)
    if look.get("stripes"):
        for x in (6, 8, 10):
            pygame.draw.line(s, _c(look["stripes"]), (x, 7 + bob), (x, 8 + bob))
    if look.get("patch"):
        pygame.draw.circle(s, _c(look["patch"]), (6, 8 + bob), 1)
    # head
    hx, hy = 12, 4 + bob
    pygame.draw.circle(s, body, (hx, hy + 1), 3)
    if look.get("face"):
        pygame.draw.circle(s, _c(look["face"]), (hx + 1, hy + 2), 2)
    pygame.draw.circle(s, ink, (hx, hy + 1), 3, 1)
    ear = look.get("ear")
    if ear == "round":
        pygame.draw.circle(s, body, (hx - 2, hy - 2), 1)
        s.set_at((hx - 2, hy - 3), ink)
    elif ear == "point":
        pygame.draw.polygon(s, body, [(hx - 2, hy - 1), (hx - 1, hy - 4), (hx, hy - 1)])
        s.set_at((hx - 1, hy - 4), ink)
    elif ear == "long":
        pygame.draw.line(s, shade(look.get("body", "#888888"), 0.7), (hx - 2, hy - 1), (hx - 3, hy + 3))
    elif ear == "horn":
        horn = pygame.Color("#F4EBD9")
        s.set_at((hx - 2, hy - 2), horn)
        s.set_at((hx - 3, hy - 3), horn)
        s.set_at((hx + 1, hy - 2), horn)
        s.set_at((hx + 2, hy - 3), horn)
    if look.get("mane"):
        for y in range(hy - 1, hy + 3):
            s.set_at((hx - 3, y), _c(look["mane"]))
    s.set_at((hx + 1, hy), ink)                                   # eye
    s.set_at((hx + 3, hy + 2), _c(look.get("nose"), "#2B2B2B"))   # nose
    if look.get("beard"):
        s.set_at((hx + 1, hy + 4), _c(look["beard"]))
        s.set_at((hx + 1, hy + 5), _c(look["beard"]))


def _pet_bird(s: pygame.Surface, look: dict, f: int) -> None:
    body, belly, ink = _c(look.get("body")), _c(look.get("belly")), rgb("k")
    bob = f
    for i, x in enumerate((6, 9)):
        pygame.draw.line(s, pygame.Color("#C99A3A"), (x, 10), (x + (1 if (i + f) % 2 else 0), 13))
    pygame.draw.polygon(s, belly, [(4, 7 + bob), (0, 3 + bob), (2, 8 + bob)])     # tail feathers
    pygame.draw.polygon(s, _c(look.get("comb")), [(3, 7 + bob), (1, 1 + bob), (4, 6 + bob)])
    pygame.draw.ellipse(s, body, (3, 5 + bob, 9, 6))
    pygame.draw.ellipse(s, ink, (3, 5 + bob, 9, 6), 1)
    pygame.draw.line(s, belly, (5, 8 + bob), (8, 8 + bob))                         # wing
    pygame.draw.circle(s, body, (11, 4 + bob), 2)
    pygame.draw.circle(s, ink, (11, 4 + bob), 2, 1)
    comb = _c(look.get("comb"), "#BC4749")
    s.set_at((10, 1 + bob), comb)
    s.set_at((11, 1 + bob), comb)
    s.set_at((11, 6 + bob), comb)                                                   # wattle
    s.set_at((12, 3 + bob), ink)
    pygame.draw.polygon(s, pygame.Color("#E9C46A"), [(13, 4 + bob), (15, 5 + bob), (13, 5 + bob)])


def _pet_snake(s: pygame.Surface, look: dict, f: int) -> None:
    body, belly, ink = _c(look.get("body")), _c(look.get("belly")), rgb("k")
    wave = (0, 1) if f == 0 else (1, 0)
    pts = [(1, 11), (3, 10 - wave[0]), (5, 11), (7, 12 - wave[1]), (9, 11), (11, 9), (12, 7)]
    for x, y in pts:
        pygame.draw.circle(s, body, (x, y), 2)
    for x, y in pts[1:-1]:
        s.set_at((x, y + 1), belly)
    pygame.draw.circle(s, body, (13, 5), 2)
    pygame.draw.circle(s, ink, (13, 5), 2, 1)
    s.set_at((14, 4), ink)
    if f == 0:
        s.set_at((15, 6), pygame.Color("#BC4749"))                                  # tongue


def _pet_dragon(s: pygame.Surface, look: dict, f: int) -> None:
    body, belly, ink = _c(look.get("body")), _c(look.get("belly")), rgb("k")
    mane = _c(look.get("mane"), "#BC4749")
    bob = f
    pts = [(1, 6 + bob), (3, 8 - bob), (5, 9), (7, 8 + bob), (9, 7)]
    for x, y in pts:
        pygame.draw.circle(s, body, (x, y), 2)
    for x, y in pts[1:]:
        s.set_at((x, y + 1), belly)
        s.set_at((x, y - 2), mane)
    for i, x in enumerate((4, 8)):
        pygame.draw.line(s, shade(look.get("body", "#888888"), 0.7), (x, 10), (x + (1 if (i + f) % 2 else -1), 12))
    pygame.draw.circle(s, body, (12, 5), 3)
    pygame.draw.circle(s, ink, (12, 5), 3, 1)
    gold = pygame.Color("#E9C46A")
    for p in ((10, 1), (11, 2), (13, 1), (12, 2)):                                  # horns
        s.set_at(p, gold)
    s.set_at((13, 4), ink)
    s.set_at((15, 6), mane)                                                         # whiskers
    s.set_at((15, 8), mane)
    s.set_at((14, 7), belly)
