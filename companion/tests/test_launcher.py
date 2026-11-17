"""The launcher's logic without its window: games and addon, versions, settings, state lines."""
import os
import json
import tempfile
import unittest
from pathlib import Path


def make_game(root: Path, addon_version: str | None = None) -> Path:
    root.mkdir(parents=True)
    (root / "Wow.exe").write_bytes(b"")
    if addon_version:
        addon = root / "Interface" / "AddOns" / "BarrensVoice"
        addon.mkdir(parents=True)
        (addon / "BarrensVoice.toc").write_text(f"## Interface: 16001\n## Version: {addon_version}\n", encoding="utf-8")
    return root


class Versions(unittest.TestCase):
    def test_compare(self):
        from bv.launcher.model import newer, version_key
        self.assertEqual(version_key("v0.4.1"), version_key("0.4.1"))
        self.assertTrue(newer("0.4.10", "0.4.9"))
        # a test build is older than its release and newer than the one before; betas in their order
        self.assertTrue(newer("0.4.0", "0.4.0b5") and newer("0.4.0b5", "0.3.0") and newer("0.4.0b10", "0.4.0b9"))
        self.assertEqual(version_key("v0.4.0-beta.5"), version_key("0.4.0b5"))
        self.assertFalse(newer("v0.4.0", "0.4.0"))
        self.assertFalse(newer("", "0.4.0"))

    def test_app_and_addon_versions(self):
        # the app's version is pyproject.toml's; the addon's, its own .toc's (raised only when it changes)
        import tomllib
        from bv.launcher.model import addon_source, addon_version, app_version
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(app_version(), tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"])
        toc = (addon_source() / "BarrensVoice.toc").read_text(encoding="utf-8")
        self.assertIn(f"## Version: {addon_version()}", toc)


class Games(unittest.TestCase):
    def test_found_with_their_addon(self):
        from bv.launcher.model import find_games
        with tempfile.TemporaryDirectory() as d:
            forever = make_game(Path(d) / "A" / "World of Warcraft" / "_forever_", "0.3.0")
            make_game(Path(d) / "B" / "World of Warcraft" / "_retail_")
            games = find_games({"wow_dir": str(forever)}, extra=[Path(d) / "B" / "World of Warcraft"])
        self.assertEqual([(g.key, g.name, g.addon) for g in games],
                         [("forever", "WoW Forever", "0.3.0"), ("retail", "WoW Retail", None)])
        self.assertEqual(games[0].root, forever)

    def test_a_folder_without_the_game_is_not_one(self):
        from bv.launcher.model import find_games
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "_retail_").mkdir()
            self.assertEqual(find_games({}, extra=[Path(d)]), [])

    def test_install_addon(self):
        from bv.launcher.model import ADDON, install_addon, toc_version
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "src" / ADDON
            source.mkdir(parents=True)
            (source / f"{ADDON}.toc").write_text("## Version: 0.4.0\n", encoding="utf-8")
            (source / "Media").mkdir()
            (source / "Media" / "README.md").write_text("x", encoding="utf-8")
            (source / "Media" / "icon.tga").write_bytes(b"tga")
            game = make_game(Path(d) / "_forever_", "0.3.0")
            old = game / "Interface" / "AddOns" / ADDON
            (old / "Removed.lua").write_text("-- gone from the new version", encoding="utf-8")
            (old / "Old").mkdir()
            (old / "Old" / "x.tga").write_bytes(b"tga")
            (old / "._Core.lua").write_text("mac", encoding="utf-8")
            (old / "VoiceList.lua").write_text("BarrensVoiceVoiceList = { 'Irina' }", encoding="utf-8")
            (source / "VoiceList.lua").write_text("BarrensVoiceVoiceList = BarrensVoiceVoiceList or {}", encoding="utf-8")
            (source / "CompanionStatus.lua").write_text("BarrensVoiceStatus = nil", encoding="utf-8")
            target = install_addon(source, game)
            # the companion's list of voices kept; the status file, not there before, comes from the addon
            self.assertIn("Irina", (target / "VoiceList.lua").read_text(encoding="utf-8"))
            self.assertTrue((target / "CompanionStatus.lua").exists())
            self.assertEqual(toc_version(target), "0.4.0")
            self.assertTrue((target / "Media" / "icon.tga").exists())
            self.assertFalse((target / "Media" / "README.md").exists())
            left = sorted(p.relative_to(target).as_posix() for p in target.rglob("*"))
            self.assertEqual(left, ["BarrensVoice.toc", "CompanionStatus.lua", "Media", "Media/icon.tga",
                                    "VoiceList.lua"])                          # the old version's own gone


