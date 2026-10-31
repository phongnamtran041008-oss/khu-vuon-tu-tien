"""The reel minigame (spec 11.1), shared by server and client (client/engine/fishing_sim.py
is a byte-for-byte copy; tests check they agree).

A vertical track 0..1. The fish (the green zone) wanders up and down; the hook rises
while the button is held and sinks when it is released. Hook inside the zone fills the
catch bar, outside drains it. Holding while the hook is above the fish strains the line;
too much strain snaps it.

The server picks the fish and sends `params` (including the seed of the fish's path).
The client runs `Reel` live and records on which steps the button changed; the server
replays those steps with the same code, so the result is decided on the server and a
client cannot claim a catch it did not play. Only + - * / and random.Random.random()
are used, so both sides compute exactly the same floats.
"""
from __future__ import annotations

import random

STEP_MS = 20

CAUGHT, ESCAPED, SNAPPED = "caught", "escaped", "snapped"


class Reel:
    def __init__(self, params: dict):
        p = self.p = params
        self.rng = random.Random(p["seed"])
        self.steps = 0
        self.max_steps = int(p["max_ms"]) // STEP_MS
        self.hook = 0.0
        self.vel = 0.0
        self.fish = 0.5
        self.target = 0.5
        self.seg_left = 0
        self.progress = float(p["start"])
        self.strain = 0.0
        self.inside = False
        self.result: str | None = None

    def _new_target(self) -> None:
        p, half = self.p, self.p["zone"] / 2
        t = self.fish + (self.rng.random() * 2 - 1) * p["range"]
        self.target = max(half, min(1 - half, t))
        lo, hi = p["seg_ms"]
        self.seg_left = int((lo + (hi - lo) * self.rng.random()) / STEP_MS) + 1

    def step(self, hold: bool) -> str | None:
        """Advance one STEP_MS; returns the result once the fish is caught or lost."""
        if self.result is not None:
            return self.result
        p = self.p
        dt = STEP_MS / 1000
        if self.seg_left <= 0:
            self._new_target()
        self.seg_left -= 1
        k = p["agility"] * dt
        self.fish += (self.target - self.fish) * (k if k < 1 else 1.0)
        acc = p["lift"] if hold else -p["gravity"]
        self.vel = max(-p["vmax"], min(p["vmax"], self.vel + acc * dt))
        self.hook += self.vel * dt
        if self.hook <= 0:
            self.hook, self.vel = 0.0, 0.0
        elif self.hook >= 1:
            self.hook, self.vel = 1.0, 0.0
        half = p["zone"] / 2
        self.inside = self.fish - half <= self.hook <= self.fish + half
        if self.inside:
            self.progress += p["gain"] * dt
        else:
            self.progress -= p["loss"] * dt
        if hold and self.hook > self.fish + half:
            self.strain += p["strain_up"] * dt
        else:
            self.strain = max(0.0, self.strain - p["strain_down"] * dt)
        self.steps += 1
        if self.progress >= 1:
            self.result = CAUGHT
        elif self.strain >= 1:
            self.result = SNAPPED
        elif self.progress <= 0 or self.steps >= self.max_steps:
            self.result = ESCAPED
        return self.result


def replay(params: dict, toggles: list[int]) -> Reel:
    """Run the minigame with the button changing state at the given step numbers
    (released at the start). Stops at the result."""
    r = Reel(params)
    flips = sorted(set(int(t) for t in toggles))
    i, hold = 0, False
    while r.result is None:
        while i < len(flips) and flips[i] <= r.steps:
            hold = not hold
            i += 1
        r.step(hold)
    return r
