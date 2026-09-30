"""
Unit tests for core/case_renderer.py.

Covers: render output dimensions, print-mask clipping, camera exclusion,
optional layer handling, deterministic rendering, and template reuse
across multiple artworks.
"""

import os
import json
import tempfile
import numpy as np
import pytest
from PIL import Image, ImageDraw

from core.catalog_models import (
    Canvas, CaseTemplate, CaseTemplateLayer, PrintRegion,
)
from core.case_renderer import render_case
from core.case_template_loader import load_case_template


# ─── Path to the real iPhone 17e template ──────────────────────────────────

TEMPLATE_DIR = os.path.join(
    os.path.dirname(__file__), "..",
    "assets", "case_templates", "apple", "iphone-17e", "hard", "rear",
)
TEMPLATE_JSON = os.path.join(TEMPLATE_DIR, "template.json")


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def iphone_template():
    """Load the real iPhone 17e template."""
    return load_case_template(TEMPLATE_JSON)


@pytest.fixture
def solid_art():
    """400x400 solid red artwork."""
    return Image.new("RGBA", (400, 400), (255, 0, 0, 255))


@pytest.fixture
def artwork_color_block():
    """Load the color-block test fixture."""
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "artworks", "color-block.png"
    )
    return Image.open(path).convert("RGBA")


@pytest.fixture
def artwork_tile_pattern():
    """Load the tile-pattern test fixture."""
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "artworks", "tile-pattern.png"
    )
    return Image.open(path).convert("RGBA")


@pytest.fixture
def artwork_transparent():
    """Load the transparent-artwork test fixture."""
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "artworks", "transparent-artwork.png"
    )
    return Image.open(path).convert("RGBA")


# ─── Minimal synthetic template for isolated tests ────────────────────────

@pytest.fixture
def minimal_template(tmp_path):
    """Create a minimal template with only required layers (base + artwork + overlay)."""
    canvas_w, canvas_h = 400, 600
    case_x, case_y = 50, 50
    case_w, case_h = 300, 500
    corner_r = 40

    # base.png — solid case body
    base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle(
        [case_x, case_y, case_x + case_w, case_y + case_h],
        radius=corner_r, fill=(240, 240, 240, 255)
    )
    base.save(str(tmp_path / "base.png"))

    # print_mask.png — slightly smaller than case body
    bezel = 10
    mask = Image.new("L", (canvas_w, canvas_h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(
        [case_x + bezel, case_y + bezel,
         case_x + case_w - bezel, case_y + case_h - bezel],
        radius=corner_r - bezel, fill=255
    )
    mask.save(str(tmp_path / "print_mask.png"))

    # overlay.png — small non-printable detail at top
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.ellipse([100, 60, 250, 110], fill=(100, 100, 100, 200))
    overlay.save(str(tmp_path / "overlay.png"))

    template_data = {
        "schema_version": 1,
        "id": "test__hard__rear",
        "device_id": "test",
        "case_type": "hard",
        "view": "rear",
        "canvas": {"width": canvas_w, "height": canvas_h},
        "print_region": {
            "mode": "mask",
            "x": case_x + bezel,
            "y": case_y + bezel,
            "width": case_w - 2 * bezel,
            "height": case_h - 2 * bezel,
            "fit": "cover",
            "mask": "print_mask.png",
        },
        "layers": [
            {"type": "base", "file": "base.png"},
            {"type": "artwork", "blend": "normal"},
            {"type": "overlay", "file": "overlay.png"},
        ],
    }

    template_path = tmp_path / "template.json"
    with open(template_path, "w") as f:
        json.dump(template_data, f)

    return load_case_template(template_path), str(tmp_path)


# ─── Output dimensions ────────────────────────────────────────────────────

class TestOutputDimensions:

    def test_render_produces_canvas_dimensions(self, iphone_template, solid_art):
        """Render output must match template canvas dimensions."""
        result = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR)
        assert result.size == (iphone_template.canvas.width, iphone_template.canvas.height)

    def test_render_produces_rgba(self, iphone_template, solid_art):
        """Render output must be RGBA."""
        result = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR)
        assert result.mode == "RGBA"

    def test_render_with_minimal_template(self, minimal_template, solid_art):
        """Render with a minimal synthetic template."""
        template, tpl_dir = minimal_template
        result = render_case(solid_art, template, template_dir=tpl_dir)
        assert result.size == (400, 600)
        assert result.mode == "RGBA"


