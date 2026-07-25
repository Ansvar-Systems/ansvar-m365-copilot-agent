#!/usr/bin/env python3
"""Render appPackage/color.png and appPackage/outline.png from assets/ansvar-mark.svg.

Source: the shipped Ansvar brand mark (https://ansvar.eu/ansvar-mark.svg), an
outline-converted vector with no font dependency: one violet plate plus one
off-white glyph path (a ruled frame enclosing the "ANSVAR" wordmark and "AI").

color.png   192x192, brand-violet plate, full glyph inside the 120x120 safe region.
outline.png 32x32, pure white on transparent. The wordmark is dropped and "AI" is
            recentred in the frame: at 32 px the wordmark aliases into an
            illegible smear, while the frame and "AI" stay crisp.

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

# Glyph bands, as fractions of the glyph's own bounding box. Measured from the
# source path's row ink profile; re-measure if the brand mark is redrawn.
WORDMARK_BAND = (0.140, 0.310)
AI_BAND = (0.315, 0.860)
FRAME_INSET_X = 0.030
FRAME_INTERIOR_Y = (0.030, 0.970)


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
    w, h = g.size
    pix = g.load()
    inset = int(FRAME_INSET_X * w)

    ai = g.crop((inset, int(AI_BAND[0] * h), w - inset, int(AI_BAND[1] * h)))
    ai = ai.crop(ai.getbbox())

    # Clear the frame interior (wordmark + old "AI"), keeping the ruled frame.
    for y in range(int(WORDMARK_BAND[0] * h), int(AI_BAND[1] * h)):
        for x in range(inset, w - inset):
            pix[x, y] = (0, 0, 0, 0)

    top = int(FRAME_INTERIOR_Y[0] * h)
    bottom = int(FRAME_INTERIOR_Y[1] * h)
    g.alpha_composite(ai, ((w - ai.width) // 2, top + ((bottom - top) - ai.height) // 2))

    g.resize((32, 32), Image.LANCZOS).save(OUT / "outline.png")
    print("outline.png  32x32  white frame + recentred AI on transparent")


if __name__ == "__main__":
    render_color()
    render_outline()
