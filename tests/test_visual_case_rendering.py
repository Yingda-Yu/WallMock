"""
Visual regression tests for the phone case rendering pipeline.

These tests verify structural and visual properties of rendered case
images, using deterministic comparison and reasonable tolerances rather
than fragile byte equality.

The tests load the real iPhone 17e template and render all three fixture
artworks, checking:
  - output dimensions
  - case body presence (non-transparent silhouette)
  - camera module protection
  - print region coverage
  - template reuse without modifications
  - deterministic re-render equality
"""

import os
import numpy as np
import pytest
from PIL import Image

from core.case_template_loader import load_case_template
from core.case_renderer import render_case


# ─── Paths ────────────────────────────────────────────────────────────────

TEMPLATE_DIR = os.path.join(
    os.path.dirname(__file__), "..",
    "assets", "case_templates", "apple", "iphone-17e", "hard", "rear",
)
TEMPLATE_JSON = os.path.join(TEMPLATE_DIR, "template.json")

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "artworks")

ARTWORKS = [
    ("color-block", "color-block.png", "cover"),
    ("tile-pattern", "tile-pattern.png", "tile"),
    ("transparent-artwork", "transparent-artwork.png", "cover"),
]

# Tolerance for visual comparison (mean absolute difference per channel)
VISUAL_TOLERANCE = 2.0  # out of 255


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def template():
    return load_case_template(TEMPLATE_JSON)


@pytest.fixture(scope="module")
def rendered_outputs():
    """Render all three artworks once and cache for the module."""
    tpl = load_case_template(TEMPLATE_JSON)
    outputs = {}
    for name, filename, fit_mode in ARTWORKS:
        art_path = os.path.join(FIXTURES_DIR, filename)
        art = Image.open(art_path).convert("RGBA")
        result = render_case(art, tpl, template_dir=TEMPLATE_DIR, fit_mode=fit_mode)
        outputs[name] = np.array(result)
    return outputs


# ─── Structural tests ───────────────────────────────────────────────────────

class TestVisualStructure:

    def test_all_outputs_have_correct_dimensions(self, rendered_outputs, template):
        """Every rendered artwork must match the template canvas size."""
        for name, arr in rendered_outputs.items():
            assert arr.shape[1] == template.canvas.width, \
                f"{name}: width {arr.shape[1]} != {template.canvas.width}"
            assert arr.shape[0] == template.canvas.height, \
                f"{name}: height {arr.shape[0]} != {template.canvas.height}"

    def test_all_outputs_are_rgba(self, rendered_outputs):
        """Every output must have 4 channels (RGBA)."""
        for name, arr in rendered_outputs.items():
            assert arr.shape[2] == 4, f"{name}: expected 4 channels, got {arr.shape[2]}"

    def test_output_is_not_blank(self, rendered_outputs):
        """No output should be entirely transparent."""
        for name, arr in rendered_outputs.items():
            alpha = arr[:, :, 3]
            assert alpha.max() > 0, f"{name}: output is blank (fully transparent)"

    def test_output_is_not_fully_opaque(self, rendered_outputs):
        """Output should have some transparent pixels (outside case body)."""
        for name, arr in rendered_outputs.items():
            alpha = arr[:, :, 3]
            assert alpha.min() == 0, \
                f"{name}: expected some transparent pixels outside case body"


# ─── Silhouette tests ─────────────────────────────────────────────────────

class TestSilhouette:

    def test_case_body_present(self, rendered_outputs, template):
        """The case body silhouette should be present (a connected region of non-transparent pixels)."""
        for name, arr in rendered_outputs.items():
            alpha = arr[:, :, 3]
            # The center of the canvas should be opaque (case body)
            cx, cy = template.canvas.width // 2, template.canvas.height // 2
            assert alpha[cy, cx] > 128, \
                f"{name}: center of canvas should be opaque (case body)"

    def test_corners_are_transparent(self, rendered_outputs, template):
        """Canvas corners should be transparent (outside rounded case body)."""
        w, h = template.canvas.width, template.canvas.height
        corners = [(0, 0), (0, h - 1), (w - 1, 0), (w - 1, h - 1)]
        for name, arr in rendered_outputs.items():
            alpha = arr[:, :, 3]
            for cx, cy in corners:
                assert alpha[cy, cx] == 0, \
                    f"{name}: corner ({cx},{cy}) should be transparent"