class Paths(unittest.TestCase):
    """The installer's starter sets BV_DATA, BV_CACHE and BV_STARTER; without them, the companion's folder."""

    def run_paths(self, env):
        import os
        import subprocess
        import sys
        code = ("from bv import paths; print(paths.CODE_DIR); print(paths.DATA_DIR); print(paths.CACHE_DIR); "
                "print(paths.starter())")
        clean = {k: v for k, v in os.environ.items() if not k.startswith("BV_")}
        out = subprocess.run([sys.executable, "-c", code], env={**clean, **env}, capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parents[1], check=True).stdout.splitlines()
        return [Path(x) for x in out[:3]] + [out[3]]

    def test_install_layout(self):
        from bv.paths import INSTALL_MARK, layout
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            code = root / "app" / "0.4.1" / "companion"
            code.mkdir(parents=True)
            self.assertIsNone(layout(code, {})["root"])                     # no mark: not an install
            (root / INSTALL_MARK).write_text("", encoding="utf-8")
            got = layout(code, {})
            self.assertEqual((got["root"], got["data"], got["cache"]), (root, root / "data", root / "cache"))
            self.assertIn(str(root / "app" / "current" / ".venv"), got["starter"])   # through the junction
            (root / "Barrens Voice.exe").write_bytes(b"")
            self.assertEqual(layout(code, {})["starter"], f'"{root / "Barrens Voice.exe"}"')   # the starter, if there
            self.assertEqual(layout(code, {"BV_DATA": "x"})["data"], Path("x"))

    def test_installed_and_not(self):
        code, data, cache, start = self.run_paths({})
        self.assertEqual((data, cache), (code, code))                   # as before the installer
        self.assertTrue(start.endswith('BarrensVoice.pyw"'))
        with tempfile.TemporaryDirectory() as d:
            code, data, cache, start = self.run_paths({"BV_DATA": f"{d}/data", "BV_CACHE": f"{d}/cache",
                                                       "BV_STARTER": '"py" "start.pyw"'})
            self.assertEqual((data, cache, start), (Path(d) / "data", Path(d) / "cache", '"py" "start.pyw"'))


class GameFolder(unittest.TestCase):
    def test_world_of_warcraft_folder_taken_for_the_game(self):
        from bv.launcher.model import game_folder
        with tempfile.TemporaryDirectory() as d:
            wow = Path(d) / "World of Warcraft"
            make_game(wow / "_forever_")
            self.assertEqual(game_folder(str(wow), "forever"), os.path.normpath(str(wow / "_forever_")))
            self.assertEqual(game_folder(str(wow / "_forever_"), "forever"), os.path.normpath(str(wow / "_forever_")))
            self.assertEqual(game_folder(str(wow), "retail"), os.path.normpath(str(wow)))   # no retail there: as typed
            self.assertEqual(game_folder("", "forever"), "")


class Config(unittest.TestCase):
    def test_update_keeps_the_rest(self):
        from bv.launcher.model import read_config, update_config
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps({"players": {"Вася": "orc-male"}, "rate": 3}), encoding="utf-8")
            update_config(path, game="retail")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual((saved["players"], saved["rate"], saved["game"]), ({"Вася": "orc-male"}, 3, "retail"))
            self.assertTrue(read_config(path)["exit_with_wow"])        # defaults under the file


