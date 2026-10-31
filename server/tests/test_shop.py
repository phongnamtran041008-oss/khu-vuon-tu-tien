"""Stage 8: the Sạp Tạp Hóa (spec 12.4), presents between friends and the daily tasks (spec 7.4)."""
import pytest
from sqlalchemy import select

from app import balance
from app.models import EquipmentInstance, Quest, Seed, User
from app.systems import quests, shop
from tests.econ_helpers import give, player, qty, set_stones, stones
from tests.helpers import answer_key, correct_answer

C = balance.load("shop")


@pytest.fixture
def at_shop(monkeypatch):
    monkeypatch.setattr(shop, "at_shop", lambda uid: True)


async def test_buying_needs_ba_chu_sap(client):
    h, uid = await player(client, "khach_xa", stones=500)
    r = await client.post("/shop/buy", json={"item_id": "truc_diep_thao", "qty": 1}, headers=h)
    assert r.json()["error"]["code"] == "too_far"
    view = (await client.get("/shop", headers=h)).json()
    assert not view["at_shop"] and any(s["item_id"] == "truc_diep_thao" for s in view["stock"])


async def test_buy_with_a_daily_limit(client, at_shop):
    h, uid = await player(client, "khach_sap", stones=5000)
    line = next(s for s in C["stock"] if s["item"] == "hoi_huyet_dan")
    r = await client.post("/shop/buy", json={"item_id": "hoi_huyet_dan", "qty": 3}, headers=h)
    assert r.status_code == 200 and r.json()["price"] == 3 * line["price"]
    assert await qty(uid, "hoi_huyet_dan") == 3 and await stones(uid) == 5000 - 3 * line["price"]
    r = await client.post("/shop/buy", json={"item_id": "hoi_huyet_dan", "qty": line["daily"]}, headers=h)
    assert r.json()["error"]["code"] == "sold_out"
    left = next(s for s in (await client.get("/shop", headers=h)).json()["stock"] if s["item_id"] == "hoi_huyet_dan")
    assert left["left"] == line["daily"] - 3
    r = await client.post("/shop/buy", json={"item_id": "linh_qua", "qty": 1}, headers=h)
    assert r.json()["error"]["code"] == "not_sold"
    await set_stones(uid, 1)
    r = await client.post("/shop/buy", json={"item_id": "hoi_huyet_dan", "qty": 1}, headers=h)
    assert r.json()["error"]["code"] == "insufficient_funds" and await qty(uid, "hoi_huyet_dan") == 3


async def test_the_next_day_the_stock_is_back(client, at_shop, frozen):
    h, uid = await player(client, "khach_hom_sau", stones=5000)
    line = next(s for s in C["stock"] if s["item"] == "truc_diep_thao")
    assert (await client.post("/shop/buy", json={"item_id": "truc_diep_thao", "qty": line["daily"]},
                              headers=h)).status_code == 200
    r = await client.post("/shop/buy", json={"item_id": "truc_diep_thao", "qty": 1}, headers=h)
    assert r.json()["error"]["code"] == "sold_out"
    frozen.advance(days=1)
    assert (await client.post("/shop/buy", json={"item_id": "truc_diep_thao", "qty": 1}, headers=h)).status_code == 200


async def test_common_seeds_count_toward_the_daily_new_seeds(client, at_shop, db):
    h, uid = await player(client, "khach_hat", stones=5000)
    r = await client.post("/shop/buy", json={"item_id": "hat_giong_thuong", "qty": 2}, headers=h)
    assert r.status_code == 200, r.text
    assert all(s["rarity"] == "common" for s in r.json()["seeds"])
    seeds = (await db.execute(select(Seed).where(Seed.user_id == uid, Seed.source == "shop"))).scalars().all()
    assert len(seeds) == 2
    user = await db.get(User, uid)
    assert user.daily_new_seeds_count == 2
    user.daily_new_seeds_count = balance.gacha()["daily_roll_limit"]
    await db.commit()
    r = await client.post("/shop/buy", json={"item_id": "hat_giong_thuong", "qty": 1}, headers=h)
    assert r.json()["error"]["code"] == "daily_limit"
    assert len((await db.execute(select(Seed).where(Seed.user_id == uid, Seed.source == "shop"))).scalars().all()) == 2


async def test_equipment_is_sold_pham_and_linh_only_and_bought_back_cheaper(client, at_shop, db):
    h, uid = await player(client, "khach_do", stones=5000)
    r = await client.post("/shop/buy", json={"item_id": "kiem_go_dao", "rarity": "linh"}, headers=h)
    assert r.status_code == 200 and r.json()["equipment"]["rarity"] == "linh"
    r = await client.post("/shop/buy", json={"item_id": "kiem_go_dao", "rarity": "thien"}, headers=h)
    assert r.json()["error"]["code"] == "not_sold"
    e = (await db.execute(select(EquipmentInstance).where(EquipmentInstance.user_id == uid))).scalar_one()
    paid = C["equipment"]["price"]["linh"]
    before = await stones(uid)
    r = await client.post("/shop/sell_equipment", json={"instance_id": e.id}, headers=h)
    assert r.status_code == 200 and 0 < r.json()["earned"] < paid
    assert await stones(uid) == before + r.json()["earned"]
    # worn gear cannot be sold
    r = await client.post("/shop/buy", json={"item_id": "non_la", "rarity": "pham"}, headers=h)
    pid = r.json()["equipment"]["id"]
    await client.post("/equipment/equip", json={"instance_id": pid}, headers=h)
    r = await client.post("/shop/sell_equipment", json={"instance_id": pid}, headers=h)
    assert r.json()["error"]["code"] == "equipped"


