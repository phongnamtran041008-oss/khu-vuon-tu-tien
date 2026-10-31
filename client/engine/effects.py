"""Small world-space effects: particles, floating text, the tone-mishap gags."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

from ..art.palette import rgb
from . import sprites


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: tuple
    size: int = 1
    age: float = 0.0
    gravity: float = 0.0


@dataclass
class FloatText:
    text: str
    x: float
    y: float
    color: str
    age: float = 0.0
    life: float = 1.6


@dataclass
class Runner:
    kind: str           # horse | villager
    x: float
    y: float
    speed: float
    age: float = 0.0
    bubble: str = ""


@dataclass
class Effects:
    particles: list = field(default_factory=list)
    texts: list = field(default_factory=list)
    runners: list = field(default_factory=list)
    flash: float = 0.0
    shake: float = 0.0
    bubbles: list = field(default_factory=list)   # (text, x, y, age, life)

    def burst(self, x: float, y: float, color: str, n: int = 14, speed: float = 40, up: bool = True) -> None:
        r = random.Random()
        for _ in range(n):
            a = r.uniform(0, math.tau)
            sp = r.uniform(speed * 0.4, speed)
            self.particles.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp - (20 if up else 0),
                                           r.uniform(0.5, 1.1), rgb(color), r.choice((1, 1, 2)), gravity=30))

    def sparkle(self, x: float, y: float, color: str = "o") -> None:
        r = random.Random()
        self.particles.append(Particle(x + r.uniform(-6, 6), y + r.uniform(-6, 2), 0, -8,
                                       r.uniform(0.4, 0.8), rgb(color), 1))

    def ink_to_light(self, x: float, y: float) -> None:
        """Ink mist dissolving into bright motes (correct answer on a withered plant)."""
        self.burst(x, y, "k", 10, 25)
        self.burst(x, y, "o", 14, 35)

    def float_text(self, text: str, x: float, y: float, color: str = "#E9C46A") -> None:
        self.texts.append(FloatText(text, x, y, color))

    def run_across(self, kind: str, y: float, cam_x: float, bubble: str = "") -> None:
        self.runners.append(Runner(kind, cam_x - 30, y, 140 if kind == "horse" else 110, bubble=bubble))

    def bubble(self, text: str, x: float, y: float, life: float = 2.5) -> None:
        self.bubbles.append([text, x, y, 0.0, life])

    def update(self, dt: float) -> None:
        for p in list(self.particles):
            p.age += dt
            if p.age > p.life:
                self.particles.remove(p)
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
        for t in list(self.texts):
            t.age += dt
            if t.age > t.life:
                self.texts.remove(t)
        for r in list(self.runners):
            r.age += dt
            r.x += r.speed * dt
            if r.age > 6:
                self.runners.remove(r)
        for b in list(self.bubbles):
            b[3] += dt
            if b[3] > b[4]:
                self.bubbles.remove(b)
        self.flash = max(0.0, self.flash - dt * 2.5)
        self.shake = max(0.0, self.shake - dt * 3)

    def draw(self, surf: pygame.Surface, cam: tuple[int, int], text_render, t: float) -> None:
        cx, cy = cam
        for r in self.runners:
            if r.kind == "horse":
                img = sprites.horse()[int(r.age * 8) % 2]
                surf.blit(img, (int(r.x - cx), int(r.y - cy - 16)))
            else:
                img = sprites.villager()[("right", 1 + int(r.age * 8) % 2)]
                surf.blit(img, (int(r.x - cx), int(r.y - cy - 24)))
                pygame.draw.circle(surf, rgb("i"), (int(r.x - cx + 11), int(r.y - cy - 15)), 1)
            if r.bubble:
                self._bubble(surf, r.bubble, r.x - cx + 8, r.y - cy - 30, text_render)
        for p in self.particles:
            a = 1 - p.age / p.life
            if a > 0.1:
                pygame.draw.rect(surf, p.color, (int(p.x - cx), int(p.y - cy), p.size, p.size))
        for ft in self.texts:
            img = text_render(ft.text, ft.color)
            y = ft.y - cy - ft.age * 14
            surf.blit(img, (int(ft.x - cx - img.get_width() / 2), int(y)))
        for text, x, y, age, life in self.bubbles:
            self._bubble(surf, text, x - cx, y - cy - min(age, 0.3) * 10, text_render)
        if self.flash > 0:
            fl = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(200 * min(1, self.flash))))
            surf.blit(fl, (0, 0))

    def _bubble(self, surf, text, x, y, text_render) -> None:
        img = text_render(text, "#2B2B2B")
        w, h = img.get_width() + 6, img.get_height() + 4
        rect = pygame.Rect(int(x - w / 2), int(y - h), w, h)
        pygame.draw.rect(surf, rgb("W"), rect)
        pygame.draw.rect(surf, rgb("k"), rect, 1)
        surf.blit(img, (rect.x + 3, rect.y + 2))
