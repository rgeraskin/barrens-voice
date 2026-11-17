"""Round trip: the addon's Lua encoder (run with LuaJIT) -> rendered strip -> Python decoder."""
import random
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "companion"))

from bv.protocol import Image, decode, parse  # noqa: E402

PROTOCOL = ROOT / "addon" / "BarrensVoice" / "Protocol.lua"
ENCODE = Path(__file__).with_name("encode.lua")
LEVELS = (0, 12, 24, 36)   # the addon's P.LEVELS
LUAJIT = shutil.which("luajit")


def encode(seq: int, payload: bytes, cells: int) -> list[tuple[int, int, int]]:
    out = subprocess.run([LUAJIT, str(ENCODE), str(PROTOCOL), str(seq), str(cells)],
                         input=payload, capture_output=True, check=True).stdout.decode()
    return [tuple(int(v) for v in line.split()) for line in out.splitlines()]


def render(cells, width: int, cell: int, rows: int, distort=lambda v: v, noise=0, seed=1,
           from_right: bool = False) -> Image:
    """The strip as the screen shows it: black bar, cells painted, through `distort` and noise."""
    rnd = random.Random(seed)
    height = cell * rows
    per_row = width // cell
    px = [[(0, 0, 0)] * width for _ in range(height)]
    for i, c in enumerate(cells):
        row, col = divmod(i, per_row)
        colour = tuple(LEVELS[v] for v in c)
        for dy in range(cell):
            for dx in range(cell):
                x = col * cell + dx
                if from_right:
                    x = width - 1 - x
                px[row * cell + dy][x] = colour
    raw = bytearray()
    for line in px:
        for r, g, b in line:
            def f(v):
                return max(0, min(255, round(distort(v)) + rnd.randint(-noise, noise)))
            raw += bytes((f(b), f(g), f(r), 255))
    return Image(bytes(raw), width, height)


