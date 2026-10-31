import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def pg():
    pygame.init()
    pygame.display.set_mode((480, 270))
    yield
