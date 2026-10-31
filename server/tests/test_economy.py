"""Stage 8 acceptance (spec 20): there is no loop that makes Linh Thạch forever. Uses
tools/economy_sim.py (the market check over the real data files and the 30-day model of three
kinds of players, whose cash flow it prints; see docs/BALANCE.md), plus a few checks of the
real server: buying back is always cheaper than buying, brewing never pays more than its
ingredients sell for."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import economy_sim as es  # noqa: E402

from app import balance  # noqa: E402
from app.systems import catalog  # noqa: E402


def test_no_instant_loop_turns_linh_thach_into_more_linh_thach():
    assert es.arbitrage() == []


def test_everything_the_shops_sell_is_bought_back_for_much_less():
    buy, sell, conv = es.market()
    cost = es.acquire_costs(buy, conv)
    for good, price in buy.items():
        if good in sell:
            assert sell[good] < price, good
            assert sell[good] < cost[good], good


def test_brewing_is_never_worth_more_than_its_ingredients_at_village_prices():
    """Even ingredients that only come from playing: a pill sells for less than what went in."""
    sell = es._stack_sell_prices()
    garden = balance.garden()
    alc = balance.load("alchemy")
    extra = max(f["extra_chance"] for f in alc["furnace"])
    fish = catalog.fish()
    for rid, r in catalog.recipes().items():
        value_in = r["fee"]
        for ing in r["ingredients"]:
            if ing["kind"] == "item":
                value_in += ing["qty"] * sell.get(ing["item"], 0)
            elif ing["kind"] == "fruit":
                value_in += ing["qty"] * garden["fruit_sell_price"][ing["rarity"]]
            else:
                value_in += ing["qty"] * min(f["sell_price"] for f in fish.values() if f["rarity"] == ing["rarity"])
        value_out = (max(r["yield"].values()) + extra) * catalog.pills()[rid]["sell_price"]
        assert value_out < value_in, (rid, value_out, value_in)


def test_gacha_never_pays_back_on_average():
    g = balance.gacha()["banners"]
    pets = catalog.pets()
    ev = sum(g["pets"]["rates"][r] * pets["dupe_stones"][r] for r in pets["dupe_stones"])
    assert ev < g["pets"]["price"]["spirit_stones"] / 2
    assert balance.gacha()["duplicate_seed_sell_price"] < g["seeds"]["price"]["spirit_stones"]


def test_thirty_days_of_three_kinds_of_player(capsys):
    lines = es.report(30)
    print("\n".join(lines))          # the cash flow (pytest -s, or run tools/economy_sim.py)
    sims = {p.id: es.simulate(p, 30) for p in es.PROFILES}
    for sim in sims.values():
        assert all(f["stones"] >= 0 for f in sim.flow)
        tin, tout = sum(sim.totals_in.values()), sum(sim.totals_out.values())
        assert tout / tin >= 0.6, sim.p.id                 # the sinks take most of what comes in
    casual, grinder = sims["thong_tha"], sims["cay_cuoc"]
    per_min = {k: sum(s.totals_in.values()) / (30 * s.p.minutes) for k, s in sims.items()}
    # more hours never earn faster per minute, and the garden (the review schedule) barely grows with hours
    assert per_min["cay_cuoc"] <= per_min["thong_tha"] * 1.1
    assert grinder.totals_in["ôn vườn"] <= 3 * casual.totals_in["ôn vườn"]


def test_money_does_not_breed_money():
    """A player who starts with a fortune buys every upgrade at once, yet a day still earns a
    bounded amount: plots, hive cells and hive levels stop at their maximum, and nothing pays
    interest on a balance."""
    p = next(x for x in es.PROFILES if x.id == "cay_cuoc")
    normal = es.simulate(p, 30)
    rich = es.simulate(p, 30, start_stones=10 ** 9)
    assert max(f["in"] for f in rich.flow) <= 1.6 * max(f["in"] for f in normal.flow)
    late = [f["in"] for f in rich.flow[-10:]]
    assert max(late) - min(late) <= 0.25 * max(late)       # flat once everything is bought


@pytest.mark.parametrize("item_id", [s["item"] for s in balance.load("shop")["stock"]
                                     if s["item"] != balance.load("shop")["seed_item"]])
def test_shop_stock_exists(item_id):
    assert catalog.stack_item(item_id) is not None