class StateLines(unittest.TestCase):
    def test_running_and_ready(self):
        from bv.launcher.model import GREEN, describe
        lines = describe({"phase": "running", "voices": "ready", "device": "RTX", "linked": True}, True, None,
                         "WoW Forever", False)
        self.assertEqual([c for c, _ in lines], [GREEN] * 4)
        self.assertEqual(lines[2][1], "Голоса рас готовы — RTX")
        self.assertEqual(lines[1][1], "WoW Forever запущена")

    def test_stopped_and_problems(self):
        from bv.launcher.model import GREY, RED, describe
        self.assertEqual(describe({}, False, None, None, True)[0][0], RED)                  # no addon
        self.assertIn("ошибкой", describe({}, False, 1, None, False)[0][1])
        self.assertIn("уже запущен", describe({}, False, 4, None, False)[0][1])
        self.assertIn("игра закрыта", describe({"phase": "game_closed"}, False, 0, None, False)[0][1])
        error = describe({"phase": "error", "error": "аддон не установлен"}, False, 1, None, False)[0]
        self.assertEqual(error, (RED, "Компаньон: аддон не установлен"))
        self.assertEqual(describe({"voices": "ready"}, False, 0, None, False)[2][0], GREY)  # stale file: not ready

    def test_bridge(self):
        from bv.launcher.model import describe
        self.assertIn("свёрнуто", describe({"window": False}, True, None, "WoW Forever", False)[3][1])
        self.assertIn("перекрывает", describe({"damaged": True}, True, None, "WoW Forever", False)[3][1])
        self.assertIn("ждём игру", describe({}, True, None, None, False)[3][1])


class CompanionState(unittest.TestCase):
    def test_file(self):
        from bv import state
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tmp" / "state.json"
            state.report(voices="x")                    # before init: nothing written anywhere
            state.init(path, phase="starting")
            state.report(voices="ready", linked=True)
            got = state.read(path)
            self.assertEqual((got["phase"], got["voices"], got["linked"]), ("starting", "ready", True))
            state.init(path)                            # a new run: a fresh file
            self.assertNotIn("voices", state.read(path))
            state._path = None
        self.assertEqual(state.read(Path(d) / "none.json"), {})


class GameOfPath(unittest.TestCase):
    def test_folders(self):
        from bv.launch import game_of_path
        self.assertEqual(game_of_path(r"E:\World of Warcraft\_forever_\Wow.exe".replace("\\", "/")), "forever")
        self.assertEqual(game_of_path("D:/World of Warcraft/_retail_/Wow.exe"), "retail")
        self.assertIsNone(game_of_path("D:/World of Warcraft/_classic_era_/WowClassic.exe"))


class Roots(unittest.TestCase):
    def test_remembered_and_wow_dir_first(self):
        from bv.dictionary import wow_roots
        roots = wow_roots({"game": "retail", "game_dirs": {"retail": "X:/WoW/_retail_"}, "wow_dir": "Y:/WoW/_forever_"})
        self.assertEqual(roots[:2], [Path("X:/WoW/_retail_"), Path("Y:/WoW/_retail_")])   # the sibling, not _forever_
        self.assertEqual(wow_roots({"wow_dir": "Y:/World of Warcraft"})[0], Path("Y:/World of Warcraft/_forever_"))

    def test_remember(self):
        from bv.launcher.model import remember
        self.assertEqual(remember({}, "forever", Path("E:/W/_forever_")), {"game_dirs": {"forever": str(Path("E:/W/_forever_"))}})
        self.assertIsNone(remember({"game_dirs": {"forever": str(Path("E:/W/_forever_"))}}, "forever", Path("E:/W/_forever_")))
        kept = remember({"game_dirs": {"retail": "D:/x"}}, "forever", Path("E:/f"))
        self.assertEqual(set(kept["game_dirs"]), {"retail", "forever"})


class CommandLine(unittest.TestCase):
    def test_parse(self):
        from bv.launcher.model import parse_args
        a = parse_args(["--retail", "--f5", "--console", "--open", "help", "--scale", "1.5"])
        self.assertEqual((a["game"], a["companion"], a["console"], a["open"], a["scale"]), ("retail", ["--f5"], True, "help", 1.5))
        self.assertEqual(parse_args(["--bogus"])["unknown"], ["--bogus"])
        self.assertEqual(parse_args(["--scale", "x"])["unknown"], ["--scale x"])
        self.assertTrue(parse_args(["/?"])["help"])
        self.assertTrue(parse_args(["--tray"])["tray"])

    def test_usage_names_every_switch(self):
        from bv.launcher.model import COMPANION_FLAGS, USAGE
        for flag in COMPANION_FLAGS + ("--forever", "--retail", "--console", "--tray", "--open", "--scale", "--help"):
            self.assertIn(flag, USAGE)


