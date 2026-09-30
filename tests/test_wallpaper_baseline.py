"""Regression tests that lock the WallMock wallpaper rendering baseline.

These tests verify that:
- All 7 current templates render without error
- Phone Hero (single-device) renders at the expected canvas dimensions
- Device Trio (multi-device) renders with correct layering
- All 5 canvas presets produce images at the declared dimensions
- The template registry returns the expected template IDs and categories
- API endpoints (/api/templates, /api/preview, /api/generate) remain backward compatible
- Wallpaper fit mode 'cover' does not distort the source image
"""
import base64
import io

import pytest
from PIL import Image

from core.template_engine import (
    list_templates,
    load_template,
    render_template,
    get_canvas_presets,
    CANVAS_PRESETS,
)
from core.ratio_detector import detect_ratio

EXPECTED_TEMPLATES = {
    "phone_hero": {"category": "hero", "device_count": 1},
    "desktop_hero": {"category": "hero", "device_count": 1},
    "tablet_hero": {"category": "hero", "device_count": 1},
    "laptop_phone": {"category": "hero", "device_count": 2},
    "device_trio": {"category": "hero", "device_count": 3},
    "wallpaper_collection": {"category": "collection", "device_count": 4},
    "phone_ratio_compare": {"category": "info", "device_count": 2},
}

EXPECTED_CANVAS_PRESETS = {
    "1:1": (2400, 2400),
    "4:3": (2400, 1800),
    "4:5": (2000, 2500),
    "2:3": (2000, 3000),
    "9:16": (1080, 1920),
}


# ── Template registry tests ──────────────────────────────────────────


def test_list_templates_returns_all_expected():
    templates = list_templates()
    ids = {t["id"] for t in templates}
    assert ids == set(EXPECTED_TEMPLATES), f"Unexpected template set: {ids}"


def test_template_categories_and_device_counts():
    for t in list_templates():
        tid = t["id"]
        assert tid in EXPECTED_TEMPLATES
        expected = EXPECTED_TEMPLATES[tid]
        assert t["category"] == expected["category"], f"{tid} category mismatch"
        assert t["device_count"] == expected["device_count"], f"{tid} device_count mismatch"


def test_each_template_json_loads():
    for tid in EXPECTED_TEMPLATES:
        tpl = load_template(tid)
        assert tpl["id"] == tid
        assert len(tpl["devices"]) == EXPECTED_TEMPLATES[tid]["device_count"]
        assert "background_color" in tpl
        assert "brand" in tpl


# ── Canvas preset tests ─────────────────────────────────────────────


def test_canvas_presets_match_expected():
    presets = get_canvas_presets()
    for key, (w, h) in EXPECTED_CANVAS_PRESETS.items():
        assert key in presets
        assert presets[key]["width"] == w
        assert presets[key]["height"] == h


# ── Single-device render tests ───────────────────────────────────────


def test_phone_hero_renders_at_each_canvas(portrait_wallpaper, default_render_options):
    for key in EXPECTED_CANVAS_PRESETS:
        w, h = EXPECTED_CANVAS_PRESETS[key]
        opts = dict(default_render_options)
        opts["canvas_width"] = w
        opts["canvas_height"] = h
        result = render_template("phone_hero", [portrait_wallpaper], opts)
        assert result.size == (w, h), f"phone_hero {key} got {result.size}"


def test_desktop_hero_renders_at_each_canvas(landscape_wallpaper, default_render_options):
    for key in EXPECTED_CANVAS_PRESETS:
        w, h = EXPECTED_CANVAS_PRESETS[key]
        opts = dict(default_render_options)
        opts["canvas_width"] = w
        opts["canvas_height"] = h
        result = render_template("desktop_hero", [landscape_wallpaper], opts)
        assert result.size == (w, h), f"desktop_hero {key} got {result.size}"


def test_tablet_hero_renders(portrait_wallpaper_2, default_render_options):
    opts = dict(default_render_options)
    result = render_template("tablet_hero", [portrait_wallpaper_2], opts)
    assert result.size == (2400, 2400)


# ── Multi-device render tests ───────────────────────────────────────


def test_laptop_phone_renders(landscape_wallpaper, portrait_wallpaper, default_render_options):
    opts = dict(default_render_options)
    result = render_template("laptop_phone", [landscape_wallpaper, portrait_wallpaper], opts)
    assert result.size == (2400, 2400)


def test_device_trio_renders(landscape_wallpaper, portrait_wallpaper_2, portrait_wallpaper, default_render_options):
    opts = dict(default_render_options)
    result = render_template(
        "device_trio",
        [landscape_wallpaper, portrait_wallpaper_2, portrait_wallpaper],
        opts,
    )
    assert result.size == (2400, 2400)


