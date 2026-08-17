import sys
import json
import base64
import io
sys.path.insert(0, '.')

from PIL import Image
from api.index import app

client = app.test_client()

# Test 1: templates endpoint
resp = client.get('/api/templates')
data = resp.get_json()
print("Templates: {} found".format(len(data["templates"])))
for t in data["templates"]:
    print("  - {}: {} ({} devices)".format(t["id"], t["name"], t["device_count"]))

# Test 2: devices endpoint
resp = client.get('/api/devices')
data = resp.get_json()
print("\nDevices: {} found".format(len(data["devices"])))

# Test 3: preview with a test image
img = Image.new('RGB', (1080, 2400), (255, 100, 100))
buf = io.BytesIO()
img.save(buf, format='JPEG', quality=85)
img_b64 = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()

resp = client.post('/api/preview', json={
    'template_id': 'single_phone',
    'images': [{'base64': img_b64, 'filename': 'test.jpg'}],
    'options': {
        'background_color': '#F5F2EB',
        'canvas_width': 1500,
        'canvas_height': 2000,
        'lockscreen': {'show': True, 'time': '9:42', 'date': '1月13日', 'auto_color': True},
        'brand': {'show_brand': True, 'name': 'Test', 'subtitle': 'SUB', 'show_subtitle': True}
    }
})
data = resp.get_json()
if data.get('success'):
    preview = data['preview']
    print("\nPreview OK: {}x{}".format(data["size"]["width"], data["size"]["height"]))
    print("Preview base64 length: {} chars".format(len(preview)))
else:
    print("\nPreview FAILED: {}".format(data.get("error")))

# Test 4: generate
resp = client.post('/api/generate', json={
    'template_id': 'single_phone',
    'images': [{'base64': img_b64, 'filename': 'test.jpg'}],
    'product_name': 'testproduct',
    'options': {
        'background_color': '#F5F2EB',
        'canvas_width': 1500,
        'canvas_height': 2000,
        'output_format': 'JPEG',
        'output_quality': 95,
        'lockscreen': {'show': True, 'time': '9:42', 'date': '1月13日', 'auto_color': True},
        'brand': {'show_brand': True, 'name': 'Test', 'subtitle': 'SUB', 'show_subtitle': True}
    }
})
data = resp.get_json()
if data.get('success'):
    print("\nGenerate OK: {}".format(data["filename"]))
    print("File size: {} KB".format(data["file_size_kb"]))
    print("Image base64 length: {} chars".format(len(data["image"])))
else:
    print("\nGenerate FAILED: {}".format(data.get("error")))

print("\n=== All tests completed ===")
