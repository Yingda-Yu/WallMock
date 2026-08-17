import sys
sys.path.insert(0, '.')

import os
import logging
from PIL import Image, ImageDraw, ImageFont
from core.template_engine import render_template
from core.image_loader import image_to_base64_preview
from core.batch_processor import save_output_image

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'debug_render.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('wallmock_debug')

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
    
    logger.info(f"创建测试图片: {width}x{height}, 红色顶部, 绿色中部, 蓝色底部, 白色文字, 黄色圆形")
    return img

def check_screen_content(img, screen_x, screen_y, screen_w, screen_h, test_name):
    screen = img.crop((screen_x, screen_y, screen_x + screen_w, screen_y + screen_h))
    
    extrema = screen.getextrema()
    logger.info(f"[{test_name}] 屏幕区域极值: R={extrema[0]}, G={extrema[1]}, B={extrema[2]}")
    
    if extrema[0][0] == 0 and extrema[0][1] == 0:
        logger.error(f"[{test_name}] 屏幕区域红色通道全黑！")
        return False
    
    non_black_count = 0
    for y in range(0, screen_h, max(1, screen_h // 50)):
        for x in range(0, screen_w, max(1, screen_w // 50)):
            pixel = screen.getpixel((x, y))
            r, g, b = pixel[:3]
            if r > 10 or g > 10 or b > 10:
                non_black_count += 1
    
    logger.info(f"[{test_name}] 非黑像素数: {non_black_count}")
    
    if non_black_count < 1000:
        logger.error(f"[{test_name}] 非黑像素少于1000，屏幕可能是黑屏！")
        return False
    
    has_red = False
    has_green = False
    has_blue = False
    has_yellow = False
    
    for y in range(0, screen_h, max(1, screen_h // 20)):
        for x in range(0, screen_w, max(1, screen_w // 20)):
            pixel = screen.getpixel((x, y))
            r, g, b = pixel[:3]
            if r > 150 and g < 100 and b < 100:
                has_red = True
            if r < 100 and g > 150 and b < 100:
                has_green = True
            if r < 100 and g < 100 and b > 150:
                has_blue = True
            if r > 200 and g > 200 and b < 100:
                has_yellow = True
    
    logger.info(f"[{test_name}] 检测到颜色: 红={has_red}, 绿={has_green}, 蓝={has_blue}, 黄={has_yellow}")
    
    if not has_red and not has_green and not has_blue:
        logger.error(f"[{test_name}] 未检测到测试图中的红/绿/蓝颜色！")
        return False
    
    return True

def test_all_templates():
    test_wp = create_test_image(1080, 2400)
    test_wp_landscape = create_test_image(1920, 1080)
    
    test_wp.save(os.path.join(LOG_DIR, 'debug_00_test_image.png'))
    
    logger.info("=" * 60)
    logger.info("开始测试所有模板")
    logger.info("=" * 60)
    
    templates = ['single_phone', 'double_phone', 'phone_pack_6', 'laptop_phone', 'all_devices', 'desktop']
    results = []
    
    for tpl_id in templates:
        logger.info(f"\n--- 测试模板: {tpl_id} ---")
        
        try:
            if tpl_id in ['laptop_phone', 'all_devices', 'desktop']:
                imgs = [test_wp_landscape, test_wp]
            else:
                imgs = [test_wp]
            
            result = render_template(tpl_id, imgs, {
                'background_color': '#F5F2EB',
                'canvas_width': 2000,
                'canvas_height': 2000,
                'lockscreen': {
                    'show': True,
                    'time': '9:42',
                    'date': '1月15日 星期三',
                    'auto_color': True,
                },
                'brand': {
                    'show_brand': True,
                    'name': '米草科技',
                    'subtitle': 'TEST OUTPUT',
                }
            })
            
            debug_path = os.path.join(LOG_DIR, f'debug_{tpl_id}.png')
            result.convert('RGB').save(debug_path, 'PNG')
            
            output_path = os.path.join(LOG_DIR, f'result_{tpl_id}.jpg')
            save_output_image(result, output_path, 'JPEG', 95, 0)
            
            logger.info(f"生成成功: {output_path}")
            logger.info(f"输出尺寸: {result.size}")
            
            passed = check_screen_content(result, 500, 300, 500, 800, tpl_id)
            
            if passed:
                results.append((tpl_id, True))
                logger.info(f"✓ {tpl_id} 测试通过")
            else:
                results.append((tpl_id, False))
                logger.error(f"✗ {tpl_id} 测试失败")
                
        except Exception as e:
            logger.error(f"✗ {tpl_id} 生成异常: {e}")
            results.append((tpl_id, False))
    
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    
    passed_count = sum(1 for _, p in results if p)
    for tpl_id, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        logger.info(f"{tpl_id}: {status}")
    
    logger.info(f"\n总计: {passed_count}/{len(results)} 通过")
    
    return passed_count == len(results)

if __name__ == "__main__":
    success = test_all_templates()
    sys.exit(0 if success else 1)