class Report(unittest.TestCase):
    def setUp(self):
        global model
        from bv.launcher import model

    def test_settings_changed_without_personal_data(self):
        defaults = {"volume": 100, "wow_dir": "", "exclude": [], "players": {}, "game_dirs": {}}
        config = dict(defaults, volume=80, wow_dir=r"D:\Games\World of Warcraft", exclude=["Вася", "Петя"],
                      players={"Ивар": "orc-1"}, game_dirs={"forever": r"E:\WoW\_forever_"},
                      launcher_dismissed="v0.4.1", f5_onnx_dir=r"C:\Users\someone\models")
        shown = model.changed_settings(config, defaults)
        text = "\n".join(shown)
        self.assertIn("volume = 80", shown)
        self.assertIn("exclude = 2 шт.", shown)
        self.assertIn("players = 1 шт.", shown)
        self.assertIn("game_dirs = forever", shown)
        self.assertIn("wow_dir = свой путь", shown)
        self.assertIn("f5_onnx_dir = свой путь", shown)
        for private in ("Вася", "Ивар", "Games", "someone", "launcher_dismissed"):
            self.assertNotIn(private, text)

    def test_hide_private(self):
        line = r"C:\Users\Someone\AppData\x.log; E:\WoW\_forever_\WTF\Account\MYACCOUNT\SavedVariables"
        out = model.hide_private(line, home=r"C:\Users\someone")
        self.assertEqual(out, r"~\AppData\x.log; E:\WoW\_forever_\WTF\Account\***\SavedVariables")

    def test_header(self):
        game = model.Game("forever", "WoW Forever", Path("E:/x"), "0.4.0")
        state = {"phase": "running", "voices": "ready", "device": "RTX", "provider": "CUDAExecutionProvider"}
        head = model.report_header("0.4.0", state, {"volume": 70}, [game], "forever", gpus=["RTX"],
                                   runtime="onnxruntime-gpu 1.32.0")
        self.assertIn("Barrens Voice 0.4.0", head)
        self.assertIn("Голоса рас: готовы на RTX (CUDAExecutionProvider)", head)
        self.assertIn("WoW Forever (аддон 0.4.0); запущена: WoW Forever", head)
        self.assertIn("volume = 70", head)
        stopped = model.report_header("0.4.0", dict(state, phase="stopped"), {"_help": "x"}, [], None,
                                      running=False, gpus=[], runtime="x")
        self.assertIn("Видеокарты: RTX", stopped)                       # from the state when Windows lists none
        self.assertIn("Компаньон: не запущен (в прошлый раз: stopped)", stopped)
        self.assertIn("Настройки не по умолчанию: нет", stopped)


class Install(unittest.TestCase):
    """bv.install: a release unpacked beside, made current through app/current, old ones pruned."""

    def release(self, d: Path, version: str) -> Path:
        import zipfile
        archive = d / f"barrens-voice-{version}.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("pyproject.toml", f'[project]\nname = "barrens-voice"\nversion = "{version}"\n')
            z.writestr("uv.lock", "version = 1\n")
            z.writestr("companion/bv/__init__.py", "")
        return archive

    def test_install_switch_prune(self):
        from unittest import mock
        from bv import install
        from bv.paths import layout
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            root = d / "BarrensVoice"
            with mock.patch("bv.install.build") as build:
                for version in ("0.4.0", "0.4.1", "0.4.2"):
                    self.assertEqual(install.install(root, self.release(d, version), "cuda", d / "uv.exe", log=lambda *a: None), version)
            self.assertEqual(build.call_args[0][2], "cuda")
            self.assertEqual(install.current_version(root), "0.4.2")
            code = Path(os.path.realpath(root / "app" / "current" / "companion"))
            self.assertEqual(layout(code, {})["root"], root.resolve())          # the code knows it is installed
            self.assertEqual(install.prune(root), ["0.4.0"])                   # current + one to go back to
            self.assertEqual(sorted(p.name for p in (root / "app").iterdir()), ["0.4.1", "0.4.2", "current"])
            self.assertFalse(any(p.name.endswith(".part") for p in (root / "app").iterdir()))