@unittest.skipUnless(LUAJIT, "luajit not installed")
class RoundTrip(unittest.TestCase):
    PAYLOAD = "\x1f".join(["party", "Громмаш-Степи", "Orc", "2", "WARRIOR", "",
                           "Всем привет! Кто идёт в Мёртвые копи? |pipe| ё"]).encode()

    def test_plain(self):
        img = render(encode(4242, self.PAYLOAD, 1180), 2360, 2, 1)
        frame = decode(img)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.seq, 4242)
        self.assertEqual(frame.payload, self.PAYLOAD)
        line = parse(frame.payload)
        self.assertEqual(line.sender, "Громмаш-Степи")
        self.assertEqual(line.sex, "2")
        self.assertTrue(line.text.startswith("Всем привет"))

    def test_gamma_noise_and_cell_sizes(self):
        for cell in (1, 2, 3, 4):
            width = 1920
            gamma = lambda v: 255 * (v / 255) ** 0.7  # brightened, as a gamma setting would
            img = render(encode(7, self.PAYLOAD, width // cell), width, cell, 1, gamma, noise=2, seed=cell)
            frame = decode(img)
            self.assertIsNotNone(frame, f"cell {cell}")
            self.assertEqual(frame.payload, self.PAYLOAD)
            self.assertEqual(frame.cell, cell)

    def test_from_the_right_edge(self):
        for width, cell in ((2360, 2), (1921, 2), (1920, 3)):   # odd widths too: a part cell at the left
            img = render(encode(77, self.PAYLOAD, width // cell), width, cell, 1, from_right=True)
            frame = decode(img)
            self.assertIsNotNone(frame, f"{width}/{cell}")
            self.assertEqual(frame.payload, self.PAYLOAD)

    def test_darker_gamma(self):
        # a darker gamma setting squeezes the dark levels together; they must stay apart
        for gamma in (1.1, 1.2):
            img = render(encode(11, self.PAYLOAD, 960), 1920, 2, 1,
                         lambda v, g=gamma: 255 * (v / 255) ** g, noise=1, seed=7)
            frame = decode(img)
            self.assertIsNotNone(frame, f"gamma {gamma}")
            self.assertEqual(frame.payload, self.PAYLOAD)

    def test_two_rows(self):
        long = ("Ж" * 900).encode()
        cells = 2 * (1000 // 2)
        img = render(encode(1, long, cells), 1000, 2, 2)
        frame = decode(img)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.payload, long[: len(frame.payload)])
        self.assertGreater(len(frame.payload), 500)
        frame.payload.decode("utf-8")  # trimmed on a character boundary

    def test_trim_fits_one_row(self):
        long = ("Ж" * 900).encode()
        img = render(encode(9, long, 600), 1200, 2, 1)
        frame = decode(img)
        self.assertIsNotNone(frame)
        frame.payload.decode("utf-8")

    def test_empty_payload(self):
        frame = decode(render(encode(65535, b"", 960), 1920, 2, 1))
        self.assertEqual((frame.seq, frame.payload), (65535, b""))

    def test_no_strip(self):
        self.assertIsNone(decode(Image(bytes(1920 * 4 * 2), 1920, 2)))
        scene = bytes(random.Random(3).randrange(256) for _ in range(1920 * 4 * 2))
        self.assertIsNone(decode(Image(scene, 1920, 2)))

    def test_damaged(self):
        from bv import protocol
        cells = encode(5, self.PAYLOAD, 960)
        r, g, b = cells[40]
        cells[40] = ((r + 1) % 4, g, b)
        self.assertIsNone(decode(render(cells, 1920, 2, 1)))
        self.assertEqual(protocol.last_failure, "damaged")
        decode(Image(bytes(1920 * 4 * 2), 1920, 2))
        self.assertEqual(protocol.last_failure, "absent")

    def test_another_protocol(self):
        # an addon of another protocol: told apart from a damaged strip, with its number
        from bv import protocol
        from bv.logs import level_of
        cells = encode(5, self.PAYLOAD, 960)
        _, _, b = cells[6]
        cells[6] = (0, 2, b)                      # the first header cell: version 0001 -> 0010 (r, g carry its 4 bits)
        self.assertIsNone(decode(render(cells, 1920, 2, 1)))
        self.assertEqual((protocol.last_failure, protocol.other_version), ("version", 2))
        which, words = protocol.mismatch(2)
        self.assertEqual(which, "newer")
        self.assertIn("обновите Barrens Voice", words)
        self.assertEqual(protocol.mismatch(0)[0], "older")
        self.assertEqual({level_of(protocol.mismatch(v)[1]) for v in (0, 2)}, {"WARN"})
        self.assertIsNotNone(decode(render(encode(5, self.PAYLOAD, 960), 1920, 2, 1)))   # ours still read
        self.assertIn(protocol.VERSION, protocol.SUPPORTED)

    def test_covered_from_the_right(self):
        # a minimap at the top edge: the strip drawn from the right, cells 19+ covered by the scene
        from bv import protocol
        img = render(encode(8, self.PAYLOAD, 960), 1920, 2, 1, from_right=True)
        raw = bytearray(img.raw)
        for y in range(2):
            for x in range(1673, 1882):
                i = (y * 1920 + x) * 4
                raw[i:i + 3] = bytes((60, 20, 1))
        self.assertIsNone(decode(Image(bytes(raw), 1920, 2)))
        self.assertEqual(protocol.last_failure, "damaged")


def scene(width: int, height: int, seed: int = 3) -> bytearray:
    """A dark game picture: noise, with stray dark purple and green pixels that look like sync cells."""
    rnd = random.Random(seed)
    raw = bytearray()
    for _ in range(width * height):
        kind = rnd.random()
        if kind < 0.02:
            r, g, b = 36, 0, 36                       # a lone "sync" pixel
        elif kind < 0.04:
            r, g, b = 0, 36, 0
        else:
            r, g, b = rnd.randint(0, 90), rnd.randint(0, 90), rnd.randint(0, 90)
        raw += bytes((b, g, r, 255))
    return raw


def paste(raw: bytearray, width: int, img: Image, x: int, y: int) -> None:
    for row in range(img.height):
        start = ((y + row) * width + x) * 4
        raw[start:start + img.width * 4] = img.raw[row * img.width * 4:(row + 1) * img.width * 4]


@unittest.skipUnless(LUAJIT, "luajit not installed")
class FindingTheStrip(unittest.TestCase):
    """The strip moved somewhere the program was not told of: found over the whole window."""
    PAYLOAD = RoundTrip.PAYLOAD

    def test_anywhere_from_either_edge(self):
        from bv.locate import find
        width, height = 640, 240
        for from_right in (False, True):
            strip = render(encode(91, self.PAYLOAD, 400 // 2), 400, 2, 1, from_right=from_right)
            raw = scene(width, height)
            paste(raw, width, strip, 120, 200)
            hit = find(bytes(raw), width, height, width_hint=400)
            self.assertIsNotNone(hit, f"from the right: {from_right}")
            x, y, w, h, frame = hit
            self.assertEqual((x, y, w), (120, 200, 400))
            self.assertEqual(frame.payload, self.PAYLOAD)

    def test_without_a_width(self):
        from bv.locate import find
        width, height = 640, 120
        raw = scene(width, height, seed=5)
        paste(raw, width, render(encode(5, self.PAYLOAD, 300), 600, 2, 1), 0, 118)   # the bottom edge
        x, y, w, h, frame = find(bytes(raw), width, height)
        self.assertEqual((x, y, h), (0, 118, 2))
        self.assertEqual(frame.seq, 5)

    def test_a_narrow_strip_of_several_rows(self):
        # 220 px wide: the addon gives it 7 rows so a long line fits; found and read in full
        from bv.locate import find
        payload = "\x1f".join(["party", "Громмаш-Степи", "Orc", "2", "WARRIOR", "", "rate=100",
                               "Длинная строка чата " * 12]).encode()[:540]
        width, height = 640, 200
        raw = scene(width, height, seed=11)
        paste(raw, width, render(encode(12, payload, 110 * 7), 220, 2, 7), 300, 60)
        hit = find(bytes(raw), width, height, width_hint=220, capture_height=64)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[:3], (300, 60, 220))
        self.assertEqual(hit[4].payload, payload)

    def test_nothing_there(self):
        from bv.locate import find
        self.assertIsNone(find(bytes(scene(320, 100, seed=9)), 320, 100))


class StripPlace(unittest.TestCase):
    def test_parse_and_region(self):
        from bv.locate import parse_place, region
        self.assertEqual(parse_place("100,50,900,2,2560,1440"), (100, 50, 900, 2, 2560, 1440))
        self.assertIsNone(parse_place("1,2,3"))
        self.assertIsNone(parse_place("1,2,0,2,10,10"))
        self.assertEqual(region((0, 0, 1920, 2, 1920, 1080), 1920, 1080, 16), (0, 0, 1920, 16))
        self.assertEqual(region((0, 1078, 1920, 2, 1920, 1080), 1920, 1080, 16), (0, 1078, 1920, 2))   # the bottom
        # a window not at the game's resolution: scaled
        self.assertEqual(region((100, 50, 900, 2, 2560, 1440), 1280, 720, 16), (50, 25, 450, 16))

    def test_saved_variables(self):
        import tempfile
        from unittest import mock
        from bv import locate
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "BarrensVoice.lua"
            path.write_text('BarrensVoiceDB = {\n["stripGeometry"] = "0,1078,1920,2,1920,1080",\n}\n', encoding="utf-8")
            with mock.patch("bv.dictionary.find_saved", return_value=path):
                self.assertEqual(locate.saved_place({}), (0, 1078, 1920, 2, 1920, 1080))

    def test_control_frame_option(self):
        line = parse("\x1f".join(["control", "", "", "", "", "", "rate=100;vol=100;voice=f5;strip=0,1078,1920,2,1920,1080", "-"]).encode())
        from bv.locate import parse_place
        self.assertEqual(parse_place(line.options["strip"]), (0, 1078, 1920, 2, 1920, 1080))


if __name__ == "__main__":
    unittest.main()
