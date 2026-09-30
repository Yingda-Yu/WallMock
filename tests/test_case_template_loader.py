"""
Unit tests for case catalog model loading and validation (Phase P1).

Tests cover:
  - Valid fixture loading (case template, design, availability)
  - Invalid configs that must fail before rendering
  - Unknown-field rejection (no silent rendering changes)
  - Path-traversal protection on IDs and file paths
  - Schema version enforcement
  - Default values for optional fields
  - Index-based listing and device filtering
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog_models import (
    Canvas,
    CaseTemplate,
    CaseTemplateLayer,
    CatalogValidationError,
    Design,
    PrintRegion,
    VariantAvailability,
)
from core import case_template_loader as loader

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_json(path: Path, data):
    """Write a JSON file to *path* (creating parent dirs as needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Case template — valid loading
# ---------------------------------------------------------------------------

class TestLoadCaseTemplateValid:
    def test_load_valid_template(self):
        tpl = loader.load_case_template(
            FIXTURES / "case_templates" / "valid_rear" / "template.json"
        )
        assert isinstance(tpl, CaseTemplate)
        assert tpl.schema_version == 1
        assert tpl.id == "test-device__hard__rear"
        assert tpl.device_id == "test-device"
        assert tpl.case_type == "hard"
        assert tpl.view == "rear"

    def test_canvas_parsed(self):
        tpl = loader.load_case_template(
            FIXTURES / "case_templates" / "valid_rear" / "template.json"
        )
        assert isinstance(tpl.canvas, Canvas)
        assert tpl.canvas.width == 1600
        assert tpl.canvas.height == 2000

    def test_print_region_parsed(self):
        tpl = loader.load_case_template(
            FIXTURES / "case_templates" / "valid_rear" / "template.json"
        )
        pr = tpl.print_region
        assert isinstance(pr, PrintRegion)
        assert pr.mode == "mask"
        assert pr.x == 200
        assert pr.y == 150
        assert pr.width == 1200
        assert pr.height == 1700
        assert pr.fit == "cover"
        assert pr.mask == "print_mask.png"

    def test_layers_parsed(self):
        tpl = loader.load_case_template(
            FIXTURES / "case_templates" / "valid_rear" / "template.json"
        )
        assert len(tpl.layers) == 5
        assert tpl.layers[0].type == "base"
        assert tpl.layers[0].file == "base.png"
        assert tpl.layers[1].type == "artwork"
        assert tpl.layers[1].file is None  # artwork must not have a file
        assert tpl.layers[2].type == "highlight"
        assert tpl.layers[2].opacity == 1.0
        assert tpl.layers[3].type == "overlay"
        assert tpl.layers[4].type == "shadow"

    def test_template_is_frozen(self):
        tpl = loader.load_case_template(
            FIXTURES / "case_templates" / "valid_rear" / "template.json"
        )
        with pytest.raises(AttributeError):
            tpl.id = "changed"

    def test_minimal_template_loads(self, tmp_path):
        """A template with only required fields and one artwork layer."""
        data = {
            "schema_version": 1,
            "id": "minimal__hard__rear",
            "device_id": "minimal",
            "case_type": "hard",
            "view": "rear",
            "canvas": {"width": 800, "height": 1000},
            "print_region": {
                "mode": "mask",
                "x": 0, "y": 0, "width": 800, "height": 1000,
                "fit": "cover",
            },
            "layers": [{"type": "artwork"}],
        }
        path = write_json(tmp_path / "template.json", data)
        tpl = loader.load_case_template(path)
        assert tpl.id == "minimal__hard__rear"
        assert len(tpl.layers) == 1
        # Defaults
        assert tpl.layers[0].blend == "normal"
        assert tpl.layers[0].opacity == 1.0


# ---------------------------------------------------------------------------
# Case template — invalid loading
# ---------------------------------------------------------------------------

class TestLoadCaseTemplateInvalid:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(CatalogValidationError, match="file does not exist"):
            loader.load_case_template(tmp_path / "nope.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json}", encoding="utf-8")
        with pytest.raises(CatalogValidationError, match="invalid JSON"):
            loader.load_case_template(path)

    def test_root_not_object(self, tmp_path):
        path = write_json(tmp_path / "t.json", [1, 2, 3])
        with pytest.raises(CatalogValidationError, match="root must be a JSON object"):
            loader.load_case_template(path)

    def test_unknown_top_level_field(self, tmp_path):
        data = {
            "schema_version": 1, "id": "a__hard__rear", "device_id": "a",
            "case_type": "hard", "view": "rear",
            "canvas": {"width": 800, "height": 1000},
            "print_region": {"mode": "mask", "x": 0, "y": 0, "width": 800, "height": 1000, "fit": "cover"},
            "layers": [{"type": "artwork"}],
            "bogus_field": True,
        }
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="unknown field.*bogus_field"):
            loader.load_case_template(path)

    def test_missing_required_field(self, tmp_path):
        data = {
            "schema_version": 1, "id": "a__hard__rear",
            "case_type": "hard", "view": "rear",
            "canvas": {"width": 800, "height": 1000},
            "print_region": {"mode": "mask", "x": 0, "y": 0, "width": 800, "height": 1000, "fit": "cover"},
            "layers": [{"type": "artwork"}],
        }
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="missing required.*device_id"):
            loader.load_case_template(path)

    def test_wrong_schema_version(self, tmp_path):
        data = _valid_template_data()
        data["schema_version"] = 2
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="schema_version.*expected 1.*got 2"):
            loader.load_case_template(path)

    def test_path_traversal_in_id(self, tmp_path):
        data = _valid_template_data()
        data["id"] = "../escape"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="invalid characters"):
            loader.load_case_template(path)

    def test_path_traversal_in_device_id(self, tmp_path):
        data = _valid_template_data()
        data["device_id"] = "../../etc/passwd"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="invalid characters"):
            loader.load_case_template(path)

    def test_invalid_case_type(self, tmp_path):
        data = _valid_template_data()
        data["case_type"] = "plastic"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="case_type.*not valid"):
            loader.load_case_template(path)

    def test_invalid_view(self, tmp_path):
        data = _valid_template_data()
        data["view"] = "side"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="view.*not valid"):
            loader.load_case_template(path)

    def test_unknown_canvas_field(self, tmp_path):
        data = _valid_template_data()
        data["canvas"]["depth"] = 3
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="canvas.*unknown field.*depth"):
            loader.load_case_template(path)

    def test_unknown_print_region_field(self, tmp_path):
        data = _valid_template_data()
        data["print_region"]["rotation"] = 90
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="print_region.*unknown field.*rotation"):
            loader.load_case_template(path)

    def test_invalid_fit_mode(self, tmp_path):
        data = _valid_template_data()
        data["print_region"]["fit"] = "stretch"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="print_region.fit.*not valid"):
            loader.load_case_template(path)

    def test_invalid_print_mode(self, tmp_path):
        data = _valid_template_data()
        data["print_region"]["mode"] = "warp"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="print_region.mode.*not valid"):
            loader.load_case_template(path)

    def test_empty_layers(self, tmp_path):
        data = _valid_template_data()
        data["layers"] = []
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="layers.*non-empty"):
            loader.load_case_template(path)

    def test_missing_artwork_layer(self, tmp_path):
        data = _valid_template_data()
        data["layers"] = [{"type": "base", "file": "base.png"}]
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="type 'artwork'"):
            loader.load_case_template(path)

    def test_artwork_layer_with_file(self, tmp_path):
        data = _valid_template_data()
        data["layers"] = [
            {"type": "artwork", "file": "should_not_have_this.png"},
        ]
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="artwork.*must not specify a file"):
            loader.load_case_template(path)

    def test_unknown_layer_field(self, tmp_path):
        data = _valid_template_data()
        data["layers"][0]["bogus"] = True
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="layers.*unknown field.*bogus"):
            loader.load_case_template(path)

    def test_invalid_layer_type(self, tmp_path):
        data = _valid_template_data()
        data["layers"][0]["type"] = "texture"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="layers.*type.*not valid"):
            loader.load_case_template(path)

    def test_opacity_out_of_range(self, tmp_path):
        data = _valid_template_data()
        data["layers"][0]["opacity"] = 1.5
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="opacity.*out of range"):
            loader.load_case_template(path)

    def test_invalid_blend_mode(self, tmp_path):
        data = _valid_template_data()
        data["layers"][0]["blend"] = "difference"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="blend.*not valid"):
            loader.load_case_template(path)

    def test_file_path_traversal(self, tmp_path):
        data = _valid_template_data()
        data["layers"][0]["file"] = "../escape.png"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="not a safe relative path"):
            loader.load_case_template(path)

    def test_canvas_width_too_small(self, tmp_path):
        data = _valid_template_data()
        data["canvas"]["width"] = 50
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="canvas.width.*below minimum"):
            loader.load_case_template(path)

    def test_mask_path_traversal(self, tmp_path):
        data = _valid_template_data()
        data["print_region"]["mask"] = "../../escape.png"
        path = write_json(tmp_path / "t.json", data)
        with pytest.raises(CatalogValidationError, match="not a safe relative path"):
            loader.load_case_template(path)


