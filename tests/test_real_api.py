import os
import requests
from PIL import Image, ImageDraw, ImageFont

SERVER_URL = "http://127.0.0.1:5876"
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def create_test_image(width=1080, height=2400):
    img = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    top_height = height // 3
    middle_height = height // 3
    bottom_height = height - top_height - middle_height
    
    draw.rectangle([(0, 0), (width - 1, top_height - 1)], fill=(255, 50, 50))
    draw.rectangle([(0, top_height), (width - 1, top_height + middle_height - 1)], fill=(50, 255, 50))
    draw.rectangle([(0, top_height + middle_height), (width - 1, height - 1)], fill=(50, 50, 255))
    
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', int(width * 0.08))
    except:
        font = ImageFont.load_default()
    
    text = "WALLMOCK TEST"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (width - tw) // 2
    ty = (height - th) // 2
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255))
    
    circle_r = min(width, height) // 8
    cx = width // 2
    cy = height // 3 * 2
    draw.ellipse([(cx - circle_r, cy - circle_r), (cx + circle_r, cy + circle_r)], fill=(255, 255, 50))
    
    return img

def test_real_upload():
    test_img = create_test_image(1080, 2400)
    test_path = os.path.join(LOG_DIR, 'test_upload.png')
    test_img.save(test_path)
    
    print("=== 测试上传图片 ===")
    with open(test_path, 'rb') as f:
        response = requests.post(f"{SERVER_URL}/api/upload", files={'images': ('test_upload.png', f, 'image/png')})
    
    if response.status_code == 200:
        result = response.json()
        if result.get('images'):
            image_id = result['images'][0]['id']
            print(f"上传成功: image_id={image_id}")
            return image_id
        else:
            print("上传成功但没有图片")
            return None
    else:
        print(f"上传失败: {response.status_code} - {response.text}")
        return None

def test_preview(image_id):
    print("\n=== 测试预览API ===")
    response = requests.post(f"{SERVER_URL}/api/preview", json={
        'image_ids': [image_id],
        'template_id': 'single_phone',
        'options': {
            'background_color': '#F5F2EB',
            'lockscreen': {'show': True, 'time': '9:42', 'date': '1月15日 星期三'},
            'brand': {'show_brand': True, 'name': '米草科技', 'subtitle': 'TEST'}
        }
    })
    
    if response.status_code == 200:
        print("预览生成成功")
        return True
    else:
        print(f"预览失败: {response.status_code} - {response.text}")
        return False

def test_generate(image_id):
    print("\n=== 测试生成API ===")
    response = requests.post(f"{SERVER_URL}/api/generate", json={
        'image_ids': [image_id],
        'template_id': 'single_phone',
        'options': {
            'background_color': '#F5F2EB',
            'lockscreen': {'show': True, 'time': '9:42', 'date': '1月15日 星期三'},
            'brand': {'show_brand': True, 'name': '米草科技', 'subtitle': 'TEST'}
        }
    })
    
    if response.status_code == 200:
        result = response.json()
        output_path = result.get('output_path', '')
        print(f"生成成功: {output_path}")
        
        if os.path.exists(output_path):
            img = Image.open(output_path)
            print(f"输出尺寸: {img.size}")
            
            w, h = img.size
            center_x = w // 2
            center_y = h // 2
            pixel = img.getpixel((center_x, center_y))
            r, g, b = pixel[:3]
            print(f"中心像素: R={r}, G={g}, B={b}")
            
            if r > 10 or g > 10 or b > 10:
                print("✓ 屏幕不是黑屏！")
            else:
                print("✗ 屏幕仍然是黑屏！")
        else:
            print(f"文件不存在: {output_path}")
            
        return output_path
    else:
        print(f"生成失败: {response.status_code} - {response.text}")
        return None

def test_generate_all_templates(image_id):
    print("\n=== 测试所有模板 ===")
    templates = ['single_phone', 'double_phone', 'phone_pack_6', 'laptop_phone', 'all_devices', 'desktop']
    results = []
    
    for tpl in templates:
        print(f"\n--- 生成 {tpl} ---")
        response = requests.post(f"{SERVER_URL}/api/generate", json={
            'image_ids': [image_id],
            'template_id': tpl,
            'options': {
                'background_color': '#F5F2EB',
                'lockscreen': {'show': True, 'time': '9:42', 'date': '1月15日 星期三'},
                'brand': {'show_brand': True, 'name': '米草科技', 'subtitle': 'TEST'}
            }
        })
        
        if response.status_code == 200:
            result = response.json()
            output_path = result.get('output_path', '')
            print(f"✓ 成功: {output_path}")
            results.append((tpl, output_path))
        else:
            print(f"✗ 失败: {response.status_code}")
            results.append((tpl, None))
    
    return results

if __name__ == "__main__":
    image_id = test_real_upload()
    
    if image_id:
        test_preview(image_id)
        single_output = test_generate(image_id)
        all_results = test_generate_all_templates(image_id)
        
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        print(f"测试图片: {os.path.abspath(os.path.join(LOG_DIR, 'test_upload.png'))}")
        print(f"单手机输出: {single_output}")
        print("\n所有模板输出路径:")
        for tpl, path in all_results:
            if path:
                print(f"  {tpl}: {path}")
