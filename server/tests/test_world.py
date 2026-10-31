"""Stage 3: the shared world without the network (spec 15.1, 17). Sessions capture what
they would send; time is a fake monotonic clock and the tick is called by hand."""
import pytest

from app.realtime import maps, movement, protocol
from app.realtime import world as wmod
from app.realtime.chat import filter_text
from app.realtime.world import Session, World, may_enter
from app.realtime.zone import ChannelZone

VILLAGE = "truc_lam_thon"
FOREST = "rung_muc_loang"


class FakeMono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def mono():
    return FakeMono()


@pytest.fixture
def w(mono):
    return World(mono=mono)


def sess(w: World, uid: int, name: str | None = None, realm: str = "pham_nhan") -> Session:
    s = Session(uid, f"user{uid}", name or f"Đạo Hữu {uid}", realm, {"hair_color": "#2B2B2B"})
    s.sent = []
    w.sessions[uid] = s
    return s


def last(s: Session, t: str) -> dict | None:
    return next((m for m in reversed(s.sent) if m.get("t") == t), None)


def run(w: World, mono: FakeMono, seconds: float, dt: float = 0.05) -> None:
    for _ in range(round(seconds / dt)):
        mono.t += dt
        w.tick(dt)


def send_steps(w: World, s: Session, seq: int, steps) -> None:
    p = s.player
    p.channel.queue_input(p, seq, steps)


# ------------------------------------------------------------------ movement
def test_movement_matches_step_function(w, mono):
    s = sess(w, 1)
    assert w.join(s, VILLAGE, "abode")
    p = s.player
    x0, y0 = p.x, p.y
    steps = [(0, -1, 16), (0, -1, 17), (-1, -1, 17)]
    send_steps(w, s, 0, steps)
    run(w, mono, 0.1)
    col = maps.load(VILLAGE).collider
    ex, ey = x0, y0
    for dx, dy, ms in steps:
        ex, ey = movement.step(ex, ey, dx, dy, ms, 74.0, col)
    assert (p.x, p.y) == (ex, ey) and p.ack == 0
    assert p.facing == "up"  # diagonal keeps the vertical facing, like the client


def test_speed_hack_is_limited_by_real_time(w, mono):
    """A client claiming 3 s of walking within 1 s of real time moves at most ~1 s worth
    (plus the small budget that may build up while standing still)."""
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    p = s.player
    y0 = p.y
    for seq in range(30):
        send_steps(w, s, seq, [(0, -1, 100)])
    run(w, mono, 1.0)
    moved = y0 - p.y
    cap_ms = 1000 + wmod.cfg()["move_budget_max_ms"]
    assert moved <= 74.0 * cap_ms / 1000 + 0.01
    assert p.ack < 29  # the rest waits for real time (or is dropped), never applied early


