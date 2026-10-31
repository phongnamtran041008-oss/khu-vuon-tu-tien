"""Fast client checks: sprites, fonts, map, UI widgets (no server)."""
import itertools
import json

import pygame

from client.art import build as B
from client.art.sprites import items, people
from client.config import assets_dir
from client.engine.display import Display
from client.engine.text import Fonts
from client.engine.tilemap import TileMap
from client.ui.kit import UI


def test_every_grid_is_rectangular():
    grids = [people.HEAD_DOWN, people.HEAD_UP, people.HEAD_RIGHT, people.TORSO_DOWN, people.TORSO_UP,
             people.TORSO_RIGHT, people.TRUC_LAO, people.TRUC_LAO_BLINK, items.STONE, items.FRUIT,
             items.SEED_ICON] + people.LEGS_FRONT + people.LEGS_SIDE + people.HORSE + items.SEED
    for style in people.HAIR.values():
        grids += list(style.values())
    for g in grids:
        B.grid(g)  # raises on a ragged row


def test_all_appearances_build():
    cfg = json.loads((assets_dir().parents[1] / "server" / "data" / "balance" / "character.json").read_text("utf-8"))
    for color, style, body in itertools.product(cfg["hair_colors"], cfg["hair_styles"], cfg["bodies"]):
        frames = B.character_frames({"hair_color": color, "hair_style": style, "body": body})
        assert len(frames) == 12
        assert all(f.get_size() == (16, 24) for f in frames.values())


def test_plants_all_stages_and_rarities():
    for stage in range(6):
        for r in ("common", "rare", "epic", "legendary"):
            assert B.plant(stage, r, "k").get_size() == (24, 24)
    assert B.withered(B.plant(5, "rare", "k"), 90).get_size() == (24, 24)


def test_fonts_fallback_and_wrap():
    f = Fonts()
    assert not f.missing, "run tools/fetch_assets.py"
    assert f._ui_has("ệ") and f._ui_has("ư")
    assert not f._ui_has("明") and not f._ui_has("→")
    mixed = f.render("Phát hiện 明 (míng)", 10, (0, 0, 0), 2)
    plain = f.render("Phát hiện  (míng)", 10, (0, 0, 0), 2)
    assert mixed.get_width() > plain.get_width()
    lines = f.wrap("Thiên địa vận hành nhờ Chữ Đạo: vạn vật có tên thì có linh khí.", 9, 200, 2)
    assert len(lines) >= 2 and all(f.size(l, 9, 2)[0] <= 200 for l in lines)
    han = f.wrap("我喜欢吃苹果我喜欢吃苹果我喜欢吃苹果", 12, 100, 2, kind="han")
    assert len(han) >= 3


def test_abode_map():
    m = TileMap(assets_dir() / "maps" / "abode.tmj")
    spawn = m.find("spawn")[0]
    assert not m.blocked(pygame.Rect(int(spawn.x) - 5, int(spawn.y) - 6, 10, 6))
    garden = m.find("area", "garden")[0]
    assert (garden.w, garden.h) == (160, 160)
    actions = {o.props.get("action") for o in m.find("interact")}
    assert {"gacha", "discoveries", "craft", "exit", "hive", "alchemy"} <= actions
    assert m.find("npc")
    for o in m.objects:
        if "sprite" in o.props:
            assert o.props["sprite"] in {"bamboo", "hut", "shrine", "tablet", "table", "gate", "mat", "rock", "hive",
                                          "furnace"}


def test_display_integer_scaling():
    d = Display(0, False, size=(1500, 840))
    assert d.scale == 3 and d.ox == (1500 - 1440) // 2
    assert d.to_base(d.to_window(100, 50)) == (100, 50)


def test_button_click_and_hotkey():
    d = Display(0, False, size=(960, 540))
    ui = UI(d, Fonts())
    pos = d.to_window(55, 25)
    ui.begin([pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)], 0.016)
    assert ui.button("b", 40, 20, 30, 10, "OK")
    assert not ui.button("c", 100, 20, 30, 10, "No")  # the click was consumed / elsewhere
    ui.begin([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1)], 0.016)
    assert ui.button("d", 0, 0, 10, 10, "1", key=pygame.K_1)
    ui.enabled = False
    ui.begin([pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)], 0.016)
    ui.enabled = False
    assert not ui.button("b", 40, 20, 30, 10, "OK")  # scenes under a modal do not react


def test_text_input_typing():
    d = Display(0, False, size=(960, 540))
    ui = UI(d, Fonts())
    ui.set_focus("name")
    ui.begin([pygame.event.Event(pygame.TEXTINPUT, text="T"), pygame.event.Event(pygame.TEXTINPUT, text="ú")], 0.016)
    assert ui.input_box("name", 10, 10, 100, 12, max_len=16) == "Tú"
    ui.begin([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0)], 0.016)
    assert ui.input_box("name", 10, 10, 100, 12) == "T"