class Update(unittest.TestCase):
    """bv.update: only a signed manifest, only an archive matching it, back to the previous on early failures."""

    def keys(self):
        import base64
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        raw = serialization.Encoding.Raw
        public = base64.b64encode(key.public_key().public_bytes(raw, serialization.PublicFormat.Raw)).decode()
        return key, public

    def test_signature(self):
        import base64
        from bv import update
        key, public = self.keys()
        manifest = b'{"version": "0.4.1"}'
        sig = base64.b64encode(key.sign(manifest)).decode()
        self.assertTrue(update.verify(manifest, sig, public))
        self.assertFalse(update.verify(manifest.replace(b"0.4.1", b"0.4.2"), sig, public))   # changed: refused
        self.assertFalse(update.verify(manifest, sig, self.keys()[1]))                     # another key: refused
        self.assertFalse(update.verify(manifest, "not base64!", public))

    def test_download_checks_the_archive(self):
        import hashlib
        import io
        from bv import update
        data = b"release bytes" * 1000

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        manifest = {"base": "https://x/", "archive": "barrens-voice-0.4.1.zip", "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as d:
            got = update.download(manifest, Path(d), fetch_stream=lambda *a, **k: Response(data))
            self.assertEqual(got.read_bytes(), data)
            with self.assertRaises(ValueError):
                update.download({**manifest, "sha256": "0" * 64}, Path(d), fetch_stream=lambda *a, **k: Response(data))
            self.assertFalse((Path(d) / "barrens-voice-0.4.1.part").exists())

    def test_back_to_the_previous_after_two_early_failures(self):
        from bv import install, update
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for v in ("0.4.0", "0.4.1"):
                (root / "app" / v).mkdir(parents=True)
            install.point_current(root, root / "app" / "0.4.0")
            update.apply(root, "0.4.1")
            self.assertEqual(install.current_version(root), "0.4.1")
            self.assertIsNone(update.record_start(root, 5, failed=True))                  # one failure: wait
            self.assertEqual(update.record_start(root, 5, failed=True), "0.4.0")         # two: back
            self.assertEqual(install.current_version(root), "0.4.0")
            update.apply(root, "0.4.1")
            self.assertIsNone(update.record_start(root, 300, failed=True))               # ran a while: not a start failure
            self.assertFalse(update.state_path(root).exists())


class WindowCode(unittest.TestCase):
    """What the tests cannot draw: the window's snapshot and its unpacking in redraw must agree (an item
    added to one and not the other broke the launcher at its first draw, 0.4.0-beta.3)."""

    def test_snapshot_matches_redraw(self):
        import ast
        tree = ast.parse((Path(__file__).resolve().parents[1] / "bv" / "launcher" / "app.py").read_text(encoding="utf-8"))
        funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        made = [n.value for n in ast.walk(funcs["snapshot"]) if isinstance(n, ast.Return)][-1]
        taken = next(n.targets[0] for n in ast.walk(funcs["redraw"])
                     if isinstance(n, ast.Assign) and isinstance(n.value, ast.Name) and n.value.id == "snap"
                     and isinstance(n.targets[0], ast.Tuple))
        self.assertEqual(len(made.elts), len(taken.elts))


class Wrap(unittest.TestCase):
    """The main window's log: a line that does not fit is wrapped under its time, not cut."""

    def test_wrap(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        try:
            from bv.launcher.paint import Painter
            p = Painter(tk.Canvas(root), "TkDefaultFont")
            short = "03:12:01 связь с аддоном есть"
            self.assertEqual(p.wrap(short, p.mono, 412, " " * 9), [short])
            long = "03:12:01 " + "слово " * 40
            lines = p.wrap(long.strip(), p.mono, 412, " " * 9)
            self.assertGreater(len(lines), 1)
            self.assertTrue(all(x.startswith(" " * 9) for x in lines[1:]))
            self.assertTrue(all(p.measure(x, p.mono) <= 412 for x in lines))
            self.assertEqual(" ".join(x.strip() for x in lines), long.strip())     # nothing lost
        finally:
            root.destroy()


class Starter(unittest.TestCase):
    """Barrens Voice.exe comes with each release and follows the current version (installs and updates)."""

    def test_follows_the_version(self):
        import zipfile
        from unittest import mock
        from bv import install, update

        def release(d, version, exe):
            archive = d / f"barrens-voice-{version}.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("pyproject.toml", f'[project]\nname = "barrens-voice"\nversion = "{version}"\n')
                z.writestr("uv.lock", "version = 1\n")
                if exe is not None:
                    z.writestr("Barrens Voice.exe", exe)
            return archive
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            root = d / "BarrensVoice"
            starter = root / "Barrens Voice.exe"
            with mock.patch("bv.install.build"):
                install.install(root, release(d, "0.4.0", b"v1"), "cuda", d / "uv.exe", log=lambda *a: None)
                self.assertEqual(starter.read_bytes(), b"v1")                       # put there by the install
                v = update.prepare(root, release(d, "0.4.1", b"v2"))
                update.apply(root, v)
                self.assertEqual(starter.read_bytes(), b"v2")                       # an update brings the new one
                v = update.prepare(root, release(d, "0.4.2", None))
                update.apply(root, v)
                self.assertEqual(starter.read_bytes(), b"v2")                       # a release without it: kept


class ReleaseUv(unittest.TestCase):
    """The uv a release names: kept when installed already, else fetched, checked and put in place after the build."""

    def test_kept_fetched_refused(self):
        import hashlib
        import io
        import zipfile
        from unittest import mock
        from bv import update
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("uv.exe", b"new uv")
        data = buf.getvalue()
        want = {"uv": {"version": "0.14.0", "url": "https://x/uv.zip", "sha256": hashlib.sha256(data).hexdigest()}}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "uv.exe").write_bytes(b"old uv")
            with mock.patch("bv.update.uv_version", return_value="0.14.0"):
                self.assertEqual(update.release_uv(root, want, fetch=lambda u: data), root / "uv.exe")   # same: kept
            with mock.patch("bv.update.uv_version", return_value="0.13.7"):
                fresh = update.release_uv(root, want, log=lambda *a: None, fetch=lambda u: data)
                self.assertEqual((fresh.name, fresh.read_bytes()), ("uv.new.exe", b"new uv"))
                with self.assertRaises(ValueError):                                                # tampered: refused
                    update.release_uv(root, {"uv": {**want["uv"], "sha256": "0" * 64}}, log=lambda *a: None,
                                      fetch=lambda u: data)
            self.assertEqual(update.release_uv(root, {}), root / "uv.exe")                          # an old manifest


class UvInPrepare(unittest.TestCase):
    """prepare() with a release naming another uv: replaced after a good build, kept after a failed one."""

    def setUp(self):
        import hashlib
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("uv.exe", b"new uv")
        self.data = buf.getvalue()
        self.manifest = {"uv": {"version": "0.14.0", "url": "https://x/uv.zip",
                                "sha256": hashlib.sha256(self.data).hexdigest()}}

    def release(self, d: Path) -> Path:
        import zipfile
        archive = d / "barrens-voice-0.4.1.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("pyproject.toml", '[project]\nname = "barrens-voice"\nversion = "0.4.1"\n')
            z.writestr("uv.lock", "version = 1\n")
        return archive

    def run_prepare(self, build):
        from unittest import mock
        from bv import update
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "BarrensVoice"
            (root / "app").mkdir(parents=True)
            (root / "uv.exe").write_bytes(b"old uv")
            with mock.patch("bv.update.uv_version", return_value="0.13.7"), \
                 mock.patch("bv.update.get", return_value=self.data), \
                 mock.patch("bv.install.build", side_effect=build):
                try:
                    update.prepare(root, self.release(Path(d)), log=lambda *a: None, manifest=self.manifest)
                except RuntimeError:
                    pass
            return (root / "uv.exe").read_bytes(), (root / "uv.new.exe").exists()

    def test_good_build_replaces_uv(self):
        used = []
        uv, leftover = self.run_prepare(lambda root, folder, runtime, uv, log: used.append(uv.name))
        self.assertEqual(used, ["uv.new.exe"])                     # the version was built with the new uv
        self.assertEqual((uv, leftover), (b"new uv", False))

    def test_failed_build_keeps_the_old_uv(self):
        def fail(*a):
            raise RuntimeError("uv sync failed")
        self.assertEqual(self.run_prepare(fail), (b"old uv", False))

    def test_uv_version_parsed(self):
        from unittest import mock
        from bv import update
        done = mock.Mock(stdout="uv 0.13.7 (316c827e0 2026-11-03 x86_64-pc-windows-msvc)\n")
        with mock.patch("subprocess.run", return_value=done):
            self.assertEqual(update.uv_version(Path("uv.exe")), "0.13.7")
        with mock.patch("subprocess.run", side_effect=OSError("missing")):
            self.assertIsNone(update.uv_version(Path("uv.exe")))
