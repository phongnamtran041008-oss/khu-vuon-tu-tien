"""Sound: word pronunciation (MP3 from assets or streamed from the server for listening
questions) and small synthesized effects, so the game needs no copyrighted sounds.
Everything degrades silently when no audio device exists."""
from __future__ import annotations

import io
import math
import random
from array import array
from pathlib import Path

import pygame

from ..config import assets_dir

RATE = 22050


class Audio:
    def __init__(self, sfx_volume: float = 0.8, voice_volume: float = 1.0):
        self.ok = False
        self.sfx_volume = sfx_volume
        self.voice_volume = voice_volume
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=1)
            self.ok = True
        except pygame.error:
            return
        self.sounds = {name: self._make(name) for name in ("click", "correct", "wrong", "coin", "crack",
                                                            "reveal", "discover", "plant", "step")}
        self.audio_dir = assets_dir() / "audio"

    # ------------------------------------------------------------ synthesis
    def _tone(self, notes: list[tuple[float, float]], wave: str = "sine", vol: float = 0.5,
              decay: float = 6.0) -> pygame.mixer.Sound:
        buf = array("h")
        rnd = random.Random(1)
        for freq, dur in notes:
            n = int(RATE * dur)
            for i in range(n):
                t = i / RATE
                env = math.exp(-decay * t) * min(1.0, i / 80)
                if wave == "noise":
                    v = rnd.uniform(-1, 1)
                elif wave == "square":
                    v = 1.0 if math.sin(2 * math.pi * freq * t) > 0 else -1.0
                    v *= 0.5
                else:
                    v = math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(4 * math.pi * freq * t)
                buf.append(int(max(-1, min(1, v * env * vol)) * 32000))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _make(self, name: str) -> pygame.mixer.Sound:
        if name == "click":
            return self._tone([(880, 0.04)], "square", 0.25, 40)
        if name == "correct":
            return self._tone([(660, 0.09), (880, 0.09), (1320, 0.18)], vol=0.45)
        if name == "wrong":
            return self._tone([(220, 0.12), (175, 0.22)], "square", 0.35, 5)
        if name == "coin":
            return self._tone([(1320, 0.05), (1760, 0.12)], vol=0.35, decay=10)
        if name == "crack":
            return self._tone([(0, 0.12)], "noise", 0.4, 18)
        if name == "reveal":
            return self._tone([(523, 0.1), (659, 0.1), (784, 0.1), (1047, 0.3)], vol=0.4, decay=4)
        if name == "discover":
            return self._tone([(784, 0.12), (988, 0.12), (1175, 0.12), (1568, 0.35)], vol=0.4, decay=3)
        if name == "plant":
            return self._tone([(330, 0.06), (392, 0.1)], vol=0.35, decay=12)
        return self._tone([(0, 0.03)], "noise", 0.08, 50)

    # ------------------------------------------------------------ playback
    def play(self, name: str) -> None:
        if self.ok and name in self.sounds:
            s = self.sounds[name]
            s.set_volume(self.sfx_volume)
            s.play()

    def has_word(self, word_id: str) -> bool:
        p = self.audio_dir / f"{word_id}.mp3"
        return self.ok and p.exists() and p.stat().st_size > 0

    def play_word(self, word_id: str) -> bool:
        if not self.has_word(word_id):
            return False
        return self._play_file(self.audio_dir / f"{word_id}.mp3")

    def play_bytes(self, data: bytes) -> bool:
        if not self.ok or not data:
            return False
        try:
            snd = pygame.mixer.Sound(file=io.BytesIO(data))
            snd.set_volume(self.voice_volume)
            snd.play()
            return True
        except pygame.error:
            return False

    def _play_file(self, path: Path) -> bool:
        try:
            snd = pygame.mixer.Sound(str(path))
            snd.set_volume(self.voice_volume)
            snd.play()
            return True
        except pygame.error:
            return False
