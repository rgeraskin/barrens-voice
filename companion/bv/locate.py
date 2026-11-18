"""Where the addon's strip is: at the bottom edge by default, at the top, or in a place of the
player's choosing (another addon may draw in the same corner).

The addon says where: `strip=x,y,width,height,screen width,screen height` (physical pixels) in its
settings frame - at login, every 2 minutes and before it moves the strip, on the strip where it
still is - and in its saved variables (`stripGeometry`) for a program started while the game runs.
Those the game writes only at /reload and logout, so the program keeps the last place it knew too
(`STORE`, per game: from the settings frame and from a search that found the strip) and starts with
whichever is newer (`known_place`): a restart mid-game after the strip moved finds it at once.
When that is wrong or missed and no strip is in view, the program looks for it over the whole
window, every 5 seconds: the corner where the first sync cell (purple) meets the second (green).
Knowing nothing yet (the very first game, before the addon has saved anything), the program grabs the
top rows: the bottom strip's height depends on the addon's settings, so that first time the search finds it.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .paths import DATA_DIR
from .protocol import MAX_CELL, Frame, Image, decode

Place = tuple[int, int, int, int, int, int]   # x, y, width, height, screen width, screen height
SAVED = re.compile(r'\["stripGeometry"\]\s*=\s*"([\d,]+)"')
# the place the program last knew, per game: {"forever": {"place": "x,y,w,h,sw,sh", "time": <unix time>}}
STORE = DATA_DIR / "tmp" / "strip.json"


def parse_place(value: str) -> Place | None:
    parts = value.split(",")
    if len(parts) != 6 or not all(p.isdigit() for p in parts):
        return None
    x, y, w, h, sw, sh = (int(p) for p in parts)
    if min(w, h, sw, sh) <= 0:
        return None
    return x, y, w, h, sw, sh


def region(place: Place, client_w: int, client_h: int, capture_height: int) -> tuple[int, int, int, int]:
    """The strip's rectangle in the window's client area to grab (x, y, width, height): the addon's
    physical pixels scaled to the client's (they differ only when the window is not at the game's
    resolution), and at least `capture_height` rows where the window has them below the strip."""
    x, y, w, h, sw, sh = place
    sx, sy = client_w / sw, client_h / sh
    rx = min(max(0, round(x * sx)), client_w - 1)
    ry = min(max(0, round(y * sy)), client_h - 1)
    rw = max(1, min(round(w * sx), client_w - rx))
    rh = max(1, min(max(round(h * sy), capture_height), client_h - ry))
    return rx, ry, rw, rh


def saved_place(config: dict) -> Place | None:
    """The strip's place as the addon last saved it (written at /reload and logout)."""
    from .dictionary import find_saved
    found = _saved(find_saved(config))
    return found[0] if found else None


def _saved(path: Path | None) -> tuple[Place, float] | None:
    """The saved variables' place and when the game wrote them."""
    try:
        if path is None:
            return None
        match = SAVED.search(path.read_text(encoding="utf-8", errors="replace"))
        place = parse_place(match.group(1)) if match else None
        return (place, path.stat().st_mtime) if place else None
    except OSError:
        return None


