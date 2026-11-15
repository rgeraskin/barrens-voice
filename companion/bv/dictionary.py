"""The addon's slang dictionary, applied here: whole words, phrases and stems ("дамагер*"), and the
regular expressions ("~pattern=replacement").

The default dictionary is read straight from the addon's Dictionary.lua (its `D.DEFAULT = [[...]]`)
and read again as soon as that file changes - so a change to the default works at once, with no
/reload (the client reads an addon's files only when it loads it). The player's own edits - their
layer over the default: entries changed or added, and default entries deleted - come from the addon
over the strip (kind "dict", in parts), and until then from its saved variables.
"""
from __future__ import annotations

import re
from pathlib import Path

SAVED = "BarrensVoice.lua"
# The player's layer the addon keeps for us in its saved variables (as it sends it over the strip).
LUA_USER = re.compile(r'\["dictionaryUser"\]\s*=\s*"((?:[^"\\]|\\.)*)"', re.S)
DEFAULT_BLOCK = re.compile(r"D\.DEFAULT\s*=\s*\[\[(.*?)\]\]", re.S)
WORD = re.compile(r"[^\W_]+")
LUA_ESCAPE = re.compile(r'\\(\d{1,3}|.)', re.S)
SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def unescape(body: str) -> str:
    """A Lua string literal's body as text (the game writes \\n, \\", \\\\ and \\ddd byte escapes)."""
    raw = bytearray()
    pos = 0
    for m in LUA_ESCAPE.finditer(body):
        raw += body[pos:m.start()].encode("utf-8")
        code = m.group(1)
        if code.isdigit():
            raw.append(int(code) & 0xFF)
        else:
            raw += SIMPLE.get(code, code).encode("utf-8")
        pos = m.end()
    raw += body[pos:].encode("utf-8")
    return raw.decode("utf-8", "replace")


GAMES = {"forever": "_forever_", "retail": "_retail_"}


def game_of(config: dict) -> str:
    """The game the companion works with: "forever" (default) or "retail" (config.json `game`, or
    the --retail / --forever switch)."""
    game = str(config.get("game") or "forever").lower()
    return game if game in GAMES else "forever"


def wow_roots(config: dict) -> list[Path]:
    """The game folder (_forever_ or _retail_, as `game` says) of the configured and the usual WoW
    installs - only that game's: with both installed, the other one's addon and saved variables must
    not be taken for this one's."""
    flavor = GAMES[game_of(config)]
    roots = [Path(config["wow_dir"])] if config.get("wow_dir") else []
    for drive in "CDEFGH":
        for base in (f"{drive}:/World of Warcraft", f"{drive}:/Games/World of Warcraft",
                     f"{drive}:/Program Files (x86)/World of Warcraft"):
            roots.append(Path(base) / flavor)
    return roots