# ─── Print-mask clipping ─────────────────────────────────────────────────

class TestPrintMaskClipping:

    def test_artwork_does_not_exceed_print_mask(self, minimal_template, solid_art):
        """Artwork must not appear outside the print mask region."""
        template, tpl_dir = minimal_template
        result = render_case(solid_art, template, template_dir=tpl_dir)

        # Load the print mask
        mask = Image.open(os.path.join(tpl_dir, "print_mask.png"))
        mask_arr = np.array(mask)

        # Where mask is 0, there should be no artwork contribution
        # We check: pixels where mask==0 should not have red (the artwork color)
        result_arr = np.array(result)
        non_printable = mask_arr == 0

        # In non-printable areas, the red channel should not be dominant
        # (the artwork is solid red, so if it leaked, R would be high)
        if non_printable.any():
            red_in_exclusion = result_arr[non_printable][:, 0]
            # Red channel should not be 255 (pure artwork red)
            # It could be 240 from base, but not 255
            assert red_in_exclusion.max() < 255, \
                "Artwork leaked outside print mask"

    def test_artwork_present_inside_print_mask(self, minimal_template, solid_art):
        """Artwork must be visible inside the print mask region."""
        template, tpl_dir = minimal_template
        result = render_case(solid_art, template, template_dir=tpl_dir)

        mask = Image.open(os.path.join(tpl_dir, "print_mask.png"))
        mask_arr = np.array(mask)
        result_arr = np.array(result)

        printable = mask_arr > 128
        if printable.any():
            # Artwork is solid red (255, 0, 0)
            red_pixels = result_arr[printable]
            # Should have significant red channel
            assert red_pixels[:, 0].mean() > 100, \
                "Artwork should be visible inside print mask"


# ─── Camera exclusion ────────────────────────────────────────────────────

class TestCameraExclusion:

    def test_camera_region_excluded_from_artwork(self, iphone_template, solid_art):
        """Artwork must not paint across the camera module region."""
        result = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR)

        # The camera module is at approximately (406, 116) with size 320
        # Per generate_iphone17e_template.py
        cam_x, cam_y = 406, 116
        cam_size = 320

        # Sample center of camera module
        cx = cam_x + cam_size // 2
        cy = cam_y + cam_size // 2
        result_arr = np.array(result)

        # The camera region should NOT be pure red (the artwork color)
        # The overlay (camera ring/lens) should be visible instead
        center_pixel = result_arr[cy, cx]
        # If artwork leaked through, R would be 255 and G,B would be 0
        assert not (center_pixel[0] == 255 and center_pixel[1] == 0 and center_pixel[2] == 0), \
            "Artwork leaked into camera module center"

    def test_camera_lens_region_protected(self, iphone_template, solid_art):
        """The lens area should be dark (not artwork color)."""
        result = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR)
        result_arr = np.array(result)

        # Lens is at center of camera module
        lens_x = 406 + (320 - 160) // 2  # CAM_X + (CAM_MOD_SIZE - LENS_D) // 2
        lens_y = 116 + (320 - 160) // 2
        lens_d = 160

        # Sample center of lens
        cx = lens_x + lens_d // 2
        cy = lens_y + lens_d // 2

        lens_pixel = result_arr[cy, cx]
        # Lens should be dark, not red
        assert lens_pixel[0] < 200, "Lens region should not have artwork red"


# ─── Optional layer handling ──────────────────────────────────────────────