def test_overlong_message_is_cut(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    p = s.player
    send_steps(w, s, 0, [(0, -1, 100)] * 10)   # 1 s in one message: over the per-message cap
    run(w, mono, 1.0)
    assert p.rejected_ms >= 1000 - wmod.cfg()["move_message_max_ms"]


def test_cannot_walk_through_walls(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    p = s.player
    col = p.channel.map.collider
    for seq in range(60):  # walk left for 3 s from the south road into the bamboo ring
        send_steps(w, s, seq, [(-1, 0, 50)])
        run(w, mono, 0.05)
    assert not col.blocked(p.x, p.y)
    assert p.x > 16  # stopped by solids, never left the map


def test_duplicate_inputs_are_ignored(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    p = s.player
    send_steps(w, s, 5, [(0, -1, 50)])
    send_steps(w, s, 5, [(0, -1, 50)])
    send_steps(w, s, 4, [(0, -1, 50)])
    assert len(p.inputs) == 1


# ------------------------------------------------------------------ snapshots & AOI
def test_players_see_each_other_and_deltas(w, mono):
    a, b = sess(w, 1, "Tiểu Trúc"), sess(w, 2, "Lão Mai")
    w.join(a, VILLAGE, "abode")
    w.join(b, VILLAGE, "abode")
    run(w, mono, 0.1)
    snap = last(a, "snap")
    assert any(e["id"] == "p2" and e["n"] == "Lão Mai" for e in snap.get("add", []))
    a.sent.clear()
    run(w, mono, 0.1)
    snap = last(a, "snap")
    assert "add" not in snap and "e" not in snap  # nothing changed: nothing resent
    send_steps(w, b, 0, [(0, -1, 50)])
    run(w, mono, 0.1)
    snap = last(a, "snap")
    assert snap["e"][0][0] == "p2"


def test_area_of_interest(w, mono):
    a, b = sess(w, 1), sess(w, 2)
    w.join(a, VILLAGE, "abode")                      # south gate, AOI cell (1, 2)
    w.join(b, VILLAGE, "abode")
    pb = b.player
    pb.x, pb.y = maps.load(VILLAGE).spawn("from_forest")  # east edge, cell (3, 1): out of range
    run(w, mono, 0.1)
    assert not any(e["id"] == "p2" for e in last(a, "snap").get("add", []))
    pb.x, pb.y = maps.load(VILLAGE).spawn("spawn")   # the square, cell (1, 1)
    run(w, mono, 0.1)
    assert any(e["id"] == "p2" for e in last(a, "snap").get("add", []))
    pb.x, pb.y = maps.load(VILLAGE).spawn("from_forest")
    run(w, mono, 0.1)
    assert "p2" in last(a, "snap").get("rm", [])


def test_own_position_and_ack_in_snapshot(w, mono):
    a = sess(w, 1)
    w.join(a, VILLAGE, "abode")
    send_steps(w, a, 7, [(1, 0, 40)])
    run(w, mono, 0.1)
    snap = last(a, "snap")
    assert snap["ack"] == 7 and snap["me"][:2] == [a.player.x, a.player.y]


# ------------------------------------------------------------------ channels
def test_channels_fill_up_and_split(w, mono):
    cap = wmod.cfg()["channel_capacity"]
    ss = [sess(w, i) for i in range(1, cap + 2)]
    for s in ss:
        assert w.join(s, VILLAGE, "abode")
    assert ss[-1].player.channel.number == 2
    assert all(s.player.channel.number == 1 for s in ss[:cap])
    chans = w.channel_list(VILLAGE)
    assert [c["players"] for c in chans] == [cap, 1]
    # the last one goes back when there is room, and the empty channel closes
    w._leave_world(ss[0].player)
    w.switch_channel(ss[-1], 1)
    assert ss[-1].player.channel.number == 1
    run(w, mono, 0.05)
    assert [c["n"] for c in w.channel_list(VILLAGE)] == [1]


def test_switch_to_full_channel_fails(w, mono):
    cap = wmod.cfg()["channel_capacity"]
    ss = [sess(w, i) for i in range(1, cap + 2)]
    for s in ss:
        w.join(s, VILLAGE, "abode")
    w.switch_channel(ss[-1], 1)
    assert last(ss[-1], "error")["code"] == "zone_full"
    w.switch_channel(ss[-1], 3)   # a brand new channel is fine
    assert ss[-1].player.channel.number == 3


def test_monsters_sleep_without_players(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    p = s.player
    p.x, p.y = maps.load(VILLAGE).spawn("from_forest")
    # stand in the east portal and go to the forest
    portal = next(a for a in p.channel.map.portals if a.props["target"] == FOREST)
    p.x, p.y = portal.x + portal.w / 2, portal.y + portal.h / 2
    assert w.join(s, FOREST, "portal")
    forest = s.player.channel
    assert forest.monsters, "the forest has Mặc Quái"
    before = [(m.x, m.y) for m in forest.monsters]
    run(w, mono, 3.0)
    assert [(m.x, m.y) for m in forest.monsters] != before
    w._leave_world(s.player)
    still = [(m.x, m.y) for m in forest.monsters]
    run(w, mono, 3.0)
    assert [(m.x, m.y) for m in forest.monsters] == still  # asleep
    for m in forest.monsters:
        assert not forest.map.collider.blocked(m.x, m.y)


# ------------------------------------------------------------------ zone changes
def test_portal_requires_standing_in_it(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    assert not w.join(s, FOREST, "portal")
    assert last(s, "error")["code"] == "not_at_portal"


def test_walk_back_to_abode(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    for seq in range(12):  # walk south through the gate (spawn is just above it)
        send_steps(w, s, seq, [(0, 1, 50)])
        run(w, mono, 0.05)
    assert w.join(s, "abode", "portal")
    z = last(s, "zone")
    assert z["zone"] == "abode" and s.player is None and 1 not in w.players
    assert w._save_now[1]["zone_id"] == "abode"
    assert not w.join(s, FOREST, "abode")   # from the abode the gate only leads to the village


def test_cannot_leave_abode_twice(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    assert not w.join(s, VILLAGE, "abode")
    assert last(s, "error")["code"] == "not_in_abode"


def test_realm_gate():
    # Rừng Mực Loang is for Luyện Khí: one realm below may enter (spec 7.3)
    assert may_enter("pham_nhan", FOREST)
    assert may_enter("luyen_khi", FOREST)


def test_realm_gate_blocks_two_realms(monkeypatch, w, mono):
    defs = dict(wmod.zone_defs())
    defs[FOREST] = {**defs[FOREST], "recommended_realm": "truc_co"}
    monkeypatch.setattr(wmod, "zone_defs", lambda: defs)
    assert not may_enter("pham_nhan", FOREST)
    assert may_enter("luyen_khi", FOREST)
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    p = s.player
    portal = next(a for a in p.channel.map.portals if a.props["target"] == FOREST)
    p.x, p.y = portal.x + portal.w / 2, portal.y + portal.h / 2
    assert not w.join(s, FOREST, "portal")
    assert last(s, "error")["code"] == "realm_too_low"


def test_resume_saved_zone(w, mono):
    s = sess(w, 1)
    s.saved_zone, s.saved_pos = VILLAGE, (440.0, 340.0, "left")
    assert w.join(s, VILLAGE, "resume")
    assert (s.player.x, s.player.y, s.player.facing) == (440.0, 340.0, "left")
    t = sess(w, 2)
    t.saved_zone = "abode"
    assert not w.join(t, VILLAGE, "resume")


def test_resume_blocked_position_goes_to_spawn(w, mono):
    s = sess(w, 1)
    s.saved_zone, s.saved_pos = VILLAGE, (2.0, 2.0, "down")   # inside the bamboo ring
    assert w.join(s, VILLAGE, "resume")
    assert (s.player.x, s.player.y) == maps.load(VILLAGE).spawn("spawn")


# ------------------------------------------------------------------ disconnects
def test_linger_then_leave(w, mono):
    a, b = sess(w, 1), sess(w, 2)
    w.join(a, VILLAGE, "abode")
    w.join(b, VILLAGE, "abode")
    w.disconnect(a)
    run(w, mono, 1.0)
    assert 1 in w.players and w.players[1].session is None
    assert any(e["id"] == "p1" for e in last(b, "snap").get("add", [])) or "p1" in b.player.known
    run(w, mono, wmod.cfg()["linger_seconds"])
    assert 1 not in w.players
    assert any("p1" in m.get("rm", []) for m in b.sent if m["t"] == "snap")
    assert w._save_now[1]["zone_id"] == VILLAGE


def test_reconnect_during_linger_keeps_place(w, mono):
    a = sess(w, 1)
    w.join(a, VILLAGE, "abode")
    send_steps(w, a, 0, [(0, -1, 50)])
    run(w, mono, 0.1)
    pos = (a.player.x, a.player.y)
    w.disconnect(a)
    run(w, mono, 5)
    a2 = sess(w, 1)
    assert w.join(a2, VILLAGE, "resume")
    assert (a2.player.x, a2.player.y) == pos and a2.player.linger_until is None
    z = last(a2, "zone")
    assert (z["x"], z["y"]) == pos


def test_message_rate_limit(mono):
    s = Session(1, "u", "n", "pham_nhan", {})
    allowed = [s.allow_message(mono.t) for _ in range(40)]
    assert allowed.count(True) == wmod.cfg()["ws_messages_per_second"]
    mono.t += 1.01
    assert s.allow_message(mono.t)


def test_bad_messages_are_rejected():
    for bad in ({"t": "teleport"}, {"x": 1}, {"t": "in", "s": 1, "k": [[0, 5, 10]]},
                {"t": "in", "s": 1, "k": [[0, 1, 1000]]}, {"t": "chat", "ch": "admin", "text": "x"}):
        with pytest.raises(protocol.BadMessage):
            protocol.parse(bad)


# ------------------------------------------------------------------ chat
def chat(w, s, ch, text, to=None):
    w.chat.handle(s, protocol.Chat(t="chat", ch=ch, text=text, to=to))


def test_world_chat_reaches_everyone_and_respects_blocks(w, mono):
    a, b, c = sess(w, 1, "An"), sess(w, 2, "Bình"), sess(w, 3, "Chi")
    c.blocks.add(1)
    chat(w, a, "world", "  xin   chào  ")
    assert last(b, "chat")["text"] == "xin chào"
    assert last(c, "chat") is None
    assert last(a, "chat")["from"]["name"] == "An"


def test_chat_limits(w, mono):
    a, b = sess(w, 1), sess(w, 2)
    chat(w, a, "world", "một")
    chat(w, a, "world", "hai")
    assert last(a, "error")["code"] == "chat_too_fast"
    mono.t += 2.0
    chat(w, a, "world", "x" * 201)
    assert last(a, "error")["code"] == "chat_too_long"
    chat(w, a, "world", "ba")
    assert [m["text"] for m in b.sent if m["t"] == "chat"] == ["một", "ba"]


def test_chat_filter(w, mono):
    assert filter_text("vcl luôn") == "*** luôn"
    assert filter_text("cây này lớn quá") == "cây này lớn quá"   # "lớn" is not a swear word


def test_zone_chat_stays_in_channel(w, mono):
    a, b, c = sess(w, 1), sess(w, 2), sess(w, 3)
    w.join(a, VILLAGE, "abode")
    w.join(b, VILLAGE, "abode")
    chat(w, a, "zone", "ai đi Rừng Mực Loang không?")
    assert last(b, "chat")["ch"] == "zone"
    assert last(c, "chat") is None  # c is in the abode
    chat(w, c, "zone", "hello")
    assert last(c, "error")["code"] == "not_in_zone"


def test_friend_chat_needs_friendship(w, mono):
    a, b = sess(w, 1, "An"), sess(w, 2, "Bình")
    chat(w, a, "friend", "chào", to="Bình")
    assert last(a, "error")["code"] == "friend_unreachable" and last(b, "chat") is None
    w.set_friends(1, 2, True)
    mono.t += 3
    chat(w, a, "friend", "chào", to="bình")
    assert last(b, "chat")["to"]["name"] == "Bình"
    assert last(a, "chat")["text"] == "chào"   # echo for the sender


def test_chat_ban_and_party(w, mono):
    import datetime as dt
    from app import clock
    a = sess(w, 1)
    a.chat_banned_until = clock.now() + dt.timedelta(hours=1)
    chat(w, a, "world", "hi")
    assert last(a, "error")["code"] == "chat_banned"
    a.chat_banned_until = None
    chat(w, a, "party", "hi")
    assert last(a, "error")["code"] == "no_party"


def test_new_channel_object_spawns_monsters_once():
    zmap = maps.load(FOREST)
    ch = ChannelZone(FOREST, 1, zmap)
    expected = sum(int(a.props["count"]) for a in zmap.monster_areas)
    assert len(ch.monsters) == expected
    assert len({m.eid for m in ch.monsters}) == expected


def test_gate_request_waits_for_queued_steps(w, mono):
    """The client asks to pass the gate right after its last steps; the server applies
    those first instead of refusing because it has not simulated them yet."""
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    for seq in range(14):
        send_steps(w, s, seq, [(0, 1, 50)])
    assert not w.join(s, "abode", "portal")      # not there yet: deferred, no error
    assert last(s, "error") is None
    run(w, mono, 1.0)
    assert last(s, "zone")["zone"] == "abode"


def test_gate_request_far_away_fails_after_steps(w, mono):
    s = sess(w, 1)
    w.join(s, VILLAGE, "abode")
    send_steps(w, s, 0, [(0, -1, 50)])
    w.join(s, "abode", "portal")
    run(w, mono, 0.5)
    assert last(s, "error")["code"] == "not_at_portal"
