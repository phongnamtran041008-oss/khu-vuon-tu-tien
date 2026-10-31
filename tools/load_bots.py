#!/usr/bin/env python3
"""Load test for the shared world (spec 2, 20 stage 3): N bots log in, walk around
Trúc Lâm Thôn and chat, while the server's tick timings are sampled from /server/stats.

    # a dev server that allows many accounts from one IP and no request rate limits:
    #   ACCOUNTS_PER_IP=500 RATE_LIMIT=0 uvicorn app.main:app --port 8000   (in server/)
    python tools/load_bots.py --server http://127.0.0.1:8000 --bots 50 --minutes 10

Passes (exit code 0) when no tick took longer than --max-tick-ms (50) or started more than
that late, every bot got into the village and none was disconnected unexpectedly. Prints a summary and can write it as JSON (--report).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time

import httpx
from websockets.asyncio.client import connect

PROTOCOL_VERSION = 3
LOOK = {"hair_color": "#2B2B2B", "hair_style": "ngan", "body": "nam"}
LINES = ["Chào mọi người!", "Ai đi Rừng Mực Loang không?", "Hôm nay ta học được chữ 水.", "Trà của Trúc Lão ngon thật.",
         "Kênh này đông vui ghê.", "Có ai biết chữ 好 ghép từ gì không?", "Đi dạo một vòng đây.", "Cây của ta sắp chín rồi!"]


def ws_url(http: str) -> str:
    return http.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws"


async def account(client: httpx.AsyncClient, i: int, prefix: str) -> str:
    user, pw = f"{prefix}{i:03d}", "botpass123"
    r = await client.post("/auth/register", json={"username": user, "password": pw})
    if r.status_code == 409:
        r = await client.post("/auth/login", json={"username": user, "password": pw})
    r.raise_for_status()
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/me", headers=h)).json()
    if not me.get("has_character"):
        r = await client.post("/character/create", json={"display_name": f"Bot {prefix} {i:03d}"[:16],
                                                         "appearance": LOOK}, headers=h)
        r.raise_for_status()
    return token


class Stats:
    def __init__(self):
        self.snaps = 0
        self.chats_in = 0
        self.chats_out = 0
        self.inputs = 0
        self.errors: dict[str, int] = {}
        self.disconnects = 0
        self.rtts: list[float] = []
        self.joined = 0
        self.corrections = 0


async def bot(i: int, token: str, args, stats: Stats, stop: asyncio.Event) -> None:
    rng = random.Random(i)
    await asyncio.sleep(rng.uniform(0, args.ramp))
    seq = 0
    while not stop.is_set():
        try:
            async with connect(ws_url(args.server), open_timeout=15, max_size=1 << 20) as ws:
                await ws.send(json.dumps({"t": "hello", "v": PROTOCOL_VERSION, "token": token}))
                welcome = json.loads(await ws.recv())
                if welcome.get("t") != "welcome":
                    stats.errors[welcome.get("code", "no_welcome")] = stats.errors.get(welcome.get("code", "no_welcome"), 0) + 1
                    return
                via = "resume" if welcome.get("zone") == "truc_lam_thon" else "abode"
                await ws.send(json.dumps({"t": "join", "zone": "truc_lam_thon", "via": via}))
                joined = asyncio.Event()

                async def reader():
                    async for raw in ws:
                        m = json.loads(raw)
                        t = m.get("t")
                        if t == "snap":
                            stats.snaps += 1
                        elif t == "chat":
                            stats.chats_in += 1
                        elif t == "zone":
                            if not joined.is_set():
                                stats.joined += 1
                            joined.set()
                        elif t == "pong" and m.get("c"):
                            stats.rtts.append(time.monotonic() - m["c"])
                        elif t == "error":
                            stats.errors[m["code"]] = stats.errors.get(m["code"], 0) + 1
                        elif t == "kicked":
                            stats.errors["kicked_" + m.get("reason", "")] = stats.errors.get("kicked_" + m.get("reason", ""), 0) + 1

                rtask = asyncio.create_task(reader())
                await asyncio.wait_for(joined.wait(), 15)
                next_chat = time.monotonic() + rng.uniform(2, args.chat_every)
                next_ping = time.monotonic() + 5
                while not stop.is_set() and not rtask.done():
                    dx, dy = rng.choice((-1, 0, 1)), rng.choice((-1, 0, 1))
                    walk_until = time.monotonic() + rng.uniform(0.5, 2.5)
                    while time.monotonic() < walk_until and not stop.is_set():
                        if dx or dy:
                            await ws.send(json.dumps({"t": "in", "s": seq, "k": [[dx, dy, 17], [dx, dy, 17], [dx, dy, 16]]}))
                            seq += 1
                            stats.inputs += 1
                        now = time.monotonic()
                        if now >= next_chat:
                            await ws.send(json.dumps({"t": "chat", "ch": rng.choice(("zone", "zone", "world")),
                                                      "text": rng.choice(LINES)}, ensure_ascii=False))
                            stats.chats_out += 1
                            next_chat = now + rng.uniform(args.chat_every * 0.5, args.chat_every * 1.5)
                        if now >= next_ping:
                            await ws.send(json.dumps({"t": "ping", "c": now}))
                            next_ping = now + 10
                        await asyncio.sleep(0.05)
                rtask.cancel()
                if stop.is_set():
                    return
        except Exception as e:  # noqa: BLE001 - count it and reconnect
            if stop.is_set():
                return
            stats.disconnects += 1
            stats.errors[type(e).__name__] = stats.errors.get(type(e).__name__, 0) + 1
            await asyncio.sleep(1 + rng.random())


async def main_async(args) -> int:
    async with httpx.AsyncClient(base_url=args.server, timeout=30) as client:
        info = (await client.get("/server/info")).json()
        print(f"server {args.server}: {info.get('name')} v{info.get('version')} protocol {info.get('protocol_version')}")
        print(f"creating/logging in {args.bots} bots...")
        tokens = []
        for i in range(args.bots):
            tokens.append(await account(client, i, args.prefix))
        stats = Stats()
        stop = asyncio.Event()
        tasks = [asyncio.create_task(bot(i, t, args, stats, stop)) for i, t in enumerate(tokens)]
        start = time.monotonic()
        end = start + args.minutes * 60
        samples = []
        last_print = 0.0
        while time.monotonic() < end:
            await asyncio.sleep(2)
            try:
                s = (await client.get("/server/stats")).json()
            except httpx.HTTPError as e:
                print("stats failed:", e)
                continue
            samples.append(s)
            if time.monotonic() - last_print >= args.print_every:
                last_print = time.monotonic()
                el = time.monotonic() - start
                chans = s["channels"].get("truc_lam_thon", [])
                print(f"[{el:6.0f}s] online {s['online']:3d} | channels {[c['players'] for c in chans]} | "
                      f"tick avg {s['tick_avg_ms']:.2f} p99 {s['tick_p99_ms']:.2f} max {s['tick_max_ms']:.2f} ms | "
                      f"late p99 {s['late_p99_ms']:.1f} max {s['late_max_ms']:.1f} ms | gc max {s.get('gc_max_ms', 0):.1f} ms | snaps {stats.snaps} chat {stats.chats_out}/{stats.chats_in} "
                      f"| disc {stats.disconnects}")
        stop.set()
        await asyncio.wait(tasks, timeout=10)
        final = (await client.get("/server/stats")).json()
    dur = args.minutes * 60
    report = {
        "bots": args.bots, "minutes": args.minutes, "joined": stats.joined,
        "tick_avg_ms": final["tick_avg_ms"], "tick_p99_ms": max(s["tick_p99_ms"] for s in samples) if samples else None,
        "tick_max_ms": final["tick_max_ms"], "late_max_ms": final["late_max_ms"],
        "ticks_over_budget": final["ticks_over_budget"], "ticks": final["ticks"],
        "gc_full_passes": final.get("gc_full_passes"), "gc_max_ms": final.get("gc_max_ms"),
        "snapshots_per_bot_per_s": round(stats.snaps / max(1, args.bots) / dur, 2),
        "inputs_sent": stats.inputs, "chats_sent": stats.chats_out, "chats_received": stats.chats_in,
        "rtt_median_ms": round(statistics.median(stats.rtts) * 1000, 1) if stats.rtts else None,
        "rtt_max_ms": round(max(stats.rtts) * 1000, 1) if stats.rtts else None,
        "disconnects": stats.disconnects, "errors": stats.errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    # spec: the tick never takes longer than 50 ms and never starts more than 50 ms late
    ok = (final["tick_max_ms"] <= args.max_tick_ms and final["late_max_ms"] <= args.max_tick_ms
          and stats.disconnects == 0 and stats.joined >= args.bots)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--bots", type=int, default=50)
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--chat-every", type=float, default=20, help="average seconds between a bot's messages")
    ap.add_argument("--ramp", type=float, default=10, help="spread the bots' arrival over this many seconds")
    ap.add_argument("--max-tick-ms", type=float, default=50)
    ap.add_argument("--prefix", default="bot")
    ap.add_argument("--print-every", type=float, default=30)
    ap.add_argument("--report", default="")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
