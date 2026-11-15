"""Make companion/wcv/game_voices.json: which game files hold each race voice (`mise run voices-table`).

The companion builds its F5 voice bank from recordings in the game client itself (read-only, on
the player's machine). It needs to know which files to read: their FileDataIDs, which are stable
across game builds. They come from the community listfile (wowdev/wow-listfile), downloaded here
into tools/.cache once; only the numbers and a tag per file go into the table - no game data.

Voices per race and sex (Skyborne, Forever's own race, has only the character's voice):
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
# Skyborne, Forever's own race (both factions): one folder per sex, sound/character/skyborne_elf_<sex>,
# files vo_skyborne_elf_<sex>_<tag>_<id>.ogg; no NPC voices. Its error messages (anything not below)
# are calm speech; these are emotes and jokes, and the rest - shouts, sounds - is left out.
SKY_EMOTES = {"hello", "bye", "thank", "yw", "nod", "no", "follow", "wait", "welcome", "congratulate",
              "healme", "train", "apologize"}
SKY_JOKES = {"flirt", "joke"}
SKY_OUT = {"roar", "cackle", "kiss", "chicken", "applaud", "violin", "charge", "cheer", "flee", "openfire", "taunt",
           "threaten", "attackmytarget", "incoming", "whoa", "oops", "sigh", "rasp", "bored", "beg", "cry", "yawn",
           "helpme"}


# The races retail added (sound/character): their player voices only, no NPC voices (their folders
# are named by zone and role, not by race and sex). Four ways the files are named:
# - classic style, one folder per race: bloodelf/bloodelffemale_err_nomana01.ogg, draenei/...;
# - "pc" folders: pcgoblinmale/vo_pcgoblinmale_errnomana01.ogg (pcgilnean: a worgen in human form);
# - tagged like Skyborne: dracthyr_visage_male/vo_dracthyr_visage_male_nomana_4737525.ogg;
# - numbered, allied races and later: pc_-_void_elf_male/vo_735_pc_-_void_elf_male_01_m.ogg - which
#   number is which line is not known, so all are emotes (2) and Whisper's transcript decides.
OLD_STYLE = {"bloodelf": "bloodelf", "draenei": "draenei"}
PC_STYLE = {"goblin": ("goblin", ""), "worgen": ("worgen", ""), "gilnean": ("worgen", "/human"),
            "pandaren": ("pandaren", "")}
TAGGED = {"dracthyr_visage": ("dracthyr", ""), "dracthyr_dragonkin": ("dracthyr", "/dragon")}
NUMBERED = [  # a folder's words -> the race, the voice's kind
    ("void_elf", "voidelf", ""), ("nightborne_elf", "nightborne", ""),
    ("highmountain_tauren", "highmountaintauren", ""), ("lightforged_draenei", "lightforgeddraenei", ""),
    ("dark_iron_dwarf", "darkirondwarf", ""), ("zandalari_troll", "zandalaritroll", ""),
    ("maghar_orc", "magharorc", ""), ("kul_tiran_human", "kultiran", ""), ("mechagnome", "mechagnome", ""),
    ("vulpera", "vulpera", ""), ("earthen", "earthendwarf", ""), ("haranir", "haranir", ""),
    ("dracthyr_female_visage", "dracthyr", ""), ("dracthyr_male_visage", "dracthyr", ""),
    ("dracthyr_female_dragon", "dracthyr", "/dragon"), ("dracthyr_male_dragon", "dracthyr", "/dragon"),
]


def retail(folder: str, stem: str):
    """classify() for the races retail added."""
    sub = folder.removeprefix("sound/character/")
    if "/" in sub:
        return None
    if sub in OLD_STYLE:
        found = re.fullmatch(rf"{sub}(female|male)_?(.+?)_?", stem)
        if not found:
            return None
        sex, tag = found.groups()
        voice = f"{OLD_STYLE[sub]}-{sex}"
        if tag.startswith("err_"):
            return voice, "error", 1
        tag = tag.replace("_", "")
        return (voice, tag, 2) if tag in CALM_EMOTES else (voice, tag, 3) if tag in JOKES else None
    found = re.fullmatch(r"pc([a-z]+?)(female|male)", sub)
    if found and found.group(1) in PC_STYLE:
        race, kind = PC_STYLE[found.group(1)]
        sex = found.group(2)
        tag = stem.removeprefix(f"vo_{sub}_")
        if tag == stem:
            return None
        voice = f"{race}-{sex}{kind}"
        if tag.startswith("err"):
            return voice, "error", 1
        return (voice, tag, 2) if tag in CALM_EMOTES else (voice, tag, 3) if tag in JOKES else None
    found = re.fullmatch(r"([a-z_]+)_(female|male)", sub)
    if found and found.group(1) in TAGGED:
        race, kind = TAGGED[found.group(1)]
        sex = found.group(2)
        tag = re.fullmatch(rf"vo_{sub}_(.+?)_?", stem)
        tag = tag.group(1) if tag else ""
        voice = f"{race}-{sex}{kind}"
        if not tag or tag in SKY_OUT or tag in {"chuckle", "alliance", "horde", "laugh", "silly"}:
            return None
        if tag in SKY_EMOTES:
            return voice, tag, 2
        if tag in SKY_JOKES:
            return voice, tag, 3
        return voice, "error", 1
    if re.fullmatch(r"vo_\d+_pc_.+_(female|male)(_[a-z]+)?_\d+_[mf]", stem):   # vo_735_pc_-_void_elf_male_01_m
        sex = "female" if "female" in sub else "male"
        for words, race, kind in NUMBERED:
            if words in sub:
                return f"{race}-{sex}{kind}", "line", 2
    return None


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
    sky = re.fullmatch(r"sound/character/skyborne_elf_(female|male)", folder)
    if sky:
        sex = sky.group(1)
        found = re.fullmatch(rf"vo_skyborne_elf_{sex}_(.+?)_?", stem)
        tag = found.group(1) if found else ""
        if not tag or tag in SKY_OUT:
            return None
        if tag in SKY_EMOTES:
            return f"skyborne-{sex}", tag, 2
        if tag in SKY_JOKES:
            return f"skyborne-{sex}", tag, 3
        return f"skyborne-{sex}", "error", 1
    found = retail(folder, stem)
    if found:
        return found
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
