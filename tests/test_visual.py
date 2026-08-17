import sys
import os
import io
import base64
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, '.')

from core.template_engine import list_templates, render_template, get_canvas_presets, CANVAS_PRESETS
from core.device_renderer import load_device_configs
from core.ratio_detector import detect_ratio

OUTPUT_DIR = Path("output/test_visual")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def create_test_wallpaper(width, height, color, label):
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    for i in range(5):
        r = min(width, height) // 2 - i * 30
        if r > 0:
            c = tuple(min(255, c + 30) for c in color)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=3)
    draw.text((cx - 50, cy - 10), label, fill=(255, 255, 255))
    return img.convert("RGBA")

test_images = [
    create_test_wallpaper(1080, 2400, (200, 60, 60), "RED"),
    create_test_wallpaper(1920, 1080, (60, 120, 200), "BLUE"),
    create_test_wallpaper(800, 1200, (60, 160, 80), "GREEN"),
    create_test_wallpaper(1080, 2400, (180, 100, 200), "PURPLE"),
    create_test_wallpaper(1080, 2400, (220, 160, 40), "GOLD"),
    create_test_wallpaper(1920, 1080, (40, 160, 180), "CYAN"),
]

templates = list_templates()
print("=== Templates ===")
for t in templates:
    print("  {} [{}] - {} devices, default: {}".format(t["id"], t["category"], t["device_count"], t.get("default_canvas", "1:1")))

print("\n=== Canvas Presets ===")
for key, p in CANVAS_PRESETS.items():
    print("  {} - {}x{}".format(key, p["width"], p["height"]))

print("\n=== Device Configs ===")
configs = load_device_configs()
for dev_id, cfg in configs.items():
    ts = cfg["total_size"]
    print("  {} - {}x{} (screen ratio: {:.3f})".format(dev_id, ts["width"], ts["height"], cfg["screen_ratio"]))

test_configs = [
    ("phone_hero", "1:1", [0]),
    ("phone_hero", "4:3", [0]),
    ("phone_hero", "4:5", [0]),
    ("phone_hero", "2:3", [0]),
    ("phone_hero", "9:16", [0]),
    ("desktop_hero", "1:1", [1]),
    ("desktop_hero", "4:3", [1]),
    ("desktop_hero", "4:5", [1]),
    ("desktop_hero", "2:3", [1]),
    ("desktop_hero", "9:16", [1]),
    ("tablet_hero", "1:1", [2]),
    ("tablet_hero", "4:3", [2]),
    ("tablet_hero", "2:3", [2]),
    ("laptop_phone", "1:1", [1, 0]),
    ("laptop_phone", "4:3", [1, 0]),
    ("laptop_phone", "2:3", [1, 0]),
    ("device_trio", "1:1", [1, 2, 0]),
    ("device_trio", "4:3", [1, 2, 0]),
    ("device_trio", "2:3", [1, 2, 0]),
    ("wallpaper_collection", "1:1", [0, 3, 4, 2]),
    ("wallpaper_collection", "4:3", [0, 3, 4, 2]),
    ("phone_ratio_compare", "1:1", [0]),
    ("phone_ratio_compare", "4:3", [0]),
]

print("\n=== Generating Test Images ===")
success_count = 0
fail_count = 0

for template_id, canvas_key, img_indices in test_configs:
    preset = CANVAS_PRESETS[canvas_key]
    canvas_w = preset["width"]
    canvas_h = preset["height"]

    imgs = [test_images[i] for i in img_indices]

    options = {
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "background_color": "#F5F2EB",
        "bg_mode": "gradient",
        "lockscreen": {
            "show": True,
            "time": "9:42",
            "date": "1月13日 星期一",
            "auto_color": True,
        },
        "brand": {
            "mode": "minimal",
            "show_brand": False,
            "show_subtitle": True,
            "subtitle": "",
            "opacity": 45,
        },
    }

    try:
        result = render_template(template_id, imgs, options)
        filename = "{}_{}.jpg".format(template_id, canvas_key.replace(":", "x"))
        out_path = OUTPUT_DIR / filename
        result.convert("RGB").save(str(out_path), "JPEG", quality=92)

        file_kb = os.path.getsize(str(out_path)) / 1024
        print("  OK  {} {} -> {}x{} ({}KB)".format(
            template_id, canvas_key, result.width, result.height, round(file_kb)))
        success_count += 1
    except Exception as e:
        print("  FAIL {} {} -> {}".format(template_id, canvas_key, str(e)))
        fail_count += 1

print("\n=== Summary ===")
print("Success: {} / {}".format(success_count, success_count + fail_count))
print("Failed: {}".format(fail_count))
print("Output directory: {}".format(OUTPUT_DIR.resolve()))