class TestOptionalLayers:

    def test_missing_highlight_does_not_crash(self, minimal_template, solid_art):
        """Template without highlight layer should render fine."""
        template, tpl_dir = minimal_template
        # minimal_template has no highlight layer
        result = render_case(solid_art, template, template_dir=tpl_dir)
        assert result.size == (400, 600)

    def test_missing_shadow_does_not_crash(self, minimal_template, solid_art):
        """Template without shadow layer should render fine."""
        template, tpl_dir = minimal_template
        # minimal_template has no shadow layer
        result = render_case(solid_art, template, template_dir=tpl_dir)
        assert result.size == (400, 600)

    def test_missing_optional_file_is_skipped(self, tmp_path, solid_art):
        """Optional layers (highlight, shadow) with missing files are skipped."""
        canvas_w, canvas_h = 300, 500
        base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        d.rounded_rectangle([30, 30, 270, 470], radius=30, fill=(240, 240, 240, 255))
        base.save(str(tmp_path / "base.png"))

        mask = Image.new("L", (canvas_w, canvas_h), 0)
        d = ImageDraw.Draw(mask)
        d.rounded_rectangle([40, 40, 260, 460], radius=25, fill=255)
        mask.save(str(tmp_path / "print_mask.png"))

        template_data = {
            "schema_version": 1,
            "id": "test__hard__rear",
            "device_id": "test",
            "case_type": "hard",
            "view": "rear",
            "canvas": {"width": canvas_w, "height": canvas_h},
            "print_region": {
                "mode": "mask",
                "x": 40, "y": 40,
                "width": 220, "height": 420,
                "fit": "cover",
                "mask": "print_mask.png",
            },
            "layers": [
                {"type": "base", "file": "base.png"},
                {"type": "artwork", "blend": "normal"},
                {"type": "highlight", "file": "highlight.png"},
                {"type": "shadow", "file": "shadow.png"},
            ],
        }
        template_path = tmp_path / "template.json"
        with open(template_path, "w") as f:
            json.dump(template_data, f)

        template = load_case_template(template_path)
        result = render_case(solid_art, template, template_dir=str(tmp_path))
        assert result.size == (300, 500)

    def test_missing_required_overlay_raises(self, tmp_path, solid_art):
        """Missing overlay (required) file must raise FileNotFoundError."""
        canvas_w, canvas_h = 300, 500
        base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        d.rounded_rectangle([30, 30, 270, 470], radius=30, fill=(240, 240, 240, 255))
        base.save(str(tmp_path / "base.png"))

        mask = Image.new("L", (canvas_w, canvas_h), 0)
        d = ImageDraw.Draw(mask)
        d.rounded_rectangle([40, 40, 260, 460], radius=25, fill=255)
        mask.save(str(tmp_path / "print_mask.png"))

        template_data = {
            "schema_version": 1,
            "id": "test__hard__rear",
            "device_id": "test",
            "case_type": "hard",
            "view": "rear",
            "canvas": {"width": canvas_w, "height": canvas_h},
            "print_region": {
                "mode": "mask",
                "x": 40, "y": 40,
                "width": 220, "height": 420,
                "fit": "cover",
                "mask": "print_mask.png",
            },
            "layers": [
                {"type": "base", "file": "base.png"},
                {"type": "artwork", "blend": "normal"},
                {"type": "overlay", "file": "overlay.png"},
            ],
        }
        template_path = tmp_path / "template.json"
        with open(template_path, "w") as f:
            json.dump(template_data, f)

        template = load_case_template(template_path)
        with pytest.raises(FileNotFoundError, match="Template layer not found"):
            render_case(solid_art, template, template_dir=str(tmp_path))


# ─── Deterministic rendering ──────────────────────────────────────────────

class TestDeterministicRender:

    def test_same_input_same_output(self, iphone_template, solid_art):
        """Rendering the same artwork twice must produce identical pixels."""
        r1 = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR)
        r2 = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR)
        assert np.array_equal(np.array(r1), np.array(r2)), \
            "Same input should produce identical output"

    def test_deterministic_with_different_fit_modes(self, iphone_template, solid_art):
        """Determinism holds across fit modes."""
        for mode in ["cover", "contain"]:
            r1 = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR, fit_mode=mode)
            r2 = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR, fit_mode=mode)
            assert np.array_equal(np.array(r1), np.array(r2)), \
                f"Deterministic render failed for mode={mode}"


