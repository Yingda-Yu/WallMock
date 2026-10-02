"""P4B Wave-1 cross-device regression tests.

Verifies that the three-device matrix (iphone-17e, iphone-17, iphone-air)
renders end-to-end with the same renderer code — no device-specific
conditionals — and that all templates remain prototype-only.
"""
import os

import pytest
from PIL import Image

from core.case_renderer import render_case
from core.case_template_loader import load_case_template
from core.contract_ids import (
    build_template_id,
    build_variant_id,
    is_valid_component_id,
    parse_template_id,
)
from core.catalog_models import (
    TEMPLATE_STATUS_PROTOTYPE,
    is_production_grade_supplier_geometry,
)


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATES_ROOT = os.path.join("assets", "case_templates")
ARTWORKS_DIR = os.path.join("tests", "fixtures", "artworks")

WAVE_1_DEVICES = ["iphone-17e", "iphone-17", "iphone-air"]
WAVE_1_ARTWORKS = ["color-block", "tile-pattern", "transparent-artwork"]


def _template_path(device_id):
    return os.path.join(
        TEMPLATES_ROOT, "apple", device_id, "hard", "rear", "template.json"
    )


def _template_dir(device_id):
    return os.path.dirname(_template_path(device_id))


# ---------------------------------------------------------------------------
# 1. All three devices load from templates
# ---------------------------------------------------------------------------

class TestWave1DevicesLoad:
    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    def test_template_loads(self, device_id):
        """Each Wave-1 device template loads without error."""
        os.chdir(REPO_ROOT)
        tpl = load_case_template(_template_path(device_id))
        assert tpl.device_id == device_id
        assert tpl.case_type == "hard"
        assert tpl.view == "rear"

    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    def test_template_id_matches_v1_grammar(self, device_id):
        """Each template ID is a valid v1 template_id."""
        os.chdir(REPO_ROOT)
        tpl = load_case_template(_template_path(device_id))
        expected = build_template_id(device_id, "hard", "rear")
        assert tpl.id == expected
        # Parsing should succeed and round-trip
        parsed = parse_template_id(tpl.id)
        assert parsed[0] == device_id
        assert parsed[1] == "hard"
        assert parsed[2] == "rear"

    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    def test_device_id_is_valid_component(self, device_id):
        """Each device_id is a valid v1 component ID."""
        assert is_valid_component_id(device_id)


# ---------------------------------------------------------------------------
# 2. All three are prototype, not production
# ---------------------------------------------------------------------------

class TestWave1PrototypeInvariant:
    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    def test_status_is_prototype(self, device_id):
        """All Wave-1 templates must be prototype status."""
        os.chdir(REPO_ROOT)
        tpl = load_case_template(_template_path(device_id))
        assert tpl.status == TEMPLATE_STATUS_PROTOTYPE

    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    def test_supplier_geometry_is_none(self, device_id):
        """All Wave-1 templates have no supplier geometry (prototype)."""
        os.chdir(REPO_ROOT)
        tpl = load_case_template(_template_path(device_id))
        assert tpl.provenance is not None
        assert not is_production_grade_supplier_geometry(
            tpl.provenance.supplier_geometry
        )

    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    def test_rejects_production_promotion(self, device_id):
        """Accidental production promotion is rejected by loader."""
        import json
        os.chdir(REPO_ROOT)
        tpl_path = _template_path(device_id)
        with open(tpl_path) as f:
            data = json.load(f)
        # Try to set production status without supplier geometry
        data["status"] = "production"
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir=".",
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name
        try:
            from core.catalog_models import CatalogValidationError
            with pytest.raises(CatalogValidationError, match="production"):
                load_case_template(tmp_path)
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 3. Same artwork renders across all three devices without code changes
# ---------------------------------------------------------------------------

