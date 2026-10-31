"""Stage 7: Ải Thủ Vườn (spec 9). The checks asked for by the stage plan:
  * replaying a valid log gives the same result (pure simulation and through the API);
  * a fake log is refused (claims that do not match, events the rules forbid, questions that
    were never answered right, a run faster than real time);
  * chapter 1 can be played through (a simple beginner strategy wins all 10 levels).
Plus plant roles, the power from mastery and wither, loadout, unlocking, rewards, the daily
cap, the Vô Tận Trận board and the Yêu Quái Phổ entries."""
import asyncio
import json
import random
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from app import clock
from app.learning.wordbank import bank
from app.models import Character, CodexEntry, Collection, Plot, Seed, TdProgress, User
from app.systems import td, td_sim
from tests.helpers import answer_key, correct_answer, register, wrong_answer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import td_bot  # noqa: E402

LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}
BEGINNER = {"火": 50, "水": 50, "木": 50, "山": 40, "一": 40, "茶": 40, "妈妈": 40, "月": 40}


# ------------------------------------------------------------------ helpers
async def player(client, name="thu_vuon", learn: dict[str, int] | None = None, realm: str | None = None):
    h, data = await register(client, name)
    r = await client.post("/character/create", json={"display_name": name.replace("_", " ").title(), "appearance": LOOK},
                          headers=h)
    assert r.status_code == 200, r.text
    uid = data["user_id"]
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        for col in (await db.execute(select(Collection).where(Collection.user_id == uid))).scalars():
            await db.delete(col)      # only the words this test asks for
        await db.flush()
        for hz, m in (learn if learn is not None else BEGINNER).items():
            db.add(Collection(user_id=uid, word_id=bank().by_hanzi[hz].id, introduced=True, mastery=m,
                              first_seen_at=clock.now()))
        if realm:
            (await db.get(Character, uid)).realm = realm
        await db.commit()
    return h, uid


def wid(hz: str) -> str:
    return bank().by_hanzi[hz].id


async def set_stars(uid: int, level_ids: list[str], stars: int = 3) -> None:
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        for lid in level_ids:
            db.add(TdProgress(user_id=uid, level_id=lid, stars=stars, best_wave=5, cleared_at=clock.now()))
        await db.commit()


async def answer(client, h, q: dict, right: bool = True) -> dict:
    key = await answer_key(q["session_id"])
    ans = correct_answer(q["qtype"], key) if right else wrong_answer(q["qtype"], key)
    r = await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": ans}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def play_via_api(client, h, frozen, level_id: str, loadout: list[str] | None = None, wrong_every: int = 0):
    """Start a run, let the bot play it (every question asked and answered for real through
    the API), and return (start response, sim, events, claim)."""
    st = (await client.post("/td/start", json={"level_id": level_id, "loadout": loadout}, headers=h))
    assert st.status_code == 200, st.text
    st = st.json()
    loop = asyncio.get_running_loop()
    count = [0]

    async def ask_async(kind, word):
        body = {"run_id": st["run_id"], "kind": kind}
        if kind == "upgrade":
            body["word_id"] = word
        r = await client.post("/td/question", json=body, headers=h)
        assert r.status_code == 200, r.text
        q = r.json()
        count[0] += 1
        right = not (wrong_every and count[0] % wrong_every == 0)
        res = await answer(client, h, q, right)
        assert res["td"]["ok"] == right
        return q["session_id"], right

    def ask(kind, word):
        return asyncio.run_coroutine_threadsafe(ask_async(kind, word), loop).result()

    sim, _, events = await asyncio.to_thread(td_bot.play, td_sim, st["params"], 1.0, 1, ask)
    claim = {k: sim.summary()[k] for k in ("result", "core_hp", "wave", "steps")}
    frozen.advance(seconds=sim.step_n * td_sim.STEP_MS / 1000 + 1)
    return st, sim, events, claim


