"""Render the spinning 3D "GF" monogram shown on the profile card as ASCII frames.

Run it once, and again whenever you change the letters or the look:

    pip install pillow
    python scripts/monogram.py

It writes assets/monogram.json: FRAMES frames of ROWS x COLS characters, one
full turn around the vertical axis, starting face-on. build_card.py plays them
back (holding the face-on frame for a moment) and needs no third-party packages.

How it works: the letters are rasterised into a mask, extruded into a slab with
bevelled front and back faces, sampled into points with surface normals, then
rotated, projected and z-buffered into a character grid. Each cell's glyph comes
from how much light the nearest surface catches, the same way donut.c shades
its torus.
"""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent

# The art block on the card is COLS x ROWS characters, each 7.2px wide and 14.2px
# tall, matching ART_COLS / ART_CHAR / ART_LINE in build_card.py.
COLS, ROWS = 52, 35
CELL_ASPECT = 14.2 / 7.2
FRAMES = 48

# Dim to bright.
RAMP = ".,-~:;=!*#$@"

DEPTH = 0.17  # half the slab's thickness, in units where the monogram is 2 tall
BEVEL = 5.0  # how far the front and back faces round off at their edges
TILT = -0.22  # radians around the horizontal axis: look slightly down onto the top edges
LIGHT = (-1.6, 2.4, -5.0)  # a point light up, left and in front of the letters
CAMERA = 5.0  # distance from the camera to the centre of the monogram


def glyph(text, font, size=320):
    font = ImageFont.truetype(font, size)
    left, top, right, bottom = font.getbbox(text)
    img = Image.new("L", (right - left + 20, bottom - top + 20), 0)
    ImageDraw.Draw(img).text((10 - left, 10 - top), text, font=font, fill=255)
    return img.crop(img.getbbox())


def monogram_mask(letters, font, gap=40, resolution=180):
    """The letters stacked into one mask, scaled so its longest side is `resolution` samples."""
    parts = [glyph(c, font) for c in letters]
    width = max(p.width for p in parts)
    height = sum(p.height for p in parts) + gap * (len(parts) - 1)
    mask = Image.new("L", (width, height), 0)
    y = 0
    for p in parts:
        mask.paste(p, ((width - p.width) // 2, y))
        y += p.height + gap
    scale = resolution / max(mask.size)
    return mask.resize((round(mask.width * scale), round(mask.height * scale)), Image.Resampling.LANCZOS)


def surface(mask):
    """Points on the extruded slab, each with its outward unit normal."""
    w, h = mask.size
    soft = mask.filter(ImageFilter.GaussianBlur(3))
    inside = lambda x, y: 0 <= x < w and 0 <= y < h and mask.getpixel((x, y)) >= 128
    s = lambda x, y: soft.getpixel((min(max(x, 0), w - 1), min(max(y, 0), h - 1))) / 255
    unit = 2 / h
    points = []
    for py in range(h):
        for px in range(w):
            if not inside(px, py):
                continue
            x, y = (px - w / 2) * unit, -(py - h / 2) * unit
            # Gradient of the blurred mask: points inward, and grows near the edges.
            gx = (s(px + 1, py) - s(px - 1, py)) / 2
            gy = -(s(px, py + 1) - s(px, py - 1)) / 2
            front = normalise((-gx * BEVEL, -gy * BEVEL, -1))
            points.append(((x, y, -DEPTH), front))
            points.append(((x, y, DEPTH), (front[0], front[1], -front[2])))
            if all(inside(px + dx, py + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                continue
            side = normalise((-gx, -gy, 0)) if gx or gy else (0, 0, -1)
            for i in range(10):
                points.append(((x, y, -DEPTH + 2 * DEPTH * i / 9), side))
    return points


def normalise(v):
    length = math.sqrt(sum(c * c for c in v)) or 1
    return tuple(c / length for c in v)


def render(points, theta):
    ct, st = math.cos(theta), math.sin(theta)
    cx, sx = math.cos(TILT), math.sin(TILT)
    # Rows per unit, scaled so the face-on monogram (2 units tall) leaves room for perspective to grow it.
    # Cells are about twice as tall as wide, so a unit spans CELL_ASPECT times as many columns.
    k1 = (ROWS - 4) / 2 * CAMERA
    depth = [[0.0] * COLS for _ in range(ROWS)]
    grid = [[" "] * COLS for _ in range(ROWS)]
    clipped = False
    for (x, y, z), (nx, ny, nz) in points:
        # Spin around the vertical axis, then tilt towards the camera.
        x1, z1 = x * ct + z * st, -x * st + z * ct
        m1, n1 = nx * ct + nz * st, -nx * st + nz * ct
        y2, z2 = y * cx - z1 * sx, y * sx + z1 * cx
        m2, n2 = ny * cx - n1 * sx, ny * sx + n1 * cx
        ooz = 1 / (CAMERA + z2)
        col = int(COLS / 2 + k1 * ooz * x1 * CELL_ASPECT)
        row = int(ROWS / 2 - k1 * ooz * y2)
        if not (0 <= col < COLS and 0 <= row < ROWS):
            clipped = True
            continue
        if ooz <= depth[row][col]:
            continue
        depth[row][col] = ooz
        to_light = normalise((LIGHT[0] - x1, LIGHT[1] - y2, LIGHT[2] - z2))
        lum = max(0.0, m1 * to_light[0] + m2 * to_light[1] + n2 * to_light[2])
        grid[row][col] = RAMP[min(len(RAMP) - 1, round(lum ** 0.85 * (len(RAMP) - 1)))]
    return ["".join(r).rstrip() for r in grid], clipped


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--letters", default="GF")
    parser.add_argument("--font", default="/System/Library/Fonts/Supplemental/Arial Black.ttf",
                        help="a heavy TrueType font")
    parser.add_argument("--out", type=Path, default=ROOT / "assets" / "monogram.json")
    parser.add_argument("--preview", type=int, metavar="N", help="print frame N instead of writing")
    args = parser.parse_args()

    points = surface(monogram_mask(args.letters, args.font))
    frames = []
    for i in range(FRAMES):
        frame, clipped = render(points, 2 * math.pi * i / FRAMES)
        if clipped:
            print(f"warning: frame {i} runs off the edge of the block")
        frames.append(frame)
    if args.preview is not None:
        print("\n".join(frames[args.preview]))
        return
    args.out.write_text(json.dumps({"cols": COLS, "rows": ROWS, "frames": frames}) + "\n", encoding="utf-8")
    print(f"wrote {len(frames)} frames to {args.out}")


if __name__ == "__main__":
    main()
