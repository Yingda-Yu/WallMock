from PIL import Image, ImageDraw, ImageFilter
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets" / "device_frames"
DEVICE_CONFIGS_DIR = BASE_DIR / "assets" / "device_frames"

DEVICE_TYPES = {
    "dynamic_island_phone": {
        "name": "Dynamic Island Phone",
        "category": "phone",
        "screen_ratio": 9 / 19.5,
        "frame_width": 20,
        "corner_radius": 48,
        "dynamic_island": {"width": 95, "height": 28, "y_offset": 12},
        "notch": None,
        "punch_hole": None,
        "side_buttons": True,
        "color": "#1A1A1A",
    },
    "notch_phone": {
        "name": "Notch Phone",
        "category": "phone",
        "screen_ratio": 9 / 19,
        "frame_width": 14,
        "corner_radius": 40,
        "dynamic_island": None,
        "notch": {"width": 160, "height": 28, "y_offset": 0},
        "punch_hole": None,
        "side_buttons": True,
        "color": "#222222",
    },
    "waterdrop_phone": {
        "name": "Waterdrop Phone",
        "category": "phone",
        "screen_ratio": 9 / 19.5,
        "frame_width": 12,
        "corner_radius": 36,
        "dynamic_island": None,
        "notch": None,
        "punch_hole": {"type": "waterdrop", "size": 16, "x_offset": 0, "y_offset": 18},
        "side_buttons": True,
        "color": "#2A2A2A",
    },
    "punch_hole_phone": {
        "name": "Punch-hole Phone",
        "category": "phone",
        "screen_ratio": 9 / 20,
        "frame_width": 10,
        "corner_radius": 32,
        "dynamic_island": None,
        "notch": None,
        "punch_hole": {"type": "center", "size": 14, "x_offset": 0, "y_offset": 14},
        "side_buttons": True,
        "color": "#1E1E1E",
    },
    "no_notch_phone": {
        "name": "No-notch Phone",
        "category": "phone",
        "screen_ratio": 9 / 19,
        "frame_width": 10,
        "corner_radius": 32,
        "dynamic_island": None,
        "notch": None,
        "punch_hole": None,
        "side_buttons": True,
        "color": "#2D2D2D",
    },
    "tablet": {
        "name": "Tablet",
        "category": "tablet",
        "screen_ratio": 3 / 4,
        "frame_width": 28,
        "corner_radius": 24,
        "dynamic_island": None,
        "notch": None,
        "punch_hole": None,
        "side_buttons": False,
        "color": "#555555",
    },
    "laptop": {
        "name": "Laptop",
        "category": "laptop",
        "screen_ratio": 16 / 10,
        "frame_width": 22,
        "top_frame_width": 30,
        "bottom_frame_width": 50,
        "corner_radius": 12,
        "dynamic_island": None,
        "notch": None,
        "punch_hole": {"type": "center", "size": 6, "x_offset": 0, "y_offset": 12},
        "side_buttons": False,
        "has_base": True,
        "color": "#6B6B6B",
    },
    "desktop_monitor": {
        "name": "Desktop Monitor",
        "category": "monitor",
        "screen_ratio": 16 / 9,
        "frame_width": 18,
        "top_frame_width": 18,
        "bottom_frame_width": 40,
        "corner_radius": 8,
        "dynamic_island": None,
        "notch": None,
        "punch_hole": None,
        "side_buttons": False,
        "has_stand": True,
        "color": "#3D3D3D",
    },
}


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def generate_device_frame(device_type, base_size=800):
    if device_type not in DEVICE_TYPES:
        raise ValueError(f"未知设备类型: {device_type}")

    config = DEVICE_TYPES[device_type]
    category = config["category"]

    if category == "phone":
        return _generate_phone_frame(config, base_size)
    elif category == "tablet":
        return _generate_tablet_frame(config, base_size)
    elif category == "laptop":
        return _generate_laptop_frame(config, base_size)
    elif category == "monitor":
        return _generate_monitor_frame(config, base_size)
    else:
        return _generate_phone_frame(config, base_size)