async def finish(client, h, run_id, events, claim):
    return await client.post("/td/finish", json={"run_id": run_id, "events": events, "claim": claim}, headers=h)


def beginner_plants() -> dict:
    return td_bot.typical_plants(BEGINNER)


# ------------------------------------------------------------------ data
def test_every_word_has_a_plant_role():
    roles = td.roles_data()["roles"]
    stats = td.cfg()["roles"]
    for w in bank().words.values():
        r = td.role_of(w.id)
        assert r in roles and r in stats, (w.hanzi, r)
    # the spec's examples (9.2), where the character exists in our word list
    for hz, r in {"火": "hoa", "日": "hoa", "热": "hoa", "水": "thuy", "雨": "thuy", "河": "thuy", "木": "moc",
                  "林": "moc", "森": "moc", "山": "son", "大": "son", "明": "quang", "月": "quang", "茶": "sinh_khi",
                  "苹果": "sinh_khi", "妈妈": "ho_tro", "你": "ho_tro", "朋友": "ho_tro", "一石二鸟": "thanh_ngu"}.items():
        assert td.role_of(wid(hz)) == r, hz
    for idiom in ("一石二鸟", "画蛇添足", "对牛弹琴"):
        assert idiom in td.cfg()["idiom_skills"]


def test_power_follows_mastery_and_wither():
    assert td.power(0, 0) == 0.6
    assert td.power(100, 0) == 1.3
    assert td.power(50, 0) == pytest.approx(0.95)
    assert td.power(100, 100) == pytest.approx(1.3 * 0.7)   # wither costs at most 30%
    assert td.power(0, 100) == pytest.approx(0.42)


def test_levels_file_matches_the_generator():
    """levels.json is generated (tools/gen_td_levels.py); 30 levels in 3 chapters, valid paths."""
    sys.path.insert(0, str(ROOT / "tools"))
    import gen_td_levels
    assert gen_td_levels.build() == td.level_data()
    lv = td.level_data()["levels"]
    assert len(lv) == 30 and [x["chapter"] for x in lv].count(1) == 10
    for x in lv + [td.level_data()["endless"]]:
        path = [tuple(c) for c in x["path"]]
        assert path[0][0] == 0 and path[-1][0] == 11
        for a, b in zip(path, path[1:]):
            assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1
        assert not set(map(tuple, x["rocks"])) & set(path)


def test_client_simulation_is_the_same_file():
    server = (ROOT / "server" / "app" / "systems" / "td_sim.py").read_bytes()
    client = (ROOT / "client" / "engine" / "td_sim.py").read_bytes()
    assert server == client


# ------------------------------------------------------------------ the simulation
@pytest.mark.parametrize("level_id", ["c1_01", "c1_08", "c2_05", "c3_10"])
def test_replaying_a_valid_log_gives_the_same_result(level_id):
    params = td.build_params(td.levels()[level_id], beginner_plants(), seed=12345)
    sim, answers, events = td_bot.play(td_sim, params, accuracy=0.8, seed=3)
    assert sim.phase in (td_sim.WON, td_sim.LOST)
    again = td_sim.replay(json.loads(json.dumps(params)), json.loads(json.dumps(answers)),
                          json.loads(json.dumps(events)))
    assert again.summary() == sim.summary()
    assert (again.kills, again.leaked, again.qi) == (sim.kills, sim.leaked, sim.qi)


def test_replay_of_the_endless_trial_is_deterministic():
    params = td.build_params(td.level_data()["endless"], beginner_plants(), seed=99, endless=True)
    sim, answers, events = td_bot.play(td_sim, params, accuracy=0.9, seed=5)
    assert sim.phase == td_sim.LOST and sim.wave >= 5
    assert td_sim.replay(params, answers, events).summary() == sim.summary()
    # the same week's seed gives everybody the same waves
    a, b = td_sim.Sim(params), td_sim.Sim(params)
    assert [td_sim.endless_wave(i, params["endless"], a.rng) for i in range(12)] == \
           [td_sim.endless_wave(i, params["endless"], b.rng) for i in range(12)]


