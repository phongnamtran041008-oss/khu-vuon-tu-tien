"""Telling players a newer game is out. Every build of the game knows the GitHub repository it
came from (`update_repo` in config.json); at start it asks GitHub Releases for the newest
release once, on its own thread, and quietly gives up without Internet — LAN worlds must
still play offline, so a failed check never shows the "mất kết nối" bar.

Releasing an update = pushing a tag (git tag v1.2.0 && git push origin v1.2.0): the
release-exe workflow builds the zip and publishes the release this checks.
"""
from __future__ import annotations

import threading

import httpx

from ..config import GAME_VERSION, version_tuple

API = "https://api.github.com/repos/{repo}/releases/latest"


def parse_release(data: dict, repo: str, current: str = GAME_VERSION) -> dict | None:
    """GitHub's latest-release JSON -> {version, url, page, notes} when newer than `current`."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    if not tag or version_tuple(tag) <= version_tuple(current):
        return None
    page = str(data.get("html_url") or f"https://github.com/{repo}/releases/latest")
    zips = [a for a in data.get("assets") or [] if str(a.get("name", "")).lower().endswith(".zip")]
    url = str(zips[0].get("browser_download_url") or page) if zips else page
    notes = " ".join(str(data.get("body") or "").split())
    return {"version": tag.lstrip("vV"), "url": url, "page": page,
            "notes": notes[:160] + ("..." if len(notes) > 160 else "")}


class UpdateChecker:
    def __init__(self, repo: str, current: str = GAME_VERSION, api: str | None = None):
        self.repo, self.current, self.api = repo.strip().strip("/"), current, api or API
        self.done = False
        self.result: dict | None = None
        threading.Thread(target=self._run, daemon=True, name="update-check").start()

    def _run(self) -> None:
        try:
            r = httpx.get(self.api.format(repo=self.repo), timeout=8, follow_redirects=True,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": f"VuonChu/{self.current}"})
            if r.status_code == 200:
                self.result = parse_release(r.json(), self.repo, self.current)
        except (httpx.HTTPError, OSError, ValueError):
            pass          # no Internet, GitHub down, no release yet: nothing to say
        self.done = True
