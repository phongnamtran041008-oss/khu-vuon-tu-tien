"""Bí cảnh art (stage 9), drawn with code from the palette like the rest of client/art: the
three realm Mặc Quái (Mặc Ảnh, Bút Yêu and the boss Nghiên Ma, 48x48), the gate in the
village, the Khe Nứt Mực rift, and the puzzle props (stones, numbered tiles, tone pillars,
the statue, the mirror, the door and the chest)."""
from __future__ import annotations

import math

import pygame

from .palette import rgb


def _s(w: int, h: int) -> pygame.Surface:
    return pygame.Surface((w, h), pygame.SRCALPHA)


# ------------------------------------------------------------------ monsters
def muc_anh(frame: int) -> pygame.Surface:
    """Mặc Ảnh: a hooded shade of ink with two pale eyes, its hem dripping."""
    s = _s(20, 22)
    sway = (0, 1)[frame % 2]
    body = [(10, 1), (16, 6), (17, 14), (18 - sway, 21), (13, 18), (10, 21), (7, 18), (2 + sway, 21), (3, 14), (4, 6)]
    pygame.draw.polygon(s, (*rgb("K"), 230), body)
    pygame.draw.polygon(s, rgb("k"), body, 1)
    pygame.draw.polygon(s, (*rgb("G"), 160), [(10, 3), (14, 7), (6, 7)])
    for x in (7, 12):
        pygame.draw.rect(s, rgb("w"), (x, 9, 2, 2))
    pygame.draw.line(s, rgb("u"), (7, 11), (8, 11))
    pygame.draw.line(s, rgb("u"), (12, 11), (13, 11))
    return s


def but_yeu(frame: int) -> pygame.Surface:
    """Bút Yêu: a brush come alive, bamboo shaft, an inky tuft and one angry eye."""
    s = _s(16, 24)
    lean = (0, 1)[frame % 2]
    pygame.draw.rect(s, rgb("V"), (6 + lean, 1, 4, 13))
    for y in (4, 8, 12):
        pygame.draw.line(s, rgb("n"), (6 + lean, y), (9 + lean, y))
    pygame.draw.rect(s, rgb("r"), (5 + lean, 13, 6, 2))
    tuft = [(4, 15), (12, 15), (11, 20), (8, 23 - lean), (5, 20)]
    pygame.draw.polygon(s, rgb("K"), tuft)
    pygame.draw.polygon(s, rgb("k"), tuft, 1)
    pygame.draw.rect(s, rgb("W"), (7 + lean, 6, 3, 3))
    pygame.draw.rect(s, rgb("r"), (8 + lean, 7, 1, 1))
    for i in range(2):
        pygame.draw.circle(s, rgb("K"), (3 + i * 10, 22 - (frame + i) % 2), 1)
    return s


def nghien_ma(frame: int) -> pygame.Surface:
    """Nghiên Ma (boss, 48x48): an inkstone grown into a crouching beast, its well full of ink
    and a vermilion seal for an eye."""
    s = _s(48, 48)
    breathe = (0, 1)[frame % 2]
    pygame.draw.ellipse(s, (0, 0, 0, 70), (6, 40, 36, 7))
    stone = pygame.Rect(5, 14 - breathe, 38, 30 + breathe)
    pygame.draw.rect(s, rgb("G"), stone, border_radius=6)
    pygame.draw.rect(s, rgb("k"), stone, 2, border_radius=6)
    for y in (24, 31, 37):
        pygame.draw.line(s, rgb("T"), (9, y - breathe), (39, y - breathe))
    well = pygame.Rect(11, 17 - breathe, 26, 9)
    pygame.draw.ellipse(s, rgb("K"), well)
    pygame.draw.ellipse(s, (*rgb("u"), 90), well.inflate(-12, -5))
    for x in (8, 18, 30, 40):   # stubby stone claws
        pygame.draw.rect(s, rgb("k"), (x - 2, 42, 4, 4))
    horns = [((9, 15), (4, 4), (14, 13)), ((39, 15), (44, 4), (34, 13))]
    for a, b, c in horns:
        pygame.draw.polygon(s, rgb("K"), [a, b, c])
    pygame.draw.rect(s, rgb("r"), (21, 28 - breathe, 6, 6))
    pygame.draw.rect(s, rgb("o"), (23, 30 - breathe, 2, 2))
    for i in range(3):   # ink dripping from the jaw
        x = 14 + i * 9
        pygame.draw.line(s, rgb("K"), (x, 44), (x, 46 + (frame + i) % 2))
    return s