def test_fake_logs_are_refused_by_the_simulation():
    params = td.build_params(td.levels()["c1_01"], beginner_plants(), seed=1)
    fire, wood = wid("火"), wid("木")
    path = [tuple(c) for c in params["path"]]
    free = next((x, y) for y in range(7) for x in range(12)
                if (x, y) not in path and [x, y] not in params["rocks"])
    good = {"q1": {"kind": "break", "word": fire, "ok": True}, "q2": {"kind": "upgrade", "word": fire, "ok": True}}

    def refused(events, answers=None):
        with pytest.raises(td_sim.LogError):
            td_sim.replay(params, answers if answers is not None else good, events)

    refused([{"s": 0, "k": "place", "x": free[0], "y": free[1], "w": wid("你")}])        # not brought
    refused([{"s": 0, "k": "place", "x": path[3][0], "y": path[3][1], "w": fire}])      # fire on the path
    refused([{"s": 0, "k": "place", "x": free[0], "y": free[1], "w": wood}])            # wood off the path
    refused([{"s": 0, "k": "place", "x": free[0], "y": free[1], "w": fire}] * 2)        # same cell twice
    refused([{"s": 0, "k": "place", "x": x, "y": y, "w": fire}                          # more than the Linh Khí
             for y in range(7) for x in range(12) if (x, y) not in path][:6])
    refused([{"s": 0, "k": "qi", "q": "made_up"}])                                       # never asked
    refused([{"s": 0, "k": "sell", "x": [1], "y": 2}])                                   # wrong types
    refused([{"s": 0, "k": "skill", "w": ["x"]}])
    refused([{"s": 0, "k": "place", "x": 1, "y": 1, "w": {"a": 1}}])
    refused(["wave"])
    refused([{"s": 0, "k": "qi", "q": "q1"}, {"s": 0, "k": "qi", "q": "q1"}])            # used twice
    refused([{"s": 0, "k": "qi", "q": "q2"}])                                            # an upgrade question
    refused([{"s": 0, "k": "place", "x": free[0], "y": free[1], "w": fire},             # upgrade about another word
             {"s": 0, "k": "up", "x": free[0], "y": free[1], "q": "q3"}],
            {**good, "q3": {"kind": "upgrade", "word": wid("水"), "ok": True}})
    refused([{"s": 5, "k": "wave"}])                                                     # time passes only in waves
    refused([{"s": 0, "k": "wave"}, {"s": 40, "k": "qi", "q": "q1"}])                    # a break question mid-wave
    refused([{"s": 0, "k": "wave"}, {"s": 3, "k": "wave"}])
    refused([{"s": 0, "k": "wave"}, {"s": 9, "k": "place", "x": free[0], "y": free[1], "w": fire},
             {"s": 4, "k": "sell", "x": free[0], "y": free[1]}])                         # going back in time
    tk = {"t1": {"kind": "tu_khi", "word": fire, "ok": True}, "t2": {"kind": "tu_khi", "word": fire, "ok": True}}
    refused([{"s": 0, "k": "wave"}, {"s": 10, "k": "qi", "q": "t1"}, {"s": 50, "k": "qi", "q": "t2"}], tk)  # Tụ Khí cooldown
    # the honest version of the same actions is fine
    ok = td_sim.replay(params, tk, [{"s": 0, "k": "wave"}, {"s": 10, "k": "qi", "q": "t1"},
                                    {"s": 10 + 200, "k": "qi", "q": "t2"}])
    assert ok.phase in (td_sim.WON, td_sim.LOST, td_sim.BUILD)


