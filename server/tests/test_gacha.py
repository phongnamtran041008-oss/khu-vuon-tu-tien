import random
from collections import Counter

from sqlalchemy import select

from app.models import AuditLog, Collection, Seed, User
from app.systems.gacha import Banner, expected_rate_with_pity
from tests.helpers import register

N = 100_000


def test_base_rates_100k():
    b = Banner.load("seeds")
    rarities, _ = b.roll(N, {}, random.Random(42), use_pity=False)
    c = Counter(rarities)
    for r, p in b.rates.items():
        assert abs(c[r] / N - p) < 0.01, (r, c[r] / N, p)


def test_rates_with_pity_match_expected():
    b = Banner.load("seeds")
    state, got = {}, Counter()
    rng = random.Random(7)
    for _ in range(N):
        (r,), state = b.roll(1, state, rng)
        got[r] += 1
    legendary = got["legendary"] / N
    epic_plus = (got["epic"] + got["legendary"]) / N
    assert abs(legendary - expected_rate_with_pity(b, "legendary", 90)) < 0.004
    assert abs(epic_plus - expected_rate_with_pity(b, "epic", 40)) < 0.01
    assert abs(legendary - 0.01) < 0.01  # spec: within 1% of the advertised rate


def test_epic_pity_on_40th():
    b = Banner.load("seeds")
    b.rates = {"common": 1.0, "rare": 0.0, "epic": 0.0, "legendary": 0.0}  # worst luck
    out, state = b.roll(40, {}, random.Random(1))
    assert all(r == "common" for r in out[:39])
    assert out[39] in ("epic", "legendary")
    assert state["epic"] == 0


def test_legendary_pity_on_90th_and_counter_resets():
    b = Banner.load("seeds")
    b.rates = {"common": 1.0, "rare": 0.0, "epic": 0.0, "legendary": 0.0}
    out, state = b.roll(90, {}, random.Random(1))
    assert out[89] == "legendary"
    assert state["legendary"] == 0 and state["epic"] == 0
    # epic pity kept firing every 40 along the way
    assert out[39] in ("epic", "legendary") and out[79] in ("epic", "legendary")


def test_pity_counter_carries_over_between_rolls():
    b = Banner.load("seeds")
    b.rates = {"common": 1.0, "rare": 0.0, "epic": 0.0, "legendary": 0.0}
    _, state = b.roll(30, {}, random.Random(1))
    out, _ = b.roll(10, state, random.Random(1))
    assert out[9] in ("epic", "legendary")


def test_ten_pull_guarantees_rare():
    b = Banner.load("seeds")
    b.rates = {"common": 1.0, "rare": 0.0, "epic": 0.0, "legendary": 0.0}
    out, _ = b.roll(10, {}, random.Random(3))
    assert out[9] != "common"
    b.rates = {"common": 0.70, "rare": 0.22, "epic": 0.07, "legendary": 0.01}
    rng = random.Random(5)
    for _ in range(2000):
        out, _ = b.roll(10, {}, rng)
        assert any(r != "common" for r in out)


