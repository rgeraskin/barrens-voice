"""Reading files out of a local WoW installation's CASC storage - read only, standard library only.

The chain: .build.info (the installed build of a product) -> its build config -> local indices
(encoded key -> archive, offset) -> BLTE blocks in Data/data/data.NNN; the encoding table maps a
content key to its encoded key, and the root table a FileDataID (and locale) to its content key.
Nothing is written to the game folder and the game process is not touched: the files are read like
any other files on the disk.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

LOCALES = {"enUS": 0x2, "koKR": 0x4, "frFR": 0x10, "deDE": 0x20, "zhCN": 0x40, "esES": 0x80, "zhTW": 0x100,
           "enGB": 0x200, "esMX": 0x1000, "ruRU": 0x2000, "ptBR": 0x4000, "itIT": 0x8000}
DEFAULT_PRODUCTS = {"_forever_": "wowf", "_retail_": "wow", "_classic_era_": "wow_classic_era"}


def product_of(flavor_dir: Path) -> str:
    """The product code of a game folder (`_forever_` -> "wowf"): its .flavor.info, else the usual one."""
    info = flavor_dir / ".flavor.info"
    if info.exists():
        lines = [line.strip() for line in info.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) >= 2:
            return lines[-1]
    return DEFAULT_PRODUCTS.get(flavor_dir.name, "wow")


def build_info(install: Path, product: str) -> dict[str, str]:
    """The installed build of `product` from the install's .build.info ("Build Key", "Version", ...)."""
    rows = [line.split("|") for line in (Path(install) / ".build.info").read_text(encoding="utf-8").splitlines()]
    head = [h.split("!")[0] for h in rows[0]]
    for row in rows[1:]:
        info = dict(zip(head, row))
        if info.get("Product") == product and info.get("Active") == "1":
            return info
    raise LookupError(f"в .build.info нет установленного продукта {product}")


class Storage:
    def __init__(self, install: Path, product: str):
        self.install = Path(install)
        self.data = self.install / "Data"
        self.build_key = build_info(self.install, product)["Build Key"]
        self.config = self._config(self.build_key)
        self.index: dict[bytes, tuple[int, int, int]] = {}
        self._load_indices()

    def _config(self, key: str) -> dict[str, list[str]]:
        out = {}
        for line in (self.data / "config" / key[:2] / key[2:4] / key).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().split()
        return out

    def _load_indices(self) -> None:
        latest: dict[int, tuple[int, str]] = {}
        for path in (self.data / "data").iterdir():
            name = path.name
            if name.endswith(".idx") and len(name) == 14:
                bucket, version = int(name[:2], 16), int(name[2:10], 16)
                if version >= latest.get(bucket, (-1, ""))[0]:
                    latest[bucket] = (version, name)
        for _, name in latest.values():
            with open(self.data / "data" / name, "rb") as f:
                header_len, _ = struct.unpack("<II", f.read(8))
                f.read(header_len)
                f.seek((8 + header_len + 0x0F) & ~0x0F)
                data_len, _ = struct.unpack("<II", f.read(8))
                raw = f.read(data_len)
            for i in range(0, len(raw) - 17, 18):
                key = raw[i:i + 9]
                high = raw[i + 9]
                low = struct.unpack(">I", raw[i + 10:i + 14])[0]
                if key not in self.index:
                    self.index[key] = ((high << 2) | (low >> 30), low & 0x3FFFFFFF,
                                       struct.unpack("<I", raw[i + 14:i + 18])[0])

    def read_ekey(self, ekey: bytes) -> bytes:
        archive, offset, size = self.index[ekey[:9]]
        with open(self.data / "data" / f"data.{archive:03d}", "rb") as f:
            f.seek(offset + 30)              # a 0x1E header: reversed key, size, flags, checksums
            return blte(f.read(size - 30))

    def ekeys_for(self, ckeys) -> dict[bytes, bytes]:
        """Encoded keys of the content keys asked (from the encoding table)."""
        want = set(ckeys)
        out: dict[bytes, bytes] = {}
        raw = self.read_ekey(bytes.fromhex(self.config["encoding"][1]))
        if raw[:2] != b"EN":
            raise ValueError("не таблица encoding")
        ck = raw[3]
        ek = raw[4]
        page_kb = struct.unpack(">H", raw[5:7])[0]
        pages = struct.unpack(">I", raw[9:13])[0]
        espec = struct.unpack(">I", raw[18:22])[0]
        pos = 22 + espec + pages * 32
        for _ in range(pages):
            page = raw[pos:pos + page_kb * 1024]
            pos += page_kb * 1024
            p = 0
            while p + 6 + ck <= len(page):
                count = page[p]
                if count == 0:
                    break
                ckey = page[p + 6:p + 6 + ck]
                if ckey in want:
                    out[ckey] = page[p + 6 + ck:p + 6 + ck + ek]
                p += 6 + ck + count * ek
        return out

    def root(self, wanted) -> dict[int, list[tuple[int, bytes]]]:
        """{FileDataID: [(locale flags, content key)]} for the FileDataIDs in `wanted`."""
        ckey = bytes.fromhex(self.config["root"][0])
        return parse_root(self.read_ekey(self.ekeys_for([ckey])[ckey]), wanted)

    def read_ckeys(self, ckeys) -> dict[bytes, bytes]:
        """The files with these content keys that this storage holds locally (retail downloads much of
        its data only when the game needs it, so a file it lists may not be on the disk)."""
        ekeys = self.ekeys_for(ckeys)
        out: dict[bytes, bytes] = {}
        for ckey, ekey in ekeys.items():
            try:
                out[ckey] = self.read_ekey(ekey)
            except (KeyError, ValueError, OSError, zlib.error, struct.error):   # struct.error: a block cut short
                continue
        return out

    def read_files(self, fdids, locale: str = "ruRU", others=()) -> dict[int, bytes]:
        """The files' bytes in `locale` - only files that have a recording of their own for it (a
        file shared by every locale is left out: for voices that is the English one). A file not in
        this storage is taken from `others` (another game's storages) by its content key: the same
        key is the same file, byte for byte."""
        flag, english = LOCALES[locale], LOCALES["enUS"]
        entries = self.root(fdids)
        chosen: dict[int, bytes] = {}
        for fdid, versions in entries.items():
            # an entry for every locale at once (its flags include enUS too) is the shared recording
            own = {ck for loc, ck in versions if loc & flag and not loc & english}
            if own:
                chosen[fdid] = next(iter(own))
        have = self.read_ckeys(chosen.values())
        own = len(have)
        for other in others:
            missing = [ck for ck in chosen.values() if ck not in have]
            if not missing:
                break
            have.update(other.read_ckeys(missing))
        # what has a recording of its own for the locale but is on no disk here (not downloaded yet)
        self.missing = [fdid for fdid, ckey in chosen.items() if ckey not in have]
        self.borrowed = len(have) - own
        return {fdid: have[ckey] for fdid, ckey in chosen.items() if ckey in have}


