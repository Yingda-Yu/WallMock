import json
import os
from pathlib import Path
from PIL import Image

from .device_renderer import render_device
from .text_renderer import render_brand_text
from .ratio_detector import detect_ratio

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


def list_templates():
    templates = []
    if not TEMPLATES_DIR.exists():
        return templates
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                tpl = json.load(fp)
                templates.append({
                    "id": tpl.get("id", f.stem),
                    "name": tpl.get("name", f.stem),
                    "description": tpl.get("description", ""),
                    "device_count": len(tpl.get("devices", [])),
                })
        except Exception:
            continue
    return templates


def load_template(template_id):
    tpl_path = TEMPLATES_DIR / f"{template_id}.json"
    if not tpl_path.exists():
        raise FileNotFoundError(f"模板不存在: {template_id}")
    with open(tpl_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_template(template_id, template_data):
    tpl_path = TEMPLATES_DIR / f"{template_id}.json"
    with open(tpl_path, "w", encoding="utf-8") as f:
        json.dump(template_data, f, ensure_ascii=False, indent=2)


def render_template(template_id, images, options=None):
    if options is None:
        options = {}

    template = load_template(template_id)

    canvas_w = options.get("canvas_width", template.get("canvas_width", 2000))
    canvas_h = options.get("canvas_height", template.get("canvas_height", 2000))
    bg_color_hex = options.get("background_color", template.get("background_color", "#FFFFFF"))
    bg_color = _hex_to_rgba(bg_color_hex)

    canvas = _create_layered_background(canvas_w, canvas_h, bg_color)

    brand_options = options.get("brand", {})
    lockscreen_options = options.get("lockscreen", {})
    per_device_options = options.get("device_options", {})

    devices = sorted(template.get("devices", []), key=lambda d: d.get("z_index", 0))

    assigned_images = _assign_images_to_devices(images, devices)

    for device_cfg in devices:
        slot = device_cfg.get("image_slot", 0)
        wp_img = assigned_images.get(slot)
        if wp_img is None:
            continue

        dev_scale = device_cfg.get("scale", 0.5)
        dev_type = device_cfg.get("type", "dynamic_island_phone")

        dev_opts = per_device_options.get(device_cfg.get("id"), {})
        final_scale = dev_scale * dev_opts.get("scale_multiplier", 1.0)
        fit_mode = dev_opts.get("fit_mode", "cover")
        offset_x = dev_opts.get("offset_x", 0)
        offset_y = dev_opts.get("offset_y", 0)
        zoom = dev_opts.get("zoom", 1.0)

        device_img = render_device(
            wp_img,
            dev_type,
            scale=final_scale,
            fit_mode=fit_mode,
            offset_x=offset_x,
            offset_y=offset_y,
            zoom=zoom,
            lockscreen_options=lockscreen_options,
        )

        pos_x = int(device_cfg.get("x", 0.5) * canvas_w - device_img.width / 2 + dev_opts.get("offset_px_x", 0))
        pos_y = int(device_cfg.get("y", 0.5) * canvas_h - device_img.height / 2 + dev_opts.get("offset_px_y", 0))

        rotation = device_cfg.get("rotation", 0) + dev_opts.get("rotation", 0)
        if rotation != 0:
            device_img = device_img.rotate(rotation, resample=Image.BICUBIC, expand=True)
            pos_x -= (device_img.width - device_img.width) // 2
            pos_y -= (device_img.height - device_img.height) // 2

        shadow_offset = device_cfg.get("shadow_offset", 15)
        shadow_blur = device_cfg.get("shadow_blur", 30)
        shadow_opacity = device_cfg.get("shadow_opacity", 30)
        
        canvas = _draw_device_shadow(canvas, device_img, pos_x, pos_y, 
                                     shadow_offset, shadow_blur, shadow_opacity)

        canvas.paste(device_img, (pos_x, pos_y), device_img)

        label_text = device_cfg.get("label_text", "")
        if label_text:
            canvas = _draw_device_label(canvas, label_text, pos_x + device_img.width // 2, pos_y + device_img.height + 10)

    brand_cfg = template.get("brand_text", {})
    if brand_cfg.get("enabled", True) and brand_options.get("show_brand", True):
        bx = int(brand_cfg.get("x", 0.5) * canvas_w)
        by = int(brand_cfg.get("y", 0.85) * canvas_h)
        subtitle = brand_options.get("subtitle", brand_cfg.get("default_subtitle", ""))
        brand_name = brand_options.get("name", "米草科技")

        text_opts = {
            "show_brand": brand_options.get("show_brand", True),
            "show_subtitle": brand_options.get("show_subtitle", True),
            "brand_size": brand_options.get("brand_size", brand_cfg.get("brand_size", 48)),
            "subtitle_size": brand_options.get("subtitle_size", brand_cfg.get("subtitle_size", 22)),
            "brand_color": brand_options.get("brand_color", "#333333"),
            "subtitle_color": brand_options.get("subtitle_color", "#888888"),
            "align": brand_options.get("align", brand_cfg.get("align", "center")),
            "uppercase_subtitle": brand_options.get("uppercase_subtitle", True),
            "letter_spacing": brand_options.get("letter_spacing", brand_cfg.get("letter_spacing", 3)),
            "line_spacing": brand_options.get("line_spacing", brand_cfg.get("line_spacing", 12)),
            "text_style": brand_options.get("text_style", brand_cfg.get("text_style", "minimal")),
        }
        canvas = render_brand_text(canvas, brand_name, subtitle, bx, by, text_opts)

    return canvas


def _assign_images_to_devices(images, devices):
    assigned = {}
    if not images:
        return assigned

    portrait_imgs = []
    landscape_imgs = []
    other_imgs = []

    for idx, img in enumerate(images):
        ratio_info = detect_ratio(img.width, img.height)
        if ratio_info["orientation"] == "portrait":
            portrait_imgs.append((idx, img))
        elif ratio_info["orientation"] == "landscape":
            landscape_imgs.append((idx, img))
        else:
            other_imgs.append((idx, img))

    for device_cfg in devices:
        slot = device_cfg.get("image_slot", 0)
        preferred = device_cfg.get("preferred_orientation", "")

        if preferred == "landscape" and landscape_imgs:
            idx, img = landscape_imgs.pop(0)
            assigned[slot] = img
        elif preferred == "portrait" and portrait_imgs:
            idx, img = portrait_imgs.pop(0)
            assigned[slot] = img
        elif preferred == "landscape" and not landscape_imgs and (portrait_imgs or other_imgs):
            source = portrait_imgs or other_imgs
            idx, img = source.pop(0)
            assigned[slot] = img
        elif preferred == "portrait" and not portrait_imgs and (landscape_imgs or other_imgs):
            source = landscape_imgs or other_imgs
            idx, img = source.pop(0)
            assigned[slot] = img
        else:
            all_remaining = portrait_imgs + landscape_imgs + other_imgs
            if all_remaining:
                idx, img = all_remaining[0]
                if portrait_imgs and portrait_imgs[0][0] == idx:
                    portrait_imgs.pop(0)
                elif landscape_imgs and landscape_imgs[0][0] == idx:
                    landscape_imgs.pop(0)
                elif other_imgs and other_imgs[0][0] == idx:
                    other_imgs.pop(0)
                assigned[slot] = img

    all_imgs = portrait_imgs + landscape_imgs + other_imgs
    for slot in range(len(devices)):
        if slot not in assigned and all_imgs:
            idx, img = all_imgs.pop(0)
            assigned[slot] = img

    for slot in range(len(devices)):
        if slot not in assigned and images:
            assigned[slot] = images[slot % len(images)]

    return assigned


def _hex_to_rgba(hex_str):
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


def _create_layered_background(width, height, base_color):
    canvas = Image.new("RGBA", (width, height), base_color)
    
    overlay_color = (base_color[0], base_color[1], base_color[2], 10)
    overlay = Image.new("RGBA", (width, height), overlay_color)
    
    overlay_size = int(min(width, height) * 0.8)
    overlay_x = (width - overlay_size) // 2
    overlay_y = (height - overlay_size) // 2
    
    gradient = Image.new("RGBA", (overlay_size, overlay_size), (0, 0, 0, 0))
    for y in range(overlay_size):
        for x in range(overlay_size):
            dx = x - overlay_size // 2
            dy = y - overlay_size // 2
            dist = (dx * dx + dy * dy) ** 0.5
            max_dist = overlay_size // 2
            if dist < max_dist:
                alpha = int(5 * (1 - dist / max_dist))
                gradient.putpixel((x, y), (0, 0, 0, alpha))
    
    canvas.paste(gradient, (overlay_x, overlay_y), gradient)
    
    return canvas


def _draw_device_shadow(canvas, device_img, pos_x, pos_y, offset, blur, opacity):
    mask = device_img.split()[3]
    
    shadow_color = (0, 0, 0, int(opacity * 2.55))
    
    shadow_layer = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
    
    shadow_offset_x = pos_x + offset
    shadow_offset_y = pos_y + offset
    
    shadow_layer.paste(shadow_color, (shadow_offset_x, shadow_offset_y), mask)
    
    from PIL import ImageFilter
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur))
    
    canvas = Image.alpha_composite(canvas, shadow_layer)
    return canvas


def _draw_device_label(canvas, text, center_x, center_y):
    from PIL import ImageDraw, ImageFont
    
    draw = ImageDraw.Draw(canvas)
    
    font_candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    
    font = None
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, 24)
                break
            except Exception:
                continue
    
    if font is None:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    
    padding = 12
    bg_w = tw + padding * 2
    bg_h = th + padding * 2
    
    bg_x = center_x - bg_w // 2
    bg_y = center_y - bg_h // 2
    
    from PIL import ImageFilter
    
    bg_layer = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    
    bg_draw.rounded_rectangle(
        [bg_x, bg_y, bg_x + bg_w, bg_y + bg_h],
        radius=8,
        fill=(255, 255, 255, 200)
    )
    
    canvas = Image.alpha_composite(canvas, bg_layer)
    
    tx = center_x - tw // 2
    ty = center_y - th // 2
    
    draw.text((tx, ty), text, font=font, fill=(80, 80, 80, 255))
    
    return canvas