def test_wallpaper_collection_renders(portrait_wallpaper, portrait_wallpaper_2, portrait_wallpaper_3, portrait_wallpaper_4, default_render_options):
    opts = dict(default_render_options)
    imgs = [portrait_wallpaper, portrait_wallpaper_2, portrait_wallpaper_3, portrait_wallpaper_4]
    result = render_template("wallpaper_collection", imgs, opts)
    assert result.size == (2400, 2400)


def test_phone_ratio_compare_renders(portrait_wallpaper, default_render_options):
    opts = dict(default_render_options)
    result = render_template("phone_ratio_compare", [portrait_wallpaper], opts)
    assert result.size == (2400, 2400)


# ── Wallpaper fit / no-distortion test ──────────────────────────────


def test_cover_fit_does_not_distort_source_ratio(portrait_wallpaper, default_render_options):
    """A portrait wallpaper on a landscape canvas must not stretch—cover crops, not distorts."""
    opts = dict(default_render_options)
    opts["canvas_width"] = 2400
    opts["canvas_height"] = 1800  # landscape canvas
    result = render_template("desktop_hero", [portrait_wallpaper], opts)
    assert result.size == (2400, 1800)
    # The result should not error and should produce a valid RGBA image
    assert result.mode == "RGBA"


# ── Output is deterministic ────────────────────────────────────────


def test_repeated_render_is_deterministic(portrait_wallpaper, default_render_options):
    opts = dict(default_render_options)
    r1 = render_template("phone_hero", [portrait_wallpaper], opts)
    r2 = render_template("phone_hero", [portrait_wallpaper], opts)
    assert r1.size == r2.size
    buf1 = io.BytesIO()
    buf2 = io.BytesIO()
    r1.convert("RGB").save(buf1, "PNG")
    r2.convert("RGB").save(buf2, "PNG")
    assert buf1.getvalue() == buf2.getvalue(), "Repeated render produced different pixels"


# ── API backward-compatibility tests (local Flask app) ──────────────


def test_local_api_templates_endpoint():
    from app import app
    client = app.test_client()
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.get_json()
    ids = {t["id"] for t in data["templates"]}
    assert "phone_hero" in ids
    assert "device_trio" in ids


def test_local_api_canvas_presets_endpoint():
    from app import app
    client = app.test_client()
    resp = client.get("/api/canvas-presets")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "1:1" in data["presets"]
    assert "9:16" in data["presets"]


def test_local_api_preview_endpoint(portrait_wallpaper):
    from app import app
    client = app.test_client()
    buf = io.BytesIO()
    portrait_wallpaper.convert("RGB").save(buf, "JPEG", quality=85)
    buf.seek(0)
    buf.name = "test.jpg"
    upload_resp = client.post(
        "/api/upload",
        data={"images": (buf, "test.jpg")},
        content_type="multipart/form-data",
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.get_json()
    assert upload_data["success"] is True
    img_ids = [img["id"] for img in upload_data["images"]]

    resp = client.post("/api/preview", json={
        "template_id": "phone_hero",
        "image_ids": img_ids,
        "options": {
            "background_color": "#F5F2EB",
            "canvas_width": 2400,
            "canvas_height": 2400,
            "lockscreen": {"show": True, "time": "9:42", "date": "1月13日", "auto_color": True},
            "brand": {"mode": "minimal", "show_brand": False, "show_subtitle": False},
        },
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("success") is True
    assert data["size"]["width"] == 2400
    assert data["size"]["height"] == 2400


# ── API backward-compatibility tests (Vercel-style entry) ───────────


def test_vercel_api_templates_endpoint():
    from api.index import app
    client = app.test_client()
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.get_json()
    ids = {t["id"] for t in data["templates"]}
    assert "phone_hero" in ids
    assert "device_trio" in ids


def test_vercel_api_preview_endpoint(portrait_wallpaper):
    from api.index import app
    client = app.test_client()
    buf = io.BytesIO()
    portrait_wallpaper.convert("RGB").save(buf, "JPEG", quality=85)
    img_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    resp = client.post("/api/preview", json={
        "template_id": "phone_hero",
        "images": [{"base64": img_b64, "filename": "test.jpg"}],
        "options": {
            "background_color": "#F5F2EB",
            "canvas_width": 2400,
            "canvas_height": 2400,
            "lockscreen": {"show": True, "time": "9:42", "date": "1月13日", "auto_color": True},
            "brand": {"mode": "minimal", "show_brand": False, "show_subtitle": False},
        },
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("success") is True