def _generate_phone_frame(config, base_size):
    ratio = config["screen_ratio"]
    frame_w = config["frame_width"]
    corner_r = config["corner_radius"]
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + frame_w * 2
    total_h = screen_h + frame_w * 2

    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    outer_r = corner_r + frame_w
    draw.rounded_rectangle([(0, 0), (total_w - 1, total_h - 1)], radius=outer_r, fill=color + (255,))

    screen_inner_r = corner_r - 1
    draw.rounded_rectangle([(frame_w, frame_w), (total_w - frame_w - 1, total_h - frame_w - 1)], radius=screen_inner_r, fill=(0, 0, 0, 0))

    if config.get("dynamic_island"):
        di = config["dynamic_island"]
        di_w = di["width"]
        di_h = di["height"]
        di_x = (total_w - di_w) // 2
        di_y = frame_w + di["y_offset"]
        draw.rounded_rectangle(
            [(di_x, di_y), (di_x + di_w - 1, di_y + di_h - 1)],
            radius=di_h // 2,
            fill=(0, 0, 0, 255),
        )

    if config.get("notch"):
        notch = config["notch"]
        n_w = notch["width"]
        n_h = notch["height"]
        n_x = (total_w - n_w) // 2
        n_y = frame_w + notch["y_offset"]
        draw.rounded_rectangle(
            [(n_x, n_y), (n_x + n_w - 1, n_y + n_h - 1)],
            radius=n_h // 2,
            fill=(0, 0, 0, 255),
        )

    if config.get("punch_hole"):
        ph = config["punch_hole"]
        ph_size = ph["size"]
        if ph["type"] == "waterdrop":
            ph_x = total_w // 2 + ph["x_offset"]
            ph_y = frame_w + ph["y_offset"]
            draw.ellipse(
                [(ph_x - ph_size // 2, ph_y - ph_size // 2), (ph_x + ph_size // 2, ph_y + ph_size // 2)],
                fill=(0, 0, 0, 255),
            )
        elif ph["type"] == "center":
            ph_x = total_w // 2 + ph["x_offset"]
            ph_y = frame_w + ph["y_offset"]
            draw.ellipse(
                [(ph_x - ph_size // 2, ph_y - ph_size // 2), (ph_x + ph_size // 2, ph_y + ph_size // 2)],
                fill=(0, 0, 0, 255),
            )

    if config.get("side_buttons"):
        btn_w = 4
        btn_h = 60
        btn_x = total_w - 1
        btn_y = total_h * 0.25
        draw.rectangle([(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)], fill=color + (200,))
        btn_y2 = total_h * 0.42
        draw.rectangle([(btn_x, btn_y2), (btn_x + btn_w, btn_y2 + btn_h * 1.5)], fill=color + (200,))

    img = _add_shadow(img, offset=(10, 15), blur=30, opacity=120)

    screen_rect = {
        "x": frame_w,
        "y": frame_w,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }

    return img, screen_rect


def _generate_tablet_frame(config, base_size):
    ratio = config["screen_ratio"]
    frame_w = config["frame_width"]
    corner_r = config["corner_radius"]
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + frame_w * 2
    total_h = screen_h + frame_w * 2

    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    outer_r = corner_r + frame_w
    draw.rounded_rectangle([(0, 0), (total_w - 1, total_h - 1)], radius=outer_r, fill=color + (255,))

    screen_inner_r = corner_r - 1
    draw.rounded_rectangle([(frame_w, frame_w), (total_w - frame_w - 1, total_h - frame_w - 1)], radius=screen_inner_r, fill=(0, 0, 0, 0))

    img = _add_shadow(img, offset=(12, 18), blur=40, opacity=100)

    screen_rect = {
        "x": frame_w,
        "y": frame_w,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }

    return img, screen_rect


def _generate_laptop_frame(config, base_size):
    ratio = config["screen_ratio"]
    side_frame = config["frame_width"]
    top_frame = config["top_frame_width"]
    bottom_frame = config["bottom_frame_width"]
    corner_r = config["corner_radius"]
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + side_frame * 2
    total_h = screen_h + top_frame + bottom_frame

    img = Image.new("RGBA", (total_w + 80, total_h + 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    offset_x = 40
    offset_y = 30

    draw.rounded_rectangle(
        [(offset_x, offset_y), (offset_x + total_w - 1, offset_y + total_h - 1)],
        radius=corner_r + 4,
        fill=color + (255,),
    )

    draw.rounded_rectangle(
        [(offset_x + side_frame, offset_y + top_frame), (offset_x + total_w - side_frame - 1, offset_y + total_h - bottom_frame - 1)],
        radius=corner_r - 1,
        fill=(0, 0, 0, 0),
    )

    screen_x = offset_x + side_frame
    screen_y = offset_y + top_frame

    if config.get("punch_hole"):
        ph = config["punch_hole"]
        ph_size = ph["size"]
        ph_x = offset_x + total_w // 2 + ph["x_offset"]
        ph_y = offset_y + top_frame // 2 + ph["y_offset"] - 6
        draw.ellipse(
            [(ph_x - ph_size // 2, ph_y - ph_size // 2), (ph_x + ph_size // 2, ph_y + ph_size // 2)],
            fill=(20, 20, 20, 255),
        )

    base_y = offset_y + total_h - 5
    base_top_w = total_w + 30
    base_bottom_w = total_w + 60
    base_h = 15

    base_pts = [
        (offset_x - 15, base_y),
        (offset_x + total_w + 15, base_y),
        (offset_x + total_w + 30, base_y + base_h),
        (offset_x - 30, base_y + base_h),
    ]
    draw.polygon(base_pts, fill=hex_to_rgb("#4A4A4A") + (255,))

    img = _add_shadow(img, offset=(15, 20), blur=45, opacity=90)

    screen_rect = {
        "x": screen_x,
        "y": screen_y,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }

    return img, screen_rect


def _generate_monitor_frame(config, base_size):
    ratio = config["screen_ratio"]
    side_frame = config["frame_width"]
    top_frame = config["top_frame_width"]
    bottom_frame = config["bottom_frame_width"]
    corner_r = config["corner_radius"]
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + side_frame * 2
    total_h = screen_h + top_frame + bottom_frame

    img = Image.new("RGBA", (total_w + 100, total_h + 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    offset_x = 50
    offset_y = 30

    draw.rounded_rectangle(
        [(offset_x, offset_y), (offset_x + total_w - 1, offset_y + total_h - 1)],
        radius=corner_r + 4,
        fill=color + (255,),
    )

    draw.rounded_rectangle(
        [(offset_x + side_frame, offset_y + top_frame), (offset_x + total_w - side_frame - 1, offset_y + total_h - bottom_frame - 1)],
        radius=corner_r - 1,
        fill=(0, 0, 0, 0),
    )

    screen_x = offset_x + side_frame
    screen_y = offset_y + top_frame

    stand_top_y = offset_y + total_h
    stand_top_w = total_w * 0.2
    stand_top_x = offset_x + (total_w - stand_top_w) // 2
    stand_top_h = 50
    draw.rectangle(
        [(stand_top_x, stand_top_y), (stand_top_x + stand_top_w, stand_top_y + stand_top_h)],
        fill=hex_to_rgb("#555555") + (255,),
    )

    stand_base_y = stand_top_y + stand_top_h
    stand_base_w = total_w * 0.45
    stand_base_x = offset_x + (total_w - stand_base_w) // 2
    stand_base_h = 18
    draw.rounded_rectangle(
        [(stand_base_x, stand_base_y), (stand_base_x + stand_base_w, stand_base_y + stand_base_h)],
        radius=stand_base_h // 2,
        fill=hex_to_rgb("#444444") + (255,),
    )

    img = _add_shadow(img, offset=(15, 25), blur=50, opacity=80)

    screen_rect = {
        "x": screen_x,
        "y": screen_y,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }

    return img, screen_rect


def _add_shadow(img, offset=(10, 10), blur=20, opacity=100):
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    alpha = img.split()[-1]

    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, opacity))
    shadow_layer.putalpha(alpha)

    for _ in range(blur // 2):
        shadow_layer = shadow_layer.filter(ImageFilter.BLUR)

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur // 3))

    result = Image.new("RGBA", (img.width + abs(offset[0]) * 2, img.height + abs(offset[1]) * 2), (0, 0, 0, 0))

    shadow_x = offset[0] + abs(offset[0])
    shadow_y = offset[1] + abs(offset[1])
    result.paste(shadow_layer, (shadow_x, shadow_y), shadow_layer)

    frame_x = abs(offset[0])
    frame_y = abs(offset[1])
    result.paste(img, (frame_x, frame_y), img)

    return result


def generate_all_devices(base_size=800):
    os.makedirs(ASSETS_DIR, exist_ok=True)
    configs = {}

    for device_type, config in DEVICE_TYPES.items():
        print(f"生成设备框: {device_type}...")
        img, screen_rect = generate_device_frame(device_type, base_size)

        png_path = ASSETS_DIR / f"{device_type}.png"
        img.save(str(png_path), "PNG")

        configs[device_type] = {
            "name": config["name"],
            "category": config["category"],
            "frame_image": f"assets/device_frames/{device_type}.png",
            "screen": screen_rect,
            "total_size": {"width": img.width, "height": img.height},
            "screen_ratio": config["screen_ratio"],
            "has_cutout": config.get("dynamic_island") is not None
            or config.get("notch") is not None
            or config.get("punch_hole") is not None,
            "cutout_type": (
                "dynamic_island"
                if config.get("dynamic_island")
                else "notch"
                if config.get("notch")
                else "punch_hole"
                if config.get("punch_hole")
                else None
            ),
            "cutout_config": config.get("dynamic_island") or config.get("notch") or config.get("punch_hole"),
        }

    config_path = ASSETS_DIR / "devices.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)

    print(f"所有设备框生成完毕，保存在: {ASSETS_DIR}")
    return configs


if __name__ == "__main__":
    generate_all_devices()
