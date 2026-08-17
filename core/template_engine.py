import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

from .device_renderer import render_device, load_device_configs
from .text_renderer import render_brand_text, get_available_font
from .ratio_detector import detect_ratio

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

CANVAS_PRESETS = {
    "1:1": {"name": "Marketplace Square", "width": 2400, "height": 2400},
    "4:3": {"name": "Marketplace Landscape", "width": 2400, "height": 1800},
    "4:5": {"name": "Product Portrait", "width": 2000, "height": 2500},
    "2:3": {"name": "Pinterest", "width": 2000, "height": 3000},
    "9:16": {"name": "Story / Reel Cover", "width": 1080, "height": 1920},
}

BG_PRESETS = {
    "warm_ivory": "#F5F2EB",
    "pure_white": "#FFFFFF",
    "soft_gray": "#F2F2F2",
    "charcoal": "#202020",
    "near_black": "#111111",
}


def get_canvas_presets():
    return CANVAS_PRESETS


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
                    "category": tpl.get("category", "hero"),
                    "description": tpl.get("description", ""),
                    "device_count": len(tpl.get("devices", [])),
                    "min_images": tpl.get("min_images", 1),
                    "default_canvas": tpl.get("default_canvas", "1:1"),
                    "thumbnail": tpl.get("thumbnail", ""),
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

    canvas_w = int(options.get("canvas_width", 2400))
    canvas_h = int(options.get("canvas_height", 2400))
    bg_color_hex = options.get("background_color", template.get("background_color", "#F5F2EB"))
    bg_mode = options.get("bg_mode", "solid")

    canvas = _create_background(canvas_w, canvas_h, bg_color_hex, bg_mode, images)

    brand_options = options.get("brand", {})
    lockscreen_options = options.get("lockscreen", {})
    per_device_options = options.get("device_options", {})
    device_sources = options.get("device_sources", {})

    devices = sorted(template.get("devices", []), key=lambda d: d.get("z_index", 0))
    device_configs = load_device_configs()

    assigned_images = _assign_images_to_devices(images, devices, device_sources)

    for device_cfg in devices:
        dev_id = device_cfg.get("id", "")
        wp_img = assigned_images.get(dev_id)
        if wp_img is None:
            continue

        dev_type = device_cfg.get("type", "dynamic_island_phone")
        if dev_type not in device_configs:
            continue

        dev_native = device_configs[dev_type]
        native_w = dev_native["total_size"]["width"]
        native_h = dev_native["total_size"]["height"]

        scale = _compute_scale(device_cfg, native_w, native_h, canvas_w, canvas_h)

        dev_opts = per_device_options.get(dev_id, {})
        fit_mode = dev_opts.get("fit_mode", "cover")
        offset_x = dev_opts.get("offset_x", 0)
        offset_y = dev_opts.get("offset_y", 0)
        zoom = dev_opts.get("zoom", 1.0)

        device_img = render_device(
            wp_img,
            dev_type,
            scale=scale,
            fit_mode=fit_mode,
            offset_x=offset_x,
            offset_y=offset_y,
            zoom=zoom,
            lockscreen_options=lockscreen_options,
        )

        pos_x, pos_y = _compute_position(device_cfg, device_img, canvas_w, canvas_h)

        rotation = device_cfg.get("rotation", 0)
        if rotation != 0:
            device_img = device_img.rotate(rotation, resample=Image.BICUBIC, expand=True)

        shadow_cfg = device_cfg.get("shadow", {})
        canvas = _draw_premium_shadow(
            canvas, device_img, pos_x, pos_y,
            ambient_blur=shadow_cfg.get("ambient_blur", 0.015),
            ambient_opacity=shadow_cfg.get("ambient_opacity", 18),
            contact_blur=shadow_cfg.get("contact_blur", 0.005),
            contact_opacity=shadow_cfg.get("contact_opacity", 35),
            contact_offset=shadow_cfg.get("contact_offset", 0.004),
        )

        canvas.paste(device_img, (pos_x, pos_y), device_img)

    brand_cfg = template.get("brand", {})
    brand_mode = brand_options.get("mode", brand_cfg.get("mode", "minimal"))
    if brand_mode != "none" and brand_options.get("show_brand", True):
        canvas = _render_branding(canvas, brand_cfg, brand_options, canvas_w, canvas_h)

    return canvas


def _compute_scale(device_cfg, native_w, native_h, canvas_w, canvas_h):
    height_ratio = device_cfg.get("height_ratio")
    width_ratio = device_cfg.get("width_ratio")
    legacy_scale = device_cfg.get("scale")

    if height_ratio and width_ratio:
        scale_h = (height_ratio * canvas_h) / native_h
        scale_w = (width_ratio * canvas_w) / native_w
        return min(scale_h, scale_w)
    elif height_ratio:
        return (height_ratio * canvas_h) / native_h
    elif width_ratio:
        return (width_ratio * canvas_w) / native_w
    elif legacy_scale:
        return legacy_scale
    else:
        return 0.5


