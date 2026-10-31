"""Stage 8: Khắc Văn (spec 12.2). A learned word with mastery >= 70, three right answers in a row,
slots by rarity, the stat of the word on the piece, scraping it off."""
from app import balance
from app.learning.wordbank import bank
from app.models import EquipmentInstance
from app.systems import inscription
from tests.econ_helpers import give, learn_words, player, qty, set_stones, stones
from tests.helpers import answer_key, correct_answer, wrong_answer

C = balance.load("inscription")


async def piece(db, uid, item="but_long_go", rarity="pham", equipped=None) -> int:
    e = EquipmentInstance(user_id=uid, item_id=item, rarity=rarity, enhance_level=0, inscriptions=[],
                          equipped_slot=equipped)
    db.add(e)
    await db.commit()
    return e.id


async def carver(client, db, name="tho_khac", rarity="pham", equipped="weapon"):
    h, uid = await player(client, name, learn=["火", "山"], mastery=80, stones=1000)
    await learn_words(uid, ["水"], 50)                 # not yet 70
    await give(uid, "muc_tinh", 20)
    pid = await piece(db, uid, rarity=rarity, equipped=equipped)
    return h, uid, pid


async def answer(client, h, q, right=True):
    key = await answer_key(q["session_id"])
    a = correct_answer(q["qtype"], key) if right else wrong_answer(q["qtype"], key)
    return (await client.post("/quiz/answer", json={"session_id": q["session_id"], "answer": a}, headers=h)).json()


async def test_three_right_answers_carve_the_word_and_its_stat(client, db):
    h, uid, pid = await carver(client, db)
    opts = (await client.get(f"/forge/inscribe/{pid}", headers=h)).json()
    fire = next(w for w in opts["words"] if w["hanzi"] == "火")
    water = next(w for w in opts["words"] if w["hanzi"] == "水")
    assert fire["ok"] and fire["stat"] == "atk" and not water["ok"] and opts["slots"] == 1
    atk0 = (await client.get("/cultivation", headers=h)).json()["stats"]["atk"]
    r = await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": fire["word_id"]}, headers=h)
    assert r.status_code == 200, r.text
    assert await stones(uid) == 1000 - C["fee"]["spirit_stones"] and await qty(uid, "muc_tinh") == 20 - 2
    q = r.json()["question"]
    seen = []
    for n in range(1, 4):
        assert q["number"] == n and q["total"] == 3 and q["context"] == "forge"
        seen.append(q["qtype"])
        res = await answer(client, h, q)
        assert res["correct"]
        if n < 3:
            assert not res["inscribe"]["done"]
            q = res["next"]
    assert len(set(seen)) >= 2                       # not the same kind of question three times
    ins = res["inscribe"]
    assert ins["success"] and ins["carved"]["hanzi"] == "火" and ins["carved"]["value"] == C["by_hanzi"]["火"]["value"]
    e = await db.get(EquipmentInstance, pid)
    await db.refresh(e)
    assert e.inscriptions[0]["hanzi"] == "火"
    atk1 = (await client.get("/cultivation", headers=h)).json()["stats"]["atk"]
    assert atk1 == atk0 + C["by_hanzi"]["火"]["value"]
    inv = (await client.get("/inventory", headers=h)).json()
    assert inv["equipment"][0]["inscriptions"][0]["hanzi"] == "火"
    # one slot on a Phàm piece: full now
    mountain = next(w for w in opts["words"] if w["hanzi"] == "山")
    r = await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": mountain["word_id"]}, headers=h)
    assert r.json()["error"]["code"] == "no_slot"


async def test_one_wrong_answer_ends_the_try_and_the_fee_is_gone(client, db):
    h, uid, pid = await carver(client, db)
    wid = bank().by_hanzi["火"].id
    q = (await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": wid}, headers=h)).json()["question"]
    res = await answer(client, h, q)
    res = await answer(client, h, res["next"], right=False)
    assert res["inscribe"] == {"done": True, "success": False, "right": 1, "total": 3}
    assert "next" not in res
    e = await db.get(EquipmentInstance, pid)
    assert e.inscriptions == []
    assert await stones(uid) == 1000 - C["fee"]["spirit_stones"]


async def test_rules(client, db):
    h, uid, pid = await carver(client, db, rarity="huyen")
    water = bank().by_hanzi["水"].id
    r = await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": water}, headers=h)
    assert r.json()["error"]["code"] == "mastery_low"
    unknown = next(w.id for w in bank().words.values() if w.hanzi not in ("火", "山", "水"))
    r = await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": unknown}, headers=h)
    assert r.json()["error"]["code"] == "not_learned"
    h2, uid2 = await player(client, "nguoi_khac")
    r = await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": water}, headers=h2)
    assert r.json()["error"]["code"] == "no_item"
    await set_stones(uid, 10)
    fire = bank().by_hanzi["火"].id
    r = await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": fire}, headers=h)
    assert r.json()["error"]["code"] == "insufficient_funds"
    assert await qty(uid, "muc_tinh") == 20                  # nothing taken


async def test_slots_by_rarity_rarity_bonus_and_erasing(client, db):
    h, uid, pid = await carver(client, db, rarity="huyen", equipped=None)
    assert inscription.slots("pham") == 1 and inscription.slots("huyen") == 2 and inscription.slots("thien") == 3
    for hz in ("火", "山"):
        q = (await client.post("/forge/inscribe/start", json={"instance_id": pid, "word_id": bank().by_hanzi[hz].id},
                               headers=h)).json()["question"]
        for _ in range(3):
            res = await answer(client, h, q)
            q = res.get("next")
        assert res["inscribe"]["success"]
    e = await db.get(EquipmentInstance, pid)
    await db.refresh(e)
    assert [i["hanzi"] for i in e.inscriptions] == ["火", "山"]
    assert e.inscriptions[0]["value"] == round(C["by_hanzi"]["火"]["value"] * C["rarity_mult"]["huyen"])
    left = await stones(uid)
    r = await client.post("/forge/inscribe/erase", json={"instance_id": pid, "index": 0}, headers=h)
    assert r.status_code == 200 and r.json()["erased"]["hanzi"] == "火"
    assert await stones(uid) == left - C["erase_fee"]
    await db.refresh(e)
    assert [i["hanzi"] for i in e.inscriptions] == ["山"]


async def test_every_word_has_a_stat():
    for w in bank().words.values():
        st = inscription.stat_for(w.id, "pham")
        assert st["stat"] in inscription.STATS_VI and st["value"] >= 1
