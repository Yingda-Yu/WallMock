from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BUNDLED_FONT = str(BASE_DIR / "assets" / "fonts" / "NotoSansSC.ttf")

def get_available_font(size=40, bold=False):
    font_candidates = [
        BUNDLED_FONT,
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_brand_text(canvas, brand_name, subtitle, position_x, position_y, options=None):
    if options is None:
        options = {}

    show_brand = options.get("show_brand", True)
    show_subtitle = options.get("show_subtitle", True)

    if not show_brand and not show_subtitle:
        return canvas

    draw = ImageDraw.Draw(canvas)

    brand_size = options.get("brand_size", 48)
    subtitle_size = options.get("subtitle_size", 22)
    brand_color = _parse_color(options.get("brand_color", "#333333"))
    subtitle_color = _parse_color(options.get("subtitle_color", "#888888"))
    letter_spacing = options.get("letter_spacing", 3)
    line_spacing = options.get("line_spacing", 12)
    align = options.get("align", "center")
    uppercase = options.get("uppercase_subtitle", True)
    text_style = options.get("text_style", "minimal")

    brand_font = get_available_font(brand_size, bold=True)
    subtitle_font = get_available_font(subtitle_size)

    subtitle_text = subtitle.upper() if uppercase else subtitle

    brand_bbox = draw.textbbox((0, 0), brand_name, font=brand_font)
    brand_w = brand_bbox[2] - brand_bbox[0]
    brand_h = brand_bbox[3] - brand_bbox[1]

    sub_bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_h = sub_bbox[3] - sub_bbox[1]

    total_h = brand_h + sub_h + line_spacing if (show_brand and show_subtitle) else (brand_h if show_brand else sub_h)

    if align == "center":
        bx = position_x - brand_w // 2
        sx = position_x - sub_w // 2
    elif align == "left":
        bx = position_x
        sx = position_x
    else:
        bx = position_x - brand_w
        sx = position_x - sub_w

    y = position_y

    if show_brand:
        if text_style == "minimal":
            draw.text((bx, y), brand_name, font=brand_font, fill=brand_color)
        else:
            shadow_color = (0, 0, 0, 30)
            draw.text((bx + 2, y + 2), brand_name, font=brand_font, fill=shadow_color)
            draw.text((bx, y), brand_name, font=brand_font, fill=brand_color)
        y += brand_h + line_spacing

    if show_subtitle:
        if letter_spacing > 0:
            chars = list(subtitle_text)
            char_widths = []
            for c in chars:
                bbox = draw.textbbox((0, 0), c, font=subtitle_font)
                char_widths.append(bbox[2] - bbox[0])
            
            total_chars_width = sum(char_widths)
            spacing = (sub_w - total_chars_width) / max(1, len(chars) - 1) if len(chars) > 1 else 0
            
            current_x = sx
            for i, c in enumerate(chars):
                draw.text((current_x, y), c, font=subtitle_font, fill=subtitle_color)
                current_x += char_widths[i] + spacing
        else:
            draw.text((sx, y), subtitle_text, font=subtitle_font, fill=subtitle_color)

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
    return (51, 51, 51, 255)