# ------------------------------------------------------------------ stage 3
def _server_movement():
    import importlib.util
    path = assets_dir().parents[1] / "server" / "app" / "realtime" / "movement.py"
    spec = importlib.util.spec_from_file_location("server_movement", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_client_and_server_movement_agree():
    """Prediction only works if both sides compute exactly the same positions."""
    import random

    from client.engine import movement as cm
    sm = _server_movement()
    tm = TileMap(assets_dir() / "maps" / "truc_lam_thon.tmj")
    solids = [(r.x, r.y, r.w, r.h) for r in tm.solids]
    cc, sc = cm.Collider(tm.px_w, tm.px_h, solids), sm.Collider(tm.px_w, tm.px_h, solids)
    rng = random.Random(7)
    x = y = None
    cx, cy = sx, sy = 448.0, 528.0
    for _ in range(3000):
        dx, dy, ms = rng.choice((-1, 0, 1)), rng.choice((-1, 0, 1)), rng.randint(1, 100)
        cx, cy = cm.step(cx, cy, dx, dy, ms, 74.0, cc)
        sx, sy = sm.step(sx, sy, dx, dy, ms, 74.0, sc)
        assert (cx, cy) == (sx, sy)
        # the collider matches the pygame rectangles the client draws with
        assert cc.blocked(cx, cy) == tm.blocked(pygame.Rect(*cm.foot_box(cx, cy)))
    assert (x, y) == (None, None) and not cc.blocked(cx, cy)
    assert open(cm.__file__, encoding="utf-8").read().split('"""', 2)[2] == \
        open(sm.__file__, encoding="utf-8").read().split('"""', 2)[2]  # same code below the docstring


def test_interpolation_between_snapshots():
    from client.net.interpolation import Interpolator
    it = Interpolator(delay=0.1)
    for i in range(5):
        it.clock_sample(i * 0.1, 10 + i * 0.1)
        it.push("p2", i * 0.1, i * 10.0, 0.0, 0, 1)
    x, y, f, m = it.sample("p2", 10.4)   # render time = server 0.3
    assert abs(x - 30.0) < 1e-6 and m == 1
    x, _, _, m = it.sample("p2", 10.45)  # halfway between 0.3 and 0.4
    assert abs(x - 35.0) < 1e-6
    x, _, _, m = it.sample("p2", 20.0)   # long after the last snapshot: hold still
    assert x == 40.0 and m == 0


def test_world_maps_have_what_the_server_needs():
    for name in ("truc_lam_thon", "rung_muc_loang"):
        tm = TileMap(assets_dir() / "maps" / f"{name}.tmj")
        assert tm.props["zone"] == name
        spawns = {o.name for o in tm.find("spawn")}
        assert "spawn" in spawns
        portals = tm.find("portal")
        assert portals and all(o.props.get("target") for o in portals)
        for o in tm.find("spawn"):
            assert not tm.blocked(pygame.Rect(int(o.x - 5), int(o.y - 6), 10, 6)), (name, o.name)
        server_copy = assets_dir().parents[1] / "server" / "maps" / f"{name}.tmj"
        assert server_copy.read_text("utf-8") == (assets_dir() / "maps" / f"{name}.tmj").read_text("utf-8")
    forest = TileMap(assets_dir() / "maps" / "rung_muc_loang.tmj")
    assert forest.find("monster_area")


def test_monster_and_village_sprites():
    from client.art.sprites import creatures
    from client.engine import sprites
    for kind in ("ink_slime", "tone_wisp"):
        frames = sprites.monster(kind)
        assert len(frames) == 2 and all(f.get_size() == (16, 16) for f in frames)
    for g in creatures.INK_SLIME + creatures.TONE_WISP:
        B.grid(g)
    for name in ("house", "pavilion", "library", "stall", "furnace", "anvil", "board", "well", "lantern",
                 "tree", "ink_tree", "portal", "td_gate", "sign"):
        assert sprites.prop(name, 1, 1).get_width() > 0
    for look in sprites.NPC_LOOKS:
        assert sprites.npc(look)[("down", 0)].get_size() == (16, 24)


def test_ws_url():
    from client.net.ws_client import ws_url
    assert ws_url("http://127.0.0.1:8000") == "ws://127.0.0.1:8000/ws"
    assert ws_url("https://abc.trycloudflare.com/") == "wss://abc.trycloudflare.com/ws"


def test_chat_target_with_spaces():
    from client.ui.chat import ChatBox

    class G:
        class state:
            friends = [{"display_name": "Tiểu Trúc"}, {"display_name": "Tiểu"}]
    box = ChatBox(G())
    assert box._friend_target("Tiểu Trúc ăn cơm chưa") == ("Tiểu Trúc", "ăn cơm chưa")
    assert box._friend_target("An chào") == ("An", "chào")


def test_day_night():
    from client.scenes.world import darkness
    assert darkness(0.5) == 0.0          # noon
    assert darkness(0.0) == 1.0          # midnight
    assert 0 < darkness(19 / 24) < 1     # dusk


def test_bee_sprites_and_flight():
    import random

    from client.engine import sprites
    from client.engine.beeflock import Flock
    look = {"body": "#BC4749", "stripe": "#E9C46A", "wing": "#FFE4C8", "eye": "#2B2B2B"}
    f0, f1 = sprites.bee(look, 0), sprites.bee(look, 1)
    assert f0.get_size() == (8, 8) and f0.get_at((3, 0)) != f1.get_at((3, 0))     # two wing frames
    assert sprites.bee(look, 0, True).get_at((7, 4)) == f0.get_at((0, 4))         # facing left = mirrored
    assert [e.get_size() for e in sprites.egg("#6A994E")] == [(12, 16)] * 3
    assert sprites.prop("hive", 0, 0).get_size() == (24, 32)
    for d in ("den_long", "hoa_sen", "chuong_gio", "co_phuong"):
        assert sprites.decoration(d, 0).get_width() > 0
    flock = Flock()
    b = flock.get("p1:0", "muc", 100, 100, 0.0)
    rnd = random.Random(1)
    for i in range(240):               # four seconds circling an anchor: stays close, never jumps
        x0, y0 = b.x, b.y
        b.update(1 / 60, 200 + rnd.uniform(-1, 1), 150, 10, 90, 16)
        assert abs(b.x - x0) < 3 and abs(b.y - y0) < 3
    assert abs(b.x - 200) < 25 and abs(b.y - 150) < 20
    flock.prune(10.0)
    assert not flock.bees
