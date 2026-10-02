"""Generate P4B Wave-1 three-device review render matrix.

Produces 3 devices × 3 artworks = 9 full renders with review crops.

Devices: iphone-17e, iphone-17, iphone-air
Artworks: color-block, tile-pattern, transparent-artwork

Output structure:
  tests/fixtures/review_outputs/p4b/<device_id>/hard/rear/
    <artwork>-full.png
    <artwork>-camera.png
    <artwork>-corner-tl.png
    <artwork>-corner-tr.png
    <artwork>-corner-bl.png
    <artwork>-corner-br.png
"""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.case_renderer import render_case
from core.case_template_loader import load_case_template

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEVICES = [
    "iphone-17e",
    "iphone-17",
    "iphone-air",
]

ARTWORKS = [
    ("color-block", "tests/fixtures/artworks/color-block.png"),
    ("tile-pattern", "tests/fixtures/artworks/tile-pattern.png"),
    ("transparent-artwork", "tests/fixtures/artworks/transparent-artwork.png"),
]

OUTPUT_BASE = os.path.join("tests", "fixtures", "review_outputs", "p4b")


def generate_crops(img, device_id):
    """Generate camera crop and four corner crops from a full render."""
    w, h = img.size

    crops = {}

    # Camera region: top-left ~25% of width, top ~25% of height
    cam_w = int(w * 0.38)
    cam_h = int(h * 0.28)
    crops["camera"] = img.crop((0, 0, cam_w, cam_h))

    # Corner crops (25% of each dimension from each corner)
    corner_w = int(w * 0.30)
    corner_h = int(h * 0.18)

    crops["corner-tl"] = img.crop((0, 0, corner_w, corner_h))
    crops["corner-tr"] = img.crop((w - corner_w, 0, w, corner_h))
    crops["corner-bl"] = img.crop((0, h - corner_h, corner_w, h))
    crops["corner-br"] = img.crop((w - corner_w, h - corner_h, w, h))

    return crops


def main():
    os.chdir(REPO_ROOT)

    print("P4B Wave-1 Render Matrix")
    print("=" * 60)
    print(f"Devices:  {len(DEVICES)} ({', '.join(DEVICES)})")
    print(f"Artworks: {len(ARTWORKS)} ({', '.join(a[0] for a in ARTWORKS)})")
    print(f"Total:    {len(DEVICES) * len(ARTWORKS)} renders")
    print()

    total_renders = 0

    for device_id in DEVICES:
        template_dir = os.path.join(
            "assets", "case_templates", "apple", device_id, "hard", "rear"
        )
        template_json = os.path.join(template_dir, "template.json")
        template = load_case_template(template_json)

        out_dir = os.path.join(OUTPUT_BASE, device_id, "hard", "rear")
        os.makedirs(out_dir, exist_ok=True)

        print(f"[{device_id}]")
        print(f"  Template: {template.id}")
        print(f"  Canvas:   {template.canvas.width}x{template.canvas.height}")
        print(f"  Status:   {template.status}")

        for art_name, art_path in ARTWORKS:
            art = Image.open(art_path).convert("RGBA")
            result = render_case(
                art, template, template_dir=template_dir, fit_mode="cover",
            )

            # Full render
            full_path = os.path.join(out_dir, f"{art_name}-full.png")
            result.save(full_path)
            size_kb = os.path.getsize(full_path) / 1024

            # Crops
            crops = generate_crops(result, device_id)
            for crop_name, crop_img in crops.items():
                crop_path = os.path.join(out_dir, f"{art_name}-{crop_name}.png")
                crop_img.save(crop_path)

            print(f"    {art_name}: {result.size[0]}x{result.size[1]} ({size_kb:.0f} KB) + {len(crops)} crops")
            total_renders += 1

        print()

    print("=" * 60)
    print(f"Done. {total_renders} renders with crops saved to {OUTPUT_BASE}/")


if __name__ == "__main__":
    main()
