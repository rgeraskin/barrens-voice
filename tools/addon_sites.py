"""Get the checkout ready for CurseForge and Wago Addons (the release workflow's addon-sites job, before
BigWigsMods/packager zips addon/BarrensVoice by .pkgmeta and uploads it): `python tools/addon_sites.py <tag>`.

Only a release goes there (vX.Y.Z): test builds reach testers through the launcher's test channel. The job
- stamps Dictionary.lua's D.REVISION as the release's archive does (release.stamp_dictionary): the same
  addon on every site, and the dictionary online compared against the same revision;
- writes .addon-sites-notes.md, the file's changelog on both sites (.pkgmeta manual-changelog): the release's
  «Что нового» and where to get the program the addon needs.
`python tools/addon_sites.py --check <zip>` (CI, after the packager without uploading): the zip holds the addon as
git tracks it, under BarrensVoice/, and nothing else.
"""
from __future__ import annotations

import sys
import subprocess
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release  # noqa: E402 - the same entries, version rules and stamp as the release's archive
from release import REPO_URL, ROOT, news  # noqa: E402

NOTES = ROOT / ".addon-sites-notes.md"
# the addon alone reads nothing aloud: on a site where it is found first, it says where the program is
LAUNCHER = ("Аддону нужна программа Barrens Voice Launcher для Windows, она и читает чат вслух. Скачай установщик "
            "`BarrensVoice-Setup.exe` со страницы выпуска на GitHub: {url}")


def notes(version: str, entries: list[dict], tag: str) -> str:
    """The sites' changelog of a release: its «Что нового» entry (title and items, Russian), the launcher it needs,
    the full English list."""
    entry = next(e for e in entries if e["version"] == version)
    parts = [f"### {entry['title']}\n\n" + "\n".join(f"- {item}" for item in entry["items"]),
             LAUNCHER.format(url=f"{REPO_URL}/releases/tag/{tag}"),
             f"Полный список изменений, на английском: [CHANGELOG.md]({REPO_URL}/blob/{tag}/CHANGELOG.md)."]
    return "\n\n".join(parts) + "\n"


def problems(tag: str, base: str, entries: list[dict]) -> list[str]:
    """Why this tag is not for the sites: not a release of pyproject.toml's version, or its entry missing."""
    version = release.tag_version(tag, base)
    if version is None:
        return [f"{tag}: not a tag of version {base}"]
    if version != news.release_of(version):
        return [f"{tag}: a test build, only releases go to CurseForge and Wago"]
    if not any(e["version"] == version for e in entries):
        return [f"{tag}: news.toml has no entry {version}"]
    return []


# tracked in the addon's folder, not for the game: the icons' credits (.pkgmeta's ignore)
LEFT_OUT = {"Media/README.md"}


def zip_problems(names: list[str], tracked: list[str]) -> list[str]:
    """What is wrong with the packager's zip (`names`) against the addon's tracked files (paths under
    addon/BarrensVoice/): every one of them under BarrensVoice/ and the repository's LICENSE (MIT: with the
    code), nothing more."""
    want = {f"BarrensVoice/{name}" for name in tracked if name not in LEFT_OUT} | {"BarrensVoice/LICENSE"}
    have = {n for n in names if not n.endswith("/")}
    return ([f"missing: {n}" for n in sorted(want - have)]
            + [f"not the addon's: {n}" for n in sorted(have - want)])


def check(zip_path: Path) -> int:
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT / "addon" / "BarrensVoice", capture_output=True,
                             check=True).stdout.decode("utf-8").split("\0")
    found = zip_problems(zipfile.ZipFile(zip_path).namelist(), [t for t in tracked if t])
    if found:
        print(f"{zip_path.name}:\n" + "\n".join(found), file=sys.stderr)
        return 1
    print(f"{zip_path.name}: the addon and nothing else")
    return 0


def main(tag: str) -> int:
    base = release.versions()["version"]
    entries = release.news_entries()
    found = problems(tag, base, entries)
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    path = ROOT / release.DICTIONARY
    path.write_bytes(release.stamp_dictionary(path.read_bytes(), release.dictionary_revision()))
    NOTES.write_text(notes(base, entries, tag), encoding="utf-8", newline="\n")
    print(f"{tag}: Dictionary.lua stamped, {NOTES.name} written")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        sys.exit(check(Path(sys.argv[2])))
    if len(sys.argv) != 2:
        sys.exit("usage: addon_sites.py <tag> | --check <zip>")
    sys.exit(main(sys.argv[1]))