def parse_root(raw: bytes, wanted) -> dict[int, list[tuple[int, bytes]]]:
    """The root table ("TSFM", versions 1 and 2): {FileDataID: [(locale flags, content key)]} for
    the FileDataIDs in `wanted`."""
    wanted = set(wanted)
    if struct.unpack("<I", raw[:4])[0] != 0x4D465354:
        raise ValueError("не таблица root")
    a, b = struct.unpack("<II", raw[4:12])
    if a == 0x18:                                      # header size, version
        version = b
        total, named = struct.unpack("<II", raw[12:20])
        pos = 0x18
    else:
        version, total, named, pos = 1, a, b, 12
    allow_unnamed = total != named
    out: dict[int, list[tuple[int, bytes]]] = {}
    while pos < len(raw):
        if version >= 2:
            count, locale, f1, f2 = struct.unpack("<IIII", raw[pos:pos + 16])
            content = f1 | f2 | (raw[pos + 16] << 17)
            pos += 17
        else:
            count, content, locale = struct.unpack("<III", raw[pos:pos + 12])
            pos += 12
        deltas = struct.unpack(f"<{count}i", raw[pos:pos + 4 * count])
        pos += 4 * count
        keys_at = pos
        pos += 16 * count
        if not (allow_unnamed and content & 0x10000000):
            pos += 8 * count                           # name hashes
        fdid = -1
        for i, delta in enumerate(deltas):
            fdid += 1 + delta
            if fdid in wanted:
                out.setdefault(fdid, []).append((locale, raw[keys_at + 16 * i:keys_at + 16 * i + 16]))
    return out


def blte(data: bytes) -> bytes:
    """A BLTE-encoded block, decoded (plain and zlib chunks; encrypted ones raise ValueError)."""
    if data[:4] != b"BLTE":
        raise ValueError("не BLTE")
    header = struct.unpack(">I", data[4:8])[0]
    if header == 0:
        return _chunk(data[8:])
    count = struct.unpack(">I", b"\0" + data[9:12])[0]
    sizes, p = [], 12
    for _ in range(count):
        sizes.append(struct.unpack(">I", data[p:p + 4])[0])
        p += 24                                        # compressed, decompressed sizes, MD5
    out, p = [], header
    for size in sizes:
        out.append(_chunk(data[p:p + size]))
        p += size
    return b"".join(out)


def _chunk(c: bytes) -> bytes:
    mode = c[:1]
    if mode == b"N":
        return c[1:]
    if mode == b"Z":
        return zlib.decompress(c[1:])
    if mode == b"F":
        return blte(c[1:])
    raise ValueError(f"блок BLTE вида {mode!r} (зашифрован?)")