# ─── Template reuse across artworks ────────────────────────────────────────

class TestTemplateReuse:

    def test_three_artworks_same_template(self, iphone_template,
                                          artwork_color_block,
                                          artwork_tile_pattern,
                                          artwork_transparent):
        """The same template must render all three artworks without changes."""
        artworks = [
            ("color-block", artwork_color_block),
            ("tile-pattern", artwork_tile_pattern),
            ("transparent-artwork", artwork_transparent),
        ]

        results = []
        for name, art in artworks:
            result = render_case(art, iphone_template, template_dir=TEMPLATE_DIR)
            assert result.size == (iphone_template.canvas.width, iphone_template.canvas.height)
            results.append((name, np.array(result)))

        # All three renders should be different from each other
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                name_i, arr_i = results[i]
                name_j, arr_j = results[j]
                assert not np.array_equal(arr_i, arr_j), \
                    f"Artwork '{name_i}' and '{name_j}' produced identical renders " \
                    f"(they should be visually different)"

    def test_different_fit_modes_produce_different_output(self, iphone_template,
                                                          artwork_color_block):
        """Different fit modes on the same artwork should produce different output."""
        r_cover = render_case(artwork_color_block, iphone_template,
                               template_dir=TEMPLATE_DIR, fit_mode="cover")
        r_contain = render_case(artwork_color_block, iphone_template,
                                template_dir=TEMPLATE_DIR, fit_mode="contain")
        r_tile = render_case(artwork_color_block, iphone_template,
                             template_dir=TEMPLATE_DIR, fit_mode="tile")

        assert not np.array_equal(np.array(r_cover), np.array(r_contain)), \
            "Cover and contain should produce different output"
        assert not np.array_equal(np.array(r_cover), np.array(r_tile)), \
            "Cover and tile should produce different output"


# ─── Fit mode override ────────────────────────────────────────────────────

class TestFitModeOverride:

    def test_override_takes_precedence(self, iphone_template, solid_art):
        """Explicit fit_mode overrides template default."""
        # Template default is "cover"
        r_default = render_case(solid_art, iphone_template, template_dir=TEMPLATE_DIR)
        r_override = render_case(solid_art, iphone_template,
                                  template_dir=TEMPLATE_DIR, fit_mode="contain")
        assert not np.array_equal(np.array(r_default), np.array(r_override)), \
            "Override fit_mode should produce different output than template default"


# ─── Zoom and offset pass-through ─────────────────────────────────────────

class TestZoomOffsetPassThrough:

    def test_zoom_changes_output(self, iphone_template, artwork_color_block):
        """Zoom parameter should affect the rendered output."""
        r1 = render_case(artwork_color_block, iphone_template,
                         template_dir=TEMPLATE_DIR, zoom=1.0)
        r2 = render_case(artwork_color_block, iphone_template,
                         template_dir=TEMPLATE_DIR, zoom=2.0)
        assert not np.array_equal(np.array(r1), np.array(r2)), \
            "Different zoom should produce different output"

    def test_offset_changes_output(self, iphone_template, artwork_color_block):
        """Offset parameter should affect the rendered output."""
        r1 = render_case(artwork_color_block, iphone_template,
                         template_dir=TEMPLATE_DIR, offset_y=0.0)
        r2 = render_case(artwork_color_block, iphone_template,
                         template_dir=TEMPLATE_DIR, offset_y=0.5)
        assert not np.array_equal(np.array(r1), np.array(r2)), \
            "Different offset should produce different output"

    def test_focal_point_changes_output(self, iphone_template, artwork_color_block):
        """Focal point parameter should affect the rendered output."""
        r1 = render_case(artwork_color_block, iphone_template,
                         template_dir=TEMPLATE_DIR, focal_point=(0.5, 0.5))
        r2 = render_case(artwork_color_block, iphone_template,
                         template_dir=TEMPLATE_DIR, focal_point=(0.2, 0.8))
        assert not np.array_equal(np.array(r1), np.array(r2)), \
            "Different focal point should produce different output"
