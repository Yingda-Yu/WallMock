import requests
import json

BASE_URL = "http://localhost:5876"

def test_render_all_templates():
    with open("input/ins_wallpaper_01_minimal_cream_vase.png", "rb") as f:
        files = {"images": f}
        resp = requests.post(f"{BASE_URL}/api/upload", files=files)
        print("上传结果:", resp.json()["success"], "上传了", resp.json()["uploaded_count"], "张图片")
    
    templates = requests.get(f"{BASE_URL}/api/templates").json()["templates"]
    
    for tpl in templates:
        print(f"\n测试: {tpl['name']}")
        options = {
            "canvas_width": 2000,
            "canvas_height": 2000,
            "background_color": "#F5F2EB",
            "brand": {
                "show_brand": True,
                "show_subtitle": True,
                "name": "米草科技",
                "subtitle": "PHONE WALLPAPER",
                "brand_size": 48,
                "subtitle_size": 22,
                "letter_spacing": 3,
                "line_spacing": 12,
                "text_style": "minimal",
                "align": "center",
            }
        }
        
        resp = requests.post(f"{BASE_URL}/api/preview", json={
            "template_id": tpl["id"],
            "options": options
        })
        
        if resp.json()["success"]:
            print(f"✓ {tpl['id']}: 渲染成功")
        else:
            print(f"✗ {tpl['id']}: 渲染失败 - {resp.json().get('error', '未知错误')}")
    
    print("\n测试完成！")

if __name__ == "__main__":
    test_render_all_templates()