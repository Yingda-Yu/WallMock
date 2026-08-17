import sys
sys.path.insert(0, '.')

import json
from app import app

client = app.test_client()

print("=== 测试 API 接口 ===")

print("\n1. 获取模板列表...")
resp = client.get('/api/templates')
data = resp.get_json()
print(f"   状态: {resp.status_code}, 模板数: {len(data.get('templates', []))}")
for t in data.get('templates', []):
    print(f"   - {t['name']} ({t['id']})")

print("\n2. 获取设备配置...")
resp = client.get('/api/devices')
data = resp.get_json()
print(f"   状态: {resp.status_code}, 设备数: {len(data.get('devices', {}))}")

print("\n3. 获取设置...")
resp = client.get('/api/settings')
data = resp.get_json()
print(f"   状态: {resp.status_code}, 应用名: {data.get('app', {}).get('name')}")

print("\n4. 空图片列表...")
resp = client.get('/api/images')
data = resp.get_json()
print(f"   状态: {resp.status_code}, 图片数: {len(data.get('images', []))}")

print("\n5. 测试主页...")
resp = client.get('/')
print(f"   状态: {resp.status_code}, 长度: {len(resp.data)}")

print("\n=== 基础 API 测试完成 ===")
