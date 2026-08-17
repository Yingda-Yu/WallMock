import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from core.template_engine import render_template, list_templates
from core.image_loader import load_image

def create_test_image(width, height, color=(200, 180, 160)):
    img = Image.new("RGBA", (width, height), color + (255,))
    draw = ImageDraw.Draw(img)
    draw.text((width//2 - 50, height//2 - 10), "Test Wallpaper", fill=(100, 100, 100))
    return img

def test_all_templates():
    test_img = create_test_image(1080, 1920)
    
    templates = list_templates()
    print(f"检测到 {len(templates)} 个模板:")
    for t in templates:
        print(f"  - {t['id']}: {t['name']} ({t['device_count']}台设备)")
    
    print("\n开始测试模板渲染...")
    
    for tpl in templates:
        try:
            result = render_template(tpl["id"], [test_img])
            output_path = f"tests/test_{tpl['id']}_optimized.png"
            result.save(output_path)
            print(f"✓ {tpl['id']}: 渲染成功 ({result.width}x{result.height})")
        except Exception as e:
            print(f"✗ {tpl['id']}: 渲染失败 - {str(e)}")
    
    print("\n测试完成！")

if __name__ == "__main__":
    test_all_templates()