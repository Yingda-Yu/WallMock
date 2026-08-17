import sys
sys.path.insert(0, '.')

import io
from PIL import Image
from app import app

client = app.test_client()

def create_test_image(width, height, color):
    img = Image.new('RGB', (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    buf.seek(0)
    return buf

print("=== 测试上传和预览 ===")

print("\n1. 上传竖屏壁纸 (1080x2400)...")
img1 = create_test_image(1080, 2400, (255, 200, 150))
data = {
    'images': (img1, 'test_portrait.jpg')
}
resp = client.post('/api/upload', data=data, content_type='multipart/form-data')
result = resp.get_json()
print(f"   状态: {resp.status_code}, 成功: {result.get('success')}, 图片数: {len(result.get('images', []))}")
if result.get('images'):
    img = result['images'][0]
    print(f"   尺寸: {img['width']}x{img['height']}")
    print(f"   比例: {img['ratio_info']['name']} ({img['ratio_info']['orientation']})")
    print(f"   推荐设备: {img['ratio_info']['device']}")

print("\n2. 上传横屏壁纸 (1920x1080)...")
img2 = create_test_image(1920, 1080, (150, 200, 255))
data = {
    'images': (img2, 'test_landscape.jpg')
}
resp = client.post('/api/upload', data=data, content_type='multipart/form-data')
result = resp.get_json()
print(f"   状态: {resp.status_code}, 图片总数: {len(result.get('images', []))}")

print("\n3. 测试比例分析...")
resp = client.post('/api/analyze', json={})
result = resp.get_json()
print(f"   推荐模板: {result.get('recommended_templates')}")

print("\n4. 测试单手机模板预览...")
resp = client.post('/api/preview', json={
    'template_id': 'single_phone',
    'options': {}
})
result = resp.get_json()
print(f"   状态: {resp.status_code}, 成功: {result.get('success')}")
if result.get('success'):
    print(f"   尺寸: {result['size']['width']}x{result['size']['height']}")

print("\n5. 测试多设备组合预览...")
resp = client.post('/api/preview', json={
    'template_id': 'all_devices',
    'options': {}
})
result = resp.get_json()
print(f"   状态: {resp.status_code}, 成功: {result.get('success')}")

print("\n6. 测试生成图片...")
resp = client.post('/api/generate', json={
    'template_id': 'single_phone',
    'product_name': '测试商品',
    'options': {
        'background_color': '#F5F2EB',
        'output_format': 'JPEG',
        'output_quality': 95,
    }
})
result = resp.get_json()
print(f"   状态: {resp.status_code}, 成功: {result.get('success')}")
if result.get('success'):
    print(f"   输出路径: {result.get('output_path')}")
    print(f"   文件大小: {result.get('file_size_kb')} KB")

print("\n7. 测试六手机模板预览...")
resp = client.post('/api/preview', json={
    'template_id': 'phone_pack_6',
    'options': {}
})
result = resp.get_json()
print(f"   状态: {resp.status_code}, 成功: {result.get('success')}")

print("\n=== 上传和预览测试完成 ===")
