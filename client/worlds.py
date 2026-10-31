"""Worlds saved on this computer (Minecraft style). Each world is a folder:

    <data_dir>/worlds/<slug>/world.json   name, dates, the world's own token secret
    <data_dir>/worlds/<slug>/world.db     everything players did in it (SQLite)
    <data_dir>/worlds/<slug>/server.log   what the world's server printed last time

Copy the folder to back a world up or move it to another PC.
"""
from __future__ import annotations

import json
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import data_dir


def worlds_dir() -> Path:
    d = data_dir() / "worlds"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class World:
    slug: str
    path: Path
    name: str
    created: float
    last_played: float
    secret: str

    @property
    def db_path(self) -> Path:
        return self.path / "world.db"

    @property
    def size_kb(self) -> int:
        return int(self.db_path.stat().st_size / 1024) if self.db_path.exists() else 0

    def save(self) -> None:
        (self.path / "world.json").write_text(json.dumps(
            {"name": self.name, "created": self.created, "last_played": self.last_played, "secret": self.secret},
            ensure_ascii=False, indent=2), "utf-8")

    def touch(self) -> None:
        self.last_played = time.time()
        self.save()


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFD", name.lower().replace("đ", "d"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:32] or "the-gioi"


def load(path: Path) -> World | None:
    try:
        d = json.loads((path / "world.json").read_text("utf-8"))
        return World(path.name, path, str(d["name"]), float(d.get("created", 0)), float(d.get("last_played", 0)),
                     str(d["secret"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_worlds() -> list[World]:
    out = [w for p in worlds_dir().iterdir() if p.is_dir() and (w := load(p))]
    return sorted(out, key=lambda w: w.last_played, reverse=True)


def create(name: str) -> World:
    name = " ".join(name.split())[:32] or "Khu Vườn"
    base = slugify(name)
    slug, n = base, 1
    while (worlds_dir() / slug).exists():
        n += 1
        slug = f"{base}-{n}"
    path = worlds_dir() / slug
    path.mkdir(parents=True)
    now = time.time()
    w = World(slug, path, name, now, now, secrets.token_hex(32))
    w.save()
    return w
