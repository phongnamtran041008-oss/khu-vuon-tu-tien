#!/usr/bin/env python3
"""Export every code-defined sprite to PNG spritesheets in client/assets/sprites/
(spec 18). The client can also build the same surfaces in memory, so the PNGs are for
inspection, for the Tiled editor (tiles.png) and for packaging."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from client.art import build as B  # noqa: E402

OUT = ROOT / "client" / "assets" / "sprites"


def sheet(surfs: list[pygame.Surface], cols: int) -> pygame.Surface:
    w = max(s.get_width() for s in surfs)
    h = max(s.get_height() for s in surfs)
    rows = (len(surfs) + cols - 1) // cols
    out = pygame.Surface((w * cols, h * rows), pygame.SRCALPHA)
    for i, s in enumerate(surfs):
        out.blit(s, ((i % cols) * w, (i // cols) * h))
    return out


def main() -> int:
    pygame.init()
    OUT.mkdir(parents=True, exist_ok=True)
    pygame.image.save(B.tileset_surface(), str(OUT / "tiles.png"))
    frames = B.character_frames({"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"})
    pygame.image.save(sheet([frames[(d, f)] for d in B.DIRS for f in range(3)], 3), str(OUT / "player_base.png"))
    pygame.image.save(sheet(B.truc_lao_frames() + B.horse_frames(), 4), str(OUT / "npcs.png"))
    seeds = [s for r in ("common", "rare", "epic", "legendary") for s in B.seed_frames(r)]
    pygame.image.save(sheet(seeds, 3), str(OUT / "seeds.png"))
    plants = [B.plant(st, r, "sheet") for r in ("common", "rare", "epic", "legendary") for st in range(6)]
    pygame.image.save(sheet(plants, 6), str(OUT / "plants.png"))
    props = [B.hut(), B.shrine(), B.bamboo(), B.tablet(), B.table(), B.gate(), B.mat(), B.rock()]
    pygame.image.save(sheet(props, 4), str(OUT / "props.png"))
    # Linh Phong (stage 5): every species x 2 wing frames, eggs by rarity, the hive and its decorations
    import json
    species = json.loads((ROOT / "server" / "data" / "creatures" / "bees.json").read_text("utf-8"))
    bees = [f for k, v in species.items() if not k.startswith("_") for f in B.bee_frames(v["look"])]
    pygame.image.save(sheet(bees, 6), str(OUT / "bees.png"))
    pets = json.loads((ROOT / "server" / "data" / "creatures" / "pets.json").read_text("utf-8"))["species"]
    pygame.image.save(sheet([f for v in pets.values() for f in B.pet_frames(v["look"])], 6), str(OUT / "pets.png"))
    eggs = [f for c in ("#7D7468", "#6A994E", "#4A7CC8", "#8E5AC8", "#C99A3A") for f in B.egg_frames(c)]
    hive = [B.hive(i) for i in range(2)] + [B.decoration(d) for d in ("den_long", "hoa_sen", "chuong_gio", "co_phuong")]
    pygame.image.save(sheet(eggs + hive, 6), str(OUT / "hive.png"))
    print("sprites written to", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
