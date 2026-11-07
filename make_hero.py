"""Generate a labelled hero PNG. Used to seed the initial hero and to produce a
visibly different test image for live verification (so an 'updated' hero is
obviously not the original)."""

import sys

from PIL import Image, ImageDraw


def make(path: str, label: str, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    w, h = 1200, 630
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):  # vertical gradient top -> bottom
        t = y / (h - 1)
        r = round(top[0] + (bottom[0] - top[0]) * t)
        g = round(top[1] + (bottom[1] - top[1]) * t)
        b = round(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    draw = ImageDraw.Draw(img)
    draw.text((60, 60), "FORGE STUDIO", fill=(255, 255, 255))
    draw.text((60, 120), label, fill=(255, 255, 255))
    img.save(path, "PNG")
    print(f"wrote {path}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "initial"
    if which == "initial":
        make("site/hero.png", "Original hero (violet)", (109, 94, 252), (24, 18, 64))
    elif which == "test":
        make("test/new-hero.png", "Updated via form upload (emerald)", (16, 185, 129), (6, 48, 38))