def test_a_wrong_answer_is_a_wrong_answer_in_the_replay():
    """The replay uses the server's record of each answer, never the client's."""
    params = td.build_params(td.levels()["c1_01"], beginner_plants(), seed=1)
    path = [tuple(c) for c in params["path"]]
    free = next((x, y) for y in range(7) for x in range(12) if (x, y) not in path and [x, y] not in params["rocks"])
    fire = wid("火")
    evs = [{"s": 0, "k": "place", "x": free[0], "y": free[1], "w": fire},
           {"s": 0, "k": "up", "x": free[0], "y": free[1], "q": "u"}]
    right = td_sim.replay(params, {"u": {"kind": "upgrade", "word": fire, "ok": True}}, evs)
    wrong = td_sim.replay(params, {"u": {"kind": "upgrade", "word": fire, "ok": False}}, evs)
    assert right.plants[free].level == 2 and wrong.plants[free].level == 1
    assert right.qi == wrong.qi          # the Linh Khí is spent either way (spec 9.1)


def test_combos_work_in_the_garden_trial():
    plants = td_bot.typical_plants({"女": 50, "子": 50, "日": 50, "月": 50, "木": 50, "人": 50})
    lv = {"id": "t", "chapter": 1, "path": [[x, 3] for x in range(12)], "rocks": [], "waves": [[]]}
    sim = td_sim.Sim(td.build_params(lv, plants, 1))
    sim.qi = 10000
    for x, y, hz in ((1, 1, "女"), (2, 1, "子"), (5, 2, "日"), (6, 2, "月"), (3, 3, "木"), (4, 3, "木"), (5, 3, "木"),
                     (3, 4, "人")):
        sim.apply({"k": "place", "x": x, "y": y, "w": wid(hz)})
    assert set(sim.combos) == {"hao", "ming", "sen", "xiu"}
    assert sim.plants[(1, 1)].buff == 1.3 and sim.plants[(2, 1)].buff == 1.3
    assert sim.plants[(6, 2)].light == 2.0
    assert sim.plants[(4, 3)].hp_mult == 1.5 and sim.plants[(3, 3)].regen > 0
    lit_wide = len(sim.lit)
    sim.apply({"k": "sell", "x": 5, "y": 2})
    assert "ming" not in sim.combos and len(sim.lit) < lit_wide


def test_hidden_monsters_need_light():
    plants = td_bot.typical_plants({"火": 100, "月": 60})
    lv = {"id": "t", "chapter": 1, "path": [[x, 3] for x in range(12)], "rocks": [],
          "waves": [[{"m": "muc_an", "n": 1, "gap": 1000, "at": 0}]]}
    dark = td_sim.Sim(td.build_params(lv, plants, 1))
    dark.qi = 1000
    for x in (2, 5, 8):
        dark.apply({"k": "place", "x": x, "y": 2, "w": wid("火")})
    dark.apply({"k": "wave"})
    while dark.phase == td_sim.WAVE:
        dark.step()
    assert dark.leaked == 1 and dark.kills == 0
    lit = td_sim.Sim(td.build_params(lv, plants, 1))
    lit.qi = 1000
    for x in (2, 5, 8):
        lit.apply({"k": "place", "x": x, "y": 2, "w": wid("火")})
    lit.apply({"k": "place", "x": 5, "y": 4, "w": wid("月")})
    lit.apply({"k": "wave"})
    while lit.phase == td_sim.WAVE:
        lit.step()
    assert lit.kills == 1 and lit.leaked == 0


def test_chapter_one_can_be_played_through():
    """A careful beginner (8 starting plants, mastery 40-50, 85% right answers) wins all of
    chapter 1, and the first levels with 3 stars."""
    plants = beginner_plants()
    for lv in td.level_data()["levels"][:10]:
        sim, answers, events = td_bot.play(td_sim, td.build_params(lv, plants, 7), accuracy=0.85, seed=1)
        assert sim.phase == td_sim.WON, (lv["id"], sim.summary())
        if lv["index"] <= 5:
            assert td.stars_for(sim.hp) == 3, lv["id"]