def _compute_position(device_cfg, device_img, canvas_w, canvas_h):
    anchor = device_cfg.get("anchor", "center")
    x_ratio = device_cfg.get("x")
    y_ratio = device_cfg.get("y")
    x_offset_ratio = device_cfg.get("x_offset_ratio", 0)
    y_offset_ratio = device_cfg.get("y_offset_ratio", 0)

    dev_w = device_img.width
    dev_h = device_img.height

    if x_ratio is not None:
        cx = x_ratio * canvas_w
    else:
        anchor_map = {
            "center": 0.5,
            "upper_center": 0.5,
            "lower_center": 0.5,
            "upper_left": 0.28,
            "upper_right": 0.72,
            "lower_left": 0.28,
            "lower_right": 0.72,
            "left_center": 0.28,
            "right_center": 0.72,
        }
        cx = anchor_map.get(anchor, 0.5) * canvas_w

    if y_ratio is not None:
        cy = y_ratio * canvas_h
    else:
        anchor_y_map = {
            "center": 0.48,
            "upper_center": 0.32,
            "lower_center": 0.66,
            "upper_left": 0.32,
            "upper_right": 0.32,
            "lower_left": 0.66,
            "lower_right": 0.66,
            "left_center": 0.48,
            "right_center": 0.48,
        }
        cy = anchor_y_map.get(anchor, 0.48) * canvas_h

    cx += x_offset_ratio * canvas_w
    cy += y_offset_ratio * canvas_h

    pos_x = int(cx - dev_w / 2)
    pos_y = int(cy - dev_h / 2)

    return pos_x, pos_y


def _assign_images_to_devices(images, devices, device_sources=None):
    if not images:
        return {}

    assigned = {}
    if device_sources:
        for dev in devices:
            dev_id = dev.get("id", "")
            slot = device_sources.get(dev_id)
            if slot is not None and slot < len(images):
                assigned[dev_id] = images[slot]
        if len(assigned) == len(devices):
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
        dev_id = device_cfg.get("id", "")
        if dev_id in assigned:
            continue

        slot = device_cfg.get("image_slot", 0)
        preferred = device_cfg.get("preferred_orientation", "")

        if preferred == "landscape" and landscape_imgs:
            idx, img = landscape_imgs.pop(0)
            assigned[dev_id] = img
        elif preferred == "portrait" and portrait_imgs:
            idx, img = portrait_imgs.pop(0)
            assigned[dev_id] = img
        elif preferred == "landscape" and not landscape_imgs:
            source = portrait_imgs or other_imgs
            if source:
                idx, img = source.pop(0)
                assigned[dev_id] = img
        elif preferred == "portrait" and not portrait_imgs:
            source = landscape_imgs or other_imgs
            if source:
                idx, img = source.pop(0)
                assigned[dev_id] = img

    all_remaining = portrait_imgs + landscape_imgs + other_imgs
    for device_cfg in devices:
        dev_id = device_cfg.get("id", "")
        if dev_id not in assigned:
            slot = device_cfg.get("image_slot", 0)
            if slot < len(images):
                assigned[dev_id] = images[slot]
            elif all_remaining:
                idx, img = all_remaining.pop(0)
                assigned[dev_id] = img
            elif images:
                assigned[dev_id] = images[slot % len(images)]

    return assigned


def _create_background(width, height, base_color_hex, mode="solid", images=None):
    bg_color = _hex_to_rgba(base_color_hex)

    if mode == "adaptive" and images:
        try:
            img = images[0]
            small = img.resize((1, 1), Image.LANCZOS)
            r, g, b = small.getpixel((0, 0))[:3]
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            if brightness > 180:
                r = int(r * 0.92 + 240 * 0.08)
                g = int(g * 0.92 + 238 * 0.08)
                b = int(b * 0.92 + 232 * 0.08)
            else:
                r = int(r * 0.15 + 30 * 0.85)
                g = int(g * 0.15 + 30 * 0.85)
                b = int(b * 0.15 + 30 * 0.85)
            bg_color = (min(r, 255), min(g, 255), min(b, 255), 255)
        except Exception:
            pass

    canvas = Image.new("RGBA", (width, height), bg_color)

    if mode != "solid":
        overlay_size = int(min(width, height) * 0.7)
        overlay_x = (width - overlay_size) // 2
        overlay_y = (height - overlay_size) // 2

        try:
            import numpy as np
            y_coords, x_coords = np.ogrid[:overlay_size, :overlay_size]
            center = overlay_size // 2
            dist = np.sqrt((x_coords - center) ** 2 + (y_coords - center) ** 2)
            max_dist = center
            alpha = np.clip(8 * (1 - dist / max_dist), 0, 255).astype(np.uint8)

            gradient_array = np.zeros((overlay_size, overlay_size, 4), dtype=np.uint8)
            gradient_array[:, :, 3] = alpha
            gradient = Image.fromarray(gradient_array, "RGBA")
            canvas.paste(gradient, (overlay_x, overlay_y), gradient)
        except ImportError:
            pass

    return canvas


