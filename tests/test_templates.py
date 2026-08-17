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

print("测试单手机模板...")
result = render_template("single_phone", [test_wp_portrait])
result.convert("RGB").convert("RGB").save("output/test/test_single_phone.jpg", "JPEG", quality=95)
print("  单手机 OK:", result.size)

print("测试双手机模板...")
result = render_template("double_phone", [test_wp_portrait, test_wp_portrait])
result.convert("RGB").save("output/test/test_double_phone.jpg", "JPEG", quality=95)
print("  双手机 OK:", result.size)

print("测试六手机模板...")
colors = ["#FFB6C1", "#98FB98", "#ADD8E6", "#DDA0DD", "#F0E68C", "#FFA07A"]
imgs = [Image.new("RGB", (1080, 2400), hex_to_rgb(c)) for c in colors]
result = render_template("phone_pack_6", imgs)
result.convert("RGB").save("output/test/test_phone_pack_6.jpg", "JPEG", quality=95)
print("  六手机 OK:", result.size)

print("测试笔记本加手机...")
result = render_template("laptop_phone", [test_wp_landscape, test_wp_portrait])
result.convert("RGB").save("output/test/test_laptop_phone.jpg", "JPEG", quality=95)
print("  笔记本加手机 OK:", result.size)

print("测试多设备组合...")
imgs4 = [
    test_wp_landscape,
    test_wp_landscape,
    Image.new("RGB", (1536, 2048), hex_to_rgb("#DDA0DD")),
    test_wp_portrait
]
result = render_template("all_devices", imgs4)
result.convert("RGB").save("output/test/test_all_devices.jpg", "JPEG", quality=95)
print("  多设备 OK:", result.size)

print("测试桌面展示...")
result = render_template("desktop", [test_wp_landscape])
result.convert("RGB").save("output/test/test_desktop.jpg", "JPEG", quality=95)
print("  桌面展示 OK:", result.size)

print("\n所有模板测试完成！结果在 output/test/ 目录下")
