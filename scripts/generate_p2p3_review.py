"""
Generate P2/P3 review outputs for visual inspection.

Renders all three test artworks through the iPhone 17e template
and saves the results for manual visual review.
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

ARTWORKS = [
    ("color-block", "tests/fixtures/artworks/color-block.png", "cover"),
    ("tile-pattern", "tests/fixtures/artworks/tile-pattern.png", "tile"),
    ("transparent-artwork", "tests/fixtures/artworks/transparent-artwork.png", "cover"),
]

OUT_DIR = "output/review/p2-p3/iphone-17e/hard/rear"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load the template
    template = load_case_template(TEMPLATE_JSON)
    print(f"Template: {template.id}")
    print(f"Canvas: {template.canvas.width}x{template.canvas.height}")
    print(f"Print region: {template.print_region.x},{template.print_region.y} "
          f"{template.print_region.width}x{template.print_region.height}")
    print()

    for name, art_path, fit_mode in ARTWORKS:
        print(f"Rendering {name} (fit={fit_mode})...")
        artwork = Image.open(art_path).convert("RGBA")
        print(f"  Artwork size: {artwork.size}")

        result = render_case(
            artwork,
            template,
            template_dir=TEMPLATE_DIR,
            fit_mode=fit_mode,
        )
        print(f"  Result size: {result.size}")

        out_path = os.path.join(OUT_DIR, f"{name}.png")
        # Composite onto clean light background for ecommerce presentation
        bg = Image.new("RGBA", result.size, (245, 243, 240, 255))
        final = Image.alpha_composite(bg, result)
        final.convert("RGB").save(out_path, "PNG")
        print(f"  Saved: {out_path}")

        # Also save a WebP version
        webp_path = os.path.join(OUT_DIR, f"{name}.webp")
        final.convert("RGB").save(webp_path, "WebP", quality=95)
        print(f"  Saved: {webp_path}")

    # Generate camera-region crop for inspection
    print("\nGenerating camera crop...")
    # Camera module is at approximately (CAM_X=406, CAM_Y=116, size=320)
    # Crop a region slightly larger than the camera module
    crop_x, crop_y = 350, 70
    crop_w, crop_h = 450, 400

    for name, art_path, fit_mode in ARTWORKS:
        result_path = os.path.join(OUT_DIR, f"{name}.png")
        img = Image.open(result_path)
        crop = img.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
        crop_path = os.path.join(OUT_DIR, f"{name}-camera-crop.png")
        crop.save(crop_path, "PNG")
        print(f"  Saved: {crop_path}")

    print("\nAll review outputs generated in", OUT_DIR)


if __name__ == "__main__":
    main()