# ------------------------------------------------------------------ the API
async def test_levels_view_and_loadout(client):
    h, uid = await player(client)
    v = (await client.get("/td/levels", headers=h)).json()
    assert len(v["levels"]) == 30 and v["loadout_max"] == 8
    assert v["levels"][0]["unlocked"] and not v["levels"][1]["unlocked"]
    assert not v["endless"]["unlocked"]
    assert {p["hanzi"] for p in v["plants"]} == set(BEGINNER)
    fire = next(p for p in v["plants"] if p["hanzi"] == "火")
    assert fire["role"] == "hoa" and fire["power"] == td.power(50, 0)
    nine = [wid(hz) for hz in BEGINNER] + [wid("火")]
    r = await client.post("/td/loadout", json={"slots": nine}, headers=h)
    assert r.status_code == 200 and len(r.json()["loadout"]) == 8   # duplicates dropped
    h2, _ = await player(client, "nguoi_moi", learn={"火": 10})
    r = await client.post("/td/loadout", json={"slots": [wid("火"), wid("水")]}, headers=h2)
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_learned"
    many = {hz: 20 for hz in ["火", "水", "木", "山", "一", "二", "三", "茶", "妈妈"]}
    h3, _ = await player(client, "nhieu_cay", learn=many)
    r = await client.post("/td/loadout", json={"slots": [wid(hz) for hz in many]}, headers=h3)
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_many"


async def test_wither_in_the_real_garden_weakens_the_plant(client, frozen):
    h, uid = await player(client)
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        db.add(Plot(user_id=uid, x=0, y=0, unlocked=True, word_id=wid("火"), stage=2, wither=80.0,
                    next_review_at=clock.now() + __import__("datetime").timedelta(days=1),
                    wither_checked_at=clock.now()))
        await db.commit()
    st = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": [wid("火"), wid("水")]},
                            headers=h)).json()
    assert st["params"]["plants"][wid("火")]["power"] == td.power(50, 80)
    assert st["params"]["plants"][wid("水")]["power"] == td.power(50, 0)


