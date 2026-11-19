"""The launcher's look, drawn on a tkinter canvas: dark stone, gold frames, the game's red lacquer
button. tkinter's own widgets cannot look like this, so everything but the text boxes is drawn."""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT_FILE = HERE / "fonts" / "Forum-Regular.ttf"      # Forum (OFL): a serif with Cyrillic
ICON_FILE = HERE / "icon.ico"
GOLD, PARCHMENT, DIM, EDGE = "#ffd100", "#f0dcae", "#a8957a", "#8a6420"
STONE_TOP, STONE_BOTTOM = "#2a1a0f", "#0b0705"


def register_font() -> str:
    """Forum for this process only (nothing is installed into Windows); its family, or a fallback."""
    try:
        if sys.platform == "win32":
            import ctypes
            if ctypes.windll.gdi32.AddFontResourceExW(str(FONT_FILE), 0x10, 0):    # FR_PRIVATE
                return "Forum"
        elif sys.platform == "darwin":
            import ctypes
            import ctypes.util
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
            ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            raw = str(FONT_FILE).encode()
            url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
            ct.CTFontManagerRegisterFontsForURL(url, 1, None)                     # process scope
            return "Forum"
    except Exception:  # noqa: BLE001 - a plainer serif then
        pass
    return "Georgia"


class ScaledCanvas(tk.Canvas):
    """A canvas drawn in design pixels (a 100 % screen) and shown at the screen's scale: coordinates,
    line widths, font sizes and embedded boxes are multiplied by `scale` as they are created, so the
    drawing code never thinks about it. With the process DPI-aware (app.main) Windows no longer
    stretches the window's bitmap: at 125-200 % text and frames stay sharp."""

    LINES = {"line", "polygon", "rectangle", "oval", "arc"}

    def __init__(self, master, scale: float = 1.0, **kw):
        self.s = scale
        super().__init__(master, **self._sized(kw))

    def _sized(self, kw: dict) -> dict:
        return {k: round(v * self.s) if k in ("width", "height") and isinstance(v, (int, float)) else v
                for k, v in kw.items()}

    def configure(self, cnf=None, **kw):
        return super().configure(cnf, **self._sized(kw))

    config = configure

    def font(self, font):
        """A font tuple with its pixel size scaled ("Segoe UI", -13) → ("Segoe UI", -16) at 125 %."""
        if isinstance(font, tuple) and len(font) >= 2 and isinstance(font[1], int):
            return (font[0], round(font[1] * self.s), *font[2:])
        return font

    def _flat(self, args):
        for a in args:
            if isinstance(a, (tuple, list)):
                yield from self._flat(a)
            else:
                yield a * self.s if isinstance(a, (int, float)) else a

    def _create(self, item_type, args, kw):
        kw = dict(kw)
        if "font" in kw:
            kw["font"] = self.font(kw["font"])
        if item_type in self.LINES and isinstance(kw.get("width"), (int, float)):
            kw["width"] = max(1, round(kw["width"] * self.s))
        elif item_type in ("text", "window"):           # text: its wrap width; window: the box's size
            kw = self._sized(kw)
        return super()._create(item_type, tuple(self._flat(args)), kw)


def mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


