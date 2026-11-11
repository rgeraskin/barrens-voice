"""Make companion/wcv/game_voices.json: which game files hold each race voice (`mise run voices-table`).

The companion builds its F5 voice bank from recordings in the game client itself (read-only, on
the player's machine). It needs to know which files to read: their FileDataIDs, which are stable
across game builds. They come from the community listfile (wowdev/wow-listfile), downloaded here
into tools/.cache once; only the numbers and a tag per file go into the table - no game data.

Voices per race and sex:
  "<race>-<sex>"         the player character's voice: its error messages ("Недостаточно маны")
                         and calm emotes (hello, thank you, yes, no, ...);
  "<race>-<sex>/<type>"  each NPC voice type of the race ("standard", "guard", "warrior", ...):
                         greetings, farewells, vendor lines, and the annoyed ones.
Each file gets a priority: 1 calm speech, 2 emotes, 3 jokes and annoyed lines (a last resort for a
reference clip). Battle cries and other shouts are left out.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".cache" / "community-listfile.csv"
URL = "https://github.com/wowdev/wow-listfile/releases/latest/download/community-listfile.csv"
OUT = ROOT / "companion" / "wcv" / "game_voices.json"

# The playable races of WoW Forever: the race as the bank names it -> its folder in sound/character
# and its prefix in sound/creature (the Forsaken's NPCs are "undead...npc").
RACES = {
    "human": ("human", "human"), "orc": ("orc", "orc"), "dwarf": ("dwarf", "dwarf"),
    "nightelf": ("nightelf", "nightelf"), "scourge": ("scourge", "undead"), "tauren": ("tauren", "tauren"),
    "gnome": ("gnome", "gnome"), "troll": ("troll", "troll"),
}
CALM_EMOTES = {"hello", "goodbye", "thankyou", "yourewelcome", "yes", "no", "followme", "waithere",
               "congratulations", "outofmana", "healme", "train", "nevermind"}
JOKES = {"flirt", "pissed", "silly", "joke"}
NPC_TAGS = {"greeting": 1, "farewell": 1, "vendor": 1, "pissed": 3}


def listfile() -> Path:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL} ...", flush=True)
        urllib.request.urlretrieve(URL, CACHE)
    return CACHE


def sex_of(name: str) -> str | None:
    return "female" if "female" in name else "male" if "male" in name else None


def classify(path: str):
    """(voice id, tag, priority) for a file of a race voice, else None."""
    folder, _, name = path.rpartition("/")
    if not name.endswith(".ogg"):
        return None
    stem = re.sub(r"\d+$", "", name[:-4])
    for race, (char_dir, npc_prefix) in RACES.items():
        if folder.startswith(f"sound/character/{char_dir}/"):
            sub = folder.rsplit("/", 1)[1]
            sex = sex_of(sub)
            if not sex:
                return None
            if sub.endswith("errormessages"):
                return f"{race}-{sex}", "error", 1
            if sub == f"{char_dir}vocal{sex}":
                tag = re.sub(r"^(?:vo_pc)?[a-z]*?(?:female|male)", "", stem)   # "undeadmalehello" too
                if tag in CALM_EMOTES:
                    return f"{race}-{sex}", tag, 2
                if tag in JOKES:
                    return f"{race}-{sex}", tag, 3
            return None
        m = re.fullmatch(rf"sound/creature/{npc_prefix}(female|male)([a-z]+)npc", folder)
        if m:
            sex, kind = m.groups()
            found = re.search(r"(greeting|farewell|vendor|pissed)$", stem)   # names vary: "...npcgreeting", "...greeting"
            tag = found.group(1) if found else ""
            if tag in NPC_TAGS:
                return f"{race}-{sex}/{kind}", tag, NPC_TAGS[tag]
            return None
    return None


def main() -> int:
    voices: dict[str, dict] = {}
    for line in listfile().open(encoding="utf-8", errors="replace"):
        fdid, _, path = line.rstrip("\n").partition(";")
        found = classify(path.lower())
        if not found:
            continue
        voice, tag, priority = found
        race, sex = voice.split("/")[0].split("-")
        entry = voices.setdefault(voice, {"race": race, "sex": sex, "files": []})
        entry["files"].append([int(fdid), tag, priority])
    for entry in voices.values():
        entry["files"].sort()
    table = {"source": "wowdev/wow-listfile (FileDataIDs only)", "voices": dict(sorted(voices.items()))}
    OUT.write_text(json.dumps(table, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    for voice, entry in table["voices"].items():
        counts = {p: sum(1 for f in entry["files"] if f[2] == p) for p in (1, 2, 3)}
        print(f"{voice:28} {len(entry['files']):4} files  calm {counts[1]:3}  emotes {counts[2]:3}  jokes {counts[3]:3}")
    print(f"{len(voices)} voices -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