async def test_locked_levels_and_chapters(client, frozen):
    h, uid = await player(client)
    r = await client.post("/td/start", json={"level_id": "c1_02"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "locked"
    await set_stars(uid, [f"c1_{i:02d}" for i in range(1, 11)])
    r = await client.post("/td/start", json={"level_id": "c2_01", "loadout": [wid("火")]}, headers=h)
    assert r.status_code == 400 and "Luyện Khí" in r.json()["error"]["message_vi"]   # chapter 2 needs the realm
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        (await db.get(Character, uid)).realm = "luyen_khi"
        await db.commit()
    assert (await client.post("/td/start", json={"level_id": "c2_01", "loadout": [wid("火")]}, headers=h)).status_code == 200
    assert (await client.post("/td/start", json={"level_id": "endless", "loadout": [wid("火")]}, headers=h)).status_code == 200
    r = await client.post("/td/start", json={"level_id": "c1_01", "loadout": [wid("一石二鸟")]}, headers=h)
    assert r.status_code == 400


async def test_full_run_through_the_api_gives_stars_and_rewards(client, frozen):
    h, uid = await player(client)
    loadout = [wid(hz) for hz in BEGINNER]
    st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", loadout)
    assert claim["result"] == "won"
    stones0 = (await client.get("/me", headers=h)).json()["spirit_stones"]
    r = await finish(client, h, st["run_id"], events, claim)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["stars"] == 3 and out["new_stars"] == [1, 2, 3]
    assert out["rewards"]["spirit_stones"] == sum(td.cfg()["rewards"]["first_star_stones"]["1"])
    assert (await client.get("/me", headers=h)).json()["spirit_stones"] == stones0 + out["rewards"]["spirit_stones"]
    assert out["next_level"] == "c1_02"
    v = (await client.get("/td/levels", headers=h)).json()
    assert v["levels"][0]["stars"] == 3 and v["levels"][1]["unlocked"]
    # the run is gone: it cannot be cashed in twice
    r = await finish(client, h, st["run_id"], events, claim)
    assert r.status_code == 404
    # questions in the run trained the words like any question outside the garden
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        cols = (await db.execute(select(Collection).where(Collection.user_id == uid))).scalars().all()
        assert sum(c.times_correct for c in cols) >= 3
        # Mặc Quái met went into the Yêu Quái Phổ
        e = await db.get(CodexEntry, (uid, "monster", "td_muc_con"))
        assert e is not None and e.progress["kills"] > 0
    book = (await client.get("/codex/monster", headers=h)).json()
    assert any(x["id"] == "td_muc_con" and x["found"] for x in book["entries"])


async def test_replays_have_a_daily_cap(client, frozen):
    h, uid = await player(client)
    await set_stars(uid, ["c1_01"])
    gains = []
    for _ in range(td.cfg()["rewards"]["daily_rewarded_plays"] + 1):
        st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", [wid(hz) for hz in BEGINNER])
        out = (await finish(client, h, st["run_id"], events, claim)).json()
        gains.append(out["rewards"].get("spirit_stones", 0))
    rp = td.cfg()["rewards"]["replay_stones"]["1"]
    assert gains == [rp] * 5 + [0]


async def test_api_refuses_fake_logs(client, frozen):
    h, uid = await player(client)
    loadout = [wid(hz) for hz in BEGINNER]
    # 1) the claim does not match what the log really gives
    st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", loadout)
    r = await finish(client, h, st["run_id"], events, {**claim, "core_hp": claim["core_hp"] + 1 if claim["core_hp"] < 20 else 19})
    assert r.status_code == 400 and r.json()["error"]["code"] == "log_mismatch"
    # 2) a forged event (a plant that was not brought)
    st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", loadout)
    path = [tuple(c) for c in st["params"]["path"]]
    free = next((x, y) for y in range(7) for x in range(12) if (x, y) not in path and [x, y] not in st["params"]["rocks"])
    forged = [{"s": 0, "k": "place", "x": free[0], "y": free[1], "w": wid("你")}] + events
    r = await finish(client, h, st["run_id"], forged, claim)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_log"
    # 3) a question the server never asked
    st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", loadout)
    forged = [dict(e, q="khong-co-cau-nay") if e.get("k") == "qi" else e for e in events]
    r = await finish(client, h, st["run_id"], forged, claim)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_log"
    # 4) a log that leaves out an answered question (a wrong Tụ Khí answer it wanted to hide)
    st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", loadout, wrong_every=4)
    hidden = [e for e in events if e.get("k") != "qi" or e is not next(x for x in events if x.get("k") == "qi")]
    r = await finish(client, h, st["run_id"], hidden, claim)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_log"
    # 5) the whole level in no time at all
    st = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": loadout}, headers=h)).json()
    events = [{"s": 0, "k": "wave"}]      # no plants: the wave walks in, the run is lost
    local = td_sim.replay(st["params"], {}, events)
    claim = {k: local.summary()[k] for k in ("result", "core_hp", "wave", "steps")}
    r = await finish(client, h, st["run_id"], events, claim)
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_fast"
    # nothing was ever rewarded
    v = (await client.get("/td/levels", headers=h)).json()
    assert v["levels"][0]["stars"] == 0


async def test_an_unfinished_log_earns_nothing(client, frozen):
    h, uid = await player(client)
    st = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": [wid("火")]}, headers=h)).json()
    frozen.advance(seconds=10)
    r = await finish(client, h, st["run_id"], [], {"result": "build", "core_hp": 20, "wave": 0, "steps": 0})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unfinished"


async def test_upgrade_questions_are_about_the_plant(client, frozen):
    h, uid = await player(client)
    st = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": [wid("火"), wid("水")]},
                            headers=h)).json()
    for _ in range(3):
        q = (await client.post("/td/question", json={"run_id": st["run_id"], "kind": "upgrade", "word_id": wid("火")},
                               headers=h)).json()
        assert q["word_id"] == wid("火") if "word_id" in q else True
        from app import db as dbm
        from app.models import QuizSession
        async with dbm.SessionLocal() as db:
            s = await db.get(QuizSession, q["session_id"])
            assert s.word_id == wid("火") and s.context == "td"
        await answer(client, h, q)
    r = await client.post("/td/question", json={"run_id": st["run_id"], "kind": "upgrade", "word_id": wid("木")},
                          headers=h)
    assert r.status_code == 400   # not brought into this run
    r = await client.post("/td/question", json={"run_id": "x", "kind": "break"}, headers=h)
    assert r.status_code == 404


