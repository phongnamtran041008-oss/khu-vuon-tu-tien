"""Stage 6 client pieces without a server: where F works, the fish icons, and that the reel
minigame the client plays is the server's own code."""
from __future__ import annotations

import json
from pathlib import Path

import pygame

from client.engine import fishing_sim as fs
from client.engine.tilemap import load_map
from client.scenes.fishing import fish_icon, water_near

ROOT = Path(__file__).resolve().parents[2]


def test_reel_minigame_is_the_servers_code():
    assert (ROOT / "client" / "engine" / "fishing_sim.py").read_bytes() == \
        (ROOT / "server" / "app" / "systems" / "fishing_sim.py").read_bytes()
    p = {"seed": 5, "zone": 0.3, "agility": 2.2, "range": 0.35, "seg_ms": [900, 1900], "gain": 0.32, "loss": 0.16,
         "start": 0.3, "lift": 3.0, "gravity": 2.4, "vmax": 1.3, "strain_up": 0.55, "strain_down": 0.4, "max_ms": 60000}
    assert fs.replay(p, []).result == fs.ESCAPED
    assert fs.replay(p, [0]).result == fs.SNAPPED


def test_water_is_found_at_the_pond_the_lake_and_not_on_dry_land():
    abode = load_map("abode")
    assert water_near(abode, 10 * 16 + 7, 17 * 16 + 8, "left") is not None      # beside the pond
    assert water_near(abode, 19 * 16 + 8, 19 * 16, "down") is None               # the spawn
    lake = load_map("ho_nghien_muc")
    area, (bx, by) = water_near(lake, 27.9 * 16, 19.6 * 16, "up")                 # end of the dock
    assert area.props["pool"] == "ho" and area.x <= bx <= area.x + area.w and area.y <= by <= area.y + area.h
    spawn = lake.find("spawn")[0]
    assert water_near(lake, spawn.x, spawn.y, "left") is None
    village = load_map("truc_lam_thon")
    assert any(o.type == "area" and o.props.get("kind") == "pond" for o in village.objects)


def test_every_species_has_an_icon():
    pygame.init()
    data = json.loads((ROOT / "server" / "data" / "creatures" / "fish.json").read_text("utf-8"))
    for fid, f in data.items():
        if fid.startswith("_"):
            continue
        img = fish_icon(f["shape"], f["color"], f.get("color2"))
        dark = fish_icon(f["shape"], f["color"], dark=True)
        assert img.get_size() == (22, 12) and dark.get_size() == (22, 12)
        assert img.get_bounding_rect().w > 10