def find_saved(config: dict) -> Path | None:
    """The newest BarrensVoice.lua under WTF/Account/*/SavedVariables of the WoW installs we know."""
    found = []
    for root in wow_roots(config):
        account = root / "WTF" / "Account"
        if account.is_dir():
            found += [p for p in account.glob(f"*/SavedVariables/{SAVED}") if p.is_file()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def saved_voices(config: dict) -> str | None:
    """The voices last chosen in the addon ("f5" or "sapi") as its saved variables keep them; None
    when there are none yet."""
    path = find_saved(config)
    if path is None:
        return None
    match = re.search(r'\["voices"\]\s*=\s*"(\w+)"', path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None


PLURAL = re.compile(r"(\d+)(\s*)\[([^\[\]|]+)\|([^\[\]|]+)\|([^\[\]|]+)\]")


def plural_form(n: int, one: str, few: str, many: str) -> str:
    """Russian noun form after a number: 1, 21 - one; 2-4, 22-24 - few; 0, 5-20, 25-30 - many."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


ORDINAL = re.compile(r"<(\d{1,4})>")


def ordinals(text: str) -> str:
    """"<60>" -> "шестидесятый" (num2words; the declension after a preposition comes later)."""
    try:
        from num2words import num2words
    except ImportError:
        return ORDINAL.sub(r"\1", text)
    return ORDINAL.sub(lambda m: num2words(int(m.group(1)), lang="ru", to="ordinal"), text)


def plurals(text: str) -> str:
    """"5 [дамагер|дамагера|дамагеров]" -> "5 дамагеров" (written by the dictionary's regexes)."""
    return PLURAL.sub(lambda m: m.group(1) + (m.group(2) or " ")
                      + plural_form(int(m.group(1)), m.group(3), m.group(4), m.group(5)), text)


def parse(dictionary: str, log) -> list[tuple[re.Pattern, str]]:
    rules = []
    for line in dictionary.splitlines():
        line = line.strip()
        if not line.startswith("~") or "=" not in line:
            continue
        pattern, replacement = line[1:].rsplit("=", 1)
        try:
            rules.append((re.compile(pattern.strip(), re.IGNORECASE), replacement.strip()))
        except re.error as e:
            log(f"словарь: регулярка «{pattern}» с ошибкой: {e}")
    return rules


def norm(word: str) -> str:
    return word.lower().replace("ё", "е")


def key_of(line: str) -> str | None:
    """The identity of a dictionary line, as the addon's D.KeyOf: its normalised words ("*" for a
    stem), or for a regex its pattern (all before the last "="); None for a line that is no entry."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("~"):
        return line.rsplit("=", 1)[0].rstrip() if "=" in line else line
    if "=" not in line:
        return None
    key = line.split("=", 1)[0].strip()
    star = key.endswith("*")
    words = [norm(w) for w in WORD.findall(key[:-1] if star else key)]
    return " ".join(words) + ("*" if star else "") if words else None


def merged(default: str, user: str) -> list[str]:
    """The entry lines of the player's dictionary: the default's, with the player's layer on top -
    its lines replace the default's of the same key or add new ones, and a line "!<default line>"
    deletes that default entry."""
    lines: dict[str, list[str]] = {}
    for line in default.splitlines():
        key = key_of(line)
        if key:
            lines.setdefault(key, []).append(line.strip())
    own: dict[str, list[str]] = {}
    for line in user.splitlines():
        line = line.strip()
        if line.startswith("!"):
            lines.pop(key_of(line[1:]) or "", None)
            continue
        key = key_of(line)
        if key:
            own.setdefault(key, []).append(line)
    lines.update(own)
    return [line for group in lines.values() for line in group]


class Dictionary:
    def __init__(self, config: dict, log, addon: Path | None = None):
        self.config, self.log = config, log
        self.addon = addon                         # the addon's folder (found by the caller)
        self.default, self.default_stamp = "", None
        self.user, self.user_path, self.user_stamp = "", None, None
        self.rules: list[tuple[re.Pattern, str]] = []
        self.exact: dict[str, str] = {}
        self.stems: list[tuple[str, str]] = []
        self.phrases: dict[str, list[tuple[list[str], bool, str]]] = {}
        self.from_addon: str | None = None        # id of the layer the addon sent over the strip
        self.parts: dict[str, dict[int, str]] = {}

    # --- sources -----------------------------------------------------------------------------

    def receive(self, options: dict, text: str) -> None:
        """A part of the player's layer sent by the addon ("id=..;part=i;of=n"); used once complete.
        From then on the saved variables (stale until the next /reload) are not read."""
        set_id, part, total = options.get("id", ""), options.get("part", ""), options.get("of", "")
        if not (set_id and part.isdigit() and total.isdigit()):
            return
        if set_id == self.from_addon:
            return                                # resent unchanged
        parts = self.parts.setdefault(set_id, {})
        parts[int(part)] = text
        if len(parts) < int(total):
            return
        joined = "\n".join(parts[i] for i in sorted(parts))
        self.parts = {}
        self.from_addon = set_id
        self.user = "" if joined == "-" else joined
        self._rebuild("правки из игры")

    def refresh(self) -> None:
        """Re-read what changed (cheap: stat calls): the addon's Dictionary.lua - the default - and,
        until the addon has sent the player's layer, its saved variables."""
        changed = []
        lua = self.addon / "Dictionary.lua" if self.addon else None
        if lua and lua.exists():
            stamp = lua.stat().st_mtime
            if stamp != self.default_stamp:
                match = DEFAULT_BLOCK.search(lua.read_text(encoding="utf-8", errors="replace"))
                if match:
                    self.default, self.default_stamp = match.group(1), stamp
                    changed.append("стандартный")
        if not self.from_addon:
            path = self.user_path if self.user_path and self.user_path.exists() else find_saved(self.config)
            if path is not None:
                stamp = path.stat().st_mtime
                if path != self.user_path or stamp != self.user_stamp:
                    self.user_path, self.user_stamp = path, stamp
                    match = LUA_USER.search(path.read_text(encoding="utf-8", errors="replace"))
                    user = unescape(match.group(1)) if match else ""
                    if user in ("-",):
                        user = ""
                    if user != self.user:
                        self.user = user
                        changed.append("правки")
        if changed:
            self._rebuild(" и ".join(changed))

    def _rebuild(self, why: str) -> None:
        lines = merged(self.default, self.user)
        self.rules = parse("\n".join(line for line in lines if line.startswith("~")), self.log)
        self.exact, self.stems, self.phrases = {}, [], {}
        for line in lines:
            if line.startswith("~") or "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            star = key.endswith("*")
            words = [norm(w) for w in WORD.findall(key[:-1] if star else key)]
            if not words:
                continue
            if len(words) == 1 and not star:
                self.exact[words[0]] = value
            elif len(words) == 1:
                self.stems.append((words[0], value))
            else:
                self.phrases.setdefault(words[0], []).append((words, star, value))
        for group in self.phrases.values():
            group.sort(key=lambda e: -len(e[0]))
        self.stems.sort(key=lambda e: -len(e[0]))
        self.log(f"словарь ({why}): записей {len(self.exact) + len(self.stems) + sum(map(len, self.phrases.values()))}, "
                 f"регулярок {len(self.rules)}")

    # --- applying ----------------------------------------------------------------------------

    def apply_words(self, text: str) -> str:
        """`text` with the dictionary's words, phrases (longest first) and stems replaced. A
        replacement is marked (\\x02...\\x03) to be declined after a preposition - unless it took
        the ending typed in chat (a stem, a phrase ending in "*"): its case is right already."""
        tokens = list(WORD.finditer(text))
        out, last, i = [], 0, 0
        while i < len(tokens):
            t = tokens[i]
            word = norm(t.group())
            value = span = None
            took_ending = False
            for words, star, entry in self.phrases.get(word, []):
                suffix = self._match(words, star, tokens, i)
                if suffix is not None:
                    value, span, took_ending = entry.replace("*", suffix), len(words), star
                    break
            if value is None and word in self.exact:
                value, span = self.exact[word], 1
            if value is None:
                for stem, entry in self.stems:
                    if word.startswith(stem):
                        value, span, took_ending = entry.replace("*", t.group()[len(stem):]), 1, True
                        break
            if value is None:
                i += 1
                continue
            out.append(text[last:t.start()])
            out.append("" if value == "" else value if took_ending else "\x02" + value + "\x03")
            last = tokens[i + span - 1].end()
            i += span
        out.append(text[last:])
        return "".join(out)

    @staticmethod
    def _match(words, star, tokens, i):
        """The suffix of a starred last word ("" if none) when `words` match the tokens from `i`."""
        if i + len(words) > len(tokens):
            return None
        for k, w in enumerate(words):
            token = tokens[i + k].group()
            if k == len(words) - 1 and star:
                if not norm(token).startswith(w):
                    return None
                return token[len(w):]
            if norm(token) != w:
                return None
        return ""

    def apply(self, text: str, mark: bool = False) -> str:
        """`text` through the regexes; with `mark`, each replacement wrapped in \\x02...\\x03 so it
        can be declined after a preposition, like the addon's replacements."""
        for pattern, replacement in self.rules:
            try:
                if mark:
                    text = pattern.sub(lambda m, r=replacement: "\x02" + m.expand(r) + "\x03", text)
                else:
                    text = pattern.sub(replacement, text)
            except (re.error, IndexError) as e:
                self.log(f"словарь: замена «{replacement}»: {e}")
        return plurals(ordinals(text))