async def test_question_answers_give_and_take_linh_khi(client, frozen):
    h, uid = await player(client)
    st = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": [wid("火")]}, headers=h)).json()
    q = (await client.post("/td/question", json={"run_id": st["run_id"], "kind": "break"}, headers=h)).json()
    assert (await answer(client, h, q, True))["td"]["qi"] == td.cfg()["qi"]["break_qi"]
    q = (await client.post("/td/question", json={"run_id": st["run_id"], "kind": "tu_khi"}, headers=h)).json()
    assert (await answer(client, h, q, False))["td"]["qi"] == -td.cfg()["qi"]["tu_khi_wrong_loss"]


async def test_endless_board(client, frozen):
    h, uid = await player(client)
    await set_stars(uid, ["c1_10"])
    h2, uid2 = await player(client, "dao_huu_b")
    await set_stars(uid2, ["c1_10"])
    results = []
    for hh in (h, h2):
        st, sim, events, claim = await play_via_api(client, hh, frozen, "endless", [wid(x) for x in BEGINNER])
        assert claim["result"] == "lost"
        out = (await finish(client, hh, st["run_id"], events, claim)).json()
        assert out["record"] and out["waves_cleared"] == sim.summary()["waves_cleared"]
        assert out["rewards"]["spirit_stones"] == min(td.cfg()["rewards"]["endless_stones_max"],
                                                      out["waves_cleared"] * td.cfg()["rewards"]["endless_stones_per_wave"])
        results.append(out["waves_cleared"])
    board = (await client.get("/td/endless/board", headers=h)).json()
    assert [r["waves"] for r in board["top"]] == sorted(results, reverse=True)
    assert sum(r["me"] for r in board["top"]) == 1
    v = (await client.get("/td/levels", headers=h)).json()
    assert v["endless"]["unlocked"] and v["endless"]["best_wave"] == results[0]


async def test_special_first_rewards(client, frozen):
    h, uid = await player(client)
    await set_stars(uid, ["c1_01"])
    await set_stars(uid, ["c1_02"], 1)
    from app import db as dbm
    async with dbm.SessionLocal() as db:
        u = await db.get(User, uid)
        got = await td._grant(db, u, td.star_rewards("c1_03", 1, 2), "c1_03")
        await db.commit()
        assert got["spirit_stones"] == td.cfg()["rewards"]["first_star_stones"]["1"][1]
        seeds = (await db.execute(select(Seed).where(Seed.user_id == uid, Seed.source == "td"))).scalars().all()
        assert len(seeds) == 1 and seeds[0].word_id in {wid(hz) for hz in BEGINNER}