# ---------------------------------------------------------------------------
# Design — valid loading
# ---------------------------------------------------------------------------

class TestLoadDesignValid:
    def test_load_both_artworks(self):
        d = loader.load_design(
            FIXTURES / "designs" / "valid_both" / "design.json"
        )
        assert isinstance(d, Design)
        assert d.schema_version == 1
        assert d.id == "sample-design"
        assert d.display_name == "Sample Design"
        assert d.case_artwork == "case.png"
        assert d.wallpaper_artwork == "wallpaper.png"
        assert d.case_fit_mode == "cover"
        assert d.focal_point == (0.5, 0.5)
        assert d.tags == ["blue", "floral"]
        assert d.active is True

    def test_load_case_only(self):
        d = loader.load_design(
            FIXTURES / "designs" / "valid_case_only" / "design.json"
        )
        assert d.case_artwork == "case.png"
        assert d.wallpaper_artwork is None
        assert d.case_fit_mode == "contain"
        assert d.focal_point == (0.3, 0.4)
        assert d.tags == []

    def test_load_wallpaper_only(self):
        d = loader.load_design(
            FIXTURES / "designs" / "valid_wallpaper_only" / "design.json"
        )
        assert d.case_artwork is None
        assert d.wallpaper_artwork == "wallpaper.png"
        assert d.active is False
        assert d.tags == ["abstract"]

    def test_default_values(self, tmp_path):
        data = {
            "schema_version": 1,
            "id": "defaults-design",
            "display_name": "Defaults",
            "case_artwork": "case.png",
        }
        path = write_json(tmp_path / "design.json", data)
        d = loader.load_design(path)
        assert d.case_fit_mode == "cover"        # default
        assert d.focal_point == (0.5, 0.5)       # default
        assert d.tags == []                       # default
        assert d.active is True                  # default

    def test_design_is_frozen(self):
        d = loader.load_design(
            FIXTURES / "designs" / "valid_both" / "design.json"
        )
        with pytest.raises(AttributeError):
            d.id = "changed"


