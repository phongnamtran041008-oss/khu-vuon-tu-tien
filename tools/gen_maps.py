#!/usr/bin/env python3
"""Generate the Tiled maps (.tmj, Tiled JSON 1.10) used by the client.

The abode map is laid out by code so it can be regenerated, and it opens in the Tiled
editor (https://www.mapeditor.org) for hand editing afterwards. Tile ids refer to
client/assets/sprites/tiles.png (written by tools/gen_sprites.py); props and areas are
rectangle objects whose `sprite`/`kind` property the client understands.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "client" / "assets" / "maps"
sys.path.insert(0, str(ROOT))

from client.art.build import TILESET  # noqa: E402

T = 16
GID = {f"{n}{v}": i + 1 for i, (n, v) in enumerate(TILESET)}


def abode() -> dict:
    W, H = 40, 24
    rng = random.Random("abode")
    ground = []
    for y in range(H):
        for x in range(W):
            r = rng.random()
            g = GID["grass0"] if r < 0.6 else GID["grass1"] if r < 0.85 else GID["grass2"]
            if r > 0.96:
                g = GID["flowers0"] if r > 0.98 else GID["flowers1"]
            if x < 2 or x >= W - 2 or y < 2 or y >= H - 2:
                g = GID["bamboo_floor0"]
            ground.append(g)

    def setg(x, y, gid):
        if 0 <= x < W and 0 <= y < H:
            ground[y * W + x] = gid

    def path(x0, y0, x1, y1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                setg(x, y, GID["path0"] if (x + y) % 3 else GID["path1"])

    # garden 5x5 plots of 32px at tiles (14..23, 7..16), framed by a path
    gx, gy = 14, 7
    path(gx - 1, gy - 1, gx + 10, gy - 1)
    path(gx - 1, gy + 10, gx + 10, gy + 10)
    path(gx - 1, gy - 1, gx - 1, gy + 10)
    path(gx + 10, gy - 1, gx + 10, gy + 10)
    path(19, gy + 10, 20, H - 3)          # to the gate
    path(8, 8, gx - 1, 8)                 # to the hut
    path(gx + 10, 8, 30, 8)               # to the shrine
    # pond (ao nhỏ), bottom-left
    for y in range(16, 20):
        for x in range(4, 10):
            setg(x, y, GID["water0"])
    for x in range(3, 11):
        setg(x, 15, GID["stone0"])
        setg(x, 20, GID["stone0"])
    for y in range(15, 21):
        setg(3, y, GID["stone0"])
        setg(10, y, GID["stone0"])
    # wooden deck in front of the hut
    for x in range(4, 9):
        setg(x, 7, GID["wood0"])

    objects, collision = [], []
    oid = [1]

    def obj(name, otype, x, y, w, h, **props):
        o = {"id": oid[0], "name": name, "type": otype, "x": x, "y": y, "width": w, "height": h,
             "rotation": 0, "visible": True,
             "properties": [{"name": k, "type": "string", "value": str(v)} for k, v in props.items()]}
        oid[0] += 1
        objects.append(o)
        return o

    def solid(x, y, w, h):
        collision.append({"id": oid[0], "name": "", "type": "solid", "x": x, "y": y, "width": w,
                          "height": h, "rotation": 0, "visible": True})
        oid[0] += 1

    # bamboo ring
    for x in range(0, W * T, T):
        obj("bamboo", "prop", x, -12, 16, 40, sprite="bamboo", variant=x // T)
        if not (18 * T <= x <= 21 * T):  # gap for the gate
            obj("bamboo", "prop", x, (H - 2) * T - 8, 16, 40, sprite="bamboo", variant=x // T + 50)
    for y in range(2 * T, (H - 2) * T, T):
        obj("bamboo", "prop", 0, y - 8, 16, 40, sprite="bamboo", variant=y // T + 100)
        obj("bamboo", "prop", (W - 1) * T, y - 8, 16, 40, sprite="bamboo", variant=y // T + 200)
    solid(0, 0, W * T, 2 * T)
    solid(0, (H - 2) * T, 18 * T, 2 * T)
    solid(22 * T, (H - 2) * T, (W - 22) * T, 2 * T)
    solid(0, 0, 2 * T, H * T)
    solid((W - 2) * T, 0, 2 * T, H * T)

    obj("hut", "prop", 3 * T, 4 * T - 8, 64, 56, sprite="hut")
    solid(3 * T + 6, 4 * T + 16, 52, 30)
    obj("Trúc Lão", "npc", 9 * T, 6 * T, 16, 24, npc="truc_lao")
    solid(9 * T + 2, 6 * T + 14, 12, 10)
    obj("Thiên Cơ Đài", "interact", 30 * T, 5 * T, 32, 44, sprite="shrine", action="gacha")
    solid(30 * T + 2, 5 * T + 30, 28, 14)
    obj("Bia Phát Hiện", "interact", 25 * T, 4 * T, 16, 24, sprite="tablet", action="discoveries")
    solid(25 * T + 2, 4 * T + 16, 12, 8)
    obj("Bàn Ghép Câu", "interact", 9 * T, 10 * T, 24, 16, sprite="table", action="craft")
    solid(9 * T + 1, 10 * T + 6, 22, 8)
    obj("Bàn đả tọa", "interact", 30 * T, 15 * T, 24, 16, sprite="mat", action="meditate")
    obj("Linh Phong Sào", "interact", 27 * T, 11 * T, 24, 32, sprite="hive", action="hive")
    solid(27 * T + 7, 11 * T + 24, 10, 8)
    obj("Đan Lô", "interact", 34 * T, 16 * T, 24, 28, sprite="furnace", action="alchemy")   # stage 8
    solid(34 * T + 3, 16 * T + 16, 18, 12)
    obj("Cổng tre", "interact", 18 * T + 8, (H - 3) * T - 4, 32, 32, sprite="gate", action="exit")
    obj("pond", "area", 4 * T, 16 * T, 6 * T, 4 * T, kind="pond")
    solid(4 * T, 16 * T, 6 * T, 4 * T)
    for (x, y) in ((27, 17), (34, 11), (12, 18)):
        obj("rock", "prop", x * T, y * T, 16, 12, sprite="rock")
        solid(x * T + 2, y * T + 4, 12, 8)
    obj("garden", "area", gx * T, gy * T, 5 * 32, 5 * 32, kind="garden")
    obj("spawn", "spawn", 19 * T + 8, (H - 5) * T, 1, 1)

    return {
        "compressionlevel": -1, "height": H, "width": W, "infinite": False,
        "orientation": "orthogonal", "renderorder": "right-down", "tiledversion": "1.10.2",
        "tileheight": T, "tilewidth": T, "type": "map", "version": "1.10",
        "nextlayerid": 4, "nextobjectid": oid[0],
        "properties": [{"name": "zone", "type": "string", "value": "abode"},
                       {"name": "name_vi", "type": "string", "value": "Động Phủ"}],
        "layers": [
            {"id": 1, "name": "ground", "type": "tilelayer", "width": W, "height": H, "x": 0, "y": 0,
             "opacity": 1, "visible": True, "data": ground},
            {"id": 2, "name": "objects", "type": "objectgroup", "draworder": "topdown", "opacity": 1,
             "visible": True, "x": 0, "y": 0, "objects": objects},
            {"id": 3, "name": "collision", "type": "objectgroup", "draworder": "topdown", "opacity": 1,
             "visible": False, "x": 0, "y": 0, "objects": collision},
        ],
        "tilesets": [{"firstgid": 1, "name": "tiles", "image": "../sprites/tiles.png",
                      "imagewidth": 128, "imageheight": 16 * ((len(TILESET) + 7) // 8), "tilewidth": T, "tileheight": T,
                      "tilecount": len(TILESET), "columns": 8, "margin": 0, "spacing": 0}],
    }


class MapBuilder:
    """Small helper for the stage 3 zones: ground grid + objects + collision rectangles."""

    def __init__(self, zone: str, name_vi: str, w: int, h: int, seed: str):
        self.zone, self.name_vi, self.W, self.H = zone, name_vi, w, h
        self.rng = random.Random(seed)
        self.ground = [0] * (w * h)
        self.objects: list[dict] = []
        self.collision: list[dict] = []
        self.oid = 1
        self.blocked_tiles: set[tuple[int, int]] = set()   # where scatter props may not go

    def setg(self, x, y, key):
        if 0 <= x < self.W and 0 <= y < self.H:
            self.ground[y * self.W + x] = GID[key]

    def fill(self, x0, y0, x1, y1, keys, reserve=True):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                k = keys if isinstance(keys, str) else keys[(x * 7 + y * 3) % len(keys)]
                self.setg(x, y, k)
                if reserve:
                    self.blocked_tiles.add((x, y))

    def obj(self, name, otype, x, y, w, h, **props):
        o = {"id": self.oid, "name": name, "type": otype, "x": x, "y": y, "width": w, "height": h,
             "rotation": 0, "visible": True,
             "properties": [{"name": k, "type": "string", "value": str(v)} for k, v in props.items()]}
        self.oid += 1
        self.objects.append(o)
        return o

    def solid(self, x, y, w, h):
        self.collision.append({"id": self.oid, "name": "", "type": "solid", "x": x, "y": y, "width": w,
                               "height": h, "rotation": 0, "visible": True})
        self.oid += 1

    def reserve(self, x, y, w, h, pad=1):
        """Mark tiles under a building so trees are not scattered into it."""
        for ty in range(int(y // T) - pad, int((y + h) // T) + pad + 1):
            for tx in range(int(x // T) - pad, int((x + w) // T) + pad + 1):
                self.blocked_tiles.add((tx, ty))

    def building(self, name, sprite, tx, ty, w, h, foot_h, otype="prop", **props):
        """Places a sprite whose bottom `foot_h` pixels are solid."""
        x, y = tx * T, ty * T
        self.obj(name, otype, x, y, w, h, sprite=sprite, **props)
        self.solid(x + 2, y + h - foot_h, w - 4, foot_h)
        self.reserve(x, y, w, h)

    def npc(self, name, look, tx, ty, **props):
        self.obj(name, "npc", tx * T, ty * T, 16, 24, npc=look, **props)
        self.solid(tx * T + 2, ty * T + 14, 12, 10)
        self.reserve(tx * T, ty * T, 16, 24, pad=1)

    def tree(self, tx, ty, sprite="tree"):
        x, y = tx * T - 8, ty * T - 24
        self.obj("tree", "prop", x, y, 32, 40, sprite=sprite, variant=self.rng.randrange(1000))
        self.solid(x + 12, y + 32, 9, 7)

    def ring(self, sprite, gaps):
        """Border of trees/bamboo with openings; gaps = set of (side, tile index)."""
        W, H = self.W, self.H
        for x in range(0, W):
            for side, yy in (("n", 0), ("s", H - 1)):
                if (side, x) in gaps:
                    continue
                if sprite == "bamboo":
                    self.obj("bamboo", "prop", x * T, yy * T - 24 + (8 if side == "n" else -8), 16, 40,
                             sprite="bamboo", variant=x + (0 if side == "n" else 300))
                elif x % 2 == 0:
                    self.tree(x, 1 if side == "n" else H - 1, sprite)
        for y in range(1, H - 1):
            for side, xx in (("w", 0), ("e", W - 1)):
                if (side, y) in gaps:
                    continue
                if sprite == "bamboo":
                    self.obj("bamboo", "prop", xx * T, y * T - 24, 16, 40, sprite="bamboo",
                             variant=y + (600 if side == "w" else 900))
                elif y % 2 == 0:
                    self.tree(xx, y + 1, sprite)
        # border collision with the gaps left open
        def runs(side, n):
            start = None
            for i in range(n + 1):
                open_ = i == n or (side, i) in gaps
                if not open_ and start is None:
                    start = i
                if open_ and start is not None:
                    yield start, i
                    start = None
        for a, b in runs("n", W):
            self.solid(a * T, 0, (b - a) * T, T + 8)
        for a, b in runs("s", W):
            self.solid(a * T, (H - 1) * T - 4, (b - a) * T, T + 4)
        for a, b in runs("w", H):
            self.solid(0, a * T, T, (b - a) * T)
        for a, b in runs("e", H):
            self.solid((W - 1) * T, a * T, T, (b - a) * T)

    def scatter_trees(self, n, sprite="tree", area=None):
        x0, y0, x1, y1 = area or (2, 2, self.W - 3, self.H - 3)
        placed = 0
        for _ in range(n * 30):
            if placed >= n:
                break
            tx, ty = self.rng.randrange(x0, x1 + 1), self.rng.randrange(y0, y1 + 1)
            near = {(tx + dx, ty + dy) for dx in (-1, 0, 1) for dy in (-2, -1, 0, 1)}
            if near & self.blocked_tiles:
                continue
            self.tree(tx, ty, sprite)
            self.blocked_tiles |= near
            placed += 1

    def build(self, extra_props: dict | None = None) -> dict:
        props = [{"name": "zone", "type": "string", "value": self.zone},
                 {"name": "name_vi", "type": "string", "value": self.name_vi}]
        for k, v in (extra_props or {}).items():
            props.append({"name": k, "type": "string", "value": str(v)})
        W, H = self.W, self.H
        return {
            "compressionlevel": -1, "height": H, "width": W, "infinite": False,
            "orientation": "orthogonal", "renderorder": "right-down", "tiledversion": "1.10.2",
            "tileheight": T, "tilewidth": T, "type": "map", "version": "1.10",
            "nextlayerid": 4, "nextobjectid": self.oid, "properties": props,
            "layers": [
                {"id": 1, "name": "ground", "type": "tilelayer", "width": W, "height": H, "x": 0, "y": 0,
                 "opacity": 1, "visible": True, "data": self.ground},
                {"id": 2, "name": "objects", "type": "objectgroup", "draworder": "topdown", "opacity": 1,
                 "visible": True, "x": 0, "y": 0, "objects": self.objects},
                {"id": 3, "name": "collision", "type": "objectgroup", "draworder": "topdown", "opacity": 1,
                 "visible": False, "x": 0, "y": 0, "objects": self.collision},
            ],
            "tilesets": [{"firstgid": 1, "name": "tiles", "image": "../sprites/tiles.png",
                          "imagewidth": 128, "imageheight": 16 * ((len(TILESET) + 7) // 8),
                          "tilewidth": T, "tileheight": T, "tilecount": len(TILESET), "columns": 8,
                          "margin": 0, "spacing": 0}],
        }


def village() -> dict:
    """Trúc Lâm Thôn: the safe hub (spec 7.1). Gate south -> abode, east -> Rừng Mực Loang."""
    m = MapBuilder("truc_lam_thon", "Trúc Lâm Thôn", 56, 36, "village")
    W, H = m.W, m.H
    for y in range(H):
        for x in range(W):
            r = m.rng.random()
            m.setg(x, y, "grass0" if r < 0.6 else "grass1" if r < 0.85 else
                   ("flowers0" if r > 0.98 else "flowers1" if r > 0.96 else "grass2"))
    south_gap = set(range(26, 30))
    east_gap = set(range(16, 20))
    west_gap = set(range(16, 20))
    # roads and the square
    m.fill(26, 24, 29, H - 1, ["path0", "path1", "path0"])            # south road to the abode
    m.fill(36, 16, W - 1, 19, ["path0", "path1", "path0"])            # east road to the forest
    m.fill(26, 8, 29, 11, ["path0", "path1"])                         # north to Thiên Cơ Các
    m.fill(10, 16, 19, 19, ["path0", "path1"])                        # west to the market
    m.fill(0, 16, 9, 19, ["path0", "path1", "path0"])                 # stage 6: west road to Hồ Nghiên Mực
    m.fill(20, 12, 35, 23, ["plaza0", "plaza1"])                      # the square
    m.fill(30, 24, 31, 27, ["path0", "path1"])
    m.fill(32, 27, 45, 28, ["path0", "path1"])                        # to Cổng Thủ Vườn
    m.fill(8, 9, 11, 15, ["path0", "path1"])                          # to Trúc Lão's house
    m.fill(36, 10, 39, 15, ["path0", "path1"])                        # to the library
    # pond in the south-west corner
    for y in range(26, 31):
        for x in range(4, 11):
            m.setg(x, y, "water0")
    m.solid(4 * T, 26 * T, 7 * T, 5 * T)
    m.reserve(4 * T, 26 * T, 7 * T, 5 * T)
    m.ring("bamboo", {("s", x) for x in south_gap} | {("e", y) for y in east_gap} | {("w", y) for y in west_gap})
    # buildings and service points (actions are handled by the client; spec 7.1)
    m.building("Thiên Cơ Các", "pavilion", 25, 3, 64, 64, 22, otype="interact", action="gacha")
    m.building("Tàng Thư Các", "library", 36, 4, 64, 56, 24, otype="interact", action="library")
    m.building("Nhà Trúc Lão", "hut", 6, 4, 64, 56, 30)
    m.npc("Trúc Lão", "truc_lao", 10, 8, action="talk_master")
    m.building("Sạp Tạp Hóa", "stall", 11, 13, 40, 32, 12, otype="interact", action="shop", variant=0)
    m.npc("Bà Chủ Sạp", "shopkeeper", 13, 11, action="shop")
    m.building("Sạp Vải", "stall", 11, 20, 40, 32, 12, otype="interact", action="cloth", variant=1)
    m.building("Lò Luyện Đan", "furnace", 16, 25, 24, 28, 14, otype="interact", action="alchemy")
    m.npc("Đan Sư", "alchemist", 14, 25, action="alchemy")
    m.building("Lò Rèn", "anvil", 21, 27, 24, 20, 10, otype="interact", action="forge")
    m.npc("Thợ Rèn", "smith", 23, 26, action="forge")
    m.building("Bảng Nhiệm Vụ", "board", 32, 10, 24, 28, 8, otype="interact", action="quests")
    m.building("Cổng Thủ Vườn", "td_gate", 44, 24, 40, 40, 6, otype="interact", action="td")
    m.obj("Giếng", "prop", 27 * T + 4, 16 * T, 24, 24, sprite="well")
    m.solid(27 * T + 6, 16 * T + 12, 20, 12)
    m.npc("Tiểu Lan", "guide", 30, 29, action="talk_guide")
    m.npc("Thủ Thư", "librarian", 41, 9, action="library")
    for i, (tx, ty) in enumerate(((20, 12), (35, 12), (20, 23), (35, 23), (25, 24), (30, 24))):
        m.obj("lantern", "prop", tx * T + 4, ty * T - 16, 8, 24, sprite="lantern", variant=i)
        m.solid(tx * T + 6, ty * T + 4, 4, 4)
    for i, (tx, ty) in enumerate(((44, 6), (49, 10), (42, 31), (49, 31), (3, 19), (36, 30))):
        m.building("Nhà dân", "house", tx, ty, 48, 48, 20, variant=i)
    m.obj("sign", "prop", 33 * T, 18 * T - 4, 16, 20, sprite="sign")
    m.obj("Đi Rừng Mực Loang", "sign", 52 * T, 14 * T, 16, 20, sprite="sign",
          text="Rừng Mực Loang →")
    m.solid(52 * T + 6, 14 * T + 14, 4, 6)
    m.scatter_trees(26)
    # zone exits (server checks the player stands inside before moving them)
    m.obj("to_abode", "portal", 26 * T, (H - 1) * T - 2, 4 * T, T + 10, target="abode", target_spawn="spawn")
    m.obj("Cổng Đông", "prop", (W - 2) * T, 16 * T - 8, 32, 40, sprite="portal")
    m.obj("to_forest", "portal", (W - 1) * T - 4, 16 * T, T + 12, 4 * T, target="rung_muc_loang",
          target_spawn="from_village")
    m.obj("spawn", "spawn", 28 * T, 21 * T, 1, 1)
    m.obj("from_abode", "spawn", 28 * T, (H - 3) * T, 1, 1)
    m.obj("from_forest", "spawn", (W - 4) * T, 18 * T, 1, 1)
    # stage 6: the pond can be fished (spec 11.1), the west gate leads to Hồ Nghiên Mực
    m.obj("pond", "area", 4 * T, 26 * T, 7 * T, 5 * T, kind="pond", pool="ao")
    m.obj("Cổng Tây", "prop", 0, 16 * T - 8, 32, 40, sprite="portal")
    m.obj("to_lake", "portal", -8, 16 * T, T + 12, 4 * T, target="ho_nghien_muc", target_spawn="from_village")
    m.obj("Đi Hồ Nghiên Mực", "sign", 3 * T, 14 * T, 16, 20, sprite="sign", text="← Hồ Nghiên Mực")
    m.solid(3 * T + 6, 14 * T + 14, 4, 6)
    m.obj("from_lake", "spawn", 3 * T, 18 * T, 1, 1)
    # stage 9: Cổng Bí Cảnh on the square (secret realms, spec 14)
    m.building("Cổng Bí Cảnh", "realm_gate", 21, 12, 40, 40, 6, otype="interact", action="realm")
    m.obj("from_realm", "spawn", 22 * T + 4, 16 * T + 4, 1, 1)
    return m.build({"music": "village", "safe": "true"})


def forest() -> dict:
    """Rừng Mực Loang: first zone with Mặc Quái (spec 7.1). West gate -> Trúc Lâm Thôn."""
    m = MapBuilder("rung_muc_loang", "Rừng Mực Loang", 60, 40, "forest")
    W, H = m.W, m.H
    for y in range(H):
        for x in range(W):
            r = m.rng.random()
            m.setg(x, y, "dark_grass0" if r < 0.6 else "dark_grass1" if r < 0.96 else
                   ("ink0" if r > 0.985 else "ink1"))
    west_gap = set(range(18, 22))
    # a winding dirt trail
    y = 19
    for x in range(0, W - 6):
        if x % 6 == 0 and x > 4:
            ny = max(6, min(H - 9, y + m.rng.choice((-2, -1, 0, 1, 2))))
            m.fill(x, min(y, ny), x + 2, max(y, ny) + 2, "dirt0")
            y = ny
        m.fill(x, y, x, y + 2, "dirt0")
    for y in range(8, 30):  # side trail north-south
        m.fill(38, y, 39, y, "dirt0")
    # a clearing where the ink is thickest
    for yy in range(26, 33):
        for xx in range(42, 54):
            m.setg(xx, yy, "ink0" if m.rng.random() < 0.3 else "ink1" if m.rng.random() < 0.3 else "dark_grass0")
            m.blocked_tiles.add((xx, yy))
    m.ring("ink_tree", {("w", y) for y in west_gap})
    m.obj("Cổng Tây", "prop", 0, 18 * T - 8, 32, 40, sprite="portal")
    m.obj("to_village", "portal", -8, 18 * T, T + 12, 4 * T, target="truc_lam_thon", target_spawn="from_forest")
    m.obj("Về Trúc Lâm Thôn", "sign", 3 * T, 15 * T, 16, 20, sprite="sign", text="← Trúc Lâm Thôn")
    m.solid(3 * T + 6, 15 * T + 14, 4, 6)
    m.reserve(0, 15 * T, 6 * T, 8 * T, pad=0)
    for i, (tx, ty) in enumerate(((14, 8), (30, 32), (52, 10), (24, 14))):
        m.obj("rock", "prop", tx * T, ty * T, 16, 12, sprite="rock", variant=i)
        m.solid(tx * T + 2, ty * T + 4, 12, 8)
        m.blocked_tiles.add((tx, ty))
    # where the monsters roam (stage 3: they wander; Vấn Đạo combat comes in stage 4)
    m.obj("slimes_entrance", "monster_area", 12 * T, 14 * T, 14 * T, 12 * T, monster="ink_slime", count=6)
    m.obj("wisps_north", "monster_area", 30 * T, 4 * T, 18 * T, 10 * T, monster="tone_wisp", count=4)
    m.obj("clearing", "monster_area", 42 * T, 24 * T, 12 * T, 9 * T, monster="ink_slime", count=5)
    m.obj("clearing_wisps", "monster_area", 42 * T, 24 * T, 12 * T, 9 * T, monster="tone_wisp", count=2)
    m.obj("fox_den", "monster_area", 44 * T, 26 * T, 8 * T, 6 * T, monster="ink_fox", count=1)
    m.scatter_trees(45, "ink_tree")
    m.scatter_trees(15, "tree")
    m.obj("spawn", "spawn", 4 * T, 20 * T, 1, 1)
    m.obj("from_village", "spawn", 4 * T, 20 * T, 1, 1)
    return m.build({"music": "forest", "safe": "false"})


def lake() -> dict:
    """Hồ Nghiên Mực: the main fishing lake (spec 7.1, 11) with Ngư Ông on his dock and a few
    Mặc Quái on the shores. East gate -> Trúc Lâm Thôn."""
    m = MapBuilder("ho_nghien_muc", "Hồ Nghiên Mực", 56, 38, "lake")
    W, H = m.W, m.H
    for y in range(H):
        for x in range(W):
            r = m.rng.random()
            m.setg(x, y, "grass0" if r < 0.55 else "grass1" if r < 0.85 else
                   ("flowers1" if r > 0.97 else "grass2"))
    east_gap = set(range(17, 21))
    water = [(14, 7, 41, 25), (10, 12, 13, 19), (42, 10, 45, 16)]   # inclusive tile rects
    dock = (27, 19, 28, 26)
    for x0, y0, x1, y1 in water:   # stone shore first, water over it
        m.fill(x0 - 1, y0 - 1, x1 + 1, y1 + 1, "stone0")
    for x0, y0, x1, y1 in water:
        m.fill(x0, y0, x1, y1, "water0")
    m.fill(dock[0], dock[1], dock[2], dock[3], "wood0")
    for x0, y0, x1, y1 in ((14, 7, 26, 25), (29, 7, 41, 25), (27, 7, 28, 18), (10, 12, 13, 19), (42, 10, 45, 16)):
        m.solid(x0 * T, y0 * T, (x1 - x0 + 1) * T, (y1 - y0 + 1) * T)
    for i, (x0, y0, x1, y1) in enumerate(water):   # where a fishing line can go (server checks it)
        m.obj(f"lake_{i}", "area", x0 * T, y0 * T, (x1 - x0 + 1) * T, (y1 - y0 + 1) * T, kind="fishing", pool="ho")
    m.fill(29, 26, 50, 27, ["path0", "path1"])                         # shore path to the east gate
    m.fill(50, 17, W - 1, 20, ["path0", "path1", "path0"])
    m.fill(50, 21, 51, 27, ["path0", "path1"])
    m.building("Lều Ngư Ông", "hut", 18, 28, 64, 56, 30)
    m.npc("Ngư Ông", "fisher", 25, 27, action="fisher")
    m.obj("Bảng Ngư Phổ", "interact", 31 * T, 28 * T, 16, 24, sprite="tablet", action="fish_book")
    m.solid(31 * T + 2, 28 * T + 16, 12, 8)
    m.reserve(31 * T, 28 * T, 16, 24)
    for i, (tx, ty) in enumerate(((26, 26), (29, 26))):
        m.obj("lantern", "prop", tx * T + 4, ty * T - 16, 8, 24, sprite="lantern", variant=i)
    m.ring("tree", {("e", y) for y in east_gap})
    m.obj("Cổng Đông", "prop", (W - 2) * T, 17 * T - 8, 32, 40, sprite="portal")
    m.obj("to_village", "portal", (W - 1) * T - 4, 17 * T, T + 12, 4 * T, target="truc_lam_thon",
          target_spawn="from_lake")
    m.obj("Về Trúc Lâm Thôn", "sign", 51 * T, 15 * T, 16, 20, sprite="sign", text="Trúc Lâm Thôn →")
    m.solid(51 * T + 6, 15 * T + 14, 4, 6)
    m.reserve(48 * T, 14 * T, 8 * T, 8 * T, pad=0)
    m.reserve(16 * T, 26 * T, 18 * T, 6 * T, pad=0)
    for i, (tx, ty) in enumerate(((8, 24), (47, 20), (12, 5))):
        m.obj("rock", "prop", tx * T, ty * T, 16, 12, sprite="rock", variant=i)
        m.solid(tx * T + 2, ty * T + 4, 12, 8)
        m.blocked_tiles.add((tx, ty))
    # Mặc Quái along the shores, away from Ngư Ông's dock
    m.obj("slimes_west", "monster_area", 2 * T, 22 * T, 10 * T, 12 * T, monster="ink_slime", count=5)
    m.obj("wisps_north", "monster_area", 18 * T, 1 * T, 24 * T, 5 * T, monster="tone_wisp", count=3)
    m.obj("slimes_east", "monster_area", 46 * T, 26 * T, 8 * T, 9 * T, monster="ink_slime", count=3)
    m.scatter_trees(34)
    m.obj("spawn", "spawn", (W - 4) * T, 19 * T, 1, 1)
    m.obj("from_village", "spawn", (W - 4) * T, 19 * T, 1, 1)
    return m.build({"music": "forest", "safe": "false"})


REALM_ROOM_W, REALM_ROOM_H = 22, 16
REALM_LAYOUT = (("compose", 0, 0), ("sentence", 1, 0), ("tone", 2, 0), ("mirror", 0, 1), ("maze", 1, 1), ("boss", 2, 1))


def secret_realm() -> dict:
    """Bí cảnh (spec 14): six walled rooms, one per puzzle kind plus the boss's den. A run
    uses 3-5 of the puzzle rooms in a random order; the server moves the party from room to
    room (they are not joined by corridors). Puzzle props are `realm_obj` objects whose
    `kind` the server and the client both understand; their state is sent at run time."""
    RW, RH = REALM_ROOM_W, REALM_ROOM_H
    m = MapBuilder("bi_canh", "Bí Cảnh", RW * 3, RH * 2, "realm")

    def ro(kind, x, y, w, h, room, **props):
        m.obj(f"{room}_{kind}{props.get('n', props.get('slot', props.get('tone', '')))}", "realm_obj", x, y, w, h,
              kind=kind, room=room, **props)

    for room, col, row in REALM_LAYOUT:
        x0, y0 = col * RW, row * RH
        for y in range(y0, y0 + RH):
            for x in range(x0, x0 + RW):
                edge = x in (x0, x0 + RW - 1) or y in (y0, y0 + RH - 1)
                m.setg(x, y, "realm_wall0" if edge else ("realm_floor0" if (x + y) % 3 else "realm_floor1"))
        m.solid(x0 * T, y0 * T, RW * T, T + 6)
        m.solid(x0 * T, (y0 + RH - 1) * T - 2, RW * T, T + 2)
        m.solid(x0 * T, y0 * T, T, RH * T)
        m.solid((x0 + RW - 1) * T, y0 * T, T, RH * T)
        m.obj(room, "realm_room", (x0 + 1) * T, (y0 + 1) * T, (RW - 2) * T, (RH - 2) * T, kind=room)
        cx, cy = x0 + 11, y0 + 7
        entry = ((x0 + 11) * T, (y0 + RH - 3) * T + 8)
        exit_tile = (x0 + 10, y0 + 1)
        if room == "compose":
            for slot, (tx, ty) in (("top", (cx, cy - 3)), ("bottom", (cx, cy + 3)), ("left", (cx - 4, cy)),
                                   ("right", (cx + 4, cy))):
                ro("pedestal", tx * T - 4, ty * T - 4, 24, 24, room, slot=slot)
        elif room == "sentence":
            for i in range(1, 9):
                tx = cx - 7 + 2 * (i - 1)
                ro("tile", tx * T - 2, cy * T - 2, 20, 20, room, n=i)
        elif room == "tone":
            for tone, (tx, ty) in ((1, (cx - 5, cy - 3)), (2, (cx + 5, cy - 3)), (3, (cx - 5, cy + 3)),
                                   (4, (cx + 5, cy + 3))):
                ro("pillar", tx * T, ty * T - 16, 16, 32, room, tone=tone)
                m.solid(tx * T + 2, ty * T + 6, 12, 10)
            ro("statue", cx * T - 4, (cy - 2) * T, 24, 32, room)
            m.solid(cx * T - 2, (cy - 2) * T + 22, 20, 10)
        elif room == "mirror":
            ro("mirror", (cx - 1) * T, (cy - 4) * T, 3 * T, 2 * T, room)
        elif room == "maze":
            # a perfect maze on the interior: cells on odd sub-tiles, walls between them
            gw, gh = RW - 3, RH - 3                      # 19 x 13 sub-grid
            open_ = {(i, j) for i in range(1, gw, 2) for j in range(1, gh, 2)}
            seen, stack = {(1, gh - 2)}, [(1, gh - 2)]
            while stack:
                ci, cj = stack[-1]
                nxt = [(ci + di, cj + dj, di, dj) for di, dj in ((2, 0), (-2, 0), (0, 2), (0, -2))
                       if (ci + di, cj + dj) in open_ and (ci + di, cj + dj) not in seen]
                if not nxt:
                    stack.pop()
                    continue
                ni, nj, di, dj = m.rng.choice(nxt)
                open_.add((ci + di // 2, cj + dj // 2))
                seen.add((ni, nj))
                stack.append((ni, nj))
            open_ |= {(1, gh - 1), (1, gh), (gw - 2, 0)}  # the way in (bottom left) and out (top right)
            for j in range(RH - 2):
                run = None
                for i in range(RW - 1):
                    wall = i < RW - 2 and (i, j) not in open_
                    tx, ty = x0 + 1 + i, y0 + 1 + j
                    if wall:
                        m.setg(tx, ty, "realm_wall0")
                        if run is None:
                            run = i
                    elif run is not None:
                        m.solid((x0 + 1 + run) * T, ty * T, (i - run) * T, T)
                        run = None
            entry = ((x0 + 2) * T + 8, (y0 + RH - 2) * T + 12)
            exit_tile = (x0 + 1 + gw - 2, y0 + 1)
            ro("maze_exit", exit_tile[0] * T - 4, exit_tile[1] * T, T + 8, T + 4, room)
        elif room == "boss":
            ro("boss_spawn", cx * T, (cy - 3) * T, 16, 16, room)
            ro("chest", cx * T - 4, (cy - 1) * T, 24, 18, room)
        ro("exit", exit_tile[0] * T, exit_tile[1] * T - 8, 2 * T if room != "maze" else T, T + 8, room)
        m.obj(f"{room}_entry", "spawn", *entry, 1, 1)
    m.obj("spawn", "spawn", 11 * T, (RH - 3) * T + 8, 1, 1)
    return m.build({"music": "forest", "safe": "false", "dark": "true"})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    server_maps = ROOT / "server" / "maps"
    server_maps.mkdir(parents=True, exist_ok=True)
    for name, fn in (("abode", abode), ("truc_lam_thon", village), ("rung_muc_loang", forest),
                     ("ho_nghien_muc", lake), ("bi_canh", secret_realm)):
        m = fn()
        data = json.dumps(m, ensure_ascii=False, indent=1).encode("utf-8")   # LF on every OS
        (OUT / f"{name}.tmj").write_bytes(data)
        (server_maps / f"{name}.tmj").write_bytes(data)
        print("wrote", (OUT / f"{name}.tmj").relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
