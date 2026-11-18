"""dist/dictionary.json: the addon's default dictionary for the dictionary online (`mise run dictionary`).

CI runs it after the tests pass on master, signs it (tools/sign.py) and puts both files in the branch
`dictionary`, where companions fetch them (bv/online_dictionary.py). `revision` is the time of the last
commit that changed Dictionary.lua - the same number tools/release.py writes into a release's Dictionary.lua
(D.REVISION), so the newer of the two is the default; the file only changes when the dictionary does.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
LUA = ROOT / "addon" / "BarrensVoice" / "Dictionary.lua"
sys.path.insert(0, str(ROOT / "companion"))
from bv.dictionary import DEFAULT_BLOCK  # noqa: E402
from bv.online_dictionary import FORMAT, regexes_ok  # noqa: E402

# D.RENAMED as the addon builds it, whichever way the table is written (a constructor, assignments, long
# strings): Dictionary.lua run by LuaJIT, the pairs written out separated by NUL bytes; an entry renamed to
# several keys as one string, the keys joined by "\n" ("renamed" stays a map of strings, as older programs read it)
RENAMED_LUA = """
local ns = { db = {} }
assert(loadfile(arg[1]))("BarrensVoice", ns)
local renamed, keys = ns.Dictionary.RENAMED or {}, {}
for k in pairs(renamed) do keys[#keys + 1] = k end
table.sort(keys)
for _, k in ipairs(keys) do
    local new = renamed[k]
    io.write(k, "\\0", type(new) == "table" and table.concat(new, "\\n") or new, "\\0")
end
"""


def revision(path: Path = LUA) -> int:
    """The time of the last commit that changed `path` (needs the history: CI checks out with fetch-depth 0)."""
    out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(ROOT))], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    if not out:
        sys.exit(f"no commit changed {path.relative_to(ROOT)}")
    return int(out)


def renamed(lua: str) -> dict[str, str]:
    """The renamed default keys (D.RENAMED) of the Lua text of Dictionary.lua, as LuaJIT loads it."""
    luajit = shutil.which("luajit")
    if not luajit:
        sys.exit("luajit not found (mise install): D.RENAMED is read by running Dictionary.lua")
    with tempfile.TemporaryDirectory() as d:
        # files, not -e: on Windows luajit is a .CMD shim, and cmd mangles quotes in arguments
        source, script = Path(d) / "Dictionary.lua", Path(d) / "renamed.lua"
        source.write_text(lua, encoding="utf-8")
        script.write_text(RENAMED_LUA, encoding="utf-8")
        done = subprocess.run([luajit, str(script), str(source)], capture_output=True)
    if done.returncode != 0:
        sys.exit(f"Dictionary.lua does not load: {done.stderr.decode('utf-8', 'replace').strip()}")
    parts = done.stdout.decode("utf-8").split("\0")[:-1]
    return dict(zip(parts[::2], parts[1::2]))


def build(text: str | None = None, rev: int | None = None) -> dict:
    lua = text if text is not None else LUA.read_text(encoding="utf-8")
    default = DEFAULT_BLOCK.search(lua)
    if not default:
        sys.exit("Dictionary.lua: no D.DEFAULT = [[...]]")
    rev = rev if rev is not None else revision()
    return {"format": FORMAT, "revision": rev,
            "date": datetime.fromtimestamp(rev, timezone.utc).strftime("%Y-%m-%d"),
            "text": default.group(1), "renamed": renamed(lua)}


def write(data: dict, out: Path) -> Path:
    """The file as bytes with "\n" line ends on every system: what is signed is what GitHub serves (written as
    text on Windows it had "\r\n", which git turned into "\n" in the branch, and no signature held)."""
    out.write_bytes((json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return out


def main() -> int:
    data = build()
    why = regexes_ok(data["text"])
    if why:
        sys.exit(f"the dictionary would be refused by the companions: {why}")
    DIST.mkdir(exist_ok=True)
    out = write(data, DIST / "dictionary.json")
    print(f"{out.relative_to(ROOT)}: revision {data['revision']} ({data['date']}), {len(data['text'].splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