class TestWave1RenderMatrix:
    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    @pytest.mark.parametrize("artwork_name", WAVE_1_ARTWORKS)
    def test_renders_without_error(self, device_id, artwork_name):
        """Every device × artwork combination renders successfully."""
        os.chdir(REPO_ROOT)
        tpl = load_case_template(_template_path(device_id))
        art_path = os.path.join(ARTWORKS_DIR, f"{artwork_name}.png")
        art = Image.open(art_path).convert("RGBA")
        result = render_case(
            art, tpl, template_dir=_template_dir(device_id), fit_mode="cover",
        )
        assert result is not None
        assert result.mode == "RGBA"
        assert result.width == tpl.canvas.width
        assert result.height == tpl.canvas.height

    @pytest.mark.parametrize("device_id", WAVE_1_DEVICES)
    def test_output_dimensions_deterministic(self, device_id):
        """Rendering the same template twice produces identical dimensions."""
        os.chdir(REPO_ROOT)
        tpl = load_case_template(_template_path(device_id))
        art_path = os.path.join(ARTWORKS_DIR, "color-block.png")
        art = Image.open(art_path).convert("RGBA")
        r1 = render_case(
            art, tpl, template_dir=_template_dir(device_id), fit_mode="cover",
        )
        r2 = render_case(
            art, tpl, template_dir=_template_dir(device_id), fit_mode="cover",
        )
        assert r1.size == r2.size

    def test_devices_have_distinct_dimensions(self):
        """The three devices have measurably different canvas sizes."""
        os.chdir(REPO_ROOT)
        sizes = set()
        for device_id in WAVE_1_DEVICES:
            tpl = load_case_template(_template_path(device_id))
            sizes.add((tpl.canvas.width, tpl.canvas.height))
        # All three should have distinct dimensions
        assert len(sizes) == 3


# ---------------------------------------------------------------------------
# 4. Print masks differ where geometry differs
# ---------------------------------------------------------------------------

class TestWave1PrintMaskDistinctness:
    def test_all_print_masks_are_different(self):
        """Devices with different geometry have different print masks."""
        os.chdir(REPO_ROOT)
        masks = {}
        for device_id in WAVE_1_DEVICES:
            tpl = load_case_template(_template_path(device_id))
            mask_path = os.path.join(_template_dir(device_id), "print_mask.png")
            mask = Image.open(mask_path).convert("L")
            masks[device_id] = mask.tobytes()

        # All three masks should be distinct (different geometry)
        unique_masks = set(masks.values())
        assert len(unique_masks) == 3, (
            "Expected 3 distinct print masks for 3 different devices"
        )

    def test_camera_exclusion_differs(self):
        """Camera exclusion regions differ appropriately between models."""
        os.chdir(REPO_ROOT)
        # Compare the top-left corner where cameras are
        for i, dev_a in enumerate(WAVE_1_DEVICES):
            for dev_b in WAVE_1_DEVICES[i + 1:]:
                mask_a_path = os.path.join(_template_dir(dev_a), "print_mask.png")
                mask_b_path = os.path.join(_template_dir(dev_b), "print_mask.png")
                mask_a = Image.open(mask_a_path).convert("L")
                mask_b = Image.open(mask_b_path).convert("L")

                # Crop the top-left camera region (25% width, 25% height)
                # Using the smaller of the two masks
                crop_w = min(mask_a.width, mask_b.width) // 3
                crop_h = min(mask_a.height, mask_b.height) // 4
                crop_a = mask_a.crop((0, 0, crop_w, crop_h))
                crop_b = mask_b.crop((0, 0, crop_w, crop_h))

                assert crop_a.tobytes() != crop_b.tobytes(), (
                    f"Camera regions of {dev_a} and {dev_b} should differ"
                )


# ---------------------------------------------------------------------------
# 5. Render capabilities snapshot matches reality
# ---------------------------------------------------------------------------