# ------------------------------------------------------------------ API
async def test_roll_charges_and_gives_seeds(client, db):
    h, _ = await register(client)
    r = await client.post("/gacha/roll", json={"banner": "seeds", "count": 1}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["spirit_stones"] == 200
    seeds = (await db.execute(select(Seed))).scalars().all()
    assert len(seeds) == 2  # tutorial seed + rolled seed
    logs = (await db.execute(select(AuditLog))).scalars().all()
    assert any(l.delta == -100 and l.reason == "gacha_seeds" for l in logs)


async def test_cannot_go_negative(client, db):
    h, _ = await register(client)
    for _ in range(3):
        assert (await client.post("/gacha/roll", json={"count": 1}, headers=h)).status_code == 200
    r = await client.post("/gacha/roll", json={"count": 1}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "insufficient_funds"
    user = (await db.execute(select(User))).scalar_one()
    assert user.spirit_stones == 0
    r = await client.post("/gacha/roll", json={"count": 10}, headers=h)
    assert r.status_code == 400
    await db.refresh(user)
    assert user.spirit_stones == 0


async def test_daily_limit_and_free_roll(client, db):
    h, _ = await register(client)
    user = (await db.execute(select(User))).scalar_one()
    user.spirit_stones = 10_000
    await db.commit()
    assert (await client.post("/gacha/roll", json={"count": 1, "free": True}, headers=h)).status_code == 200
    r = await client.post("/gacha/roll", json={"count": 1, "free": True}, headers=h)
    assert r.json()["error"]["code"] == "no_free_roll"
    assert (await client.post("/gacha/roll", json={"count": 10}, headers=h)).status_code == 200
    r = await client.post("/gacha/roll", json={"count": 10}, headers=h)
    assert r.json()["error"]["code"] == "daily_limit"  # only 4 left
    for _ in range(4):
        assert (await client.post("/gacha/roll", json={"count": 1}, headers=h)).status_code == 200
    r = await client.post("/gacha/roll", json={"count": 1}, headers=h)
    assert r.json()["error"]["message_vi"] == "Hạt giống cần nghỉ ngơi, mai quay lại nhé."
    await db.refresh(user)
    assert user.spirit_stones == 10_000 - 900 - 400  # failed rolls were not charged


async def test_daily_limit_resets_at_midnight_utc7(client, db, frozen):
    h, _ = await register(client)
    user = (await db.execute(select(User))).scalar_one()
    user.spirit_stones = 10_000
    await db.commit()
    for _ in range(15):
        await client.post("/gacha/roll", json={"count": 1}, headers=h)
    assert (await client.post("/gacha/roll", json={"count": 1}, headers=h)).status_code == 400
    frozen.advance(hours=17)  # 15:00 UTC+7 -> 08:00 UTC+7 the next day
    assert (await client.post("/gacha/roll", json={"count": 1}, headers=h)).status_code == 200


async def test_prefers_new_words_then_duplicates(client, db, frozen):
    h, _ = await register(client)
    user = (await db.execute(select(User))).scalar_one()
    user.spirit_stones = 100_000
    await db.commit()
    seen = []
    for day in range(8):
        for _ in range(15):
            r = await client.post("/gacha/roll", json={"count": 1}, headers=h)
            if r.status_code != 200:
                break
            seen += r.json()["results"]
        frozen.advance(days=1)
    from app.learning.wordbank import bank
    owned = {bank().by_hanzi["水"].id}  # tutorial seed
    n_dups = 0
    for item in seen:
        wid, r = item["word"]["id"], item["rarity"]
        if item["duplicate"]:
            n_dups += 1
            assert {w.id for w in bank().gacha_pool(1, r)} <= owned, "duplicate before pool exhausted"
        else:
            assert wid not in owned, "new seed repeated an owned word"
            owned.add(wid)
    assert n_dups > 0  # 120 rolls > 80 common+rare words, so duplicates must have appeared
    cols = (await db.execute(select(Collection))).scalars().all()
    assert len(cols) == len({c.word_id for c in cols})


async def test_sell_duplicate_seed(client, db):
    h, _ = await register(client)
    seed = (await db.execute(select(Seed))).scalar_one()
    r = await client.post("/seeds/sell", json={"seed_id": seed.id}, headers=h)
    assert r.json()["error"]["code"] == "not_duplicate"
    seed.duplicate = True
    await db.commit()
    r = await client.post("/seeds/sell", json={"seed_id": seed.id}, headers=h)
    assert r.status_code == 200 and r.json()["spirit_stones"] == 320


async def test_closed_banner(client, monkeypatch):
    h, _ = await register(client)
    from app import balance
    cfg = balance.gacha()
    monkeypatch.setitem(cfg["banners"], "pets", {**cfg["banners"]["pets"], "enabled": False})
    r = await client.post("/gacha/roll", json={"banner": "pets", "count": 1}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "banner_closed"
    monkeypatch.undo()
    # stage 8: the Linh Thú banner is open (300 Linh Thạch is not enough for 500)
    r = await client.post("/gacha/roll", json={"banner": "pets", "count": 1}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "insufficient_funds"
    info = (await client.get("/gacha/banners", headers=h)).json()["banners"]
    seeds = next(b for b in info if b["id"] == "seeds")
    assert seeds["rates"]["legendary"] == 0.01 and seeds["effective_rates_with_pity"]["legendary"] > 0.01


async def test_concurrent_spending_never_negative(client, db):
    import asyncio
    h, _ = await register(client, "racer")
    rs = await asyncio.gather(*[client.post("/gacha/roll", json={"count": 1}, headers=h) for _ in range(6)])
    ok = [r for r in rs if r.status_code == 200]
    assert len(ok) == 3
    user = (await db.execute(select(User))).scalar_one()
    await db.refresh(user)
    assert user.spirit_stones == 0
    spent = (await db.execute(select(AuditLog).where(AuditLog.reason == "gacha_seeds"))).scalars().all()
    assert sum(l.delta for l in spent) == -300
