import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_wallpaper(width, height, color, label=""):
    """Create a small deterministic test wallpaper with a visible pattern."""
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    for i in range(5):
        r = min(width, height) // 2 - i * 30
        if r > 0:
            lighter = tuple(min(255, c + 40) for c in color)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=lighter, width=3)
    if label:
        draw.text((cx - len(label) * 4, cy - 8), label, fill=(255, 255, 255))
    return img.convert("RGBA")


@pytest.fixture
def portrait_wallpaper():
    """1080x2400 portrait phone wallpaper."""
    return _make_wallpaper(1080, 2400, (200, 60, 60), "RED")


@pytest.fixture
def landscape_wallpaper():
    """1920x1080 landscape desktop wallpaper."""
    return _make_wallpaper(1920, 1080, (60, 120, 200), "BLUE")


@pytest.fixture
def square_wallpaper():
    """1080x1080 square wallpaper."""
    return _make_wallpaper(1080, 1080, (60, 160, 80), "GREEN")


@pytest.fixture
def portrait_wallpaper_2():
    """Second portrait wallpaper for multi-image templates."""
    return _make_wallpaper(1080, 2400, (180, 100, 200), "PURPLE")


@pytest.fixture
def portrait_wallpaper_3():
    """Third portrait wallpaper for collection template."""
    return _make_wallpaper(1080, 2400, (220, 160, 40), "GOLD")


@pytest.fixture
def portrait_wallpaper_4():
    """Fourth portrait wallpaper for collection template."""
    return _make_wallpaper(1080, 2400, (40, 160, 180), "CYAN")


@pytest.fixture
def default_render_options():
    """Standard render options matching the web UI defaults."""
    return {
        "background_color": "#F5F2EB",
        "bg_mode": "gradient",
        "canvas_width": 2400,
        "canvas_height": 2400,
        "lockscreen": {
            "show": True,
            "show_time": True,
            "show_date": True,
            "time": "9:42",
            "date": "1月13日 星期一",
            "auto_color": True,
            "text_shadow": True,
        },
        "brand": {
            "mode": "minimal",
            "show_brand": False,
            "show_subtitle": True,
            "subtitle": "",
            "opacity": 45,
        },
    }


def render_opts(canvas_key, overrides=None):
    """Build render options for a given canvas preset key."""
    from core.template_engine import CANVAS_PRESETS

    preset = CANVAS_PRESETS[canvas_key]
    opts = {
        "background_color": "#F5F2EB",
        "bg_mode": "gradient",
        "canvas_width": preset["width"],
        "canvas_height": preset["height"],
        "lockscreen": {
            "show": True,
            "time": "9:42",
            "date": "1月13日 星期一",
            "auto_color": True,
        },
        "brand": {
            "mode": "minimal",
            "show_brand": False,
            "show_subtitle": False,
            "subtitle": "",
            "opacity": 45,
        },
    }
    if overrides:
        opts.update(overrides)
    return opts
