import sys
sys.path.insert(0, '.')

import os
from pathlib import Path
from PIL import Image
from core.batch_processor import batch_process, scan_input_dir, detect_ratio

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output" / "batch_test"

def create_test_image(path, width, height, color):
    img = Image.new('RGB', (width, height), color)
    img.save(path, 'JPEG', quality=95)

print("=== 测试批量处理 ===")

test_product = INPUT_DIR / "测试商品A"
test_product.mkdir(exist_ok=True)

print("创建测试图片...")
create_test_image(test_product / "wallpaper_01.jpg", 1080, 2400, (255, 180, 120))
create_test_image(test_product / "wallpaper_02.jpg", 1080, 2340, (120, 200, 255))
create_test_image(test_product / "wallpaper_03.jpg", 1080, 2400, (180, 255, 180))
create_test_image(test_product / "wallpaper_04.jpg", 1920, 1080, (200, 180, 255))
create_test_image(test_product / "wallpaper_05.jpg", 1080, 2400, (255, 220, 180))
create_test_image(test_product / "wallpaper_06.jpg", 1080, 2340, (180, 220, 255))

single_img = INPUT_DIR / "单张壁纸.jpg"
create_test_image(single_img, 1080, 2400, (255, 200, 200))

print("\n扫描 input 目录...")
products = scan_input_dir(str(INPUT_DIR))
print(f"发现 {len(products)} 个项目:")
for p in products:
    print(f"  - {p['name']} ({p['type']}): {len(p['images'])} 张图")

print("\n开始批量处理...")
results = batch_process(str(INPUT_DIR), str(OUTPUT_DIR), {
    "templates": ["single_phone", "double_phone", "phone_pack_6", "laptop_phone", "all_devices", "desktop"],
})

print(f"\n处理结果:")
for r in results:
    if r.get('success'):
        print(f"  ✅ {r['product']}: 生成 {r['generated_count']} 张")
        for f in r.get('output_files', []):
            size_kb = os.path.getsize(f) / 1024
            print(f"     - {os.path.basename(f)} ({size_kb:.0f} KB)")
    else:
        print(f"  ❌ {r['product']}: {r.get('error', '未知错误')}")

success_count = sum(1 for r in results if r.get('success'))
print(f"\n总计: {success_count}/{len(results)} 成功")

print("\n=== 批量处理测试完成 ===")
