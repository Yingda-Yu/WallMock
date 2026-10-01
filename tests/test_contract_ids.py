"""Tests for shared contract IDs, token vocabularies, and helpers.

Covers:
- Component ID validity
- Composite ID builders (template_id, variant_id, render_asset_id)
- Composite ID parsers
- Shared token vocab enums (case_type, view, status)
- Content hash helpers
- Asset path safety
"""
import hashlib
import pytest

from core.contract_ids import (
    build_content_hash,
    build_render_asset_id,
    build_template_id,
    build_variant_id,
    CASE_TYPES_V1,
    COMPOSITE_SEP,
    CONTRACT_NAME,
    CONTRACT_VERSION,
    is_safe_relative_path,
    is_valid_case_type,
    is_valid_component_id,
    is_valid_content_hash,
    is_valid_template_status,
    is_valid_view,
    parse_template_id,
    parse_variant_id,
    RENDER_ASSET_FORMAT_V1,
    VIEWS_V1,
)


# ---------------------------------------------------------------------------
# Contract identity
# ---------------------------------------------------------------------------

class TestContractIdentity:
    def test_contract_name(self):
        assert CONTRACT_NAME == "spartina-device-render-catalog"

    def test_contract_version(self):
        assert CONTRACT_VERSION == 1

    def test_render_asset_format(self):
        assert RENDER_ASSET_FORMAT_V1 == "webp"


# ---------------------------------------------------------------------------
# Component ID validity
# ---------------------------------------------------------------------------

class TestComponentIdValidation:
    def test_valid_kebab_case(self):
        assert is_valid_component_id("iphone-17e")
        assert is_valid_component_id("blue-hydrangea")
        assert is_valid_component_id("a")
        assert is_valid_component_id("1")
        assert is_valid_component_id("x-1")

    def test_rejects_double_underscore(self):
        """Component IDs must not contain __ (composite separator)."""
        assert not is_valid_component_id("foo__bar")
        assert not is_valid_component_id("iphone-17e__hard")

    def test_rejects_uppercase(self):
        assert not is_valid_component_id("iPhone")
        assert not is_valid_component_id("Blue-Hydrangea")

    def test_rejects_empty(self):
        assert not is_valid_component_id("")

    def test_rejects_non_string(self):
        assert not is_valid_component_id(None)
        assert not is_valid_component_id(123)
        assert not is_valid_component_id([])

    def test_rejects_leading_hyphen(self):
        assert not is_valid_component_id("-bad")

    def test_rejects_slash(self):
        assert not is_valid_component_id("foo/bar")


# ---------------------------------------------------------------------------
# Shared token vocabularies
# ---------------------------------------------------------------------------

class TestSharedTokenVocab:
    def test_case_type_v1_enum(self):
        """v1 case types: hard, tough, magsafe, clear, soft."""
        assert "hard" in CASE_TYPES_V1
        assert "tough" in CASE_TYPES_V1
        assert "magsafe" in CASE_TYPES_V1
        assert "clear" in CASE_TYPES_V1
        assert "soft" in CASE_TYPES_V1
        # transparent is NOT in v1 (replaced by clear)
        assert "transparent" not in CASE_TYPES_V1

    def test_views_v1_enum(self):
        """v1 view types: rear, angle, front, closeup."""
        assert "rear" in VIEWS_V1
        assert "angle" in VIEWS_V1
        assert "front" in VIEWS_V1
        assert "closeup" in VIEWS_V1

    def test_is_valid_case_type(self):
        assert is_valid_case_type("hard")
        assert is_valid_case_type("clear")
        assert not is_valid_case_type("transparent")
        assert not is_valid_case_type("Hard")
        assert not is_valid_case_type("")

    def test_is_valid_view(self):
        assert is_valid_view("rear")
        assert is_valid_view("closeup")
        assert not is_valid_view("side")
        assert not is_valid_view("")

    def test_is_valid_template_status(self):
        assert is_valid_template_status("prototype")
        assert is_valid_template_status("production")
        assert not is_valid_template_status("experimental")
        assert not is_valid_template_status("")


# ---------------------------------------------------------------------------
# Template ID builder/parser
# ---------------------------------------------------------------------------

class TestTemplateId:
    def test_build_valid(self):
        tid = build_template_id("iphone-17e", "hard", "rear")
        assert tid == "iphone-17e__hard__rear"

    def test_build_uses_composite_sep(self):
        tid = build_template_id("a", "hard", "rear")
        assert tid.count(COMPOSITE_SEP) == 2

    def test_parse_valid(self):
        dev, ct, view = parse_template_id("iphone-17e__hard__rear")
        assert dev == "iphone-17e"
        assert ct == "hard"
        assert view == "rear"

    def test_round_trip(self):
        """build then parse gives back original components."""
        for dev, ct, view in [
            ("iphone-17e", "hard", "rear"),
            ("samsung-galaxy-s25", "tough", "angle"),
            ("pixel-10", "magsafe", "front"),
        ]:
            tid = build_template_id(dev, ct, view)
            d, c, v = parse_template_id(tid)
            assert (d, c, v) == (dev, ct, view)

    def test_build_rejects_bad_device(self):
        with pytest.raises(ValueError):
            build_template_id("bad__id", "hard", "rear")

    def test_build_rejects_bad_case_type(self):
        with pytest.raises(ValueError):
            build_template_id("iphone-17e", "transparent", "rear")

    def test_build_rejects_bad_view(self):
        with pytest.raises(ValueError):
            build_template_id("iphone-17e", "hard", "side")

    def test_parse_rejects_wrong_component_count(self):
        with pytest.raises(ValueError, match="expected 3 components"):
            parse_template_id("iphone-17e__hard")  # only 2 parts
        with pytest.raises(ValueError, match="expected 3 components"):
            parse_template_id("a__b__c__d")  # 4 parts

    def test_parse_rejects_bad_components(self):
        with pytest.raises(ValueError):
            parse_template_id("BadDevice__hard__rear")
        with pytest.raises(ValueError):
            parse_template_id("iphone-17e__transparent__rear")
        with pytest.raises(ValueError):
            parse_template_id("iphone-17e__hard__side")


