"""Stage 7 client pieces without a server: the board runs the server's own simulation, the
level map and the board draw, and a log played on the client replays to the same end."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from client.engine import td_sim

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


PLANTS = {"huo3_706b": ("hoa", "火"), "shui3_6c34": ("thuy", "水"), "mu4_6728": ("moc", "木"), "shan1_5c71": ("son", "山"),
          "yi1_4e00": ("kim", "一"), "cha2_8336": ("sinh_khi", "茶"), "ma1ma5_5988": ("ho_tro", "妈妈"),
          "yue4_6708": ("quang", "月")}


def params() -> dict:
    """Like the server's td.build_params, from the data files (the client tests never import
    the server package)."""
    data = ROOT / "server" / "data"
    c = json.loads((data / "balance" / "td.json").read_text("utf-8"))
    lv = next(x for x in json.loads((data / "td" / "levels.json").read_text("utf-8"))["levels"] if x["id"] == "c1_03")
    plants = {w: {"role": r, "hanzi": hz, "pinyin": "", "power": 0.95, "rarity": "common"} for w, (r, hz) in PLANTS.items()}
    return {"level": lv["id"], "cols": c["grid"]["cols"], "rows": c["grid"]["rows"], "path": lv["path"],
            "rocks": lv["rocks"], "core_hp": c["core_hp"], "qi": {**c["qi"], "start": c["chapters"][0]["qi_start"]},
            "upgrade": c["upgrade"], "sell_refund": c["sell_refund"], "roles": c["roles"], "monsters": c["monsters"],
            "combos": c["combos"], "boss_stun_mult": c["boss_stun_mult"], "wave_max_seconds": c["wave_max_seconds"],
            "plants": plants, "seed": 4, "waves": lv["waves"], "hp_mult": 1.0}


def test_board_runs_the_servers_simulation():
    assert (ROOT / "client" / "engine" / "td_sim.py").read_bytes() == \
        (ROOT / "server" / "app" / "systems" / "td_sim.py").read_bytes()


def test_a_log_played_on_the_client_replays_to_the_same_end():
    import td_bot
    p = params()
    sim, answers, events = td_bot.play(td_sim, p, accuracy=0.8, seed=2)
    again = td_sim.replay(json.loads(json.dumps(p)), answers, json.loads(json.dumps(events)))
    assert again.summary() == sim.summary() and sim.phase == td_sim.WON


def test_board_and_map_draw(tmp_path):
    from client.config import Config, Session
    from client.main import Game
    from client.scenes.td import TdPlayScene, monster_frames
    game = Game(Config(server_url="http://127.0.0.1:9"), Session(tmp_path / "s.json"), size=(960, 540))
    game.api.post = lambda *a, **k: None     # no server: questions are never asked
    game.api.get = lambda *a, **k: None
    run = {"run_id": "r", "params": params(), "max_speed": 2, "name_vi": "Thử", "monsters": []}
    sc = game.push(TdPlayScene(game, run, None))
    sc.busy = False
    word = next(w for w, d in run["params"]["plants"].items() if d["role"] == "hoa")
    path = {tuple(c) for c in run["params"]["path"]}
    cell = next((x, y) for y in range(7) for x in range(12) if (x, y) not in path and [x, y] not in run["params"]["rocks"])
    sc.card = word
    sc.place(*cell)
    assert cell in sc.sim.plants and sc.events[-1]["k"] == "place"
    sc.start_wave()
    for _ in range(80):
        game.step(0.05, [])
    assert sc.sim.step_n > 0 and sc.sim.monsters
    for kind in run["params"]["monsters"]:
        assert monster_frames(kind)
    game.api.close()      # (not shutdown(): it quits pygame for the tests that follow)
