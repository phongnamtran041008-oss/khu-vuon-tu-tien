"""Ải Thủ Vườn (spec 9.1, 9.2, 16): levels and their unlocking, the loadout of up to 8 plant
types, a run from start to finish, the Linh Khí questions and the weekly Vô Tận Trận board.

The game runs on the client (td_sim.py, the same file on both sides). The server picks the
seed, sends every number the simulation needs, asks and grades every question, and at the
end replays the client's event log (`td_sim.replay`): only a log that reaches exactly the
result the client claims, within a believable real time, earns anything. A run in progress
is saved in `td_runs` with its log, so a game closed mid-level can continue it.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import random
import uuid
from functools import lru_cache

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import balance, clock
from ..config import DATA_DIR
from ..learning import quiz, selection, srs
from ..learning import question_bank as qb
from ..learning.wordbank import bank
from ..models import (Character, CodexEntry, Collection, Plot, QuizSession, Seed, TdLoadout, TdProgress, TdRun,
                      User)
from . import catalog, cultivation, inventory, items, td_sim

ENDLESS = "endless"


class TdError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(message_vi)
        self.status, self.code, self.message_vi = status, code, message_vi


def cfg() -> dict:
    return balance.load("td")


@lru_cache(maxsize=1)
def level_data() -> dict:
    return json.loads((DATA_DIR / "td" / "levels.json").read_text("utf-8"))


def levels() -> dict[str, dict]:
    return {lv["id"]: lv for lv in level_data()["levels"]}


@lru_cache(maxsize=1)
def roles_data() -> dict:
    return json.loads((DATA_DIR / "plants" / "plant_roles.json").read_text("utf-8"))


def role_of(word_id: str) -> str:
    """Spec 9.2: special characters by hand, the rest by topic."""
    w = bank().get(word_id)
    rd = roles_data()
    return rd["by_hanzi"].get(w.hanzi) or rd["by_topic"][w.topic]


def power(mastery: float, wither: float) -> float:
    """Spec 9.1: mastery 0 -> 60%, 100 -> 130%; wither in the real garden up to -30%."""
    p = cfg()["power"]
    m = max(0.0, min(100.0, float(mastery))) / 100
    w = max(0.0, min(100.0, float(wither))) / 100
    return round((p["mastery_min"] + (p["mastery_max"] - p["mastery_min"]) * m) * (1 - p["wither_max_penalty"] * w), 4)


def week_key(now: dt.datetime) -> str:
    y, w, _ = (now + clock.VN_OFFSET).isocalendar()
    return f"{ENDLESS}_{y}w{w:02d}"


# ------------------------------------------------------------------ plants the player can bring
async def plant_entries(db: AsyncSession, user: User) -> dict[str, dict]:
    """Every learned word as a plant: role, power from mastery and the real garden's wither
    (the healthiest plot of that word counts; a word not growing now has no wither)."""
    cols = (await db.execute(select(Collection).where(
        Collection.user_id == user.id, Collection.introduced.is_(True)))).scalars().all()
    now = clock.now()
    wither: dict[str, float] = {}
    from ..garden.garden import wither_rate
    rate = await wither_rate(db, user.id)
    for p in (await db.execute(select(Plot).where(Plot.user_id == user.id, Plot.word_id.is_not(None)))).scalars():
        srs.refresh_wither(p, now, rate)
        wither[p.word_id] = min(wither.get(p.word_id, 100.0), p.wither)
    out = {}
    b = bank()
    skills = cfg()["idiom_skills"]
    for c in cols:
        if c.word_id not in b.words:
            continue
        w = b.get(c.word_id)
        role = role_of(c.word_id)
        e = {"word_id": w.id, "hanzi": w.hanzi, "pinyin": w.pinyin, "meaning_vi": w.meaning_vi,
             "rarity": w.rarity, "role": role, "mastery": c.mastery, "wither": round(wither.get(w.id, 0.0), 1),
             "power": power(c.mastery, wither.get(w.id, 0.0))}
        if role == "thanh_ngu":
            e["skill"] = skills.get(w.hanzi)
            if e["skill"] is None:
                continue
        out[w.id] = e
    return out


def sim_plants(entries: dict[str, dict], loadout: list[str]) -> dict[str, dict]:
    out = {}
    for wid in loadout:
        e = entries[wid]
        d = {"role": e["role"], "hanzi": e["hanzi"], "pinyin": e["pinyin"], "power": e["power"], "rarity": e["rarity"]}
        if e.get("skill"):
            d["skill"] = e["skill"]
        out[wid] = d
    return out


def build_params(level: dict, plants: dict[str, dict], seed: int, endless: bool = False) -> dict:
    """Everything td_sim needs (sent to the client as is)."""
    c = cfg()
    p = {"level": level["id"], "cols": c["grid"]["cols"], "rows": c["grid"]["rows"],
         "path": level["path"], "rocks": level.get("rocks", []), "core_hp": c["core_hp"],
         "qi": c["qi"], "upgrade": c["upgrade"], "sell_refund": c["sell_refund"], "roles": c["roles"],
         "monsters": c["monsters"], "combos": c["combos"], "boss_stun_mult": c["boss_stun_mult"],
         "wave_max_seconds": c["wave_max_seconds"], "plants": plants, "seed": seed}
    if endless:
        p["waves"] = None
        p["endless"] = {k: v for k, v in c["endless"].items() if not k.startswith("_")}
        p["hp_mult"] = 1.0
    else:
        ch = next(x for x in c["chapters"] if x["id"] == level["chapter"])
        p["waves"] = level["waves"]
        p["hp_mult"] = ch["hp_mult"]
        p["qi"] = {**c["qi"], "start": ch["qi_start"]}
    return p


# ------------------------------------------------------------------ progress and unlocking
async def progress(db: AsyncSession, user_id: int) -> dict[str, TdProgress]:
    return {r.level_id: r for r in (await db.execute(select(TdProgress).where(TdProgress.user_id == user_id))).scalars()}


def unlocked(level_id: str, prog: dict[str, TdProgress], realm: str) -> tuple[bool, str | None]:
    """(open, why not). The first level is open; each next one needs the one before cleared;
    a new chapter also needs its realm (spec 9.1: chapters follow the realms)."""
    c = cfg()
    if level_id == ENDLESS:
        need = c["endless"]["unlock_level"]
        ok = prog.get(need) is not None and prog[need].stars > 0
        return ok, None if ok else f"Qua ải {levels()[need]['name_vi']} để mở Vô Tận Trận."
    lv = levels()[level_id]
    ch = next(x for x in c["chapters"] if x["id"] == lv["chapter"])
    order = cultivation.order()
    if order.index(realm) < order.index(ch["min_realm"]):
        return False, f"Cần đạt {cultivation.realm_name(ch['min_realm'])}."
    ids = [x["id"] for x in level_data()["levels"]]
    i = ids.index(level_id)
    if i == 0:
        return True, None
    prev = prog.get(ids[i - 1])
    if prev is None or prev.stars <= 0:
        return False, f"Qua ải {levels()[ids[i - 1]]['name_vi']} trước đã."
    return True, None


async def _char(db: AsyncSession, user: User) -> Character:
    ch = await db.get(Character, user.id)
    if ch is None:
        raise TdError(400, "no_character", "Hãy tạo nhân vật trước.")
    return ch


def _daily(user: User) -> dict:
    d = dict((user.flags or {}).get("td_daily") or {})
    today = clock.local_date(clock.now())
    if d.get("date") != today:
        d = {"date": today, "n": 0}
    return d


def daily_left(user: User) -> int:
    return max(0, cfg()["rewards"]["daily_rewarded_plays"] - _daily(user)["n"])


def _use_daily(user: User) -> None:
    d = _daily(user)
    d["n"] += 1
    user.flags = {**(user.flags or {}), "td_daily": d}


async def saved_loadout(db: AsyncSession, user_id: int) -> list[str]:
    row = await db.get(TdLoadout, user_id)
    return list(row.slots or []) if row else []


def monster_kinds(level: dict) -> list[str]:
    seen: list[str] = []
    for wave in level["waves"]:
        for g in wave:
            if g["m"] not in seen:
                seen.append(g["m"])
    return seen


def monster_card(kind: str) -> dict:
    m = cfg()["monsters"][kind]
    return {"id": kind, "name_vi": m["name_vi"], "hp": m["hp"], "speed": m["speed"], "leak": m["leak"],
            "resist": m["resist"], "weakness_vi": m["weakness_vi"], "hidden": bool(m.get("hidden")),
            "boss": bool(m.get("boss"))}


def star_rewards(level_id: str, chapter: int, star: int) -> dict:
    r = cfg()["rewards"]
    out = {"spirit_stones": r["first_star_stones"][str(chapter)][star - 1]}
    extra = r["special"].get(level_id, {}).get(str(star))
    if extra:
        out.update(extra)
    return out


async def levels_view(db: AsyncSession, user: User) -> dict:
    ch = await _char(db, user)
    prog = await progress(db, user.id)
    c = cfg()
    out = []
    for lv in level_data()["levels"]:
        ok, why = unlocked(lv["id"], prog, ch.realm)
        pr = prog.get(lv["id"])
        out.append({"id": lv["id"], "chapter": lv["chapter"], "index": lv["index"], "name_vi": lv["name_vi"],
                    "waves": len(lv["waves"]), "unlocked": ok, "locked_vi": why,
                    "stars": pr.stars if pr else 0, "best_wave": pr.best_wave if pr else 0,
                    "monsters": [monster_card(k) for k in monster_kinds(lv)],
                    "first_rewards": [star_rewards(lv["id"], lv["chapter"], s) for s in (1, 2, 3)]})
    ok, why = unlocked(ENDLESS, prog, ch.realm)
    wk = week_key(clock.now())
    mine = prog.get(wk)
    entries = await plant_entries(db, user)
    run = await current_run(db, user.id)
    active = None
    if run is not None:
        active = {"run_id": run.id, "level_id": run.level_id, "name_vi": _level_of(run.level_id)["name_vi"],
                  "waves": sum(1 for e in run.events or [] if isinstance(e, dict) and e.get("k") == "wave")}
    return {"active_run": active, "chapters": [{k: v for k, v in x.items()} for x in c["chapters"]], "levels": out,
            "endless": {"unlocked": ok, "locked_vi": why, "week": wk, "best_wave": mine.best_wave if mine else 0},
            "loadout": [w for w in await saved_loadout(db, user.id) if w in entries],
            "loadout_max": c["loadout_max"], "plants": sorted(entries.values(), key=lambda e: (e["role"], e["word_id"])),
            "roles": roles_data()["roles"], "role_stats": c["roles"], "stars_need": c["stars"],
            "daily_left": daily_left(user), "daily_max": c["rewards"]["daily_rewarded_plays"]}


async def save_loadout(db: AsyncSession, user: User, slots: list) -> dict:
    entries = await plant_entries(db, user)
    clean = _check_loadout(slots, entries)
    row = await db.get(TdLoadout, user.id)
    if row is None:
        db.add(TdLoadout(user_id=user.id, slots=clean))
    else:
        row.slots = clean
    await db.flush()
    return {"loadout": clean}


def _check_loadout(slots, entries: dict[str, dict]) -> list[str]:
    if not isinstance(slots, list) or not all(isinstance(s, str) for s in slots):
        raise TdError(400, "bad_loadout", "Bộ cây không hợp lệ.")
    clean: list[str] = []
    for s in slots:
        if s not in clean:
            clean.append(s)
    if len(clean) > cfg()["loadout_max"]:
        raise TdError(400, "too_many", f"Chỉ mang được tối đa {cfg()['loadout_max']} loại cây.")
    for s in clean:
        if s not in entries:
            raise TdError(400, "not_learned", "Chỉ mang được cây của những chữ con đã học.")
    return clean


# ------------------------------------------------------------------ runs
_finishing: set[str] = set()     # runs whose log is being replayed right now


def _expired(row: TdRun) -> bool:
    return clock.now() - row.started_at > dt.timedelta(hours=cfg()["anti_cheat"]["run_hours"])


async def _drop(db: AsyncSession, row: TdRun) -> None:
    """Delete a run for good (committed now: the error that follows rolls back the rest)."""
    await db.delete(row)
    await db.commit()


async def current_run(db: AsyncSession, user_id: int) -> TdRun | None:
    row = (await db.execute(select(TdRun).where(TdRun.user_id == user_id)
                            .order_by(TdRun.started_at.desc()))).scalars().first()
    if row is not None and _expired(row):
        await db.delete(row)
        await db.flush()
        return None
    return row


async def _get_run(db: AsyncSession, user_id: int, run_id: str) -> TdRun:
    row = await db.get(TdRun, run_id) if isinstance(run_id, str) else None
    if row is None or row.user_id != user_id:
        raise TdError(404, "no_run", "Lượt thủ vườn này không còn nữa, vào ải lại nhé.")
    if _expired(row):
        await _drop(db, row)
        raise TdError(404, "no_run", "Lượt thủ vườn này đã quá lâu, vào ải lại nhé.")
    return row


def _seed(level_id: str, rng: random.Random) -> int:
    if level_id == ENDLESS:   # the same waves for everybody this week (a fair board)
        h = hashlib.sha256(week_key(clock.now()).encode()).digest()
        return int.from_bytes(h[:4], "big")
    return rng.randrange(1, 2 ** 31)


def _level_of(level_id: str) -> dict:
    return level_data()["endless"] if level_id == ENDLESS else levels()[level_id]


def run_view(row: TdRun) -> dict:
    """What the client needs to play (or continue) a run."""
    level = _level_of(row.level_id)
    kinds = cfg()["monsters"] if row.level_id == ENDLESS else monster_kinds(level)
    return {"run_id": row.id, "level_id": row.level_id, "params": row.params, "step_ms": td_sim.STEP_MS,
            "max_speed": cfg()["anti_cheat"]["max_speed"], "name_vi": level["name_vi"],
            "monsters": [monster_card(k) for k in kinds]}


async def start(db: AsyncSession, user: User, level_id: str, loadout: list | None,
                rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    ch = await _char(db, user)
    if level_id != ENDLESS and level_id not in levels():
        raise TdError(404, "no_level", "Không có ải này.")
    prog = await progress(db, user.id)
    ok, why = unlocked(level_id, prog, ch.realm)
    if not ok:
        raise TdError(400, "locked", why or "Ải này chưa mở.")
    entries = await plant_entries(db, user)
    slots = _check_loadout(loadout if loadout is not None else await saved_loadout(db, user.id), entries)
    if not any(entries[s]["role"] != "thanh_ngu" for s in slots):
        raise TdError(400, "empty_loadout", "Chọn ít nhất một cây trồng được để mang vào ải.")
    await save_loadout(db, user, slots)
    params = build_params(_level_of(level_id), sim_plants(entries, slots), _seed(level_id, rng),
                          endless=level_id == ENDLESS)
    from . import pets
    bonus = await pets.skill_value(db, user.id, "td_qi")   # Khỉ (stage 8): more Linh Khí to start with
    if bonus:
        params["qi"] = {**params["qi"], "start": params["qi"]["start"] + int(bonus)}
    await db.execute(delete(TdRun).where(TdRun.user_id == user.id))   # a new run replaces an unfinished one
    now = clock.now()
    row = TdRun(id=uuid.uuid4().hex, user_id=user.id, level_id=level_id, params=params, questions={}, events=[],
                started_at=now, updated_at=now)
    db.add(row)
    await db.flush()
    return run_view(row)


def _check_events(events, last_step: int) -> None:
    if not isinstance(events, list):
        raise TdError(400, "bad_log", "Nhật ký ải không hợp lệ.")
    for ev in events:
        s = ev.get("s") if isinstance(ev, dict) else None
        if not isinstance(s, int) or isinstance(s, bool) or s < last_step or not isinstance(ev.get("k"), str):
            raise TdError(400, "bad_log", "Nhật ký ải không hợp lệ.")
        last_step = s


async def save_events(db: AsyncSession, user: User, run_id: str, start_at: int, events: list) -> dict:
    """Spec 16 `/td/event`: the client saves its log as it plays (from index `start_at`). A part
    already saved may be sent again (it must be the same); nothing saved can be changed or
    removed, so closing the game never lets a player take a move back."""
    row = await _get_run(db, user.id, run_id)
    have = list(row.events or [])
    if not isinstance(start_at, int) or start_at < 0 or start_at > len(have):
        raise TdError(409, "log_gap", "Nhật ký ải bị hụt một đoạn.")
    overlap = have[start_at:start_at + len(events)]
    if events[:len(overlap)] != overlap:
        raise TdError(409, "log_conflict", "Nhật ký ải khác với đoạn đã lưu.")
    new = events[len(overlap):]
    _check_events(new, have[-1]["s"] if have else 0)
    if len(have) + len(new) > cfg()["anti_cheat"]["max_events"]:
        raise TdError(400, "too_many", "Nhật ký ải quá dài.")
    if new:
        row.events = have + new
        row.updated_at = clock.now()
    return {"saved": len(row.events)}


async def resume(db: AsyncSession, user: User) -> dict:
    """Continue the run left unfinished: its parameters, the saved log and the answers the log
    uses. A question asked after the last save was never applied; it is dropped."""
    row = await current_run(db, user.id)
    if row is None:
        raise TdError(404, "no_run", "Không có lượt thủ vườn nào đang dở.")
    used = {ev.get("q") for ev in row.events or [] if isinstance(ev, dict)}
    row.questions = {sid: q for sid, q in (row.questions or {}).items() if sid in used}
    return {**run_view(row), "events": row.events, "answers": _answers(row)}


async def ask(db: AsyncSession, user: User, run_id: str, kind: str, word_id: str | None,
              rng: random.Random | None = None) -> dict:
    """A question for the run: 'break' (Linh Khí Vấn Đạo between waves), 'tu_khi' (the Tụ Khí
    button during a wave) or 'upgrade' (always about the plant's own character, spec 9.1)."""
    rng = rng or random.Random()
    run = await _get_run(db, user.id, run_id)
    c = cfg()
    if len(run.questions or {}) >= c["anti_cheat"]["max_questions"]:
        raise TdError(400, "too_many", "Đã hỏi quá nhiều câu trong lượt này.")
    ch = await _char(db, user)
    tier = cultivation.tier_of(ch.realm)
    if kind == "upgrade":
        d = run.params["plants"].get(word_id or "")
        if d is None or d["role"] == "thanh_ngu":
            raise TdError(400, "no_plant", "Cây này không có trong bộ cây mang theo.")
        wid = word_id
    elif kind in ("break", "tu_khi"):
        try:
            wid = await selection.pick_word(db, user.id, tier, rng)
        except selection.NoWordAvailable:
            raise TdError(400, "nothing_learned", "Hãy học ít nhất một chữ trong vườn trước đã.")
    else:
        raise TdError(400, "bad_kind", "Loại câu hỏi không hợp lệ.")
    w = bank().get(wid)
    types = balance.quiz()["types"]
    allowed = [q for q in c["quiz_types"][kind] if types[q]["min_tier"] <= tier] or ["Q1", "Q2"]
    try:
        question = qb.generate_any(allowed, w, quiz.gen_context(rng, max_tier=max(tier, w.tier)))
    except qb.QuestionError:
        question = qb.generate_any(["Q1", "Q2"], w, quiz.gen_context(rng, max_tier=max(tier, w.tier)))
    out = await quiz.create_session(db, user, "td", question, ref=run.id)
    run.questions = {**(run.questions or {}), out["session_id"]: {"kind": kind, "word": wid, "ok": None}}
    return out


async def td_handler(db: AsyncSession, user: User, s: QuizSession, correct: bool, now: dt.datetime) -> dict:
    """Mastery as anywhere outside the garden (spec 8.3); the run remembers the result, which
    is what the replay uses (the client's word is never trusted)."""
    out = await quiz.practice_handler(db, user, s, correct, now)
    run = await db.get(TdRun, s.ref) if s.ref else None
    if run is not None and run.user_id == user.id and s.id in (run.questions or {}):
        q = {**run.questions[s.id], "ok": bool(correct)}
        run.questions = {**run.questions, s.id: q}
        c = cfg()["qi"]
        gain = {"break": c["break_qi"] if correct else 0,
                "tu_khi": c["tu_khi_qi"] if correct else -c["tu_khi_wrong_loss"],
                "upgrade": 0}[q["kind"]]
        out["td"] = {"kind": q["kind"], "ok": bool(correct), "qi": gain}
    return out


quiz.register_handler("td", td_handler)


async def cancel(db: AsyncSession, user: User) -> dict:
    res = await db.execute(delete(TdRun).where(TdRun.user_id == user.id))
    return {"cancelled": bool(res.rowcount)}


def _answers(run: TdRun) -> dict:
    """Results the replay may use. A question never answered counts as wrong."""
    return {sid: {"kind": q["kind"], "word": q["word"], "ok": bool(q["ok"])}
            for sid, q in (run.questions or {}).items()}


async def finish(db: AsyncSession, user: User, run_id: str, events: list, claim: dict) -> dict:
    run = await _get_run(db, user.id, run_id)
    if run.id in _finishing:
        raise TdError(409, "busy", "Đang kiểm tra lượt này.")
    c = cfg()["anti_cheat"]
    saved = list(run.events or [])
    if not isinstance(events, list) or events[:len(saved)] != saved:
        await _drop(db, run)
        raise TdError(400, "bad_log", "Nhật ký ải khác với đoạn đã lưu, máy chủ không chấp nhận.")
    _finishing.add(run.id)
    try:
        sim = await asyncio.to_thread(td_sim.replay, run.params, _answers(run), events, c["max_events"])
    except td_sim.LogError as e:
        await _drop(db, run)
        raise TdError(400, "bad_log", f"Nhật ký ải không hợp lệ ({e}), máy chủ không chấp nhận.")
    finally:
        _finishing.discard(run.id)
    questions, level_id, started = dict(run.questions or {}), run.level_id, run.started_at
    if set(questions) - sim.used_q:
        await _drop(db, run)
        raise TdError(400, "bad_log", "Nhật ký ải bỏ sót câu hỏi đã trả lời, máy chủ không chấp nhận.")
    got = sim.summary()
    if not isinstance(claim, dict) or any(claim.get(k) != got[k] for k in ("result", "core_hp", "wave", "steps")):
        await _drop(db, run)
        raise TdError(400, "log_mismatch", "Kết quả gửi lên không khớp khi máy chủ chơi lại nhật ký ải.")
    played = (clock.now() - started).total_seconds()
    needed = sim.step_n * td_sim.STEP_MS / 1000 / c["max_speed"]
    if played < needed * c["time_slack"] - c["time_grace_s"]:
        await _drop(db, run)
        raise TdError(400, "too_fast", "Ải kết thúc nhanh hơn thời gian thật, máy chủ không chấp nhận.")
    if got["result"] not in (td_sim.WON, td_sim.LOST):
        await _drop(db, run)
        raise TdError(400, "unfinished", "Ải chưa kết thúc.")
    await db.delete(run)
    await _record_monsters(db, user.id, sim)
    if level_id == ENDLESS:
        return {**got, **(await _endless_result(db, user, sim))}
    return {**got, **(await _level_result(db, user, level_id, sim))}


async def _record_monsters(db: AsyncSession, user_id: int, sim: td_sim.Sim) -> None:
    """Mặc Quái met in the garden go into the Yêu Quái Phổ (spec 9.3)."""
    now = clock.now()
    for kind in sim.met:
        eid = "td_" + kind
        e = await db.get(CodexEntry, (user_id, "monster", eid))
        if e is None:
            e = CodexEntry(user_id=user_id, codex="monster", entry_id=eid, discovered_at=now, progress={"kills": 0})
            db.add(e)
        e.progress = {**(e.progress or {}), "kills": int((e.progress or {}).get("kills", 0)) + sim.killed.get(kind, 0)}
    await db.flush()


def stars_for(core_hp: int) -> int:
    need = cfg()["stars"]
    return next((s for s in (3, 2, 1) if core_hp >= need[str(s)]), 0)


async def _grant(db: AsyncSession, user: User, reward: dict, ref: str) -> dict:
    got: dict = {}
    for cur in ("spirit_stones", "immortal_jade"):
        if reward.get(cur):
            await inventory.change_currency(db, user.id, cur, reward[cur], "td_reward", ref)
            got[cur] = got.get(cur, 0) + reward[cur]
    if reward.get("items"):
        got["items"] = await items.grant_items(db, user.id, [{"item": k, "qty": v} for k, v in reward["items"].items()],
                                               "td_reward", ref)
    if reward.get("seed"):
        learned = (await db.execute(select(Collection.word_id).where(
            Collection.user_id == user.id, Collection.introduced.is_(True)))).scalars().all()
        pool = [w for w in learned if w in bank().words and bank().get(w).gacha]
        if pool:
            wid = random.choice(sorted(pool))
            db.add(Seed(user_id=user.id, word_id=wid, duplicate=True, source="td", obtained_at=clock.now()))
            got["seed"] = {"word_id": wid, "hanzi": bank().get(wid).hanzi}
    return got


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if k in ("spirit_stones", "immortal_jade"):
            out[k] = out.get(k, 0) + v
        elif k == "items":
            out["items"] = out.get("items", []) + v
        else:
            out[k] = v
    return out


async def _level_result(db: AsyncSession, user: User, level_id: str, sim: td_sim.Sim) -> dict:
    lv = levels()[level_id]
    row = await db.get(TdProgress, (user.id, level_id))
    if row is None:
        row = TdProgress(user_id=user.id, level_id=level_id, stars=0, best_wave=0)
        db.add(row)
    prev = row.stars
    won = sim.phase == td_sim.WON
    stars = stars_for(sim.hp) if won else 0
    row.best_wave = max(row.best_wave, sim.wave if won else sim.wave - 1)
    rewards: dict = {}
    new_stars = []
    if stars > prev:
        for s in range(prev + 1, stars + 1):
            rewards = _merge(rewards, await _grant(db, user, star_rewards(level_id, lv["chapter"], s), level_id))
            new_stars.append(s)
        row.stars = stars
        if row.cleared_at is None:
            row.cleared_at = clock.now()
    elif won and daily_left(user) > 0:
        _use_daily(user)
        stones = cfg()["rewards"]["replay_stones"][str(lv["chapter"])]
        rewards = await _grant(db, user, {"spirit_stones": stones}, level_id)
        rewards["replay"] = True
    if won:
        from . import quests
        await quests.on_event(db, user.id, "td_win", "*")
    await db.flush()
    ids = [x["id"] for x in level_data()["levels"]]
    nxt = ids[ids.index(level_id) + 1] if won and ids.index(level_id) + 1 < len(ids) else None
    return {"stars": stars, "prev_stars": prev, "new_stars": new_stars, "rewards": rewards,
            "daily_left": daily_left(user), "next_level": nxt}


async def _endless_result(db: AsyncSession, user: User, sim: td_sim.Sim) -> dict:
    cleared = sim.summary()["waves_cleared"]
    wk = week_key(clock.now())
    row = await db.get(TdProgress, (user.id, wk))
    if row is None:
        row = TdProgress(user_id=user.id, level_id=wk, stars=0, best_wave=0)
        db.add(row)
    record = cleared > row.best_wave
    if record:
        row.best_wave = cleared
        row.cleared_at = clock.now()
    rewards: dict = {}
    r = cfg()["rewards"]
    stones = min(r["endless_stones_max"], cleared * r["endless_stones_per_wave"])
    if stones and daily_left(user) > 0:
        _use_daily(user)
        rewards = await _grant(db, user, {"spirit_stones": stones}, wk)
    await db.flush()
    return {"waves_cleared": cleared, "record": record, "rewards": rewards, "daily_left": daily_left(user),
            "board": await board(db, user)}


async def board(db: AsyncSession, user: User | None = None) -> dict:
    """Spec 9.1: the Vô Tận Trận ranks the most waves held this week."""
    wk = week_key(clock.now())
    rows = (await db.execute(
        select(TdProgress.user_id, TdProgress.best_wave, Character.display_name)
        .join(Character, Character.user_id == TdProgress.user_id)
        .where(TdProgress.level_id == wk, TdProgress.best_wave > 0)
        .order_by(TdProgress.best_wave.desc(), TdProgress.cleared_at)
        .limit(cfg()["endless"]["board_top"]))).all()
    return {"week": wk, "top": [{"rank": i + 1, "name": name, "waves": best, "me": user is not None and uid == user.id}
                                for i, (uid, best, name) in enumerate(rows)]}
