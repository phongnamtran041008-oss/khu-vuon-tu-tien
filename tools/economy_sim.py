"""Economy check and 30-day cash-flow model (stage 8, spec 12.1; explained in docs/BALANCE.md).

    python tools/economy_sim.py                 # 30 days, 3 kinds of player, the daily flow of Linh Thạch
    python tools/economy_sim.py --days 60 --csv flow.csv
    python tools/economy_sim.py --market        # only the market check

Two parts, both reading the real data files in server/data (nothing is copied here):

1. The market. Every exchange that needs neither time nor a question is a node in a graph:
   buying from a shop, selling to the village, brewing, cutting bait, enhancing, opening a
   gacha (by its expected value). For every good we compute the cheapest way to get it with
   Linh Thạch only (a fixed point over those exchanges). If anything could then be sold for
   at least what it costs, there is a loop that makes money without playing: `arbitrage()`
   must be empty. Things that only come with time or answers (quả chữ, cá, mật, đồ rơi) have
   no Linh Thạch price at all, so they can never close a loop.

2. The model. Three players (Thong Thả 20 minutes a day, Chăm Chỉ 1 hour, Cày Cuốc 4 hours)
   play 30 days. Every income is a number from the data (stones per review, fruit prices,
   loot tables, fish prices by rarity, Thủ Vườn rewards and their daily cap, daily tasks,
   honey...) times how much of that activity the player does; every sink (gacha, opening
   plots and hive cells, enhancing, furnace, rods, alchemy fees, khắc văn, shop) is bought by
   a simple shopping list when the player can afford it. Daily caps and the review schedule
   bound what more hours can bring.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "server" / "data"
INF = float("inf")


def load(rel: str) -> dict:
    d = json.loads((DATA / rel).read_text("utf-8"))
    return {k: v for k, v in d.items() if not k.startswith("_")} if isinstance(d, dict) else d


def bal(name: str) -> dict:
    return load(f"balance/{name}.json")


# =================================================================== 1. the market
def _stack_sell_prices() -> dict[str, float]:
    out: dict[str, float] = {}
    for rel in ("items/materials.json", "items/pills.json", "items/baits.json"):
        for iid, it in load(rel).items():
            if isinstance(it, dict) and it.get("sell_price"):
                out[iid] = float(it["sell_price"])
    for fid, f in load("creatures/fish.json").items():
        out[f"fish_{fid}"] = float(f["sell_price"])
    return out


def market() -> tuple[dict[str, float], dict[str, float], list[dict]]:
    """(buy prices, sell prices, conversions). A conversion: {name, inputs {good: qty},
    fee, outputs {good: expected qty}}. Goods: item ids, fish_<id>, fruit:<rarity>,
    equip:<id>:<rarity>:<level>, stones are the unit."""
    buy: dict[str, float] = {}
    sell = _stack_sell_prices()
    conv: list[dict] = []

    def cheaper(good, price):
        buy[good] = min(buy.get(good, INF), float(price))

    shop = bal("shop")
    for s in shop["stock"]:
        cheaper(s["item"], s["price"])
    for iid, price in bal("library")["shop"].items():
        cheaper(iid, price)
    for bid, b in load("items/baits.json").items():
        if b.get("buy"):
            cheaper(bid, b["buy"])
        if b.get("craft"):
            conv.append({"name": f"cắt mồi {bid}", "inputs": {b["craft"]["from"]: 1}, "fee": 0,
                         "outputs": {bid: b["craft"]["makes"]}})
    # fruits, by rarity (the cheapest word of that rarity is what a recipe would use)
    garden = bal("garden")
    pet_fruit = max((s["skill"]["value"] for s in load("creatures/pets.json")["species"].values()
                     if s["skill"]["type"] == "fruit_sell"), default=0)
    for r, p in garden["fruit_sell_price"].items():
        sell[f"fruit:{r}"] = p * (1 + pet_fruit)
    sell["seed:dup"] = bal("gacha")["duplicate_seed_sell_price"]
    # equipment: bought Phàm/Linh, enhanced level by level, sold back
    eq = load("items/equipment.json")
    enh = eq["enhance"]
    es = shop["equipment_sell"]
    for rar in eq["rarities"]:
        for lvl in range(enh["max_level"] + 1):
            sell[f"equip:{rar}:{lvl}"] = es["by_rarity"][rar] * (1 + es["per_enhance"] * lvl)
        for lvl in range(enh["max_level"]):
            # failing keeps the piece: the expected cost of one level is cost / success
            k = 100 / enh["success_pct"][lvl]
            conv.append({"name": f"cường hóa {rar} +{lvl + 1}",
                         "inputs": {f"equip:{rar}:{lvl}": 1, enh["material"]: enh["material_qty"][lvl] * k},
                         "fee": enh["cost_stones"][lvl] * k, "outputs": {f"equip:{rar}:{lvl + 1}": 1}})
    for rar, price in shop["equipment"]["price"].items():
        cheaper(f"equip:{rar}:0", price)
    # alchemy at the best furnace, every pill at its best quality
    alc = bal("alchemy")
    extra = max(f["extra_chance"] for f in alc["furnace"])
    fish = load("creatures/fish.json")
    fish_r = ["pham", "linh", "huyen", "dia", "thien"]
    for rid, r in load("recipes.json")["recipes"].items():
        ins: dict[str, float] = {}
        for ing in r["ingredients"]:
            if ing["kind"] == "item":
                ins[ing["item"]] = ins.get(ing["item"], 0) + ing["qty"]
            elif ing["kind"] == "fruit":
                ins[f"fruit:{ing['rarity']}"] = ing["qty"]
            else:   # the cheapest fish allowed
                lo = fish_r.index(ing["rarity"])
                f = min((fid for fid, x in fish.items() if fish_r.index(x["rarity"]) >= lo),
                        key=lambda fid: fish[fid]["sell_price"])
                ins[f"fish_{f}"] = ing["qty"]
        conv.append({"name": f"luyện {rid}", "inputs": ins, "fee": r["fee"],
                     "outputs": {rid: max(r["yield"].values()) + extra}})
    # gacha by expected value (spec 13: random, so its average is what matters)
    g = bal("gacha")["banners"]
    pets = load("creatures/pets.json")
    dupe = pets["dupe_stones"]
    conv.append({"name": "Linh Thú (đã đủ cấp, thành Linh Thạch)", "inputs": {}, "fee": g["pets"]["price"]["spirit_stones"],
                 "outputs": {"stones": sum(g["pets"]["rates"][r] * dupe[r] for r in dupe)}})
    wax = bal("bees")["release_wax"]
    conv.append({"name": "Trứng Ong (thả ong lấy sáp)", "inputs": {}, "fee": g["bees"]["price"]["spirit_stones"],
                 "outputs": {"sap_ong": sum(g["bees"]["rates"][r] * wax[r] for r in wax)}})
    conv.append({"name": "Hạt Chữ (hạt trùng)", "inputs": {}, "fee": g["seeds"]["price"]["spirit_stones"],
                 "outputs": {"seed:dup": 1}})
    conv.append({"name": "Hạt Giống Thường (hạt trùng)", "inputs": {},
                 "fee": next(s["price"] for s in shop["stock"] if s["item"] == shop["seed_item"]),
                 "outputs": {"seed:dup": 1}})
    return buy, sell, conv


def acquire_costs(buy: dict[str, float], conv: list[dict]) -> dict[str, float]:
    """Cheapest Linh Thạch cost of each good through shops and conversions (fixed point)."""
    cost = dict(buy)
    for _ in range(200):
        changed = False
        for c in conv:
            total = c["fee"] + sum(q * cost.get(g, INF) for g, q in c["inputs"].items())
            if total == INF:
                continue
            outs = {g: q for g, q in c["outputs"].items() if q > 0}
            if len(outs) != 1:
                continue
            (g, q), = outs.items()
            if g == "stones":
                continue
            per = total / q
            if per < cost.get(g, INF) - 1e-9:
                cost[g] = per
                changed = True
        if not changed:
            break
    return cost


def arbitrage() -> list[dict]:
    """Every way to turn Linh Thạch into more Linh Thạch without time or answers (must be [])."""
    buy, sell, conv = market()
    cost = acquire_costs(buy, conv)
    bad = []
    for g, price in sell.items():
        if cost.get(g, INF) <= price + 1e-9:
            bad.append({"good": g, "cost": cost[g], "sell": price})
    for c in conv:    # gacha straight to stones
        if "stones" in c["outputs"]:
            total = c["fee"] + sum(q * cost.get(g, INF) for g, q in c["inputs"].items())
            if c["outputs"]["stones"] >= total:
                bad.append({"good": c["name"], "cost": total, "sell": c["outputs"]["stones"]})
    return bad


def market_report() -> list[str]:
    buy, sell, conv = market()
    cost = acquire_costs(buy, conv)
    lines = ["Hàng mua được bằng Linh Thạch: giá rẻ nhất để có (mua hoặc tự làm) và giá làng thu mua", ""]
    rows = sorted((g for g in cost if g in sell), key=lambda g: sell[g] / cost[g], reverse=True)
    for g in rows:
        lines.append(f"  {g:28s} có được ≥ {cost[g]:8.1f}   bán được {sell[g]:7.1f}   ({sell[g] / cost[g]:.0%})")
    bad = arbitrage()
    lines.append("")
    lines.append("KHÔNG có vòng lặp tạo tiền." if not bad else f"VÒNG LẶP TẠO TIỀN: {bad}")
    return lines


# =================================================================== 2. the 30-day model
@dataclass
class Profile:
    id: str
    name_vi: str
    minutes: int
    review_checks: int          # times a day the garden is opened (reviews due get answered then)
    accuracy: float             # share of right answers
    kills: int                  # monsters a day
    casts: int                  # fishing casts a day
    td_plays: int               # Thủ Vườn levels a day
    brews: int                  # pills brewed a day
    dailies: float              # share of daily tasks finished
    seed_rolls: int             # paid Hạt Chữ rolls a day (on top of the free one)
    egg_every: int              # buys a bee egg every N days (0 = never)
    pet_every: int              # rolls Linh Thú every N days (0 = never)
    enhance_to: int             # wants its gear at this +level
    inscribe_every: int         # khắc văn every N days (0 = never)
    reserve: int                # never spends below this


PROFILES = [
    Profile("thong_tha", "Thong Thả (20 phút/ngày)", 20, 1, 0.75, 8, 0, 0, 0, 0.35, 0, 0, 0, 2, 0, 100),
    Profile("cham_chi", "Chăm Chỉ (1 giờ/ngày)", 60, 2, 0.85, 30, 10, 2, 1, 0.9, 1, 4, 10, 5, 7, 200),
    Profile("cay_cuoc", "Cày Cuốc (4 giờ/ngày)", 240, 4, 0.9, 140, 50, 6, 4, 1.0, 4, 1, 3, 8, 3, 300),
]


@dataclass
class Sim:
    p: Profile
    stones: float
    jade: float = 0
    plots: int = 9
    hive_cells: int = 5
    bees: int = 1
    hive_level: int = 1
    gear_level: int = 0
    furnace: int = 1
    rods: int = 0
    flow: list = field(default_factory=list)
    totals_in: dict = field(default_factory=dict)
    totals_out: dict = field(default_factory=dict)

    def earn(self, what: str, n: float, day: dict) -> None:
        if n <= 0:
            return
        self.stones += n
        day["in"][what] = day["in"].get(what, 0) + n
        self.totals_in[what] = self.totals_in.get(what, 0) + n

    def spend(self, what: str, n: float, day: dict, force: bool = False) -> bool:
        if n <= 0:
            return True
        if not force and self.stones - n < self.p.reserve:
            return False
        if self.stones < n:
            return False
        self.stones -= n
        day["out"][what] = day["out"].get(what, 0) + n
        self.totals_out[what] = self.totals_out.get(what, 0) + n
        return True


def _avg(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def rates() -> dict:
    """Per-action values taken from the data files."""
    garden = bal("garden")
    seeds = bal("gacha")["banners"]["seeds"]
    fruit_value = sum(seeds["rates"][r] * garden["fruit_sell_price"][r] for r in seeds["rates"])
    per_stage = garden["reward_per_new_stage"]
    review_stones = [per_stage * s for s in range(2, 6)]          # 1 -> 5: four paid reviews per plant
    sell = _stack_sell_prices()
    eq_sell = bal("shop")["equipment_sell"]["by_rarity"]
    mons = load("creatures/monsters.json")
    mix = {"ink_slime": 0.55, "tone_wisp": 0.4, "ink_fox": 0.05}
    kill = 0.0
    for kind, share in mix.items():
        m = mons[kind]
        v = _avg(m["stones"])
        for d in m["drops"]:
            if "item" in d:
                v += d["chance"] * _avg(d["qty"]) * sell.get(d["item"], 0)
            else:
                v += d["chance"] * eq_sell["pham"]
        kill += share * v
    fishing = bal("fishing")
    fish = load("creatures/fish.json")
    w = fishing["rarity_weight"]
    fish_v = sum(w[r] * _avg(f["sell_price"] for f in fish.values() if f["rarity"] == r) for r in w) / sum(w.values())
    bait = next(b["buy"] for b in load("items/baits.json").values() if b.get("buy"))
    td = bal("td")["rewards"]
    q = load("quests.json")
    daily = q["daily"]
    pool = {t["id"]: t for t in daily["pool"]}
    other = [t for t in daily["pool"] if t["id"] not in daily["always"]]
    daily_stones = sum(pool[t]["rewards"].get("spirit_stones", 0) for t in daily["always"]) + \
        daily["count"] * _avg(t["rewards"].get("spirit_stones", 0) for t in other)
    chain_stones = sum(st["rewards"].get("spirit_stones", 0) for c in q["chains"].values() for st in c["steps"])
    chain_jade = sum(st["rewards"].get("immortal_jade", 0) for c in q["chains"].values() for st in c["steps"])
    return {"fruit_value": fruit_value, "review_stones": review_stones, "harvest": garden["harvest_fruits"],
            "kill": kill, "fish": fish_v, "bait": bait, "td_replay": td["replay_stones"]["1"],
            "td_daily_cap": td["daily_rewarded_plays"], "td_first": [sum(v) for v in td["first_star_stones"].values()],
            "daily_stones": daily_stones, "daily_bonus": daily["all_done_bonus"].get("spirit_stones", 0),
            "daily_jade": daily["all_done_bonus"].get("immortal_jade", 0),
            "chain_stones": chain_stones, "chain_jade": chain_jade, "honey_price": sell["linh_mat"],
            "help": bal("social")["help_reward"] * bal("social")["help_daily_limit"]}


def simulate(p: Profile, days: int = 30, start_stones: float | None = None) -> Sim:
    r = rates()
    eco = bal("economy")
    garden = bal("garden")
    gacha = bal("gacha")["banners"]
    eq = load("items/equipment.json")["enhance"]
    hive = bal("bees")["hive"]
    alc = bal("alchemy")
    ins = bal("inscription")
    rods = load("items/rods.json")
    rod_list = [x["price"]["spirit_stones"] for x in rods.values() if x.get("price")]
    s = Sim(p, float(eco["starting_spirit_stones"] if start_stones is None else start_stones))
    hours = p.minutes / 60
    # a plant needs 5 right reviews over 10 min + 1 + 3 + 7 days; a player who opens the
    # garden k times a day loses about half a check interval on each of the 3 long waits
    cycle_days = (11 + 3 * 0.5 / p.review_checks) / p.accuracy
    plant_slots = 0.0
    td_first_left = list(r["td_first"]) * 10      # 30 levels, first stars once
    for d in range(1, days + 1):
        day = {"day": d, "in": {}, "out": {}}
        # --- income
        plant_slots = min(s.plots, plant_slots + 1 + p.seed_rolls)            # seeds: free roll + bought
        cycles = plant_slots / cycle_days
        s.earn("ôn vườn", cycles * sum(r["review_stones"]) * p.accuracy, day)
        fruit = cycles * r["harvest"] * r["fruit_value"]
        brew_fruit = min(fruit, p.brews * 2 * garden["fruit_sell_price"]["common"])   # fruits go into the furnace
        s.earn("bán quả chữ", fruit - brew_fruit, day)
        s.earn("hạ quái", p.kills * r["kill"], day)
        s.earn("câu cá", p.casts * 0.55 * r["fish"], day)                 # about half the casts land a fish
        s.spend("mồi câu", p.casts * r["bait"], day, force=True)
        plays = min(p.td_plays, r["td_daily_cap"])
        first = 0
        for _ in range(min(p.td_plays, 3)):
            if td_first_left and p.td_plays:
                first += td_first_left.pop(0)
        s.earn("ải Thủ Vườn", plays * r["td_replay"] + first, day)
        s.earn("nhiệm vụ hằng ngày", p.dailies * r["daily_stones"] + (r["daily_bonus"] if p.dailies >= 0.99 else 0), day)
        s.jade += r["daily_jade"] if p.dailies >= 0.99 else 0
        chain_days = max(1, round(14 * 60 / p.minutes))                      # one-off story rewards
        if d <= chain_days:
            s.earn("nhiệm vụ cốt truyện", r["chain_stones"] / chain_days, day)
            s.jade += r["chain_jade"] / chain_days
        honey = min(s.bees * 24 * hive["levels"][s.hive_level - 1]["honey_mult"],
                    hive["levels"][s.hive_level - 1]["capacity"] * p.review_checks)
        s.earn("bán Linh Mật", honey * 0.5 * r["honey_price"], day)          # half goes to bees and pills
        s.earn("tưới giúp bạn", r["help"] * min(1.0, p.minutes / 60), day)
        # --- spending, most wanted first
        for _ in range(p.seed_rolls):
            s.spend("gacha Hạt Chữ", gacha["seeds"]["price"]["spirit_stones"], day)
        costs = garden["plot_unlock_costs"]
        if s.plots - 9 < len(costs) and s.spend("mở ô đất", costs[s.plots - 9], day):
            s.plots += 1
        if p.brews:
            fee = _avg(x["fee"] for x in load("recipes.json")["recipes"].values() if x["min_realm"] == "pham_nhan")
            s.spend("phí luyện đan + dược thảo", p.brews * (fee + 8), day, force=True)
            nxt = next((f for f in alc["furnace"] if f["level"] == s.furnace + 1), None)
            if nxt and s.spend("nâng lò đan", nxt["cost"]["spirit_stones"], day):
                s.furnace += 1
        if p.egg_every and d % p.egg_every == 0 and s.spend("gacha Trứng Ong", gacha["bees"]["price"]["spirit_stones"], day):
            s.bees += 1
        if s.bees > s.hive_cells - 1 and s.hive_cells - 5 < len(hive["cell_costs"]):
            if s.spend("mở ô tổ ong", hive["cell_costs"][s.hive_cells - 5], day):
                s.hive_cells += 1
        if s.hive_level < len(hive["levels"]) and s.bees >= 2 * s.hive_level:
            if s.spend("nâng cấp tổ ong", hive["levels"][s.hive_level]["cost"]["spirit_stones"], day):
                s.hive_level += 1
        if s.gear_level < p.enhance_to:
            lvl = s.gear_level
            k = 100 / eq["success_pct"][lvl]
            if s.spend("cường hóa", 6 * (eq["cost_stones"][lvl] * k), day):   # six pieces
                s.gear_level += 1
        if p.inscribe_every and d % p.inscribe_every == 0:
            s.spend("khắc văn", ins["fee"]["spirit_stones"], day)
        if p.pet_every and d % p.pet_every == 0:
            s.spend("gacha Linh Thú", gacha["pets"]["price"]["spirit_stones"], day)
        if p.casts and s.rods < len(rod_list) and s.spend("mua cần câu", rod_list[s.rods], day):
            s.rods += 1
        if p.kills >= 30:
            s.spend("đan dược ở sạp", 2 * 40, day)
        s.flow.append({"day": d, "in": sum(day["in"].values()), "out": sum(day["out"].values()),
                       "stones": s.stones, "jade": s.jade, "detail_in": day["in"], "detail_out": day["out"]})
    return s


def report(days: int = 30, csv_path: str | None = None) -> list[str]:
    lines = []
    sims = [simulate(p, days) for p in PROFILES]
    lines.append(f"Dòng Linh Thạch {days} ngày (vào / ra / còn lại cuối ngày)")
    lines.append("")
    head = "Ngày " + "".join(f"| {p.name_vi:^31s}" for p in PROFILES)
    lines.append(head)
    for d in range(days):
        row = f"{d + 1:4d} "
        for sim in sims:
            f = sim.flow[d]
            row += f"| +{f['in']:6.0f} -{f['out']:6.0f} ={f['stones']:8.0f}    "
        lines.append(row)
    for sim in sims:
        tin, tout = sum(sim.totals_in.values()), sum(sim.totals_out.values())
        lines.append("")
        lines.append(f"{sim.p.name_vi}: vào {tin:,.0f}, ra {tout:,.0f} ({tout / tin:.0%} quay về vòi xả), "
                     f"còn {sim.stones:,.0f} Linh Thạch, {sim.jade:.0f} Tiên Ngọc".replace(",", "."))
        lines.append("  Nguồn vào: " + ", ".join(f"{k} {v:,.0f}".replace(",", ".")
                                                for k, v in sorted(sim.totals_in.items(), key=lambda x: -x[1])))
        lines.append("  Vòi xả:    " + ", ".join(f"{k} {v:,.0f}".replace(",", ".")
                                                for k, v in sorted(sim.totals_out.items(), key=lambda x: -x[1])))
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["profile", "day", "in", "out", "stones", "jade"])
            for sim in sims:
                for f in sim.flow:
                    w.writerow([sim.p.id, f["day"], round(f["in"]), round(f["out"]), round(f["stones"]), round(f["jade"], 1)])
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--csv")
    ap.add_argument("--market", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(market_report()))
    if not a.market:
        print()
        print("\n".join(report(a.days, a.csv)))
    return 1 if arbitrage() else 0


if __name__ == "__main__":
    sys.exit(main())
