from PIL import Image, ImageDraw, ImageFilter
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets" / "device_frames"

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


def generate_device_frame(device_type, base_size=1600):
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
    mult = base_size / 800
    ratio = config["screen_ratio"]
    frame_w = int(config["frame_width"] * mult)
    corner_r = int(config["corner_radius"] * mult)
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + frame_w * 2
    total_h = screen_h + frame_w * 2

    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    outer_r = corner_r + frame_w
    draw.rounded_rectangle([(0, 0), (total_w - 1, total_h - 1)], radius=outer_r, fill=color + (255,))

    screen_inner_r = max(corner_r - int(mult), 0)
    draw.rounded_rectangle([(frame_w, frame_w), (total_w - frame_w - 1, total_h - frame_w - 1)], radius=screen_inner_r, fill=(0, 0, 0, 0))

    if config.get("dynamic_island"):
        di = config["dynamic_island"]
        di_w = int(di["width"] * mult)
        di_h = int(di["height"] * mult)
        di_x = (total_w - di_w) // 2
        di_y = frame_w + int(di["y_offset"] * mult)
        draw.rounded_rectangle(
            [(di_x, di_y), (di_x + di_w - 1, di_y + di_h - 1)],
            radius=di_h // 2,
            fill=(0, 0, 0, 255),
        )

    if config.get("notch"):
        notch = config["notch"]
        n_w = int(notch["width"] * mult)
        n_h = int(notch["height"] * mult)
        n_x = (total_w - n_w) // 2
        n_y = frame_w + int(notch["y_offset"] * mult)
        draw.rounded_rectangle(
            [(n_x, n_y), (n_x + n_w - 1, n_y + n_h - 1)],
            radius=n_h // 2,
            fill=(0, 0, 0, 255),
        )

    if config.get("punch_hole"):
        ph = config["punch_hole"]
        ph_size = int(ph["size"] * mult)
        ph_x = total_w // 2 + int(ph["x_offset"] * mult)
        ph_y = frame_w + int(ph["y_offset"] * mult)
        draw.ellipse(
            [(ph_x - ph_size // 2, ph_y - ph_size // 2), (ph_x + ph_size // 2, ph_y + ph_size // 2)],
            fill=(0, 0, 0, 255),
        )

    if config.get("side_buttons"):
        btn_w = max(int(4 * mult), 6)
        btn_h = int(60 * mult)
        btn_x = total_w - btn_w
        btn_y = int(total_h * 0.25)
        draw.rectangle([(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)], fill=color + (200,))
        btn_y2 = int(total_h * 0.42)
        draw.rectangle([(btn_x, btn_y2), (btn_x + btn_w, btn_y2 + int(btn_h * 1.5))], fill=color + (200,))

    screen_rect = {
        "x": frame_w,
        "y": frame_w,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }
    return img, screen_rect


def _generate_tablet_frame(config, base_size):
    mult = base_size / 800
    ratio = config["screen_ratio"]
    frame_w = int(config["frame_width"] * mult)
    corner_r = int(config["corner_radius"] * mult)
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + frame_w * 2
    total_h = screen_h + frame_w * 2

    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    outer_r = corner_r + frame_w
    draw.rounded_rectangle([(0, 0), (total_w - 1, total_h - 1)], radius=outer_r, fill=color + (255,))

    screen_inner_r = max(corner_r - int(mult), 0)
    draw.rounded_rectangle([(frame_w, frame_w), (total_w - frame_w - 1, total_h - frame_w - 1)], radius=screen_inner_r, fill=(0, 0, 0, 0))

    screen_rect = {
        "x": frame_w,
        "y": frame_w,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }
    return img, screen_rect


def _generate_laptop_frame(config, base_size):
    mult = base_size / 800
    ratio = config["screen_ratio"]
    side_frame = int(config["frame_width"] * mult)
    top_frame = int(config["top_frame_width"] * mult)
    bottom_frame = int(config["bottom_frame_width"] * mult)
    corner_r = int(config["corner_radius"] * mult)
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + side_frame * 2
    total_h = screen_h + top_frame + bottom_frame

    pad_x = int(40 * mult)
    pad_y = int(30 * mult)
    img_w = total_w + pad_x * 2
    img_h = total_h + pad_y * 2 + int(15 * mult)

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        [(pad_x, pad_y), (pad_x + total_w - 1, pad_y + total_h - 1)],
        radius=corner_r + int(4 * mult),
        fill=color + (255,),
    )

    draw.rounded_rectangle(
        [(pad_x + side_frame, pad_y + top_frame), (pad_x + total_w - side_frame - 1, pad_y + total_h - bottom_frame - 1)],
        radius=max(corner_r - int(mult), 0),
        fill=(0, 0, 0, 0),
    )

    screen_x = pad_x + side_frame
    screen_y = pad_y + top_frame

    if config.get("punch_hole"):
        ph = config["punch_hole"]
        ph_size = int(ph["size"] * mult)
        ph_x = pad_x + total_w // 2 + int(ph["x_offset"] * mult)
        ph_y = pad_y + top_frame // 2 + int(ph["y_offset"] * mult) - int(6 * mult)
        draw.ellipse(
            [(ph_x - ph_size // 2, ph_y - ph_size // 2), (ph_x + ph_size // 2, ph_y + ph_size // 2)],
            fill=(20, 20, 20, 255),
        )

    base_y = pad_y + total_h - int(5 * mult)
    base_top_w = total_w + int(30 * mult)
    base_bottom_w = total_w + int(60 * mult)
    base_h = int(15 * mult)

    base_pts = [
        (pad_x - int(15 * mult), base_y),
        (pad_x + total_w + int(15 * mult), base_y),
        (pad_x + total_w + int(30 * mult), base_y + base_h),
        (pad_x - int(30 * mult), base_y + base_h),
    ]
    draw.polygon(base_pts, fill=hex_to_rgb("#4A4A4A") + (255,))

    screen_rect = {
        "x": screen_x,
        "y": screen_y,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }
    return img, screen_rect


def _generate_monitor_frame(config, base_size):
    mult = base_size / 800
    ratio = config["screen_ratio"]
    side_frame = int(config["frame_width"] * mult)
    top_frame = int(config["top_frame_width"] * mult)
    bottom_frame = int(config["bottom_frame_width"] * mult)
    corner_r = int(config["corner_radius"] * mult)
    color = hex_to_rgb(config["color"])

    screen_w = base_size
    screen_h = int(screen_w / ratio)

    total_w = screen_w + side_frame * 2
    total_h = screen_h + top_frame + bottom_frame

    pad_x = int(50 * mult)
    pad_y = int(30 * mult)
    stand_h = int(68 * mult)
    img_w = total_w + pad_x * 2
    img_h = total_h + pad_y + stand_h

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        [(pad_x, pad_y), (pad_x + total_w - 1, pad_y + total_h - 1)],
        radius=corner_r + int(4 * mult),
        fill=color + (255,),
    )

    draw.rounded_rectangle(
        [(pad_x + side_frame, pad_y + top_frame), (pad_x + total_w - side_frame - 1, pad_y + total_h - bottom_frame - 1)],
        radius=max(corner_r - int(mult), 0),
        fill=(0, 0, 0, 0),
    )

    screen_x = pad_x + side_frame
    screen_y = pad_y + top_frame

    stand_top_y = pad_y + total_h
    stand_top_w = int(total_w * 0.2)
    stand_top_x = pad_x + (total_w - stand_top_w) // 2
    stand_top_h = int(50 * mult)
    draw.rectangle(
        [(stand_top_x, stand_top_y), (stand_top_x + stand_top_w, stand_top_y + stand_top_h)],
        fill=hex_to_rgb("#555555") + (255,),
    )

    stand_base_y = stand_top_y + stand_top_h
    stand_base_w = int(total_w * 0.45)
    stand_base_x = pad_x + (total_w - stand_base_w) // 2
    stand_base_h = int(18 * mult)
    draw.rounded_rectangle(
        [(stand_base_x, stand_base_y), (stand_base_x + stand_base_w, stand_base_y + stand_base_h)],
        radius=stand_base_h // 2,
        fill=hex_to_rgb("#444444") + (255,),
    )

    screen_rect = {
        "x": screen_x,
        "y": screen_y,
        "width": screen_w,
        "height": screen_h,
        "corner_radius": corner_r,
    }
    return img, screen_rect


def generate_all_devices(base_size=1600):
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
