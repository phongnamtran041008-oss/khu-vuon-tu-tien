"""Loads Tiled JSON maps (.tmj) and draws them (spec 2: maps made in Tiled)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pygame

from ..art import build as B


@dataclass
class MapObject:
    id: int
    name: str
    type: str
    x: float
    y: float
    w: float
    h: float
    props: dict = field(default_factory=dict)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    @property
    def foot_y(self) -> float:
        return self.y + self.h


class TileMap:
    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text("utf-8"))
        self.w, self.h = data["width"], data["height"]
        self.tw, self.th = data["tilewidth"], data["tileheight"]
        self.props = {p["name"]: p["value"] for p in data.get("properties", [])}
        self.ground: list[int] = []
        self.objects: list[MapObject] = []
        self.solids: list[pygame.Rect] = []
        for layer in data["layers"]:
            if layer["type"] == "tilelayer" and layer["name"] == "ground":
                self.ground = layer["data"]
            elif layer["type"] == "objectgroup":
                for o in layer["objects"]:
                    props = {p["name"]: p["value"] for p in o.get("properties", [])}
                    mo = MapObject(o["id"], o.get("name", ""), o.get("type", ""), o["x"], o["y"],
                                   o["width"], o["height"], props)
                    if layer["name"] == "collision":
                        self.solids.append(mo.rect)
                    else:
                        self.objects.append(mo)
        self.px_w, self.px_h = self.w * self.tw, self.h * self.th
        self._tiles = {i + 1: B.tile(n, v) for i, (n, v) in enumerate(B.TILESET)}
        self._water_gid = next(i + 1 for i, (n, _) in enumerate(B.TILESET) if n == "water")
        self._water_frames = [B.tile("water", 0, f) for f in range(4)]
        self.water_cells = [(i % self.w, i // self.w) for i, g in enumerate(self.ground) if g == self._water_gid]
        self.surface = pygame.Surface((self.px_w, self.px_h))
        for i, gid in enumerate(self.ground):
            t = self._tiles.get(gid)
            if t:
                self.surface.blit(t, ((i % self.w) * self.tw, (i // self.w) * self.th))

    def find(self, otype: str | None = None, name: str | None = None) -> list[MapObject]:
        return [o for o in self.objects if (otype is None or o.type == otype) and (name is None or o.name == name)]

    def draw_ground(self, target: pygame.Surface, cam: tuple[int, int], t: float) -> None:
        cx, cy = cam
        target.blit(self.surface, (0, 0), pygame.Rect(cx, cy, target.get_width(), target.get_height()))
        frame = self._water_frames[int(t * 2) % 4]
        for x, y in self.water_cells:
            px, py = x * self.tw - cx, y * self.th - cy
            if -16 < px < target.get_width() and -16 < py < target.get_height():
                target.blit(frame, (px, py))

    def blocked(self, r: pygame.Rect) -> bool:
        if r.left < 0 or r.top < 0 or r.right > self.px_w or r.bottom > self.px_h:
            return True
        return r.collidelist(self.solids) != -1


_MAPS: dict[str, TileMap] = {}


def load_map(name: str) -> TileMap:
    from ..config import assets_dir
    if name not in _MAPS:
        _MAPS[name] = TileMap(assets_dir() / "maps" / f"{name}.tmj")
    return _MAPS[name]
