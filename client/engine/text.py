"""Text rendering with per-character font fallback.

Vietnamese interface text uses the pixel font VT323; any character it lacks (Chinese
characters, pinyin tone marks such as ǎ or ǚ) is drawn with Noto Sans SC at the same
size, so a line like "Phát hiện 明 (míng)!" renders correctly in one call.
Sizes are given in base pixels (480x270) and multiplied by the display scale.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import pygame

from ..config import assets_dir

UI_FONT = "VT323-Regular.ttf"
HAN_FONT = "NotoSansSC-Game.otf"


class Fonts:
    def __init__(self, font_dir: Path | None = None):
        d = font_dir or assets_dir() / "fonts"
        self.ui_path = d / UI_FONT if (d / UI_FONT).exists() else None
        han = d / HAN_FONT
        if not han.exists():
            alt = d / "NotoSansSC-Regular.otf"
            han = alt if alt.exists() else None
        self.han_path = han
        self._fonts: dict = {}
        self._has: dict = {}
        self._cache: OrderedDict = OrderedDict()
        self.missing = self.ui_path is None or self.han_path is None

    def font(self, kind: str, px: int) -> pygame.font.Font:
        key = (kind, px)
        if key not in self._fonts:
            path = self.ui_path if kind == "ui" else self.han_path
            try:
                self._fonts[key] = pygame.font.Font(str(path) if path else None, px)
            except (OSError, pygame.error):
                self._fonts[key] = pygame.font.Font(None, px)
        return self._fonts[key]

    def _ui_has(self, ch: str) -> bool:
        """True if VT323 really draws this character (missing glyphs render as the same
        .notdef box, so compare against a code point that is certainly absent)."""
        if ch not in self._has:
            if ord(ch) >= 0x2E80:
                self._has[ch] = False
                return False
            f = self.font("ui", 16)
            try:
                if not hasattr(self, "_notdef"):
                    nd = f.render("\ue000", False, (255, 255, 255))
                    self._notdef = (nd.get_size(), pygame.image.tobytes(nd, "RGBA"))
                g = f.render(ch, False, (255, 255, 255))
                sig = (g.get_size(), pygame.image.tobytes(g, "RGBA"))
                self._has[ch] = sig != self._notdef and g.get_width() > 0
            except (pygame.error, UnicodeError):
                self._has[ch] = False
        return self._has[ch]

    def _runs(self, text: str, kind: str) -> list[tuple[str, str]]:
        if kind == "han":
            return [("han", text)]
        runs: list[tuple[str, str]] = []
        for ch in text:
            k = "ui" if (ch == " " or self._ui_has(ch)) else "han"
            if runs and runs[-1][0] == k:
                runs[-1] = (k, runs[-1][1] + ch)
            else:
                runs.append((k, ch))
        return runs

    def _px(self, kind: str, size: float, scale: int) -> int:
        # VT323 has a tall em box; this factor makes its x-height match Noto visually
        return max(6, int(round(size * scale * (1.45 if kind == "ui" else 1.0))))

    def render(self, text: str, size: float, color, scale: int, kind: str = "ui",
               antialias: bool | None = None) -> pygame.Surface:
        key = (text, size, tuple(color) if not isinstance(color, str) else color, scale, kind, antialias)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        col = pygame.Color(color)
        parts = []
        for k, chunk in self._runs(text, kind):
            aa = antialias if antialias is not None else (k == "han")
            f = self.font(k, self._px(k, size, scale))
            parts.append((k, f.render(chunk, aa, col)))
        if not parts:
            parts = [("ui", self.font("ui", self._px("ui", size, scale)).render("", False, col))]
        h = max(p.get_height() for _, p in parts)
        w = sum(p.get_width() for _, p in parts)
        surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        x = 0
        for k, p in parts:
            # vertically centre each run on the line
            surf.blit(p, (x, (h - p.get_height()) // 2 + (int(scale * 0.5) if k == "ui" else 0)))
            x += p.get_width()
        self._cache[key] = surf
        if len(self._cache) > 1500:
            self._cache.popitem(last=False)
        return surf

    def size(self, text: str, size: float, scale: int, kind: str = "ui") -> tuple[int, int]:
        return self.render(text, size, (0, 0, 0), scale, kind).get_size()

    def wrap(self, text: str, size: float, max_w_px: int, scale: int, kind: str = "ui") -> list[str]:
        """Word wrap; Chinese runs can break between any two characters."""
        lines: list[str] = []
        for para in text.split("\n"):
            cur = ""
            tokens = []
            word = ""
            for ch in para:
                if ch == " ":
                    tokens.append(word + " ")
                    word = ""
                elif ord(ch) >= 0x2E80:
                    if word:
                        tokens.append(word)
                        word = ""
                    tokens.append(ch)
                else:
                    word += ch
            if word:
                tokens.append(word)
            for t in tokens:
                trial = cur + t
                if cur and self.size(trial.rstrip(), size, scale, kind)[0] > max_w_px:
                    lines.append(cur.rstrip())
                    cur = t.lstrip()
                else:
                    cur = trial
            lines.append(cur.rstrip())
        return lines