# ─── Camera module tests ──────────────────────────────────────────────────

class TestCameraModule:

    # Camera module geometry from generate_iphone17e_template.py
    CAM_X, CAM_Y = 406, 116
    CAM_SIZE = 320
    LENS_D = 160
    LENS_X = CAM_X + (CAM_SIZE - LENS_D) // 2
    LENS_Y = CAM_Y + (CAM_SIZE - LENS_D) // 2

    def test_lens_is_dark(self, rendered_outputs):
        """The camera lens center should be dark (not artwork color)."""
        cx = self.LENS_X + self.LENS_D // 2
        cy = self.LENS_Y + self.LENS_D // 2

        for name, arr in rendered_outputs.items():
            pixel = arr[cy, cx]
            # Lens should not be bright red/green/blue from artwork
            # It should be relatively dark
            brightness = pixel[:3].mean()
            assert brightness < 150, \
                f"{name}: lens center brightness {brightness} too high (artwork may have leaked)"

    def test_camera_ring_present(self, rendered_outputs):
        """The camera ring (metallic bezel) should be visible around the lens."""
        # Sample a point on the ring (between lens edge and camera module edge)
        ring_x = self.LENS_X - 10  # just outside lens, inside ring
        ring_y = self.LENS_Y + self.LENS_D // 2

        for name, arr in rendered_outputs.items():
            # The ring area should be opaque (part of overlay)
            alpha = arr[ring_y, ring_x, 3]
            assert alpha > 128, \
                f"{name}: camera ring area should be opaque"

    def test_camera_region_not_pure_artwork(self, rendered_outputs):
        """The camera module area should not be pure artwork color."""
        # Sample several points within the camera module
        for name, arr in rendered_outputs.items():
            # Check center of camera module
            cx = self.CAM_X + self.CAM_SIZE // 2
            cy = self.CAM_Y + self.CAM_SIZE // 2
            pixel = arr[cy, cx]

            # For color-block (red artwork), the camera area should not be pure red
            # The overlay should sit above the artwork
            # Check that not all three conditions are true (pure artwork):
            # R > 200 and G < 50 and B < 50 would indicate leaked red artwork
            assert not (pixel[0] > 200 and pixel[1] < 50 and pixel[2] < 50), \
                f"{name}: camera module center appears to be pure artwork (overlay missing)"


# ─── Print region tests ──────────────────────────────────────────────────

class TestPrintRegion:

    def test_print_region_has_artwork(self, rendered_outputs, template):
        """The print region should contain artwork (non-zero color values)."""
        pr = template.print_region
        cx = pr.x + pr.width // 2
        cy = pr.y + pr.height // 2

        for name, arr in rendered_outputs.items():
            pixel = arr[cy, cx]
            # Should be opaque
            assert pixel[3] > 128, \
                f"{name}: center of print region should be opaque"
            # Should not be the base case color (240, 248, 245)
            # i.e., artwork should be visible
            assert not (abs(pixel[0] - 248) < 5 and abs(pixel[1] - 247) < 5 and abs(pixel[2] - 245) < 5), \
                f"{name}: print region center looks like bare case body (no artwork)"

    def test_outside_case_body_is_transparent(self, rendered_outputs, template):
        """Pixels well outside the case body should be transparent."""
        # Sample a point in the top-left margin
        for name, arr in rendered_outputs.items():
            # Top-left area, well outside the case
            assert arr[10, 10, 3] == 0, \
                f"{name}: pixel (10,10) should be transparent (outside case body)"
            # Bottom-right area
            h, w = arr.shape[:2]
            assert arr[h - 10, w - 10, 3] == 0, \
                f"{name}: pixel ({w-10},{h-10}) should be transparent"


# ─── Deterministic rendering ──────────────────────────────────────────────

