"""The launcher's logic without its window: games and addon, versions, settings, state lines."""
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
        self.assertEqual(version_key("v0.4.1"), (0, 4, 1))
        self.assertTrue(newer("0.4.10", "0.4.9"))
        self.assertFalse(newer("v0.4.0", "0.4.0"))
        self.assertFalse(newer("", "0.4.0"))

    def test_app_version_is_the_toc(self):
        from bv.launcher.model import addon_source, app_version
        toc = (addon_source() / "BarrensVoice.toc").read_text(encoding="utf-8")
        self.assertIn(f"## Version: {app_version()}", toc)


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
            target = install_addon(source, game)
            self.assertEqual(toc_version(target), "0.4.0")
            self.assertTrue((target / "Media" / "icon.tga").exists())
            self.assertFalse((target / "Media" / "README.md").exists())


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
