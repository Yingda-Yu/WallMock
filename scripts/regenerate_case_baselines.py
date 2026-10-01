"""
Regenerate visual regression baselines for case rendering tests.

This is the ONLY way to update baselines. Tests never auto-create or
auto-update baselines — baseline regeneration is an explicit developer
action to prevent CI from silently blessing a changed renderer.

Usage:
    python scripts/regenerate_case_baselines.py

The script renders all three fixture artworks through the iPhone 17e
template and saves the results as compressed PNGs under
tests/fixtures/baselines/.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from core.case_template_loader import load_case_template
from core.case_renderer import render_case

TEMPLATE_DIR = "assets/case_templates/apple/iphone-17e/hard/rear"
TEMPLATE_JSON = os.path.join(TEMPLATE_DIR, "template.json")

FIXTURES_DIR = "tests/fixtures/artworks"
BASELINE_DIR = "tests/fixtures/baselines"

ARTWORKS = [
    ("color-block", "color-block.png", "cover"),
    ("tile-pattern", "tile-pattern.png", "tile"),
    ("transparent-artwork", "transparent-artwork.png", "cover"),
]


def main():
    os.makedirs(BASELINE_DIR, exist_ok=True)

    template = load_case_template(TEMPLATE_JSON)
    print(f"Template: {template.id}")
    print(f"Canvas: {template.canvas.width}x{template.canvas.height}")
    print()

    for name, filename, fit_mode in ARTWORKS:
        art_path = os.path.join(FIXTURES_DIR, filename)
        art = Image.open(art_path).convert("RGBA")

        print(f"Rendering {name} (fit={fit_mode})...")
        result = render_case(
            art, template,
            template_dir=TEMPLATE_DIR,
            fit_mode=fit_mode,
        )

        out_path = os.path.join(BASELINE_DIR, f"case-{name}.png")
        result.save(out_path, "PNG")

        file_size_kb = os.path.getsize(out_path) / 1024
        print(f"  Saved: {out_path} ({file_size_kb:.1f} KB)")

    print()
    print(f"Done. {len(ARTWORKS)} baselines regenerated in {BASELINE_DIR}/")


if __name__ == "__main__":
    main()
