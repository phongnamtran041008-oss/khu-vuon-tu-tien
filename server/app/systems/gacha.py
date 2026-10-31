"""Gacha (spec 6.1, 13): a pure rarity engine shared by every banner, plus the seed
banner's server-side resolution. All randomness and all charging happen on the server."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .. import balance


class GachaError(Exception):
    def __init__(self, code: str, message_vi: str):
        super().__init__(message_vi)
        self.code, self.message_vi = code, message_vi


@dataclass
class Banner:
    id: str
    rarities: list[str]          # low -> high
    rates: dict[str, float]
    pity: list[dict]             # [{"min_rarity": "legendary", "every": 90}, ...]
    ten_pull_min_rarity: str | None

    @classmethod
    def load(cls, banner_id: str) -> "Banner":
        cfg = balance.gacha()["banners"].get(banner_id)
        if cfg is None:
            raise GachaError("unknown_banner", "Không có quầy quay này.")
        b = cls(banner_id, cfg["rarities"], cfg["rates"], cfg["pity"], cfg.get("ten_pull_min_rarity"))
        if abs(sum(b.rates.values()) - 1.0) > 1e-9 or set(b.rates) != set(b.rarities):
            raise ValueError(f"bad rates for banner {banner_id}")
        return b

    def rank(self, rarity: str) -> int:
        return self.rarities.index(rarity)

    def _sample(self, rng: random.Random, at_least: str | None) -> str:
        floor = self.rank(at_least) if at_least else 0
        allowed = self.rarities[floor:]
        weights = [self.rates[r] for r in allowed]
        if sum(weights) <= 0:
            return allowed[0]
        x = rng.random() * sum(weights)
        for r, wgt in zip(allowed, weights):
            x -= wgt
            if x < 0:
                return r
        return allowed[-1]

    def roll(self, n: int, pity_state: dict, rng: random.Random,
             use_pity: bool = True) -> tuple[list[str], dict]:
        """Rolls n rarities. pity_state maps min_rarity -> rolls since last hit of it.
        Returns (rarities, new_pity_state); the input dict is not modified."""
        state = {p["min_rarity"]: int(pity_state.get(p["min_rarity"], 0)) for p in self.pity}
        out: list[str] = []
        for i in range(n):
            forced: str | None = None
            if use_pity:
                # highest-rarity rule first (list is ordered high -> low in config, but be safe)
                for p in sorted(self.pity, key=lambda p: -self.rank(p["min_rarity"])):
                    if state[p["min_rarity"]] + 1 >= p["every"]:
                        forced = p["min_rarity"]
                        break
            if (forced is None and n == 10 and i == 9 and self.ten_pull_min_rarity
                    and all(self.rank(r) < self.rank(self.ten_pull_min_rarity) for r in out)):
                forced = self.ten_pull_min_rarity
            r = self._sample(rng, forced)
            out.append(r)
            for p in self.pity:
                if self.rank(r) >= self.rank(p["min_rarity"]):
                    state[p["min_rarity"]] = 0
                else:
                    state[p["min_rarity"]] += 1
        return out, state


def expected_rate_with_pity(banner: Banner, rarity_floor: str, every: int) -> float:
    """Long-run share of rolls that reach `rarity_floor` given a hard pity at `every` (for display)."""
    p = sum(banner.rates[r] for r in banner.rarities[banner.rank(rarity_floor):])
    expected_gap = sum((1 - p) ** k for k in range(every))
    return 1 / expected_gap