async def test_saved_log_lets_a_closed_game_continue(client, frozen):
    """/td/event saves the log as it grows; /td/resume gives it back after the game was closed,
    and the run finishes normally from there."""
    h, uid = await player(client)
    st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", [wid(hz) for hz in BEGINNER])
    half = len(events) // 2
    r = await client.post("/td/event", json={"run_id": st["run_id"], "start": 0, "events": events[:half]}, headers=h)
    assert r.status_code == 200 and r.json()["saved"] == half
    v = (await client.get("/td/levels", headers=h)).json()
    assert v["active_run"]["level_id"] == "c1_01" and v["active_run"]["run_id"] == st["run_id"]
    # the run is saved in the database (not in memory): nothing is lost when the server restarts
    from app import db as dbm
    from app.models import TdRun
    async with dbm.SessionLocal() as db:
        assert len((await db.get(TdRun, st["run_id"])).events) == half
    # saving the second half again from an earlier index is fine (the overlap is the same)
    r = await client.post("/td/event", json={"run_id": st["run_id"], "start": half - 2, "events": events[half - 2:]},
                          headers=h)
    assert r.status_code == 200 and r.json()["saved"] == len(events)
    res = (await client.post("/td/resume", headers=h)).json()          # the game was closed and opened again
    assert res["run_id"] == st["run_id"] and res["events"] == events
    used = {e["q"] for e in events if "q" in e}
    assert set(res["answers"]) == used and all(a["ok"] for a in res["answers"].values())
    # the client rebuilds the board from the saved log, stopping where the log stops
    mid = td_sim.replay(res["params"], res["answers"], res["events"][:half], finish=False)
    assert mid.step_n == events[half - 1]["s"] and len(mid.plants) > 0
    out = await finish(client, h, st["run_id"], events, claim)
    assert out.status_code == 200 and out.json()["stars"] >= 1
    assert (await client.get("/td/levels", headers=h)).json()["active_run"] is None


async def test_a_saved_move_cannot_be_taken_back(client, frozen):
    h, uid = await player(client)
    st, sim, events, claim = await play_via_api(client, h, frozen, "c1_01", [wid(hz) for hz in BEGINNER])
    n = len(events) // 2
    assert (await client.post("/td/event", json={"run_id": st["run_id"], "start": 0, "events": events[:n]},
                              headers=h)).status_code == 200
    changed = [dict(e, x=e.get("x", 0) + 1) if e.get("k") == "place" else e for e in events[:n]]
    r = await client.post("/td/event", json={"run_id": st["run_id"], "start": 0, "events": changed}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "log_conflict"
    r = await client.post("/td/event", json={"run_id": st["run_id"], "start": n + 5, "events": events[n:]}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "log_gap"
    # finishing with a different past than the one saved is refused (and the run is gone)
    r = await finish(client, h, st["run_id"], changed + events[n:], claim)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_log"
    assert (await finish(client, h, st["run_id"], events, claim)).status_code == 404


async def test_resume_drops_questions_asked_after_the_last_save(client, frozen):
    h, uid = await player(client)
    st = (await client.post("/td/start", json={"level_id": "c1_01", "loadout": [wid("火"), wid("木")]},
                            headers=h)).json()
    q = (await client.post("/td/question", json={"run_id": st["run_id"], "kind": "break"}, headers=h)).json()
    await answer(client, h, q)
    res = (await client.post("/td/resume", headers=h)).json()      # closed before the answer was logged
    assert res["events"] == [] and res["answers"] == {}
    local, events = td_sim.Sim(st["params"], {}), []                 # no plants at all: lost, but a valid log
    while local.phase not in (td_sim.WON, td_sim.LOST):
        events.append({"s": local.step_n, "k": "wave"})
        local.apply(events[-1])
        while local.phase == td_sim.WAVE:
            local.step()
    frozen.advance(seconds=local.step_n * td_sim.STEP_MS / 1000)
    claim = {k: local.summary()[k] for k in ("result", "core_hp", "wave", "steps")}
    r = await finish(client, h, st["run_id"], events, claim)
    assert r.status_code == 200 and r.json()["result"] == "lost", r.text
    assert (await client.post("/td/resume", headers=h)).status_code == 404