# ---------------------------------------------------------------------------
# Variant ID builder/parser
# ---------------------------------------------------------------------------

class TestVariantId:
    def test_build_valid(self):
        vid = build_variant_id("blue-hydrangea", "iphone-17e", "hard")
        assert vid == "blue-hydrangea__iphone-17e__hard"

    def test_parse_valid(self):
        design, dev, ct = parse_variant_id("blue-hydrangea__iphone-17e__hard")
        assert design == "blue-hydrangea"
        assert dev == "iphone-17e"
        assert ct == "hard"

    def test_round_trip(self):
        for design, dev, ct in [
            ("dreamy-florals", "iphone-17e", "hard"),
            ("amoled-dark", "pixel-10-pro", "clear"),
        ]:
            vid = build_variant_id(design, dev, ct)
            d, dv, c = parse_variant_id(vid)
            assert (d, dv, c) == (design, dev, ct)

    def test_build_rejects_bad_design(self):
        with pytest.raises(ValueError):
            build_variant_id("bad__id", "iphone-17e", "hard")

    def test_parse_rejects_wrong_count(self):
        with pytest.raises(ValueError):
            parse_variant_id("just-one")


# ---------------------------------------------------------------------------
# Render asset ID
# ---------------------------------------------------------------------------

class TestRenderAssetId:
    def test_build_valid(self):
        raid = build_render_asset_id(
            "blue-hydrangea__iphone-17e__hard", "rear", 1200,
        )
        assert raid == "blue-hydrangea__iphone-17e__hard__rear__w1200"

    def test_deterministic(self):
        """Same inputs always produce same output."""
        a = build_render_asset_id("d__dev__hard", "rear", 800)
        b = build_render_asset_id("d__dev__hard", "rear", 800)
        assert a == b

    def test_rejects_bad_variant_id(self):
        with pytest.raises(ValueError):
            build_render_asset_id("not-a-valid-id", "rear", 800)

    def test_rejects_bad_view(self):
        with pytest.raises(ValueError):
            build_render_asset_id("d__dev__hard", "side", 800)

    def test_rejects_zero_width(self):
        with pytest.raises(ValueError):
            build_render_asset_id("d__dev__hard", "rear", 0)

    def test_rejects_negative_width(self):
        with pytest.raises(ValueError):
            build_render_asset_id("d__dev__hard", "rear", -1)


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_build_from_valid_hex(self):
        h = "a" * 64
        result = build_content_hash(h)
        assert result == f"sha256:{h}"
        assert is_valid_content_hash(result)

    def test_valid_sha256(self):
        # Compute a real SHA-256
        real = hashlib.sha256(b"hello world").hexdigest()
        ch = build_content_hash(real)
        assert is_valid_content_hash(ch)

    def test_rejects_short(self):
        assert not is_valid_content_hash("sha256:abc123")

    def test_rejects_wrong_prefix(self):
        assert not is_valid_content_hash("md5:" + "a" * 32)

    def test_rejects_uppercase(self):
        assert not is_valid_content_hash("sha256:" + "A" * 64)

    def test_build_rejects_bad_length(self):
        with pytest.raises(ValueError):
            build_content_hash("too-short")


# ---------------------------------------------------------------------------
# Asset path safety
# ---------------------------------------------------------------------------

class TestSafePath:
    def test_valid_paths(self):
        assert is_safe_relative_path("design/iphone-17e/hard/rear-800.webp")
        assert is_safe_relative_path("a/b/c.png")
        assert is_safe_relative_path("file.webp")

    def test_rejects_absolute(self):
        assert not is_safe_relative_path("/etc/passwd")
        assert not is_safe_relative_path("\\windows\\system32")

    def test_rejects_path_traversal(self):
        assert not is_safe_relative_path("../etc/passwd")
        assert not is_safe_relative_path("foo/../bar")

    def test_rejects_empty_components(self):
        assert not is_safe_relative_path("foo//bar")

    def test_rejects_no_extension(self):
        assert not is_safe_relative_path("noext")

    def test_rejects_uppercase(self):
        assert not is_safe_relative_path("Foo/Bar.PNG")

    def test_rejects_drive_letters(self):
        assert not is_safe_relative_path("C:/windows/system32")
