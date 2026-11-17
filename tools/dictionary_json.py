"""dist/dictionary.json: the addon's default dictionary for the dictionary online (`mise run dictionary`).

CI runs it after the tests pass on master, signs it (tools/sign.py) and puts both files in the branch
`dictionary`, where companions fetch them (bv/online_dictionary.py). `revision` is the time of the last
commit that changed Dictionary.lua - the same number tools/release.py writes into a release's Dictionary.lua
(D.REVISION), so the newer of the two is the default; the file only changes when the dictionary does.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
LUA = ROOT / "addon" / "BarrensVoice" / "Dictionary.lua"
sys.path.insert(0, str(ROOT / "companion"))
from bv.dictionary import DEFAULT_BLOCK, unescape  # noqa: E402
from bv.online_dictionary import FORMAT, regexes_ok  # noqa: E402

RENAMED_BLOCK = re.compile(r"^D\.RENAMED\s*=\s*\{(.*?)^\}", re.S | re.M)
PAIR = re.compile(r'\[\s*"((?:[^"\\]|\\.)*)"\s*\]\s*=\s*"((?:[^"\\]|\\.)*)"')


def revision(path: Path = LUA) -> int:
    """The time of the last commit that changed `path` (needs the history: CI checks out with fetch-depth 0)."""
    out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(ROOT))], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    if not out:
        sys.exit(f"no commit changed {path.relative_to(ROOT)}")
    return int(out)


def build(text: str | None = None, rev: int | None = None) -> dict:
    lua = text if text is not None else LUA.read_text(encoding="utf-8")
    default = DEFAULT_BLOCK.search(lua)
    if not default:
        sys.exit("Dictionary.lua: no D.DEFAULT = [[...]]")
    block = RENAMED_BLOCK.search(lua)
    renamed = {unescape(a): unescape(b) for a, b in PAIR.findall(block.group(1))} if block else {}
    rev = rev if rev is not None else revision()
    return {"format": FORMAT, "revision": rev,
            "date": datetime.fromtimestamp(rev, timezone.utc).strftime("%Y-%m-%d"),
            "text": default.group(1), "renamed": renamed}


def main() -> int:
    data = build()
    why = regexes_ok(data["text"])
    if why:
        sys.exit(f"the dictionary would be refused by the companions: {why}")
    DIST.mkdir(exist_ok=True)
    out = DIST / "dictionary.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: revision {data['revision']} ({data['date']}), {len(data['text'].splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
