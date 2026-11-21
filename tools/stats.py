"""How many people use Barrens Voice, from what GitHub counts by itself: the downloads of each release's files
(`mise run stats`). No telemetry of our own: the program reports nothing about its users.
- BarrensVoice-Setup.exe: new installs (the installer downloaded);
- barrens-voice-<version>.zip: installs that updated to this version - the nearest to how many use it;
- manifest.json: update checks (at every start and hourly), activity rather than people.
The dictionary online comes from raw.githubusercontent.com, which counts nothing. CurseForge and Wago count the
addon's downloads in their authors' dashboards.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion"))
from bv.update import AGENT, RELEASES  # noqa: E402 - the same request the updater makes

SETUP = "BarrensVoice-Setup.exe"
MANIFEST = "manifest.json"


def row(release: dict) -> dict:
    """One release's counts: its tag, date, and the downloads of the installer, the archive and the manifest."""
    counts = {a.get("name"): a.get("download_count", 0) for a in release.get("assets", []) if isinstance(a, dict)}
    archive = sum(n for name, n in counts.items() if isinstance(name, str) and name.startswith("barrens-voice-")
                  and name.endswith(".zip"))
    return {"tag": release.get("tag_name", "?"), "date": (release.get("published_at") or "")[:10],
            "test": bool(release.get("prerelease")), "setup": counts.get(SETUP, 0), "updated": archive,
            "checks": counts.get(MANIFEST, 0)}


def report(releases: list[dict]) -> str:
    """The table, newest first, then the totals: every release, and the stable ones alone."""
    rows = [row(r) for r in releases if isinstance(r, dict) and not r.get("draft")]
    lines = [f"{'release':<16} {'date':<10} {'installer':>9} {'updated':>7} {'checks':>6}"]
    for r in rows:
        lines.append(f"{r['tag']:<16} {r['date']:<10} {r['setup']:>9} {r['updated']:>7} {r['checks']:>6}")
    for name, part in (("total", rows), ("stable", [r for r in rows if not r["test"]])):
        lines.append(f"{name:<27} {sum(r['setup'] for r in part):>9} {sum(r['updated'] for r in part):>7} "
                     f"{sum(r['checks'] for r in part):>6}")
    return "\n".join(lines)


def main() -> int:
    headers = {"User-Agent": AGENT}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(RELEASES, headers=headers), timeout=15) as response:  # noqa: S310
        print(report(json.loads(response.read())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
