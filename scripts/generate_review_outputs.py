"""Generate review images for P2/P3 vertical slice.

Outputs per artwork:
  - Full render (case-{name}.png)
  - Camera region crop (case-{name}__camera.png)
  - Four corner crops (case-{name}__corner-tl.png, -tr.png, -bl.png, -br.png)
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.case_template_loader import load_case_template
from core.case_renderer import render_case

TEMPLATE_DIR = os.path.join(
    "assets", "case_templates", "apple", "iphone-17e", "hard", "rear"
)
TEMPLATE_JSON = os.path.join(TEMPLATE_DIR, "template.json")
FIXTURES_DIR = os.path.join("tests", "fixtures")
OUTPUT_DIR = os.path.join("tests", "fixtures", "review_outputs")

ARTWORKS = [
    ("color-block", "artworks/color-block.png", "cover"),
    ("tile-pattern", "artworks/tile-pattern.png", "tile"),
    ("transparent-artwork", "artworks/transparent-artwork.png", "cover"),
]

# Camera region (approximate — based on template generator values)
CAM_X, CAM_Y, CAM_W, CAM_H = 450, 80, 760, 240

# Corner crop size (from each corner of print region)
CORNER_SIZE = 200
PRINT_X, PRINT_Y, PRINT_W, PRINT_H = 335, 45, 930, 1910


def save_crop(img, name, label, x, y, w, h):
    """Crop and save, clamping to image bounds."""
    iw, ih = img.size
    x = max(0, min(x, iw - 1))
    y = max(0, min(y, ih - 1))
    w = min(w, iw - x)
    h = min(h, ih - y)
    crop = img.crop((x, y, x + w, y + h))
    out_path = os.path.join(OUTPUT_DIR, f"{name}__{label}.png")
    crop.save(out_path, "PNG")
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  {label}: {crop.size} -> {out_path} ({size_kb:.1f} KB)")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    template = load_case_template(TEMPLATE_JSON)
    print(f"Template: {template.id}")
    print(f"Canvas: {template.canvas.width}x{template.canvas.height}")
    print()

    for name, filename, fit_mode in ARTWORKS:
        art_path = os.path.join(FIXTURES_DIR, filename)
        art = Image.open(art_path).convert("RGBA")
        print(f"Rendering {name} (fit={fit_mode})...")
        result = render_case(
            art, template, template_dir=TEMPLATE_DIR, fit_mode=fit_mode
        )

        # Full render
        full_path = os.path.join(OUTPUT_DIR, f"case-{name}.png")
        result.save(full_path, "PNG")
        size_kb = os.path.getsize(full_path) / 1024
        print(f"  full: {result.size} -> {full_path} ({size_kb:.1f} KB)")

        # Camera region crop
        save_crop(result, f"case-{name}", "camera",
                  CAM_X, CAM_Y, CAM_W, CAM_H)

        # Four corner crops (from print region corners)
        corners = [
            ("corner-tl", PRINT_X, PRINT_Y),
            ("corner-tr", PRINT_X + PRINT_W - CORNER_SIZE, PRINT_Y),
            ("corner-bl", PRINT_X, PRINT_Y + PRINT_H - CORNER_SIZE),
            ("corner-br", PRINT_X + PRINT_W - CORNER_SIZE,
             PRINT_Y + PRINT_H - CORNER_SIZE),
        ]
        for label, cx, cy in corners:
            save_crop(result, f"case-{name}", label, cx, cy,
                      CORNER_SIZE, CORNER_SIZE)
        print()

    total = len(ARTWORKS) * (1 + 1 + 4)
    print(f"Done. {total} review images generated in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