# ---------------------------------------------------------------------------
# Design — invalid loading
# ---------------------------------------------------------------------------

class TestLoadDesignInvalid:
    def test_missing_display_name(self, tmp_path):
        data = {"schema_version": 1, "id": "x", "case_artwork": "c.png"}
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="missing required.*display_name"):
            loader.load_design(path)

    def test_unknown_field(self, tmp_path):
        data = _valid_design_data()
        data["bogus"] = True
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="unknown field.*bogus"):
            loader.load_design(path)

    def test_wrong_schema_version(self, tmp_path):
        data = _valid_design_data()
        data["schema_version"] = 99
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="schema_version.*expected 1"):
            loader.load_design(path)

    def test_path_traversal_in_id(self, tmp_path):
        data = _valid_design_data()
        data["id"] = "../escape"
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="invalid characters"):
            loader.load_design(path)

    def test_empty_display_name(self, tmp_path):
        data = _valid_design_data()
        data["display_name"] = "   "
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="display_name.*must not be empty"):
            loader.load_design(path)

    def test_both_artworks_missing(self, tmp_path):
        data = {
            "schema_version": 1,
            "id": "empty-design",
            "display_name": "Empty",
        }
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="at least one of case_artwork or wallpaper_artwork"):
            loader.load_design(path)

    def test_invalid_fit_mode(self, tmp_path):
        data = _valid_design_data()
        data["case_fit_mode"] = "stretch"
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="case_fit_mode.*not valid"):
            loader.load_design(path)

    def test_invalid_focal_point(self, tmp_path):
        data = _valid_design_data()
        data["focal_point"] = [0.5, 1.5]
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="focal_point.*out of range"):
            loader.load_design(path)

    def test_focal_point_wrong_length(self, tmp_path):
        data = _valid_design_data()
        data["focal_point"] = [0.5]
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="focal_point.*length 2"):
            loader.load_design(path)

    def test_tags_not_array(self, tmp_path):
        data = _valid_design_data()
        data["tags"] = "not-an-array"
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="tags.*expected array"):
            loader.load_design(path)

    def test_artwork_path_traversal(self, tmp_path):
        data = _valid_design_data()
        data["case_artwork"] = "../escape.png"
        path = write_json(tmp_path / "d.json", data)
        with pytest.raises(CatalogValidationError, match="not a safe relative path"):
            loader.load_design(path)