# ------------------------------------------------------------------ presents
async def friends(client, db):
    ha, a = await player(client, "ban_a")
    hb, b = await player(client, "ban_b")
    await client.post("/friends/request", json={"display_name": "Ban B"}, headers=ha)
    r = await client.post("/friends/accept", json={"user_id": a}, headers=hb)
    assert r.status_code == 200, r.text
    return ha, a, hb, b


async def test_presents_between_friends(client, db):
    ha, a, hb, b = await friends(client, db)
    await give(a, "linh_mat", 20)
    await give(a, "linh_qua", 2, bound=True)
    r = await client.post("/friends/gift", json={"friend_id": b, "item_id": "linh_mat", "qty": 3}, headers=ha)
    assert r.status_code == 200, r.text
    assert await qty(a, "linh_mat") == 17 and await qty(b, "linh_mat") == 3
    r = await client.post("/friends/gift", json={"friend_id": b, "item_id": "linh_qua", "qty": 1}, headers=ha)
    assert r.json()["error"]["code"] == "not_enough"          # bound things stay
    r = await client.post("/friends/gift", json={"friend_id": b, "item_id": "linh_mat", "qty": 6}, headers=ha)
    assert r.json()["error"]["code"] == "bad_count"
    r = await client.post("/friends/gift", json={"friend_id": b, "item_id": "dp_hoi_huyet", "qty": 1}, headers=ha)
    assert r.json()["error"]["code"] == "not_giftable"
    for _ in range(C["gift"]["per_day"] - 1):
        assert (await client.post("/friends/gift", json={"friend_id": b, "item_id": "linh_mat", "qty": 1},
                                  headers=ha)).status_code == 200
    r = await client.post("/friends/gift", json={"friend_id": b, "item_id": "linh_mat", "qty": 1}, headers=ha)
    assert r.json()["error"]["code"] == "gift_limit"
    hc, c = await player(client, "nguoi_la")
    await give(c, "linh_mat", 2)
    r = await client.post("/friends/gift", json={"friend_id": a, "item_id": "linh_mat", "qty": 1}, headers=hc)
    assert r.json()["error"]["code"] == "not_friend"


# ------------------------------------------------------------------ daily tasks
async def test_daily_tasks_progress_claim_bonus_and_rotate(client, db, frozen):
    h, uid = await player(client, "hang_ngay", learn=["水", "火"], stones=0)
    qs = (await client.get("/quests", headers=h)).json()
    daily = qs["daily"]
    from app.systems import catalog
    cfg = catalog.quests()["daily"]
    assert len(daily) == len(cfg["always"]) + cfg["count"]
    assert daily[0]["id"].endswith(":d_answer") and all(q["chain"] == "daily" for q in daily)
    assert not any(q["id"].startswith("d2") for q in qs["quests"])        # the chains list stays as it was
    need = daily[0]["objective"]["count"]
    for _ in range(need):
        q = (await client.post("/quiz/practice", json={}, headers=h)).json()
        await client.post("/quiz/answer", json={"session_id": q["session_id"],
                                                "answer": correct_answer(q["qtype"], await answer_key(q["session_id"]))},
                          headers=h)
    daily = (await client.get("/quests", headers=h)).json()["daily"]
    assert daily[0]["state"] == "done"
    r = await client.post("/quests/claim", json={"quest_id": daily[0]["id"]}, headers=h)
    assert r.status_code == 200 and r.json()["rewards"]["bonus"] is None      # not all done yet
    # finish the others by hand, the last claim gives the bonus once
    for q in daily[1:]:
        row = await db.get(Quest, (uid, q["id"]))
        row.state = "done"
    await db.commit()
    before = await stones(uid)
    res = None
    for q in daily[1:]:
        res = (await client.post("/quests/claim", json={"quest_id": q["id"]}, headers=h)).json()
    assert res["rewards"]["bonus"] and res["rewards"]["bonus"]["immortal_jade"] >= 1
    assert (await client.get("/quests", headers=h)).json()["daily_bonus"]["claimed"]
    assert await stones(uid) > before
    # tomorrow: new tasks, yesterday's are gone
    frozen.advance(days=1)
    nxt = (await client.get("/quests", headers=h)).json()
    assert all(q["state"] == "active" for q in nxt["daily"]) and nxt["daily"][0]["id"] != daily[0]["id"]
    rows = (await db.execute(select(Quest.quest_id).where(Quest.user_id == uid))).scalars().all()
    assert not any(qid in rows for qid in (q["id"] for q in daily))
    assert not nxt["daily_bonus"]["claimed"]


def test_daily_pick_is_stable_for_the_day_and_differs_between_players():
    a = quests.daily_ids(1, "2026-10-30")
    assert a == quests.daily_ids(1, "2026-10-30")
    picks = {tuple(quests.daily_ids(u, "2026-10-30")) for u in range(1, 30)}
    assert len(picks) > 3
