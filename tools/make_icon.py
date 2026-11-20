"""Draws the addon icon: a golden speech bubble with sound waves on a dark arcane background.
Writes addon/BarrensVoice/Icon.tga (64x64, what the game reads), the launcher's window, tray and
shortcut icon companion/bv/launcher/icon.ico (16-256 px), tools/icon_preview.png, the CurseForge and Wago
projects' logo docs/images/logo.png (CurseForge: 400x400, not webp), the chat's icon
addon/BarrensVoice/Media/chat.tga (the bubble alone on a clear background: before «Barrens Voice:» in the chat,
whose background shows through), and the smiley of the «Помощь» texts, addon/BarrensVoice/Media/smile.tga (the
game's fonts have no emoji).
Run: mise run icon"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 512                     # drawn large, scaled down for smooth edges
ROOT = Path(__file__).resolve().parents[1]


def radial(size, inner, outer):
    img = Image.new("RGB", (size, size))
    px = img.load()
    c = size / 2
    for y in range(size):
        for x in range(size):
            t = min(1.0, math.hypot(x - c * 0.85, y - c * 0.8) / (size * 0.72))
            px[x, y] = tuple(int(inner[i] + (outer[i] - inner[i]) * t) for i in range(3))
    return img


def main():
    img = radial(S, (52, 40, 92), (8, 6, 20)).convert("RGBA")
    d = ImageDraw.Draw(img)

    # Bevelled frame, like the game's ability icons.
    d.rectangle([0, 0, S - 1, S - 1], outline=(150, 115, 50, 255), width=14)
    d.rectangle([14, 14, S - 15, S - 15], outline=(40, 28, 10, 255), width=6)
    symbol(img)
    finish(img)


def symbol(img):
    """The speech bubble with its dots and the sound waves, drawn onto `img` (S x S)."""
    # Speech bubble: shadow, body, tail.
    def bubble(draw, dx, dy, fill):
        draw.rounded_rectangle([70 + dx, 110 + dy, 330 + dx, 330 + dy], radius=95, fill=fill)
        draw.polygon([(120 + dx, 300 + dy), (95 + dx, 420 + dy), (205 + dx, 318 + dy)], fill=fill)

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bubble(ImageDraw.Draw(shadow), 14, 16, (0, 0, 0, 170))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    body = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bubble(ImageDraw.Draw(body), 0, 0, (255, 255, 255, 255))
    gold = Image.new("RGBA", (S, S))
    gp = gold.load()
    for y in range(S):                      # vertical gold gradient
        t = y / S
        gp_row = (int(255 - 60 * t), int(222 - 95 * t), int(120 - 90 * t), 255)
        for x in range(S):
            gp[x, y] = gp_row
    img.paste(gold, (0, 0), body)
    rim = ImageDraw.Draw(img)
    rim.rounded_rectangle([70, 110, 330, 330], radius=95, outline=(110, 70, 20, 255), width=8)

    # Three dots in the bubble: someone is talking.
    for cx in (140, 200, 260):
        rim.ellipse([cx - 20, 200, cx + 20, 240], fill=(70, 40, 10, 255))

    # Sound waves to the right.
    for i, r in enumerate((70, 120, 170)):
        box = [290 - r, 220 - r, 290 + r, 220 + r]
        rim.arc(box, start=-38, end=38, fill=(120, 220, 255, 255 - i * 45), width=24 - i * 4)


def chat():
    """The chat's icon: the bubble and waves on a clear background, cut to them (a square, a little room round),
    32x32. The framed icon is opaque - a dark square on the chat, whose background is clear."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    symbol(img)
    left, top, right, bottom = img.getchannel("A").getbbox()
    side = max(right - left, bottom - top) + 16
    cx, cy = (left + right) // 2, (top + bottom) // 2
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(img.crop((cx - side // 2, cy - side // 2, cx - side // 2 + side, cy - side // 2 + side)))
    square.resize((32, 32), Image.LANCZOS).save(ROOT / "addon" / "BarrensVoice" / "Media" / "chat.tga", rle=False)


def finish(img):
    icon = img.resize((64, 64), Image.LANCZOS)
    icon.save(ROOT / "addon" / "BarrensVoice" / "Icon.tga")
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "tools" / "icon_preview.png")
    img.resize((400, 400), Image.LANCZOS).save(ROOT / "docs" / "images" / "logo.png")
    # each size scaled from the large drawing (Pillow would scale the 256 one down itself, less sharply)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [img.resize((n, n), Image.LANCZOS) for n in sizes]
    frames[-1].save(ROOT / "companion" / "bv" / "launcher" / "icon.ico", sizes=[(n, n) for n in sizes],
                    append_images=frames[:-1])
    print("ok")


def smile():
    """A small yellow smiley, drawn large and scaled down (32x32, as the game wants a power of two)."""
    n = 256
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, n - 8, n - 8], fill=(255, 204, 77, 255), outline=(120, 80, 10, 255), width=10)
    for cx in (92, 164):                                   # the eyes
        d.ellipse([cx - 14, 82, cx + 14, 124], fill=(70, 45, 10, 255))
    d.arc([64, 84, 192, 196], start=25, end=155, fill=(70, 45, 10, 255), width=16)   # the smile
    img.resize((32, 32), Image.LANCZOS).save(ROOT / "addon" / "BarrensVoice" / "Media" / "smile.tga", rle=False)


if __name__ == "__main__":
    smile()
    chat()
    main()