def _draw_premium_shadow(canvas, device_img, pos_x, pos_y,
                         ambient_blur=0.015, ambient_opacity=18,
                         contact_blur=0.005, contact_opacity=35,
                         contact_offset=0.004):
    from PIL import ImageFilter

    mask = device_img.split()[3]
    canvas_w, canvas_h = canvas.size

    blur_radius_ambient = max(int(max(canvas_w, canvas_h) * ambient_blur), 8)
    blur_radius_contact = max(int(max(canvas_w, canvas_h) * contact_blur), 4)
    contact_off = max(int(max(canvas_w, canvas_h) * contact_offset), 2)

    padding = blur_radius_ambient * 3
    shadow_w = device_img.width + padding * 2
    shadow_h = device_img.height + padding * 2

    ambient = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    ambient_layer = Image.new("RGBA", device_img.size, (0, 0, 0, ambient_opacity))
    ambient_layer.putalpha(mask)
    ambient.paste(ambient_layer, (padding, padding), ambient_layer)
    ambient = ambient.filter(ImageFilter.GaussianBlur(radius=blur_radius_ambient))

    shadow_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    amb_x = pos_x - padding + int(blur_radius_ambient * 0.3)
    amb_y = pos_y - padding + int(blur_radius_ambient * 0.5)
    shadow_canvas.paste(ambient, (amb_x, amb_y), ambient)

    contact = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    contact_layer = Image.new("RGBA", device_img.size, (0, 0, 0, contact_opacity))
    contact_layer.putalpha(mask)
    contact.paste(contact_layer, (padding, padding), contact_layer)
    contact = contact.filter(ImageFilter.GaussianBlur(radius=blur_radius_contact))

    ct_x = pos_x - padding + 2
    ct_y = pos_y - padding + contact_off
    shadow_canvas.paste(contact, (ct_x, ct_y), contact)

    canvas = Image.alpha_composite(canvas, shadow_canvas)
    return canvas


def _render_branding(canvas, brand_cfg, brand_options, canvas_w, canvas_h):
    brand_mode = brand_options.get("mode", brand_cfg.get("mode", "minimal"))

    if brand_mode == "watermark":
        return _render_watermark(canvas, brand_options, canvas_w, canvas_h)

    bx = int(brand_cfg.get("y_ratio", 0.94) * canvas_h) if "y_ratio" in brand_cfg else int(brand_cfg.get("y", 0.88) * canvas_h)
    bx_x = int(canvas_w * 0.5)

    brand_name = brand_options.get("name", brand_cfg.get("default_name", ""))
    subtitle = brand_options.get("subtitle", brand_cfg.get("default_subtitle", ""))

    opacity = brand_options.get("opacity", 45)
    brand_size = int(brand_options.get("brand_size", brand_cfg.get("brand_size", 42)) * canvas_w / 2400)
    subtitle_size = int(brand_options.get("subtitle_size", brand_cfg.get("subtitle_size", 20)) * canvas_w / 2400)
    brand_size = max(brand_size, 18)
    subtitle_size = max(subtitle_size, 12)

    text_opts = {
        "show_brand": brand_options.get("show_brand", True),
        "show_subtitle": brand_options.get("show_subtitle", True),
        "brand_size": brand_size,
        "subtitle_size": subtitle_size,
        "brand_color": brand_options.get("brand_color", "#333333"),
        "subtitle_color": brand_options.get("subtitle_color", "#888888"),
        "align": brand_options.get("align", "center"),
        "uppercase_subtitle": brand_options.get("uppercase_subtitle", True),
        "letter_spacing": brand_options.get("letter_spacing", 3),
        "line_spacing": brand_options.get("line_spacing", 10),
        "text_style": "minimal",
        "opacity": opacity,
    }

    canvas = render_brand_text(canvas, brand_name, subtitle, bx_x, bx, text_opts)
    return canvas


def _render_watermark(canvas, brand_options, canvas_w, canvas_h):
    draw = ImageDraw.Draw(canvas)

    text = brand_options.get("watermark_text", brand_options.get("name", "SPARTINA"))
    font_size = max(int(canvas_w * 0.04), 28)
    font = get_available_font(font_size)
    opacity = brand_options.get("opacity", 10)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    spacing_x = tw + int(tw * 0.8)
    spacing_y = th + int(th * 1.5)

    angle = -30
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    y = -canvas_h // 2
    while y < canvas_h + canvas_h // 2:
        x = -canvas_w // 2
        while x < canvas_w + canvas_w // 2:
            overlay_draw.text((x, y), text, font=font, fill=(128, 128, 128, opacity))
            x += spacing_x
        y += spacing_y

    overlay = overlay.rotate(angle, resample=Image.BICUBIC, expand=False, center=(canvas_w // 2, canvas_h // 2))

    canvas = Image.alpha_composite(canvas, overlay)
    return canvas


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
