#!/usr/bin/env python3
"""A simple Thủ Vườn player for tests and balancing (spec 9). It plays like a careful
beginner: greedy placement on the cells that cover the most path, a couple of Mộc blockers,
upgrades when it has spare Linh Khí, every break question and Tụ Khí whenever ready.

`decide(sim)` only looks at a td_sim.Sim and returns the actions to take now, so the same
strategy drives the pure simulation (server tests, `python tools/td_bot.py`) and the real
client in the UI test.

    python tools/td_bot.py            # every level with a typical loadout: result, stars
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ATTACK_ORDER = ["kim", "hoa", "thuy", "son", "quang"]


def _coverage(sim, x: int, y: int, rng: float) -> int:
    rr = rng * rng
    return sum(1 for px, py in sim.path if (px - x) ** 2 + (py - y) ** 2 <= rr)


def best_cell(sim, word: str) -> tuple[int, int] | None:
    role = sim.defs[word]["role"]
    r = sim.roles[role]
    best, score = None, -1.0
    for y in range(sim.rows):
        for x in range(sim.cols):
            if sim.can_place(x, y, word) not in (None, "no_qi"):
                continue
            if r.get("on_path"):
                i = sim.path_at[(x, y)]
                frac = i / max(1, len(sim.path) - 1)
                if frac < 0.35 or frac > 0.9:
                    continue
                covered = sum(1 for c in sim.order if sim.plants[c].role in ATTACK_ORDER and i in sim.plants[c].reach)
                s = covered * 10 - abs(frac - 0.65) * 10
                s -= 30 * sum(1 for j in sim.moc_at if abs(j - i) < 3)
            elif role == "ho_tro":
                s = sum(2 if sim.plants[nb].role in ATTACK_ORDER else 0
                        for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if nb in sim.plants)
                if s == 0:
                    continue
            elif role == "sinh_khi":
                s = -_coverage(sim, x, y, 2.5)   # keep good spots for fighters
            else:
                s = _coverage(sim, x, y, r["range"])
            if s > score:
                best, score = (x, y), s
    return best


def _count(sim, role: str) -> int:
    return sum(1 for c in sim.order if sim.plants[c].role == role)


def wanted(sim) -> list[str]:
    """Plant words in the order this player would like to place them next."""
    by_role: dict[str, list[str]] = {}
    for w, d in sim.defs.items():
        by_role.setdefault(d["role"], []).append(w)
    for ws in by_role.values():
        ws.sort(key=lambda w: -sim.defs[w]["power"])
    hidden = any(sim.kinds[k].get("hidden") for k in sim.kinds if any(
        g["m"] == k for wave in (sim.p.get("waves") or []) for g in wave)) or not sim.p.get("waves")
    out = []
    if "sinh_khi" in by_role and _count(sim, "sinh_khi") < (1 if sim.wave < 3 else 2):
        out.append(by_role["sinh_khi"][0])
    if hidden and "quang" in by_role and _count(sim, "quang") < 2:
        out.append(by_role["quang"][0])
    if "moc" in by_role and _count(sim, "moc") < 1 + sim.wave // 3 and _count(sim, "moc") < 3:
        out.append(by_role["moc"][0])
    fighters = [r for r in ATTACK_ORDER if r in by_role and r != "quang"]
    if fighters:
        counts = sorted(fighters, key=lambda r: (_count(sim, r), ATTACK_ORDER.index(r)))
        out.extend(by_role[r][0] for r in counts)
    if "ho_tro" in by_role and _count(sim, "ho_tro") < 2 and len(sim.plants) >= 4:
        out.append(by_role["ho_tro"][0])
    return out


def decide(sim, allow_upgrade: bool = True) -> list[dict]:
    """Actions to take right now (without "s"; the caller adds the step). Placement first;
    an upgrade (which needs a question) is returned as {"k": "up", ...} without "q"."""
    acts: list[dict] = []
    for word in wanted(sim):
        if sim.qi < sim.cost_to_place(word):
            break
        cell = best_cell(sim, word)
        if cell is not None:
            return [{"k": "place", "x": cell[0], "y": cell[1], "w": word}]
    if allow_upgrade and len(sim.plants) >= 5:
        best = None
        for c in sim.order:
            pl = sim.plants[c]
            cost = sim.cost_to_upgrade(pl)
            if pl.role in ATTACK_ORDER and cost is not None and sim.qi >= cost + 40:
                key = (pl.level, -len(pl.reach))
                if best is None or key < best[0]:
                    best = (key, pl)
        if best:
            pl = best[1]
            acts.append({"k": "up", "x": pl.x, "y": pl.y, "w": pl.word})
    return acts


def skill_now(sim) -> str | None:
    for w, d in sim.defs.items():
        if d.get("skill") and w not in sim.skills_used and sim.phase == "wave":
            if sum(m.max_hp for m in sim.monsters) > 500 or any(sim.kinds[m.kind].get("boss") for m in sim.monsters):
                return w
    return None


def play(td_sim, params: dict, accuracy: float = 0.85, seed: int = 1, ask=None) -> tuple[object, dict, list]:
    """Play a whole level in the pure simulation. Returns (sim, answers, events).
    `ask(kind, word) -> (session id, right?)` asks a real question (server tests); without it
    the answers are made up with the given accuracy."""
    rng = random.Random(seed)
    answers: dict = {}
    sim = td_sim.Sim(params, answers)
    events: list = []
    n = [0]

    def question(kind: str, word: str) -> str:
        if ask is not None:
            sid, ok = ask(kind, word)
        else:
            n[0] += 1
            sid, ok = f"q{n[0]}", rng.random() < accuracy
        answers[sid] = {"kind": kind, "word": word, "ok": ok}
        return sid

    def do(ev: dict) -> None:
        ev = {"s": sim.step_n, **ev}
        sim.apply(ev)
        events.append(ev)

    any_word = next(iter(params["plants"]))
    while sim.phase not in (td_sim.WON, td_sim.LOST):
        if sim.phase == td_sim.BUILD:
            for _ in range(params["qi"]["break_questions"]):
                do({"k": "qi", "q": question("break", any_word)})
            for _ in range(30):
                acts = decide(sim)
                if not acts:
                    break
                a = acts[0]
                if a["k"] == "up":
                    do({"k": "up", "x": a["x"], "y": a["y"], "q": question("upgrade", a["w"])})
                else:
                    do(a)
            do({"k": "wave"})
            continue
        sim.step()
        if sim.phase != td_sim.WAVE:
            continue
        if sim.step_n - sim.last_tu_khi >= sim.tu_khi_cd() and sim.step_n % 7 == 0:
            do({"k": "qi", "q": question("tu_khi", any_word)})
        w = skill_now(sim)
        if w:
            do({"k": "skill", "w": w})
        if sim.step_n % 10 == 0:
            acts = decide(sim)
            if acts:
                a = acts[0]
                if a["k"] == "up":
                    do({"k": "up", "x": a["x"], "y": a["y"], "q": question("upgrade", a["w"])})
                else:
                    do(a)
    return sim, answers, events


TYPICAL = {"火": 50, "水": 50, "木": 50, "山": 40, "一": 40, "茶": 40, "妈妈": 40, "月": 40}


def typical_plants(mastery: dict[str, int] | None = None, wither: float = 0.0) -> dict:
    """A beginner's loadout from the real word list and plant roles."""
    sys.path.insert(0, str(ROOT / "server"))
    from app.learning.wordbank import bank
    from app.systems import td
    out = {}
    for w in bank().words.values():
        m = (mastery or TYPICAL).get(w.hanzi)
        if m is not None:
            out[w.id] = {"role": td.role_of(w.id), "hanzi": w.hanzi, "pinyin": w.pinyin, "power": td.power(m, wither)}
            sk = td.cfg()["idiom_skills"].get(w.hanzi)
            if sk:
                out[w.id]["skill"] = sk
    return out


def main() -> int:
    sys.path.insert(0, str(ROOT / "server"))
    from app.systems import td, td_sim
    acc = float(sys.argv[1]) if len(sys.argv) > 1 else 0.85
    plus = int(sys.argv[2]) if len(sys.argv) > 2 else 0      # extra mastery for everyone
    plants = typical_plants({k: min(100, v + plus) for k, v in TYPICAL.items()})
    for lv in td.level_data()["levels"]:
        res = []
        for seed in (1, 2, 3):
            sim, answers, events = play(td_sim, td.build_params(lv, plants, 7), acc, seed)
            res.append(f"{sim.phase[:1]}{sim.hp:>2}w{sim.wave}")
        print(lv["id"], lv["name_vi"][:18].ljust(18), " ".join(res), "plants", len(sim.plants),
              "steps", sim.step_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