def _store(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remembered(path: Path, game: str) -> tuple[Place, float] | None:
    """The place the program last knew for this game, and when it learnt it; None if none."""
    entry = _store(path).get(game)
    if not isinstance(entry, dict) or not isinstance(entry.get("time"), (int, float)):
        return None
    place = parse_place(str(entry.get("place", "")))
    return (place, float(entry["time"])) if place else None


def remember(path: Path, game: str, place: Place, now: float | None = None) -> bool:
    """Keep `place` as the strip's last known place for `game` (written only when it changed; a file
    that cannot be written is left as it is). True if written."""
    known = remembered(path, game)
    if known and known[0] == place:
        return False
    data = _store(path)
    data[game] = {"place": ",".join(str(v) for v in place), "time": time.time() if now is None else now}
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def known_place(config: dict, store: Path | None = None) -> tuple[Place, str] | None:
    """Where the strip should be at start: the addon's saved place or the program's own, whichever is
    newer, with where it came from ("saved" or "own"); None when neither is known. The saved variables
    and the store are this game's (`game` in config.json): the other game's strip may be elsewhere."""
    from .dictionary import find_saved, game_of
    saved = _saved(find_saved(config))
    own = remembered(STORE if store is None else store, game_of(config))
    if own and (saved is None or own[1] > saved[1]):
        return own[0], "own"
    return (saved[0], "saved") if saved else None


def find(raw: bytes, width: int, height: int, width_hint: int | None = None, capture_height: int = 16,
         limit: int = 2000) -> tuple[int, int, int, int, Frame] | None:
    """The strip anywhere in a BGRA grab of the window's client area: (x, y, width, height to grab,
    the frame on it), or None. Its cells start at the left edge of the strip or at the right; a
    width the addon gave (`width_hint`) keeps rows of a long line apart, else the strip is taken to
    run to the window's edge."""
    import numpy as np

    px = np.frombuffer(raw, np.uint8).reshape(height, width, 4)
    b, g, r = (px[..., k].astype(np.int16) for k in range(3))
    sync = (r > g + 4) & (b > g + 4) & (r < 160) & (b < 160)      # the first sync cell: dark purple
    green = (g > r + 4) & (g > b + 4) & (g < 160)                  # the second: dark green
    light = r + g + b
    grey = (abs(r - g) <= 6) & (abs(g - b) <= 6)

    def shifted(mask, dx):                                         # mask[y, x + dx] at [y, x]
        if dx == 0:
            return mask
        out = np.zeros_like(mask)
        if dx > 0:
            out[:, :-dx] = mask[:, dx:]
        else:
            out[:, -dx:] = mask[:, :dx]
        return out

    hits: list[tuple[int, int, int]] = []
    for step in (1, -1):                                           # cells from the left, from the right
        near = np.zeros_like(sync)                                 # purple, then green within a cell
        for c in range(1, MAX_CELL + 1):
            near |= shifted(green, step * c) & shifted(sync, step * (c - 1))
        ys, xs = np.nonzero(sync & near)
        good: list[tuple[int, int]] = []
        for c in range(1, MAX_CELL + 1):
            # The whole header of a frame: the sync cell exactly c pixels (none before it), the green
            # one c pixels, then four calibration cells, grey and even, each lighter than the one
            # before - a picture hardly has all of it. One condition at a time, on the candidates
            # still left: most fall at the first ones. A condition: (mask, offset, wanted) - the
            # pixel `offset` cells along from the candidate is (or is not) in `mask`.
            last = xs + step * (6 * c - 1)
            keep = (last >= 0) & (last < width) & (xs - step >= 0) & (xs - step < width)
            edge = (last >= 0) & (last < width) & ~((xs - step >= 0) & (xs - step < width))
            conditions = [(sync, -1, False)]
            conditions += [(sync, k, True) for k in range(c)] + [(sync, c, False)]
            conditions += [(green, c + k, True) for k in range(c)] + [(green, 2 * c, False)]
            conditions += [(grey, 2 * c + i * c + k, True) for i in range(4) for k in range(c)]
            cy, cx = ys[keep | edge], xs[keep | edge]
            at_edge = edge[keep | edge]
            for mask, offset, wanted in conditions:
                if len(cy) == 0:
                    break
                hit = mask[cy, np.clip(cx + step * offset, 0, width - 1)] == wanted
                if offset < 0:
                    hit |= at_edge                                 # nothing before the window's edge
                cy, cx, at_edge = cy[hit], cx[hit], at_edge[hit]
            for i in range(4 * (c > 1)):                           # each calibration cell even
                if len(cy) == 0:
                    break
                base = light[cy, cx + step * (2 * c + i * c)]
                hit = np.ones(len(cy), bool)
                for k in range(1, c):
                    hit &= light[cy, cx + step * (2 * c + i * c + k)] == base
                cy, cx = cy[hit], cx[hit]
            if len(cy):
                levels = [light[cy, cx + step * (2 * c + i * c)] for i in range(4)]
                hit = (levels[1] > levels[0] + 6) & (levels[2] > levels[1] + 6) & (levels[3] > levels[2] + 6)
                good += list(zip(cy[hit].tolist(), cx[hit].tolist()))
        hits += [(y, x, step) for y, x in sorted(good)[:limit]]
    for y, x, step in hits:
        rh = min(capture_height, height - y)
        if step == 1:
            w = min(width_hint or width - x, width - x)
            x0 = x
        else:
            w = min(width_hint or x + 1, x + 1)
            x0 = x + 1 - w
        crop = np.ascontiguousarray(px[y:y + rh, x0:x0 + w])
        frame = decode(Image(crop.tobytes(), w, rh))
        if frame is not None:
            return x0, y, w, rh, frame
    return None