class Painter:
    """Drawing on one canvas; `redraw` (the window's) draws everything again after a change."""

    def __init__(self, canvas: tk.Canvas, title_font: str):
        self.c = canvas
        self.title_font = title_font
        win = sys.platform == "win32"
        # sizes in pixels (negative): in points tkinter would scale them with the screen's DPI
        self.body = ("Segoe UI", -13) if win else ("Helvetica Neue", -13)
        self.small = ("Segoe UI", -12) if win else ("Helvetica Neue", -12)
        self.mono = ("Consolas", -11) if win else ("Menlo", -11)
        self.hover_cursor = "hand2"
        self._fonts: dict = {}                                    # for fit: measuring fonts, made once
        self.tips: dict[str, str] = {}                            # tag -> its hint, shown on a rest of the mouse
        self._tip = self._tip_job = None

    def background(self, w: int, h: int) -> None:
        c = self.c
        for y in range(0, h, 4):                                   # dark stone, warmer at the top
            c.create_rectangle(0, y, w, y + 4, fill=mix(STONE_TOP, STONE_BOTTOM, y / h), width=0)
        top = mix(STONE_TOP, STONE_BOTTOM, 42 / h)
        for k in range(24):                                        # the glow behind the title
            r = w * 0.45 - k * w * 0.017
            c.create_oval(w / 2 - r, 42 - r * 0.42, w / 2 + r, 42 + r * 0.42, width=0,
                          fill=mix(top, "#5a3612", (k + 1) / 24 * 0.55))
        c.create_rectangle(3, 3, w - 4, h - 4, outline="#6b4c1c")
        c.create_rectangle(6, 6, w - 7, h - 7, outline="#c9a24a")

    def title(self, w: int, text: str, subtitle: str = "", size: int = 40, y: int = 44) -> None:
        self.c.create_text(w / 2 + 1, y + 2, text=text, fill="#000000", font=(self.title_font, -size))
        self.c.create_text(w / 2, y, text=text, fill=GOLD, font=(self.title_font, -size))
        if subtitle:
            self.c.create_text(w / 2, y + 36, text=subtitle, fill=DIM, font=self.small)

    def rounded(self, x0, y0, x1, y1, r=6, **kw):
        """A rectangle with round corners: a smoothed polygon through its corners' points."""
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
               x0, y1 - r, x0, y0 + r, x0, y0]
        return self.c.create_polygon(pts, smooth=True, **kw)

    def panel(self, x0, y0, x1, y1, title: str = "", tag: str = "") -> None:
        self.rounded(x0, y0, x1, y1, r=8, fill="#160f09", outline=EDGE, width=2, tags=tag or ())
        if title:
            self.c.create_text(x0 + 14, y0 + 18, text=title, anchor="w", fill=GOLD, font=(self.title_font, -20),
                               tags=tag or ())

    def hover(self, tag: str, on, off) -> None:
        self.c.tag_bind(tag, "<Enter>", lambda e: (on(), self.c.config(cursor=self.hover_cursor), self._tip_soon(tag)))
        self.c.tag_bind(tag, "<Leave>", lambda e: (off(), self.c.config(cursor=""), self.hide_tip()))

    def click(self, tag: str, action) -> None:
        if action:
            self.c.tag_bind(tag, "<Button-1>", lambda e: (self.hide_tip(), action()))

    # --- hints: a small window by the mouse after it rests half a second on an item with a tip ---------

    def _tip_soon(self, tag: str) -> None:
        self.hide_tip()
        if tag in self.tips:
            self._tip_job = self.c.after(500, lambda: self._show_tip(self.tips.get(tag)))

    def _show_tip(self, text: str | None) -> None:
        self._tip_job = None
        if not text:
            return
        s = getattr(self.c, "s", 1.0)
        self._tip = tip = tk.Toplevel(self.c)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        font = self.c.font(self.small) if hasattr(self.c, "font") else self.small
        tk.Label(tip, text=text, justify="left", wraplength=round(330 * s), font=font, bg="#23170d", fg=PARCHMENT,
                 relief="solid", bd=1, padx=round(8 * s), pady=round(5 * s)).pack()
        tip.update_idletasks()
        x = min(self.c.winfo_pointerx() + 14, self.c.winfo_screenwidth() - tip.winfo_width() - 8)
        y = self.c.winfo_pointery() + 20
        if y + tip.winfo_height() > self.c.winfo_screenheight() - 40:
            y = self.c.winfo_pointery() - tip.winfo_height() - 10
        tip.wm_geometry(f"+{max(0, x)}+{max(0, y)}")

    def hide_tip(self) -> None:
        if self._tip_job:
            self.c.after_cancel(self._tip_job)
            self._tip_job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def lacquer(self, x0, y0, x1, y1, top, bottom, tag) -> None:
        """Red lacquer in round corners: gradient lines clipped to the rounding, under the gold edge."""
        self.c.delete(tag + "fill")
        s = getattr(self.c, "s", 1.0)
        r, rows = 7, round((y1 - y0) * s)                       # one line per screen pixel row
        for i in range(rows):
            edge = min(i, rows - 1 - i) / s
            inset = r - (r * r - (r - edge) ** 2) ** 0.5 if edge < r else 0
            self.c.create_line(x0 + inset, y0 + i / s, x1 - inset, y0 + i / s, fill=mix(top, bottom, i / rows),
                               tags=(tag, tag + "fill"))
        self.c.tag_lower(tag + "fill", tag + "edge")

    def big_button(self, x0, y0, x1, y1, text, tag, action=None, enabled=True) -> None:
        """The game's red button (Play); dimmed and deaf when not `enabled`."""
        c = self.c
        top, bottom = ("#b3241f", "#4d0b08") if enabled else ("#4a2a20", "#24130e")
        self.rounded(x0, y0, x1, y1, r=8, fill="", outline="#d4a73a" if enabled else "#6b5226", width=2,
                     tags=(tag, tag + "edge"))
        self.lacquer(x0, y0, x1, y1, top, bottom, tag)
        c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=text, fill=GOLD if enabled else DIM,
                      font=(self.title_font, -26), tags=tag)
        if enabled:
            self.hover(tag, lambda: self.lacquer(x0, y0, x1, y1, "#d23a2c", "#5c0f0b", tag),
                       lambda: self.lacquer(x0, y0, x1, y1, top, bottom, tag))
            self.click(tag, action)

    def button(self, x0, y0, x1, y1, text, tag, action=None, font=None, tip=None) -> None:
        """A small dark button with a gold edge on hover."""
        if tip:
            self.tips[tag] = tip
        self.rounded(x0, y0, x1, y1, r=5, fill="#23170d", outline=EDGE, tags=(tag, tag + "box"))
        self.c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=text, fill=PARCHMENT, font=font or self.body,
                           tags=(tag, tag + "text"))
        self.hover(tag, lambda: (self.c.itemconfig(tag + "box", outline=GOLD), self.c.itemconfig(tag + "text", fill=GOLD)),
                   lambda: (self.c.itemconfig(tag + "box", outline=EDGE), self.c.itemconfig(tag + "text", fill=PARCHMENT)))
        self.click(tag, action)

    def link(self, x, y, text, tag, action, anchor="w", font=None, tip=None) -> None:
        """Gold text that acts as a button."""
        if tip:
            self.tips[tag] = tip
        self.c.create_text(x, y, text=text, anchor=anchor, fill=GOLD, font=font or self.small, tags=tag)
        self.hover(tag, lambda: self.c.itemconfig(tag, fill="#fff2a8"), lambda: self.c.itemconfig(tag, fill=GOLD))
        self.click(tag, action)

    def check(self, x, y, text, on: bool, tag, action, tip=None, enabled: bool = True) -> None:
        """A check box with its label; not `enabled`: grey, its value kept, no click - its hint says why."""
        if tip:
            self.tips[tag] = tip
        edge = "#b8862b" if enabled else "#5a4220"
        self.rounded(x, y - 8, x + 16, y + 8, r=3, fill="#1b120a", outline=edge, tags=(tag, tag + "box"))
        if on:
            self.c.create_line(x + 3, y, x + 7, y + 5, x + 14, y - 6, fill=GOLD if enabled else DIM, width=3, tags=tag)
        self.c.create_text(x + 26, y, text=text, anchor="w", fill=PARCHMENT if enabled else DIM, font=self.body, tags=tag)
        if not enabled:                     # the hint only, on hover; a tag's bindings outlive a redraw: the click off
            self.c.tag_unbind(tag, "<Button-1>")
            self.c.tag_bind(tag, "<Enter>", lambda e: self._tip_soon(tag))
            self.c.tag_bind(tag, "<Leave>", lambda e: self.hide_tip())
            return
        self.hover(tag, lambda: self.c.itemconfig(tag + "box", outline=GOLD),
                   lambda: self.c.itemconfig(tag + "box", outline="#b8862b"))
        self.click(tag, action)

    def fit(self, text: str, font, width: int) -> str:
        """`text` cut with "…" to fit `width` pixels."""
        s = getattr(self.c, "s", 1.0)
        f = self._fonts.get(font)
        if f is None:
            f = self._fonts[font] = tkfont.Font(font=self.c.font(font) if s != 1 else font)
        width = width * s
        if f.measure(text) <= width:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if f.measure(text[:mid] + "…") <= width:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + "…"

    def wrap(self, text: str, font, width: int, indent: str = "") -> list[str]:
        """`text` broken at spaces into lines of at most `width` pixels (a word longer than a line is cut by
        `fit`); the lines after the first start with `indent`. A fallback: the main window's lines are written
        to fit one line, and one that does not is better wrapped than cut."""
        lines, line = [], ""
        for word in text.split(" "):
            candidate = f"{line} {word}" if line else (indent + word if lines else word)
            if line and self.measure(candidate, font) > width:
                lines.append(line)
                line = indent + word
            else:
                line = candidate
        lines.append(line)
        return [self.fit(x, font, width) for x in lines]

    def measure(self, text: str, font) -> float:
        """The width of `text` in design pixels."""
        s = getattr(self.c, "s", 1.0)
        f = self._fonts.get(font)
        if f is None:
            f = self._fonts[font] = tkfont.Font(font=self.c.font(font) if s != 1 else font)
        return f.measure(text) / s

    def entry(self, x, y, width, value: str, readonly=False) -> tk.Entry:
        """A text box in the same colours, placed on the canvas."""
        var = tk.StringVar(value=value)
        box = tk.Entry(self.c, textvariable=var, font=self.c.font(self.body) if hasattr(self.c, "font") else self.body, bg="#0d0906", fg=PARCHMENT, insertbackground=GOLD,
                       readonlybackground="#0d0906", relief="flat", highlightthickness=1,
                       highlightbackground="#5a4220", highlightcolor=GOLD, selectbackground="#6b4c1c")
        if readonly:
            box.config(state="readonly")
        box.var = var
        self.c.create_window(x, y, window=box, anchor="w", width=width, height=26)
        return box


def window_icon(root: tk.Tk) -> None:
    try:
        root.iconbitmap(default=str(ICON_FILE))
    except tk.TclError:
        pass

