"""«Что нового»: news.toml, the players' news of every release.

news.toml (the repository's root) is the one source: an entry per release of the program, keyed by the program's
version (pyproject.toml's), newest first; Russian, «ты», for players. `problems` says what is wrong with it (the
tests check the file by it), `visible` which entries a version shows.
"""
from __future__ import annotations

import re
import tomllib
from datetime import datetime
from pathlib import Path

SOURCE = "news.toml"
KINDS = ("big", "small")
FIELDS = {"version", "date", "kind", "title", "summary", "items"}
VERSION = re.compile(r"\d+\.\d+\.\d+(?:b\d+)?")
DATE = re.compile(r"\d\d\.\d\d\.\d{4}")
MAX_SUMMARY = 100             # letters: one line in the chat after «обновление 0.4.0 beta 16 — »
MAX_ITEMS = 10
# not in the game's font (an arrow, an en dash), or the game's markup (|c, |H, |T...)
FORBIDDEN = ("→", "–", "|")
YOU = ("вы", "вас", "вам", "вами", "ваш", "ваша", "ваше", "ваши", "вашего", "вашей", "вашу", "ваших", "вашим")


def version_key(version: str) -> tuple:
    """Versions in order, a test build before its release (bv.install's order)."""
    from .install import version_key as key
    return key(version)


def release_of(version: str) -> str:
    """The release a version leads to: "0.4.0b5" -> "0.4.0"."""
    return re.sub(r"b\d+$", "", version)


def load(path: Path) -> list[dict]:
    """The entries of a news.toml, as written (newest first). Raises OSError, ValueError (TOML) or TypeError (no
    list of tables under `entry`)."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("entry", [])
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise TypeError(f"{SOURCE}: [[entry]] tables expected")
    return entries


def _texts(entry: dict) -> list[str]:
    items = entry.get("items")
    return [t for t in [entry.get("title"), entry.get("summary"), *(items if isinstance(items, list) else [])]
            if isinstance(t, str)]


def entry_problems(entry: dict) -> list[str]:
    """What is wrong with one entry, in words; [] when it is fine."""
    name = entry.get("version") if isinstance(entry.get("version"), str) else "?"
    out = []
    unknown = sorted(set(entry) - FIELDS)
    if unknown:
        out.append(f"{name}: unknown fields {unknown}")
    if not (isinstance(entry.get("version"), str) and VERSION.fullmatch(entry["version"])):
        out.append(f"{name}: version must be like \"0.4.1\" (or a test build's \"0.4.1b3\")")
    if "date" in entry:
        date = entry["date"]
        try:
            if not (isinstance(date, str) and DATE.fullmatch(date)):
                raise ValueError
            datetime.strptime(date, "%d.%m.%Y")
        except ValueError:
            out.append(f"{name}: date must be a real day as \"DD.MM.YYYY\", not {date!r}")
    if entry.get("kind") not in KINDS:
        out.append(f"{name}: kind must be \"big\" or \"small\"")
    for field in ("title", "summary"):
        if not (isinstance(entry.get(field), str) and entry[field].strip()):
            out.append(f"{name}: {field} must be a text")
    items = entry.get("items")
    if not (isinstance(items, list) and 0 < len(items) <= MAX_ITEMS
            and all(isinstance(i, str) and i.strip() for i in items)):
        out.append(f"{name}: items must be 1 to {MAX_ITEMS} texts")
    summary = entry.get("summary")
    if isinstance(summary, str):
        if len(summary) > MAX_SUMMARY:
            out.append(f"{name}: the summary is one short line ({len(summary)} letters, at most {MAX_SUMMARY})")
        if summary.rstrip().endswith((".", "!")):
            out.append(f"{name}: no full stop after the summary (the chat line adds one)")
    for text in _texts(entry):
        if "\n" in text or "\r" in text:
            out.append(f"{name}: one line each: {text!r}")
        for bad in FORBIDDEN:
            if bad in text:
                out.append(f"{name}: no {bad!r} (the game's font or markup): {text}")
        words = re.findall(r"[а-яё]+", text.lower())
        if any(w in YOU for w in words):
            out.append(f"{name}: «ты», not «вы»: {text}")
    return out


def problems(entries: list[dict]) -> list[str]:
    """What is wrong with news.toml's entries, in words; [] when it is fine: each entry's own, one entry a version,
    newest first, and only the newest release (the one in work, and its test builds) without a date."""
    out = []
    for e in entries:
        out += entry_problems(e)
    if out:
        return out
    versions = [e["version"] for e in entries]
    if len(set(versions)) != len(versions):
        out.append("one entry a version: " + ", ".join(sorted({v for v in versions if versions.count(v) > 1})))
    if versions != sorted(versions, key=version_key, reverse=True):
        out.append("newest first: " + ", ".join(versions))
    newest = release_of(versions[0]) if versions else None
    for e in entries:
        if "date" not in e and release_of(e["version"]) != newest:
            out.append(f"{e['version']}: released, so it needs its date")
    return out


def visible(entries: list[dict], version: str) -> list[dict]:
    """The entries a version shows, newest first (News.lua's N.Visible, the same rule): its release's and every older
    one - a test build has its release's entry from its first build on - and a test build's own from that build on."""
    if not VERSION.fullmatch(version or ""):
        return []
    release = version_key(release_of(version))
    own = version_key(version)
    out = [e for e in entries if version_key(e["version"]) <= (own if "b" in e["version"] else release)]
    return sorted(out, key=lambda e: version_key(e["version"]), reverse=True)
