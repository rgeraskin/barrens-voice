"""The two lists of the program's libraries agree: pyproject.toml (the installer's uv sync) and
companion/requirements.txt (BarrensVoice.cmd, a run from the source)."""
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def name_and_pin(spec: str) -> tuple[str, str]:
    spec = spec.split(";")[0].strip()
    name = re.split(r"[=<>!~ \[]", spec, maxsplit=1)[0].lower().replace("_", "-")
    return name, spec[len(name):].strip()


class Requirements(unittest.TestCase):
    def test_same_libraries_and_versions(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
        listed = [line.strip() for line in (ROOT / "companion" / "requirements.txt").read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.startswith("#")]
        self.assertEqual(dict(map(name_and_pin, listed)), dict(map(name_and_pin, project)))


if __name__ == "__main__":
    unittest.main()
