"""Is a release tag ready to be pushed? `mise run check-tag <tag> [<commit>]`, and the pre-push hook
(.githooks/pre-push, `mise run hooks`) for every tag a push carries.

CI builds a release only after its tag is public, and tools/release.py refuses it there when news.toml or
CHANGELOG.md is not ready; this says the same (release.tag_problems: one list of checks for both) before the push.
It reads pyproject.toml, news.toml, CHANGELOG.md and the addon's .toc as the tagged commit has them (git show in the
current repository), not the working tree. Offline, and only the standard library: no tests are run.
Exit 0: ready; 1: not ready (what to fix on stderr); 2: wrong use.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release import tag_problems  # noqa: E402


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True)


def reader(commit: str):
    """read(name): the file's text at `commit`, None when it has no such file."""
    def read(name: str) -> str | None:
        shown = git("show", f"{commit}:{name}")
        return shown.stdout.decode("utf-8") if shown.returncode == 0 else None
    return read


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        print("usage: check_tag.py <tag> [<commit or tag object>]", file=sys.stderr)
        return 2
    tag = argv[0]
    peeled = git("rev-parse", "--verify", "--quiet", f"{argv[-1]}^{{commit}}")
    if peeled.returncode != 0:
        print(f"{tag}: {argv[-1]} is no commit here", file=sys.stderr)
        return 2
    problems = tag_problems(tag, reader(peeled.stdout.decode().strip()))
    if problems:
        print(f"{tag} is not ready for a release (CI would refuse it once the tag is public):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(f"Fix it in a commit, move the tag there (git tag -f {tag}) and push again.", file=sys.stderr)
        return 1
    print(f"{tag}: ready (its version, news.toml, CHANGELOG.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
