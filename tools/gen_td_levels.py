#!/usr/bin/env python3
"""Generate the 30 levels of Ải Thủ Vườn (spec 9.1) and the Vô Tận Trận map into
server/data/td/levels.json.

Each level has a path of grid cells from the ink gate (left) to the Linh Mạch (right), a few
rocks where nothing grows, and its waves of Mặc Quái. Paths come from hand-drawn waypoint
templates; waves are composed from a monster-health budget that grows with the level and
the wave (numbers in server/data/balance/td.json, "level_gen"). The output is deterministic,
so running the script again gives the same file unless the template or the numbers changed.

    python tools/gen_td_levels.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "server" / "data"
OUT = DATA / "td" / "levels.json"

# waypoints on the 12 x 7 grid; consecutive points share a row or a column
TEMPLATES = {
    "zigzag":  [(0, 0), (2, 0), (2, 6), (5, 6), (5, 0), (8, 0), (8, 6), (11, 6)],
    "snake":   [(0, 0), (10, 0), (10, 3), (1, 3), (1, 6), (11, 6)],
    "s_bend":  [(0, 1), (4, 1), (4, 5), (8, 5), (8, 2), (11, 2)],
    "hook":    [(0, 3), (3, 3), (3, 1), (7, 1), (7, 5), (11, 5)],
    "steps":   [(0, 6), (3, 6), (3, 2), (6, 2), (6, 4), (9, 4), (9, 0), (11, 0)],
    "comb":    [(0, 4), (2, 4), (2, 1), (5, 1), (5, 4), (8, 4), (8, 1), (11, 1)],
    "valley":  [(0, 5), (5, 5), (5, 1), (9, 1), (9, 4), (11, 4)],
    "terrace": [(0, 2), (6, 2), (6, 4), (3, 4), (3, 6), (11, 6)],
    "cliff":   [(0, 5), (4, 5), (4, 2), (7, 2), (7, 6), (11, 6)],
    "river":   [(0, 3), (11, 3)],
}
ENDLESS = [(0, 0), (10, 0), (10, 2), (1, 2), (1, 4), (10, 4), (10, 6), (11, 6)]

# chapter -> templates of its 10 levels (long paths first: easier)
CHAPTER_PATHS = {
    1: ["zigzag", "snake", "zigzag", "s_bend", "snake", "hook", "steps", "comb", "valley", "snake"],
    2: ["terrace", "cliff", "comb", "steps", "hook", "valley", "s_bend", "terrace", "cliff", "zigzag"],
    3: ["valley", "hook", "cliff", "terrace", "s_bend", "comb", "steps", "river", "hook", "snake"],
}

NAMES = {
    1: ["Ngõ Trúc", "Luống Rau Đầu Hè", "Giàn Mướp", "Bờ Ao Sau Nhà", "Vạt Cải Vàng",
        "Hàng Rào Dâm Bụt", "Bậc Đá Rêu", "Vườn Ươm Hạt Chữ", "Thung Cỏ May", "Cổng Linh Mạch"],
    2: ["Lối Mòn Trúc Biếc", "Suối Mực Chảy Ngược", "Rặng Trúc Kẽo Kẹt", "Đồi Măng Non", "Am Tranh Bỏ Hoang",
        "Đầm Sen Đen", "Khe Đá Mù Sương", "Bãi Lau Gió", "Vách Trúc Khắc Chữ", "Hang Mực Vương"],
    3: ["Cửa Linh Mạch Cổ", "Bậc Thang Ngọc", "Giếng Mực Ngàn Năm", "Thềm Bia Vỡ", "Hành Lang Đèn Lồng",
        "Điện Thư Pháp", "Sân Đá Tam Sinh", "Sông Mực Thẳng Tắp", "Vọng Lâu Gió Bấc", "Tâm Linh Mạch"],
}


def expand(points: list[tuple[int, int]]) -> list[list[int]]:
    cells = [list(points[0])]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        assert x0 == x1 or y0 == y1, (x0, y0, x1, y1)
        dx = (x1 > x0) - (x1 < x0)
        dy = (y1 > y0) - (y1 < y0)
        x, y = x0, y0
        while (x, y) != (x1, y1):
            x, y = x + dx, y + dy
            cells.append([x, y])
    assert len({tuple(c) for c in cells}) == len(cells), "a path must not cross itself"
    return cells


def rocks_for(path: list[list[int]], cols: int, rows: int, rng: random.Random, n: int) -> list[list[int]]:
    """A few rocks away from the path (cosmetic, and they take a couple of good spots)."""
    on = {tuple(c) for c in path}
    spots = [(x, y) for y in range(rows) for x in range(cols) if (x, y) not in on]
    rng.shuffle(spots)
    out = []
    for x, y in spots:
        near = sum(1 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) if (x + dx, y + dy) in on)
        if near == 0 and len(out) < n:
            out.append([x, y])
    return sorted(out)


def compose_waves(n_index: int, n_waves: int, td: dict, rng: random.Random, boss: bool) -> list[list[dict]]:
    g = td["level_gen"]
    mons = td["monsters"]
    kinds = [k for k, first in g["kinds"] if first <= n_index]
    newest = kinds[-1]
    waves = []
    for w in range(n_waves):
        budget = (g["budget_first"] + g["budget_first_per_level"] * (n_index - 1)
                  + (g["budget_wave"] + g["budget_wave_per_level"] * (n_index - 1)) * w)
        gap_hi, gap_lo = g["gap_ms"]
        gap = int(gap_hi - (gap_hi - gap_lo) * min(1.0, (n_index - 1 + w) / 30))
        groups, at = [], 0
        # the newest kind of this level shows up from the second wave, a few at a time
        pool = kinds if w >= 1 else (kinds[:-1] or kinds)
        while budget > 0:
            kind = newest if (w >= 1 and kind_due(groups, newest) and rng.random() < 0.35) else rng.choice(pool)
            hp = mons[kind]["hp"]
            n = max(1, min(5, int(budget / hp)))
            if n * hp > budget and groups:
                break
            groups.append({"m": kind, "n": n, "gap": gap, "at": at})
            budget -= n * hp
            at += n * gap + g["group_pause_ms"]
        if boss and w == n_waves - 1:
            groups.append({"m": "mac_vuong", "n": 1, "gap": gap, "at": at + 800})
        waves.append(groups)
    return waves


def kind_due(groups: list[dict], kind: str) -> bool:
    return sum(1 for g in groups if g["m"] == kind) < 2


def build() -> dict:
    td = json.loads((DATA / "balance" / "td.json").read_text("utf-8"))
    cols, rows = td["grid"]["cols"], td["grid"]["rows"]
    g = td["level_gen"]
    levels = []
    for ch in (1, 2, 3):
        for i in range(10):
            lid = f"c{ch}_{i + 1:02d}"
            n_index = (ch - 1) * 10 + i + 1
            rng = random.Random(lid)
            path = expand(TEMPLATES[CHAPTER_PATHS[ch][i]])
            levels.append({
                "id": lid, "chapter": ch, "index": i + 1, "name_vi": NAMES[ch][i],
                "path": path, "rocks": rocks_for(path, cols, rows, rng, 3 + ch),
                "waves": compose_waves(n_index, g["waves"][str(ch)][i], td, rng, n_index in g["boss_levels"]),
            })
    endless_path = expand(ENDLESS)
    return {
        "_comment": "Sinh bởi tools/gen_td_levels.py, đừng sửa tay: sửa template trong script hoặc số liệu trong balance/td.json rồi chạy lại.",
        "levels": levels,
        "endless": {"id": "endless", "name_vi": "Vô Tận Trận", "path": endless_path,
                    "rocks": rocks_for(endless_path, cols, rows, random.Random("endless"), 2)},
    }


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # one level per line: readable diffs, still compact
    text = text.replace('{"id":"c', '\n{"id":"c').replace(',"endless":', ',\n"endless":')
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['levels'])} levels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