class TestWave1Capabilities:
    def test_capabilities_have_all_three_devices(self):
        """Render capabilities include all three Wave-1 devices."""
        os.chdir(REPO_ROOT)
        from core.contract_export import build_render_capabilities
        caps = build_render_capabilities(TEMPLATES_ROOT)
        assert len(caps["devices"]) >= 3
        for device_id in WAVE_1_DEVICES:
            assert device_id in caps["devices"]

    def test_all_templates_are_prototype(self):
        """All capability templates report prototype status."""
        os.chdir(REPO_ROOT)
        from core.contract_export import build_render_capabilities
        caps = build_render_capabilities(TEMPLATES_ROOT)
        for device_id in WAVE_1_DEVICES:
            dev = caps["devices"][device_id]
            for tpl in dev["templates"]:
                assert tpl["template_status"] == "prototype"
                assert tpl["production_publishable"] is False
                assert tpl["renderable"] is True

    def test_each_device_has_hard_rear(self):
        """Each device has a hard/rear template entry."""
        os.chdir(REPO_ROOT)
        from core.contract_export import build_render_capabilities
        caps = build_render_capabilities(TEMPLATES_ROOT)
        for device_id in WAVE_1_DEVICES:
            dev = caps["devices"][device_id]
            hard_rear = [
                t for t in dev["templates"]
                if t["case_type"] == "hard" and t["view"] == "rear"
            ]
            assert len(hard_rear) == 1, f"{device_id} missing hard/rear template"
            assert hard_rear[0]["template_id"] == build_template_id(
                device_id, "hard", "rear"
            )


# ---------------------------------------------------------------------------
# 6. Contract bundle validates with 3 devices
# ---------------------------------------------------------------------------

class TestWave1ContractBundle:
    def test_bundle_validates_valid(self):
        """The example contract bundle with 3 devices passes validation."""
        os.chdir(REPO_ROOT)
        from core.bundle_validator import validate_contract_bundle
        bundle_dir = os.path.join("examples", "storefront-contract")
        report = validate_contract_bundle(bundle_dir)
        assert report.valid, f"Bundle invalid: {report.errors}"

    def test_bundle_has_three_devices(self):
        """Bundle contains exactly three Wave-1 devices."""
        os.chdir(REPO_ROOT)
        from core.bundle_validator import validate_contract_bundle
        bundle_dir = os.path.join("examples", "storefront-contract")
        report = validate_contract_bundle(bundle_dir)
        assert report.info["devices_count"] == 3

    def test_bundle_has_three_variants(self):
        """Bundle contains exactly three variants (one per device)."""
        os.chdir(REPO_ROOT)
        from core.bundle_validator import validate_contract_bundle
        bundle_dir = os.path.join("examples", "storefront-contract")
        report = validate_contract_bundle(bundle_dir)
        assert report.info["variants_count"] == 3

    def test_bundle_contract_version_unchanged(self):
        """Contract version remains at 1 — data-only expansion."""
        os.chdir(REPO_ROOT)
        import json
        bundle_path = os.path.join(
            "examples", "storefront-contract", "contract_bundle.v1.json"
        )
        with open(bundle_path) as f:
            bundle = json.load(f)
        assert bundle["contract_version"] == 1
        assert bundle["contract"] == "spartina-device-render-catalog"


# ---------------------------------------------------------------------------
# 7. iPhone Air plateau overlay — component visibility regression
# ---------------------------------------------------------------------------

