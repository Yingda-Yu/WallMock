from PIL import Image, ImageDraw, ImageFont
import os
import json
import logging
from pathlib import Path

from .wallpaper_fitter import fit_wallpaper, apply_rounded_corners, create_screen_mask
from .image_loader import load_image

BASE_DIR = Path(__file__).resolve().parent.parent
DEVICES_JSON = BASE_DIR / "assets" / "device_frames" / "devices.json"
BUNDLED_FONT = str(BASE_DIR / "assets" / "fonts" / "NotoSansSC.ttf")

DEBUG = os.environ.get('WALLMOCK_DEBUG', '0') == '1'

if DEBUG:
    LOG_DIR = BASE_DIR / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_DIR / 'device_renderer.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
logger = logging.getLogger('device_renderer')

_debug_counter = 0

def _get_debug_counter():
    global _debug_counter
    _debug_counter += 1
    return _debug_counter

def _debug_save(img, counter, step, name):
    if DEBUG:
        img.save(LOG_DIR / f"debug_{counter}_{step:02d}_{name}.png")


def load_device_configs():
    with open(DEVICES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def get_available_font(size=40, bold=False):
    font_candidates = [
        BUNDLED_FONT,
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def get_text_color_for_wallpaper(wallpaper_crop):
    try:
        small = wallpaper_crop.resize((1, 1), Image.LANCZOS)
        r, g, b = small.getpixel((0, 0))[:3]
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return (255, 255, 255, 255) if brightness < 128 else (0, 0, 0, 255)
    except Exception:
        return (255, 255, 255, 255)


def render_device(wallpaper_img, device_type, scale=1.0, fit_mode="cover", offset_x=0, offset_y=0, zoom=1.0, lockscreen_options=None):
    device_configs = load_device_configs()
    if device_type not in device_configs:
        raise ValueError(f"未知设备类型: {device_type}")

    dev_cfg = device_configs[device_type]
    frame_path = BASE_DIR / dev_cfg["frame_image"]
    frame_img = load_image(str(frame_path))

    screen = dev_cfg["screen"]
    sw = int(screen["width"] * scale)
    sh = int(screen["height"] * scale)
    sx = int(screen["x"] * scale)
    sy = int(screen["y"] * scale)
    corner_r = int(screen["corner_radius"] * scale)

    counter = _get_debug_counter()
    logger.info(f"=== 渲染设备 {counter} ===")
    logger.info(f"设备类型: {device_type}")
    logger.info(f"壁纸尺寸: {wallpaper_img.size}, mode={wallpaper_img.mode}")
    logger.info(f"屏幕区域: x={sx}, y={sy}, w={sw}, h={sh}, corner_r={corner_r}")
    logger.info(f"设备框尺寸: {frame_img.size}")

    debug_step = 1
    _debug_save(frame_img.convert("RGBA"), counter, debug_step, "frame")
    debug_step += 1

    _debug_save(wallpaper_img, counter, debug_step, "loaded")
    debug_step += 1

    if scale != 1.0:
        frame_img = frame_img.resize(
            (int(frame_img.width * scale), int(frame_img.height * scale)),
            Image.LANCZOS,
        )
        sx = int(sx)
        sy = int(sy)

    fitted_wp = fit_wallpaper(wallpaper_img, sw, sh, fit_mode, offset_x, offset_y, zoom)
    logger.info(f"fit_wallpaper 后尺寸: {fitted_wp.size}")
    _debug_save(fitted_wp, counter, debug_step, "fitted")
    debug_step += 1

    fitted_wp = apply_rounded_corners(fitted_wp, corner_r)
    logger.info(f"apply_rounded_corners 后尺寸: {fitted_wp.size}")
    _debug_save(fitted_wp, counter, debug_step, "masked")
    debug_step += 1

    result = Image.new("RGBA", frame_img.size, (0, 0, 0, 0))

    result.paste(fitted_wp, (sx, sy), fitted_wp)
    logger.info(f"壁纸粘贴到位置: ({sx}, {sy})")
    _debug_save(result, counter, debug_step, "screen_composited")
    debug_step += 1

    if lockscreen_options and lockscreen_options.get("show", True):
        result = _render_lockscreen(result, sw, sh, sx, sy, fitted_wp, lockscreen_options, dev_cfg)
        _debug_save(result, counter, debug_step, "lockscreen")
        debug_step += 1

    result.paste(frame_img, (0, 0), frame_img)
    logger.info(f"设备框粘贴完成")
    _debug_save(result, counter, debug_step, "final")
    debug_step += 1

    screen_area = result.crop((sx, sy, sx + sw, sy + sh))
    extrema = screen_area.getextrema()
    logger.info(f"屏幕区域极值: R={extrema[0]}, G={extrema[1]}, B={extrema[2]}")

    center_pixel = screen_area.getpixel((sw // 2, sh // 2))
    logger.info(f"屏幕中心像素: {center_pixel}")

    return result


def _render_lockscreen(canvas, sw, sh, sx, sy, fitted_wp, options, dev_cfg):
    draw = ImageDraw.Draw(canvas)

    show_time = options.get("show_time", True)
    show_date = options.get("show_date", True)
    auto_color = options.get("auto_color", True)

    time_str = options.get("time", "9:42")
    date_str = options.get("date", "1月13日 星期一")

    time_size = options.get("time_size", int(sh * 0.08))
    date_size = options.get("date_size", int(sh * 0.032))

    top_sample = fitted_wp.crop((0, 0, sw, max(int(sh * 0.15), 2)))
    text_color = get_text_color_for_wallpaper(top_sample) if auto_color else _parse_color(options.get("text_color", "#FFFFFF"))

    time_font = get_available_font(time_size, bold=True)
    date_font = get_available_font(date_size)

    if show_time:
        bbox = draw.textbbox((0, 0), time_str, font=time_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = sx + (sw - tw) // 2
        ty = sy + int(sh * 0.08)

        if options.get("text_shadow", True):
            shadow_color = (0, 0, 0, 80)
            draw.text((tx + 1, ty + 1), time_str, font=time_font, fill=shadow_color)

        draw.text((tx, ty), time_str, font=time_font, fill=text_color)

    if show_date:
        bbox = draw.textbbox((0, 0), date_str, font=date_font)
        dw = bbox[2] - bbox[0]
        dh = bbox[3] - bbox[1]
        dx = sx + (sw - dw) // 2
        dy = sy + int(sh * 0.08) + time_size + int(sh * 0.01)

        if options.get("text_shadow", True):
            shadow_color = (0, 0, 0, 80)
            draw.text((dx + 1, dy + 1), date_str, font=date_font, fill=shadow_color)

        draw.text((dx, dy), date_str, font=date_font, fill=text_color)

    return canvas


def _parse_color(hex_str):
    if hex_str.startswith("#"):
        hex_str = hex_str[1:]
    if len(hex_str) == 6:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return (r, g, b, 255)
    elif len(hex_str) == 8:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        a = int(hex_str[6:8], 16)
        return (r, g, b, a)
    return (255, 255, 255, 255)