class TestDeterministic:

    def test_re_render_is_identical(self, template):
        """Re-rendering the same artwork must produce identical pixels."""
        art_path = os.path.join(FIXTURES_DIR, "color-block.png")
        art = Image.open(art_path).convert("RGBA")

        r1 = render_case(art, template, template_dir=TEMPLATE_DIR, fit_mode="cover")
        r2 = render_case(art, template, template_dir=TEMPLATE_DIR, fit_mode="cover")

        arr1 = np.array(r1)
        arr2 = np.array(r2)

        assert np.array_equal(arr1, arr2), \
            "Re-render of same input should be pixel-identical"

    def test_all_artworks_deterministic(self, template):
        """Each artwork should produce deterministic output."""
        for name, filename, fit_mode in ARTWORKS:
            art_path = os.path.join(FIXTURES_DIR, filename)
            art = Image.open(art_path).convert("RGBA")

            r1 = render_case(art, template, template_dir=TEMPLATE_DIR, fit_mode=fit_mode)
            r2 = render_case(art, template, template_dir=TEMPLATE_DIR, fit_mode=fit_mode)

            assert np.array_equal(np.array(r1), np.array(r2)), \
                f"{name}: re-render should be identical"


# ─── Template reuse ────────────────────────────────────────────────────────

class TestTemplateReuse:

    def test_all_three_artworks_render(self, template):
        """All three artworks must render successfully through the same template."""
        for name, filename, fit_mode in ARTWORKS:
            art_path = os.path.join(FIXTURES_DIR, filename)
            art = Image.open(art_path).convert("RGBA")
            result = render_case(art, template, template_dir=TEMPLATE_DIR, fit_mode=fit_mode)
            assert result is not None
            assert result.size == (template.canvas.width, template.canvas.height)

    def test_artworks_produce_different_output(self, rendered_outputs):
        """Each artwork should produce a visually different render."""
        names = list(rendered_outputs.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                arr_i = rendered_outputs[names[i]]
                arr_j = rendered_outputs[names[j]]
                assert not np.array_equal(arr_i, arr_j), \
                    f"'{names[i]}' and '{names[j]}' produced identical renders"

    def test_template_not_modified_between_renders(self, template):
        """The template object should be the same (immutable) before and after rendering."""
        art_path = os.path.join(FIXTURES_DIR, "color-block.png")
        art = Image.open(art_path).convert("RGBA")

        # Capture template state before
        tpl_id_before = template.id
        tpl_layers_before = len(template.layers)
        tpl_canvas_before = (template.canvas.width, template.canvas.height)

        # Render
        render_case(art, template, template_dir=TEMPLATE_DIR)

        # Template should be unchanged
        assert template.id == tpl_id_before
        assert len(template.layers) == tpl_layers_before
        assert (template.canvas.width, template.canvas.height) == tpl_canvas_before


# ─── Visual regression with tolerance ─────────────────────────────────────

class TestVisualRegression:
    """
    Visual regression baseline comparison.

    On first run, saves reference images. On subsequent runs, compares
    against the saved reference with a per-channel tolerance.

    To update baselines: delete tests/fixtures/baselines/ and re-run.
    """

    BASELINE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "baselines")

    def test_visual_baseline_match(self, template):
        """Rendered output should match saved baseline within tolerance."""
        os.makedirs(self.BASELINE_DIR, exist_ok=True)

        for name, filename, fit_mode in ARTWORKS:
            art_path = os.path.join(FIXTURES_DIR, filename)
            art = Image.open(art_path).convert("RGBA")
            result = render_case(art, template, template_dir=TEMPLATE_DIR, fit_mode=fit_mode)
            result_arr = np.array(result)

            baseline_path = os.path.join(self.BASELINE_DIR, f"case-{name}.npy")

            if not os.path.exists(baseline_path):
                # First run: save baseline
                np.save(baseline_path, result_arr)
                pytest.skip(f"Baseline saved for {name} — re-run to verify")
            else:
                baseline_arr = np.load(baseline_path)
                assert baseline_arr.shape == result_arr.shape, \
                    f"{name}: shape mismatch {result_arr.shape} vs {baseline_arr.shape}"

                diff = np.abs(result_arr.astype(np.int16) - baseline_arr.astype(np.int16))
                mean_diff = diff.mean()

                assert mean_diff <= VISUAL_TOLERANCE, \
                    f"{name}: visual diff {mean_diff:.2f} exceeds tolerance {VISUAL_TOLERANCE}"