MONSTERS = {"muc_anh": muc_anh, "but_yeu": but_yeu, "nghien_ma": nghien_ma}


def monster_frames(kind: str) -> list[pygame.Surface]:
    return [MONSTERS[kind](f) for f in range(2)]


# ------------------------------------------------------------------ village gate and rift
def realm_gate(frame: int = 0) -> pygame.Surface:
    """40x40 Cổng Bí Cảnh: two black stone posts and a torn curtain of ink between them."""
    s = _s(40, 40)
    tear = _s(24, 30)
    for y in range(30):
        w = 6 + int(5 * math.sin((y + frame * 2) * 0.5)) + (y % 7 == 0) * 2
        pygame.draw.line(tear, (*rgb("m"), 120), (12 - w, y), (12 + w, y))
        pygame.draw.line(tear, (*rgb("K"), 220), (12 - w // 2, y), (12 + w // 2, y))
    s.blit(tear, (8, 8))
    for x in (2, 32):
        pygame.draw.rect(s, rgb("K"), (x, 6, 6, 34))
        pygame.draw.rect(s, rgb("G"), (x, 6, 6, 34), 1)
    pygame.draw.rect(s, rgb("k"), (0, 2, 40, 6))
    pygame.draw.rect(s, rgb("r"), (16, 0, 8, 5))
    return s


def rift(frame: int = 0) -> pygame.Surface:
    """24x32 Khe Nứt Mực: a vertical tear in the air, ink swirling, purple light at the rim."""
    s = _s(24, 32)
    for y in range(30):
        k = math.sin(y / 29 * math.pi)
        w = int(2 + 7 * k + math.sin(y * 0.8 + frame) * 1.5)
        pygame.draw.line(s, (*rgb("m"), 110), (12 - w - 2, y + 1), (12 + w + 2, y + 1))
        pygame.draw.line(s, rgb("K"), (12 - w, y + 1), (12 + w, y + 1))
    for i in range(4):
        a = frame * 0.7 + i * 1.6
        pygame.draw.circle(s, rgb("i"), (12 + int(math.cos(a) * 5), 16 + int(math.sin(a) * 10)), 1)
    return s


# ------------------------------------------------------------------ puzzle props
def pedestal(active: bool, lit: bool) -> pygame.Surface:
    """24x24 stone pedestal seen from above; the active ones glow, gold when someone stands on."""
    s = _s(24, 24)
    pygame.draw.ellipse(s, rgb("T"), (1, 3, 22, 18))
    pygame.draw.ellipse(s, rgb("k"), (1, 3, 22, 18), 1)
    pygame.draw.ellipse(s, rgb("t"), (4, 5, 16, 12))
    if active:
        pygame.draw.ellipse(s, (*rgb("o" if lit else "a"), 170), (5, 6, 14, 10), 2)
    return s


def rune_tile(state: str) -> pygame.Surface:
    """20x20 numbered floor stone: 'idle', 'next' (glowing), 'done' (gold), 'off' (unused)."""
    s = _s(20, 20)
    base = {"off": "G", "idle": "T", "next": "t", "done": "O"}[state]
    pygame.draw.rect(s, rgb(base), (1, 1, 18, 18))
    pygame.draw.rect(s, rgb("k"), (1, 1, 18, 18), 1)
    if state == "next":
        pygame.draw.rect(s, (*rgb("o"), 200), (2, 2, 16, 16), 2)
    return s


TONE_CURVES = {1: [(3, 9), (11, 9)], 2: [(3, 15), (11, 8)], 3: [(3, 10), (7, 16), (11, 8)], 4: [(3, 8), (11, 16)]}


def pillar(tone: int, glow: bool = False) -> pygame.Surface:
    """16x32 stone pillar with its tone contour carved in red (spec 14.2: Trụ Thanh Điệu)."""
    s = _s(16, 32)
    pygame.draw.rect(s, rgb("T"), (2, 2, 12, 28))
    pygame.draw.rect(s, rgb("k"), (2, 2, 12, 28), 1)
    pygame.draw.rect(s, rgb("t"), (0, 0, 16, 4))
    pygame.draw.rect(s, rgb("k"), (0, 0, 16, 4), 1)
    pygame.draw.rect(s, rgb("t"), (0, 28, 16, 4))
    pygame.draw.rect(s, rgb("k"), (0, 28, 16, 4), 1)
    pts = [(x + 1, y + 2) for x, y in TONE_CURVES[tone]]
    pygame.draw.lines(s, rgb("o" if glow else "r"), False, pts, 2)
    return s


def statue(frame: int = 0) -> pygame.Surface:
    """24x32 the reading statue: a stone scholar holding a scroll."""
    s = _s(24, 32)
    pygame.draw.rect(s, rgb("T"), (2, 24, 20, 8))
    pygame.draw.rect(s, rgb("k"), (2, 24, 20, 8), 1)
    pygame.draw.polygon(s, rgb("t"), [(6, 24), (8, 10), (16, 10), (18, 24)])
    pygame.draw.polygon(s, rgb("k"), [(6, 24), (8, 10), (16, 10), (18, 24)], 1)
    pygame.draw.circle(s, rgb("t"), (12, 7), 5)
    pygame.draw.circle(s, rgb("k"), (12, 7), 5, 1)
    pygame.draw.rect(s, rgb("w"), (7, 15, 10, 5))
    pygame.draw.rect(s, rgb("k"), (7, 15, 10, 5), 1)
    if frame % 2:
        pygame.draw.circle(s, rgb("o"), (12, 7), 2)
    return s


def mirror(frame: int = 0) -> pygame.Surface:
    """48x40 the meaning mirror: a round bronze mirror on a stand over a pool of light."""
    s = _s(48, 40)
    pygame.draw.ellipse(s, (*rgb("a"), 90), (4, 26, 40, 13))
    pygame.draw.rect(s, rgb("O"), (22, 18, 4, 12))
    pygame.draw.circle(s, rgb("O"), (24, 12), 11)
    pygame.draw.circle(s, rgb("k"), (24, 12), 11, 1)
    pygame.draw.circle(s, rgb("a"), (24, 12), 8)
    a = frame * 0.8
    pygame.draw.line(s, rgb("W"), (20 + int(math.cos(a) * 2), 8), (23, 6), 1)
    return s


def realm_exit(opened: bool, frame: int = 0) -> pygame.Surface:
    """32x24 the room's door in the north wall: sealed with ink, or open on light."""
    s = _s(32, 24)
    pygame.draw.rect(s, rgb("k"), (0, 0, 32, 24))
    inner = pygame.Rect(4, 4, 24, 20)
    if opened:
        pygame.draw.rect(s, (*rgb("o"), 200), inner)
        pygame.draw.rect(s, rgb("W"), inner.inflate(-10, -6))
    else:
        pygame.draw.rect(s, rgb("K"), inner)
        for i in range(3):
            y = 7 + i * 5 + frame % 2
            pygame.draw.line(s, rgb("G"), (6, y), (25, y))
    pygame.draw.rect(s, rgb("r"), (13, 0, 6, 3))
    return s


def chest(opened: bool) -> pygame.Surface:
    """24x18 the treasure chest of the den (spec 14.3)."""
    s = _s(24, 18)
    pygame.draw.rect(s, rgb("b"), (1, 7, 22, 10))
    pygame.draw.rect(s, rgb("k"), (1, 7, 22, 10), 1)
    if opened:
        pygame.draw.rect(s, rgb("o"), (3, 4, 18, 4))
        pygame.draw.polygon(s, rgb("B"), [(1, 7), (4, 0), (20, 0), (23, 7)])
    else:
        pygame.draw.rect(s, rgb("B"), (1, 2, 22, 6))
    pygame.draw.rect(s, rgb("k"), (1, 2, 22, 6), 1)
    pygame.draw.rect(s, rgb("O"), (10, 6, 4, 5))
    return s