class TestIPhoneAirPlateauOverlay:
    """Regression tests for the iPhone Air full-width plateau.

    Guards against the stale ImageDraw/alpha_composite lifecycle bug
    where flash and mic were drawn with a stale ImageDraw context and
    never appeared in the final overlay.
    """

    @pytest.fixture
    def air_template(self):
        os.chdir(REPO_ROOT)
        return load_case_template(_template_path("iphone-air"))

    @pytest.fixture
    def air_overlay(self):
        os.chdir(REPO_ROOT)
        overlay_path = os.path.join(_template_dir("iphone-air"), "overlay.png")
        return Image.open(overlay_path).convert("RGBA")

    @pytest.fixture
    def air_camera_region(self, air_template):
        """Get the camera_region dict from the loaded template."""
        assert air_template.camera_region is not None
        cr = air_template.camera_region
        # camera_region may be a dict or object — normalize to dict
        if isinstance(cr, dict):
            return {
                "x": cr["x"],
                "y": cr["y"],
                "w": cr["width"] if "width" in cr else cr.get("w", 0),
                "h": cr["height"] if "height" in cr else cr.get("h", 0),
            }
        return {
            "x": cr.x,
            "y": cr.y,
            "w": cr.width,
            "h": cr.height,
        }

    def test_flash_visible_in_overlay(self, air_overlay, air_camera_region):
        """Flash pixel is non-transparent and light-colored at its config position."""
        # Config: flash at cx = case_x + case_w * 0.62, cy = lens_cy - 4
        # We sample within the camera region at the expected flash location
        px = air_overlay.load()
        # Sample several points across the flash area (right-center of region)
        region_cx = air_camera_region["x"] + air_camera_region["w"] * 0.62
        region_cy = air_camera_region["y"] + air_camera_region["h"] * 0.5
        # Flash should be a light/cream color with full alpha
        for dx in [-10, 0, 10]:
            for dy in [-10, 0, 10]:
                x = int(region_cx + dx)
                y = int(region_cy + dy)
                r, g, b, a = px[x, y]
                assert a > 150, (
                    f"Flash pixel at ({x},{y}) is transparent (alpha={a})"
                )
                # Flash is cream/light yellow-ish, not dark like lens
                brightness = (r + g + b) / 3
                assert brightness > 150, (
                    f"Flash pixel at ({x},{y}) too dark (brightness={brightness})"
                )

    def test_mic_visible_in_overlay(self, air_overlay, air_camera_region):
        """Mic pixel is non-transparent and dark at its config position."""
        px = air_overlay.load()
        # Mic at far right: 82% across the camera region
        region_cx = air_camera_region["x"] + air_camera_region["w"] * 0.82
        region_cy = air_camera_region["y"] + air_camera_region["h"] * 0.5
        for dx in [-4, 0, 4]:
            for dy in [-4, 0, 4]:
                x = int(region_cx + dx)
                y = int(region_cy + dy)
                r, g, b, a = px[x, y]
                assert a > 150, (
                    f"Mic pixel at ({x},{y}) is transparent (alpha={a})"
                )
                # Mic is dark (near-black)
                brightness = (r + g + b) / 3
                assert brightness < 80, (
                    f"Mic pixel at ({x},{y}) too bright (brightness={brightness})"
                )

    def test_lens_visible_in_overlay(self, air_overlay, air_camera_region):
        """Lens is visible (dark with ring) at the left side of the plateau."""
        px = air_overlay.load()
        # Lens at ~22% across the camera region
        region_cx = air_camera_region["x"] + air_camera_region["w"] * 0.22
        region_cy = air_camera_region["y"] + air_camera_region["h"] * 0.5
        # Center of lens should be very dark
        r, g, b, a = px[int(region_cx), int(region_cy)]
        assert a > 200, "Lens center is transparent"
        brightness = (r + g + b) / 3
        assert brightness < 60, f"Lens center too bright (brightness={brightness})"

    def test_camera_region_contains_flash(self, air_template, air_camera_region):
        """camera_region fully contains the flash component."""
        # Flash position from config: cx = case_x + case_w * 0.62
        # Flash size = 44, so half = 22
        case_x = (air_template.canvas.width - int(
            (74.7 + 2 * 1.2) * 13
        )) // 2
        # Use the camera region from template metadata
        cr = air_camera_region
        flash_cx = cr["x"] + cr["w"] * 0.62
        flash_cy = cr["y"] + cr["h"] * 0.5
        flash_half = 22 + 5  # size/2 + pad
        assert flash_cx - flash_half >= cr["x"] - 5, (
            "Flash left edge extends outside camera_region"
        )
        assert flash_cx + flash_half <= cr["x"] + cr["w"] + 5, (
            "Flash right edge extends outside camera_region"
        )
        assert flash_cy - flash_half >= cr["y"] - 5, (
            "Flash top edge extends outside camera_region"
        )
        assert flash_cy + flash_half <= cr["y"] + cr["h"] + 5, (
            "Flash bottom edge extends outside camera_region"
        )

    def test_camera_region_contains_mic(self, air_template, air_camera_region):
        """camera_region fully contains the mic component."""
        cr = air_camera_region
        mic_cx = cr["x"] + cr["w"] * 0.82
        mic_cy = cr["y"] + cr["h"] * 0.5
        mic_r = 11 + 5  # radius + pad
        assert mic_cx - mic_r >= cr["x"] - 5, (
            "Mic left edge extends outside camera_region"
        )
        assert mic_cx + mic_r <= cr["x"] + cr["w"] + 5, (
            "Mic right edge extends outside camera_region"
        )
        assert mic_cy - mic_r >= cr["y"] - 5, (
            "Mic top edge extends outside camera_region"
        )
        assert mic_cy + mic_r <= cr["y"] + cr["h"] + 5, (
            "Mic bottom edge extends outside camera_region"
        )

    def test_camera_region_contains_lens(self, air_template, air_camera_region):
        """camera_region fully contains the lens component."""
        cr = air_camera_region
        lens_cx = cr["x"] + cr["w"] * 0.22
        lens_cy = cr["y"] + cr["h"] * 0.5
        lens_r = 65 + 12 + 5  # radius + ring + pad
        assert lens_cx - lens_r >= cr["x"] - 5, (
            "Lens left edge extends outside camera_region"
        )
        assert lens_cx + lens_r <= cr["x"] + cr["w"] + 5, (
            "Lens right edge extends outside camera_region"
        )
        assert lens_cy - lens_r >= cr["y"] - 5, (
            "Lens top edge extends outside camera_region"
        )
        assert lens_cy + lens_r <= cr["y"] + cr["h"] + 5, (
            "Lens bottom edge extends outside camera_region"
        )

    def test_plateau_spans_full_width(self, air_overlay, air_camera_region):
        """The plateau spans nearly the full width of the camera region."""
        cr = air_camera_region
        # Plateau should cover >80% of the camera region width
        # (full-width plateau with small side insets)
        px = air_overlay.load()
        mid_y = int(cr["y"] + cr["h"] * 0.5)
        # Scan horizontally across the middle of the region
        opaque_pixels = 0
        for x in range(cr["x"], cr["x"] + cr["w"]):
            _, _, _, a = px[x, mid_y]
            if a > 50:
                opaque_pixels += 1
        coverage = opaque_pixels / cr["w"]
        assert coverage > 0.9, (
            f"Plateau only covers {coverage:.1%} of camera region width, "
            "expected >90% (full-width plateau)"
        )

    def test_print_mask_excludes_plateau_area(self, air_template, air_camera_region):
        """Print mask has near-zero printable area across the plateau center band."""
        os.chdir(REPO_ROOT)
        mask_path = os.path.join(_template_dir("iphone-air"), "print_mask.png")
        mask = Image.open(mask_path).convert("L")
        px = mask.load()
        cr = air_camera_region

        # Sample the center band of the plateau (middle 40% vertically)
        # where the pill shape is fully rectangular — no rounded-end gaps
        band_top = int(cr["y"] + cr["h"] * 0.3)
        band_bottom = int(cr["y"] + cr["h"] * 0.7)

        total = 0
        printable = 0
        for x in range(cr["x"], cr["x"] + cr["w"]):
            for y in range(band_top, band_bottom):
                total += 1
                if px[x, y] > 128:
                    printable += 1

        ratio = printable / total
        assert ratio < 0.01, (
            f"Print mask has {ratio:.1%} printable pixels in plateau center band, "
            "expected <1% (plateau should be excluded from print)"
        )