# ---------------------------------------------------------------------------
# Availability — valid loading
# ---------------------------------------------------------------------------

class TestLoadAvailabilityValid:
    def test_load_valid(self):
        entries = loader.load_availability(
            FIXTURES / "availability" / "valid.json"
        )
        assert len(entries) == 2

        e0 = entries[0]
        assert isinstance(e0, VariantAvailability)
        assert e0.variant_id == "sample-design__test-device__hard"
        assert e0.design_id == "sample-design"
        assert e0.device_id == "test-device"
        assert e0.case_type == "hard"
        assert e0.available is True
        assert e0.supplier_sku == "SKU-001"
        assert e0.supplier_id == "supplier-a"

        e1 = entries[1]
        assert e1.available is False
        assert e1.supplier_sku is None
        assert e1.supplier_id is None

    def test_availability_is_frozen(self):
        entries = loader.load_availability(
            FIXTURES / "availability" / "valid.json"
        )
        with pytest.raises(AttributeError):
            entries[0].available = False

    def test_empty_array_loads(self, tmp_path):
        path = write_json(tmp_path / "a.json", [])
        entries = loader.load_availability(path)
        assert entries == []


# ---------------------------------------------------------------------------
# Availability — invalid loading
# ---------------------------------------------------------------------------

class TestLoadAvailabilityInvalid:
    def test_root_not_array(self, tmp_path):
        path = write_json(tmp_path / "a.json", {"not": "array"})
        with pytest.raises(CatalogValidationError, match="root must be a JSON array"):
            loader.load_availability(path)

    def test_variant_id_mismatch(self, tmp_path):
        data = [_valid_availability_entry()]
        data[0]["variant_id"] = "wrong__id__hard"
        path = write_json(tmp_path / "a.json", data)
        with pytest.raises(CatalogValidationError, match="variant_id.*does not match"):
            loader.load_availability(path)

    def test_missing_required_field(self, tmp_path):
        data = [_valid_availability_entry()]
        del data[0]["available"]
        path = write_json(tmp_path / "a.json", data)
        with pytest.raises(CatalogValidationError, match="missing required.*available"):
            loader.load_availability(path)

    def test_unknown_field(self, tmp_path):
        data = [_valid_availability_entry()]
        data[0]["bogus"] = True
        path = write_json(tmp_path / "a.json", data)
        with pytest.raises(CatalogValidationError, match="unknown field.*bogus"):
            loader.load_availability(path)

    def test_invalid_case_type(self, tmp_path):
        data = [_valid_availability_entry()]
        data[0]["case_type"] = "plastic"
        path = write_json(tmp_path / "a.json", data)
        with pytest.raises(CatalogValidationError, match="case_type.*not valid"):
            loader.load_availability(path)

    def test_available_not_boolean(self, tmp_path):
        data = [_valid_availability_entry()]
        data[0]["available"] = "yes"
        path = write_json(tmp_path / "a.json", data)
        with pytest.raises(CatalogValidationError, match="available.*expected"):
            loader.load_availability(path)

    def test_path_traversal_in_design_id(self, tmp_path):
        data = [_valid_availability_entry()]
        data[0]["design_id"] = "../escape"
        path = write_json(tmp_path / "a.json", data)
        with pytest.raises(CatalogValidationError, match="invalid characters"):
            loader.load_availability(path)


