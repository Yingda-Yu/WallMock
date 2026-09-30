"""
Generate three synthetic/original test artworks for WallMock case rendering.

These are safe to commit (original creations, no competitor artwork):
  1. color-block — geometric blocks for crop/alignment/masking validation
  2. tile-pattern — small seamless repeating pattern for tile mode
  3. transparent-artwork — RGBA with transparent regions for alpha testing
"""

import math
import numpy as np
from PIL import Image, ImageDraw

OUT_DIR = "tests/fixtures/artworks"


def generate_color_block():
    """Geometric color blocks with strong boundaries."""
    W, H = 1080, 2400
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Four quadrant blocks with distinct colors
    cx, cy = W // 2, H // 2

    # Top-left: warm coral
    d.rectangle([0, 0, cx, cy], fill=(255, 107, 107, 255))
    # Top-right: teal
    d.rectangle([cx, 0, W, cy], fill=(72, 191, 176, 255))
    # Bottom-left: golden yellow
    d.rectangle([0, cy, cx, H], fill=(255, 193, 79, 255))
    # Bottom-right: deep blue
    d.rectangle([cx, cy, W, H], fill=(62, 121, 192, 255))

    # Add diagonal stripes across center for alignment check
    for i in range(-W, W + H, 80):
        d.polygon(
            [(i, 0), (i + 40, 0), (i + 40 + H, H), (i + H, H)],
            fill=(255, 255, 255, 180)
        )

    # Add corner markers (circles at each corner)
    r = 60
    for x, y, color in [
        (r, r, (255, 255, 255, 255)),
        (W - r, r, (0, 0, 0, 255)),
        (r, H - r, (0, 0, 0, 255)),
        (W - r, H - r, (255, 255, 255, 255)),
    ]:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    # Add a labeled center cross
    d.line([cx - 50, cy, cx + 50, cy], fill=(255, 255, 255, 255), width=4)
    d.line([cx, cy - 50, cx, cy + 50], fill=(255, 255, 255, 255), width=4)

    return img


def generate_tile_pattern():
    """Small seamless repeating pattern (geometric dots and lines)."""
    tile_w, tile_h = 120, 120
    W, H = 1080, 2400

    # Create one tile
    tile = Image.new("RGBA", (tile_w, tile_h), (245, 235, 220, 255))
    td = ImageDraw.Draw(tile)

    # Diagonal lines
    for i in range(0, tile_w + tile_h, 20):
        td.line(
            [(i, 0), (i - tile_h, tile_h)],
            fill=(180, 140, 90, 200),
            width=2,
        )

    # Central dot
    cx, cy = tile_w // 2, tile_h // 2
    td.ellipse(
        [cx - 18, cy - 18, cx + 18, cy + 18],
        fill=(60, 80, 120, 255)
    )
    td.ellipse(
        [cx - 10, cy - 10, cx + 10, cy + 10],
        fill=(120, 160, 200, 255)
    )

    # Corner accent dots (seamless — split across tile edges)
    r = 8
    for x, y in [(0, 0), (tile_w, 0), (0, tile_h), (tile_w, tile_h)]:
        td.ellipse([x - r, y - r, x + r, y + r], fill=(200, 80, 80, 255))

    # Tile the pattern
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for y in range(0, H, tile_h):
        for x in range(0, W, tile_w):
            img.paste(tile, (x, y))

    return img


def generate_transparent_artwork():
    """RGBA artwork with transparent regions."""
    W, H = 1080, 2400
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Transparent background with scattered solid shapes

    # Large semi-transparent gradient circle
    cx, cy = W // 2, H // 2
    for i in range(200, 0, -1):
        r = i * 2
        alpha = int(255 * (1 - i / 200) * 0.6)
        d.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(100, 50, 150, alpha)
        )

    # Solid accent shapes
    # Diamond
    d.polygon(
        [(cx, cy - 300), (cx + 150, cy), (cx, cy + 300), (cx - 150, cy)],
        fill=(255, 200, 50, 255)
    )

    # Outline ring (hollow)
    d.ellipse(
        [cx - 400, cy - 400, cx + 400, cy + 400],
        outline=(255, 255, 255, 220), width=8
    )
    d.ellipse(
        [cx - 360, cy - 360, cx + 360, cy + 360],
        outline=(255, 100, 100, 180), width=4
    )

    # Corner triangles (fully transparent in centers)
    for corner, color in [
        ((0, 0, 300, 300), (200, 60, 60, 255)),
        ((W - 300, 0, W, 300), (60, 200, 120, 255)),
        ((0, H - 300, 300, H), (60, 100, 200, 255)),
        ((W - 300, H - 300, W, H), (200, 200, 60, 255)),
    ]:
        x1, y1, x2, y2 = corner
        d.polygon(
            [(x1, y1), (x2, y1), (x2, y2)],
            fill=color
        )

    # Vertical text-like stripes (alternating transparent/solid)
    for x in range(0, W, 60):
        if (x // 60) % 2 == 0:
            d.line([x, 0, x, H], fill=(255, 255, 255, 30), width=30)

    return img


if __name__ == "__main__":
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Generating test artworks...")

    cb = generate_color_block()
    cb.save(os.path.join(OUT_DIR, "color-block.png"))
    print(f"  color-block.png  {cb.size}")

    tp = generate_tile_pattern()
    tp.save(os.path.join(OUT_DIR, "tile-pattern.png"))
    print(f"  tile-pattern.png  {tp.size}")

    ta = generate_transparent_artwork()
    ta.save(os.path.join(OUT_DIR, "transparent-artwork.png"))
    print(f"  transparent-artwork.png  {ta.size}")

    print("Done.")
