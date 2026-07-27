#!/usr/bin/env python3
"""Render appPackage/color.png and appPackage/outline.png from assets/ansvar-mark.svg.

Source: the shipped Ansvar brand mark (https://ansvar.eu/ansvar-mark.svg), an
outline-converted vector with no font dependency: one violet plate plus one
off-white glyph path (a ruled frame enclosing the "ANSVAR" wordmark and "AI").

color.png   192x192, brand-violet plate, full glyph inside the 120x120 safe region.
outline.png 32x32, pure white on transparent, the SAME full glyph as color.png.
            Store validation requires the outline icon to be identical to the
            colour icon in design (Teams store guidelines; validation round 1,
            issue 7) — do not simplify or recompose the glyph here even where a
            reduced mark would render crisper at 32 px.

Run: python3 scripts/render-icons.py
"""
import io
import re
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "ansvar-mark.svg"
OUT = ROOT / "appPackage"

BRAND = (0x63, 0x55, 0xE6, 0xFF)  # #6355E6, the plate colour in the source mark
GLYPH_OFF_WHITE = "#f3f6f6"

def glyph(colour: str, size: int = 2400) -> Image.Image:
    """Render the mark's glyph path alone, cropped to its ink, in `colour`."""
    svg = SRC.read_text()
    svg = re.sub(r"<rect[^>]*/>", "", svg)  # drop the violet plate
    svg = svg.replace(GLYPH_OFF_WHITE, colour)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    return im.crop(im.getbbox())


def render_color() -> None:
    g = glyph(GLYPH_OFF_WHITE)
    g.thumbnail((120, 120), Image.LANCZOS)  # fit the 120x120 safe region
    canvas = Image.new("RGBA", (192, 192), BRAND)
    canvas.alpha_composite(g, ((192 - g.width) // 2, (192 - g.height) // 2))
    canvas.save(OUT / "color.png")
    print(f"color.png   192x192  glyph {g.width}x{g.height} on #6355E6")


def render_outline() -> None:
    g = glyph("#ffffff")
    g.thumbnail((32, 32), Image.LANCZOS)
    canvas = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    canvas.alpha_composite(g, ((32 - g.width) // 2, (32 - g.height) // 2))
    canvas.save(OUT / "outline.png")
    print("outline.png  32x32  full glyph, white on transparent")


if __name__ == "__main__":
    render_color()
    render_outline()