# ---------------------------------------------------------------------------
# Index-based listing
# ---------------------------------------------------------------------------

class TestListCaseTemplates:
    def test_empty_index_returns_empty(self, monkeypatch):
        monkeypatch.setattr(loader, "CASE_TEMPLATES_DIR", FIXTURES / "nonexistent_dir")
        assert loader.list_case_templates() == []

    def test_loads_indexed_templates(self, monkeypatch, tmp_path):
        # Create a temp case_templates dir with index + template
        ct_dir = tmp_path / "case_templates"
        ct_dir.mkdir()
        tpl_dir = ct_dir / "dev" / "hard" / "rear"
        tpl_dir.mkdir(parents=True)
        write_json(tpl_dir / "template.json", _valid_template_data())

        index = {"templates": [{"path": "dev/hard/rear/template.json"}]}
        write_json(ct_dir / "index.json", index)

        monkeypatch.setattr(loader, "CASE_TEMPLATES_DIR", ct_dir)
        templates = loader.list_case_templates()
        assert len(templates) == 1
        assert templates[0].id == "test-device__hard__rear"

    def test_get_for_device_filters(self, monkeypatch, tmp_path):
        ct_dir = tmp_path / "case_templates"
        ct_dir.mkdir()

        # Template for device A
        tpl_a = ct_dir / "dev-a" / "hard" / "rear"
        tpl_a.mkdir(parents=True)
        data_a = _valid_template_data()
        data_a["id"] = "dev-a__hard__rear"
        data_a["device_id"] = "dev-a"
        write_json(tpl_a / "template.json", data_a)

        # Template for device B
        tpl_b = ct_dir / "dev-b" / "hard" / "rear"
        tpl_b.mkdir(parents=True)
        data_b = _valid_template_data()
        data_b["id"] = "dev-b__hard__rear"
        data_b["device_id"] = "dev-b"
        write_json(tpl_b / "template.json", data_b)

        index = {
            "templates": [
                {"path": "dev-a/hard/rear/template.json"},
                {"path": "dev-b/hard/rear/template.json"},
            ]
        }
        write_json(ct_dir / "index.json", index)

        monkeypatch.setattr(loader, "CASE_TEMPLATES_DIR", ct_dir)
        result = loader.get_case_templates_for_device("dev-a")
        assert len(result) == 1
        assert result[0].device_id == "dev-a"

    def test_get_for_device_rejects_bad_id(self):
        with pytest.raises(CatalogValidationError, match="invalid characters"):
            loader.get_case_templates_for_device("../escape")


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------

def _valid_template_data():
    return {
        "schema_version": 1,
        "id": "test-device__hard__rear",
        "device_id": "test-device",
        "case_type": "hard",
        "view": "rear",
        "canvas": {"width": 1600, "height": 2000},
        "print_region": {
            "mode": "mask", "x": 200, "y": 150,
            "width": 1200, "height": 1700, "fit": "cover",
            "mask": "print_mask.png",
        },
        "layers": [
            {"type": "base", "file": "base.png"},
            {"type": "artwork"},
            {"type": "overlay", "file": "overlay.png"},
        ],
    }


def _valid_design_data():
    return {
        "schema_version": 1,
        "id": "sample-design",
        "display_name": "Sample Design",
        "case_artwork": "case.png",
        "wallpaper_artwork": "wallpaper.png",
        "case_fit_mode": "cover",
        "focal_point": [0.5, 0.5],
        "tags": ["blue"],
        "active": True,
    }


def _valid_availability_entry():
    return {
        "variant_id": "sample-design__test-device__hard",
        "design_id": "sample-design",
        "device_id": "test-device",
        "case_type": "hard",
        "available": True,
    }

