import sys
sys.path.insert(0, '.')

from PIL import Image
from core.template_engine import render_template
import os

os.makedirs("output/test", exist_ok=True)

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

test_wp_portrait = Image.new("RGB", (1080, 2400), hex_to_rgb("#FFE4B5"))
test_wp_landscape = Image.new("RGB", (1920, 1080), hex_to_rgb("#87CEEB"))
test_wp_square = Image.new("RGB", (1080, 1080), hex_to_rgb("#DDA0DD"))

DEFAULT_OPTS = {
    "background_color": "#F5F2EB",
    "bg_mode": "gradient",
    "canvas_width": 2400,
    "canvas_height": 2400,
    "lockscreen": {"show": True, "time": "9:42", "date": "1月13日", "auto_color": True},
    "brand": {"mode": "minimal", "show_brand": False, "show_subtitle": False},
}

print("测试 Phone Hero...")
result = render_template("phone_hero", [test_wp_portrait], DEFAULT_OPTS)
result.convert("RGB").save("output/test/test_phone_hero.jpg", "JPEG", quality=95)
print("  Phone Hero OK:", result.size)

print("测试 Desktop Hero...")
result = render_template("desktop_hero", [test_wp_landscape], DEFAULT_OPTS)
result.convert("RGB").save("output/test/test_desktop_hero.jpg", "JPEG", quality=95)
print("  Desktop Hero OK:", result.size)

print("测试 Tablet Hero...")
result = render_template("tablet_hero", [test_wp_portrait], DEFAULT_OPTS)
result.convert("RGB").save("output/test/test_tablet_hero.jpg", "JPEG", quality=95)
print("  Tablet Hero OK:", result.size)

print("测试 Laptop + Phone...")
result = render_template("laptop_phone", [test_wp_landscape, test_wp_portrait], DEFAULT_OPTS)
result.convert("RGB").save("output/test/test_laptop_phone.jpg", "JPEG", quality=95)
print("  Laptop + Phone OK:", result.size)

print("测试 Device Trio...")
imgs3 = [test_wp_landscape, test_wp_square, test_wp_portrait]
result = render_template("device_trio", imgs3, DEFAULT_OPTS)
result.convert("RGB").save("output/test/test_device_trio.jpg", "JPEG", quality=95)
print("  Device Trio OK:", result.size)

print("测试 Wallpaper Collection...")
imgs4 = [test_wp_portrait, test_wp_square, test_wp_landscape, test_wp_portrait]
result = render_template("wallpaper_collection", imgs4, DEFAULT_OPTS)
result.convert("RGB").save("output/test/test_wallpaper_collection.jpg", "JPEG", quality=95)
print("  Wallpaper Collection OK:", result.size)

print("测试 Phone Ratio Compare...")
result = render_template("phone_ratio_compare", [test_wp_portrait], DEFAULT_OPTS)
result.convert("RGB").save("output/test/test_phone_ratio_compare.jpg", "JPEG", quality=95)
print("  Phone Ratio Compare OK:", result.size)

print("\n所有模板测试完成！结果在 output/test/ 目录下")
