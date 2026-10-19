"""Regenerate the favicon set from ../icon.png after the logo changes: python3 assets/favicon/make.py (needs Pillow).
Small sizes use a tight crop of the anvil, which stays readable at 16px; large ones keep the whole logo.
The docs build (harness_map.py --docs-only) only copies these files, so it needs no image library."""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
src = Image.open(HERE.parent / "icon.png").convert("RGBA")


def tight(size):
    im = src.crop((84, 70, 444, 430)).resize((size * 8, size * 8), Image.LANCZOS)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=im.width * 0.2, fill=255)
    im.putalpha(mask)
    return im.resize((size, size), Image.LANCZOS)


def full(size):
    return src.resize((size, size), Image.LANCZOS)


tight(48).save(HERE / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
tight(96).save(HERE / "icon-96.png", optimize=True)          # Google search results: a multiple of 48px
full(180).save(HERE / "apple-touch-icon.png", optimize=True)
full(192).save(HERE / "icon-192.png", optimize=True)
full(512).save(HERE / "icon-512.png", optimize=True)
