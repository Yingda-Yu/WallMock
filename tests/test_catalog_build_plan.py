"""
Tests for catalog build plan loading and validation.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog_build_plan import (
    CatalogBuildPlan,
    BuildTarget,
    BuildRenderOptions,
    load_catalog_build_plan,
    find_template_dir,
)
from core.catalog_models import CatalogValidationError


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "assets" / "case_templates"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _write_plan(tmp_path, plan_dict):
    """Helper: write a plan dict to a JSON file and return the path."""
    path = tmp_path / "plan.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan_dict, f)
    return str(path)


def _valid_plan_dict():
    """Return a minimal valid build plan dict matching the P4B matrix."""
    return {
        "schema_version": 1,
        "mode": "preview",
        "design_ids": ["color-block"],
        "targets": [
            {
                "device_id": "iphone-17e",
                "case_type": "hard",
                "views": ["rear"],
                "widths": [800, 1200, 1600],
            },
            {
                "device_id": "iphone-17",
                "case_type": "hard",
                "views": ["rear"],
                "widths": [800, 1200, 1600],
            },
            {
                "device_id": "iphone-air",
                "case_type": "hard",
                "views": ["rear"],
                "widths": [800, 1200, 1600],
            },
        ],
        "render_options": {
            "fit_mode": "cover",
            "zoom": 1.0,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "webp_quality": 85,
        },
    }


# ---------------------------------------------------------------------------
# Valid plan loading
# ---------------------------------------------------------------------------

class TestValidPlanLoading:
    def test_load_valid_preview_plan(self, tmp_path):
        plan_path = _write_plan(tmp_path, _valid_plan_dict())
        plan = load_catalog_build_plan(plan_path, validate_templates_exist=False)
        assert isinstance(plan, CatalogBuildPlan)
        assert plan.schema_version == 1
        assert plan.mode == "preview"
        assert plan.design_ids == ["color-block"]
        assert len(plan.targets) == 3

    def test_load_valid_publish_plan(self, tmp_path):
        d = _valid_plan_dict()
        d["mode"] = "publish"
        plan_path = _write_plan(tmp_path, d)
        plan = load_catalog_build_plan(plan_path, validate_templates_exist=False)
        assert plan.mode == "publish"

    def test_total_asset_count(self, tmp_path):
        plan_path = _write_plan(tmp_path, _valid_plan_dict())
        plan = load_catalog_build_plan(plan_path, validate_templates_exist=False)
        # 3 devices x 1 view x 3 widths x 1 design = 9
        assert plan.total_asset_count() == 9

    def test_all_device_ids(self, tmp_path):
        plan_path = _write_plan(tmp_path, _valid_plan_dict())
        plan = load_catalog_build_plan(plan_path, validate_templates_exist=False)
        devices = plan.all_device_ids()
        assert devices == ["iphone-17", "iphone-17e", "iphone-air"]

    def test_render_options_defaults(self, tmp_path):
        d = _valid_plan_dict()
        d["render_options"] = {"fit_mode": "cover"}
        plan_path = _write_plan(tmp_path, d)
        plan = load_catalog_build_plan(plan_path, validate_templates_exist=False)
        assert plan.render_options.fit_mode == "cover"
        assert plan.render_options.zoom == 1.0
        assert plan.render_options.offset_x == 0.0
        assert plan.render_options.offset_y == 0.0
        assert plan.render_options.webp_quality == 85

    def test_widths_sorted(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["widths"] = [1600, 800, 1200]  # unsorted
        plan_path = _write_plan(tmp_path, d)
        plan = load_catalog_build_plan(plan_path, validate_templates_exist=False)
        assert plan.targets[0].widths == [800, 1200, 1600]

    def test_views_sorted(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["views"] = ["front", "rear"]  # unsorted
        plan_path = _write_plan(tmp_path, d)
        plan = load_catalog_build_plan(plan_path, validate_templates_exist=False)
        assert plan.targets[0].views == ["front", "rear"]


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_invalid_schema_version(self, tmp_path):
        d = _valid_plan_dict()
        d["schema_version"] = 2
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="schema_version"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_missing_schema_version(self, tmp_path):
        d = _valid_plan_dict()
        del d["schema_version"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="schema_version"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_unknown_top_level_field(self, tmp_path):
        d = _valid_plan_dict()
        d["extra_field"] = "nope"
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="unknown field"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)


# ---------------------------------------------------------------------------
# Mode validation
# ---------------------------------------------------------------------------

class TestModeValidation:
    def test_invalid_mode(self, tmp_path):
        d = _valid_plan_dict()
        d["mode"] = "production"
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="mode"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_missing_mode(self, tmp_path):
        d = _valid_plan_dict()
        del d["mode"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="mode"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)


# ---------------------------------------------------------------------------
# Design ID validation
# ---------------------------------------------------------------------------

class TestDesignIdValidation:
    def test_empty_design_ids(self, tmp_path):
        d = _valid_plan_dict()
        d["design_ids"] = []
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="design_ids"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_duplicate_design_ids(self, tmp_path):
        d = _valid_plan_dict()
        d["design_ids"] = ["color-block", "color-block"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="duplicate"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_invalid_design_id_with_dots(self, tmp_path):
        d = _valid_plan_dict()
        d["design_ids"] = ["color.block"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="design_ids"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_invalid_design_id_path_traversal(self, tmp_path):
        d = _valid_plan_dict()
        d["design_ids"] = ["../evil"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="design_ids"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_invalid_design_id_uppercase(self, tmp_path):
        d = _valid_plan_dict()
        d["design_ids"] = ["ColorBlock"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="design_ids"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)


# ---------------------------------------------------------------------------
# Target validation
# ---------------------------------------------------------------------------

class TestTargetValidation:
    def test_empty_targets(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"] = []
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="targets"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_duplicate_targets(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"] = [
            {
                "device_id": "iphone-17",
                "case_type": "hard",
                "views": ["rear"],
                "widths": [800],
            },
            {
                "device_id": "iphone-17",
                "case_type": "hard",
                "views": ["front"],
                "widths": [800],
            },
        ]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="duplicate target"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_invalid_device_id(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["device_id"] = "Invalid/ID"
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="device_id"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_invalid_case_type(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["case_type"] = "rubber"
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="case_type"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_missing_target_fields(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"] = [{"device_id": "iphone-17"}]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="missing"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_unknown_target_field(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["extra"] = "nope"
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="unknown field"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)


# ---------------------------------------------------------------------------
# View validation
# ---------------------------------------------------------------------------

class TestViewValidation:
    def test_empty_views(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["views"] = []
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="views"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_duplicate_views(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["views"] = ["rear", "rear"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="duplicate view"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_invalid_view(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["views"] = ["side"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="view"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)


# ---------------------------------------------------------------------------
# Width validation
# ---------------------------------------------------------------------------

class TestWidthValidation:
    def test_empty_widths(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["widths"] = []
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="widths"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_duplicate_widths(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["widths"] = [800, 800, 1200]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="duplicate width"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_width_too_small(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["widths"] = [50]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="width"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_width_too_large(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["widths"] = [10000]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="width"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_non_integer_width(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"][0]["widths"] = ["800"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="width"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)


# ---------------------------------------------------------------------------
# Render options validation
# ---------------------------------------------------------------------------

class TestRenderOptionsValidation:
    def test_missing_fit_mode(self, tmp_path):
        d = _valid_plan_dict()
        del d["render_options"]["fit_mode"]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="fit_mode"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_invalid_fit_mode(self, tmp_path):
        d = _valid_plan_dict()
        d["render_options"]["fit_mode"] = "stretch"
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="fit_mode"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_zoom_out_of_range(self, tmp_path):
        d = _valid_plan_dict()
        d["render_options"]["zoom"] = 20.0
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="zoom"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_offset_out_of_range(self, tmp_path):
        d = _valid_plan_dict()
        d["render_options"]["offset_x"] = 2.0
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="offset_x"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_webp_quality_out_of_range(self, tmp_path):
        d = _valid_plan_dict()
        d["render_options"]["webp_quality"] = 150
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="webp_quality"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)

    def test_unknown_render_option(self, tmp_path):
        d = _valid_plan_dict()
        d["render_options"]["unknown_option"] = True
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="unknown field"):
            load_catalog_build_plan(plan_path, validate_templates_exist=False)


# ---------------------------------------------------------------------------
# Template existence validation
# ---------------------------------------------------------------------------

class TestTemplateExistenceValidation:
    def test_validates_templates_exist(self, tmp_path):
        plan_path = _write_plan(tmp_path, _valid_plan_dict())
        # Should succeed because all P4B templates exist
        plan = load_catalog_build_plan(
            plan_path,
            templates_root=str(TEMPLATES_ROOT),
            validate_templates_exist=True,
        )
        assert len(plan.targets) == 3

    def test_unknown_device_fails_template_validation(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"] = [{
            "device_id": "no-such-device",
            "case_type": "hard",
            "views": ["rear"],
            "widths": [800],
        }]
        plan_path = _write_plan(tmp_path, d)
        with pytest.raises(CatalogValidationError, match="no template found"):
            load_catalog_build_plan(
                plan_path,
                templates_root=str(TEMPLATES_ROOT),
                validate_templates_exist=True,
            )

    def test_skip_template_validation(self, tmp_path):
        d = _valid_plan_dict()
        d["targets"] = [{
            "device_id": "no-such-device",
            "case_type": "hard",
            "views": ["rear"],
            "widths": [800],
        }]
        plan_path = _write_plan(tmp_path, d)
        # Should succeed when template validation is disabled
        plan = load_catalog_build_plan(
            plan_path,
            templates_root=str(TEMPLATES_ROOT),
            validate_templates_exist=False,
        )
        assert len(plan.targets) == 1


# ---------------------------------------------------------------------------
# File not found / invalid JSON
# ---------------------------------------------------------------------------

class TestFileErrors:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(CatalogValidationError, match="does not exist"):
            load_catalog_build_plan(tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        with open(path, "w") as f:
            f.write("not json {{{")
        with pytest.raises(CatalogValidationError, match="invalid JSON"):
            load_catalog_build_plan(str(path))

    def test_root_not_object(self, tmp_path):
        path = tmp_path / "array.json"
        with open(path, "w") as f:
            f.write("[1, 2, 3]")
        with pytest.raises(CatalogValidationError, match="root must be"):
            load_catalog_build_plan(str(path))


# ---------------------------------------------------------------------------
# find_template_dir
# ---------------------------------------------------------------------------

class TestFindTemplateDir:
    def test_finds_iphone_17_hard_rear(self):
        result = find_template_dir(str(TEMPLATES_ROOT), "iphone-17", "hard", "rear")
        assert result is not None
        assert "iphone-17" in result
        assert "hard" in result
        assert "rear" in result

    def test_finds_iphone_17e_hard_rear(self):
        result = find_template_dir(str(TEMPLATES_ROOT), "iphone-17e", "hard", "rear")
        assert result is not None
        assert "iphone-17e" in result

    def test_finds_iphone_air_hard_rear(self):
        result = find_template_dir(str(TEMPLATES_ROOT), "iphone-air", "hard", "rear")
        assert result is not None
        assert "iphone-air" in result

    def test_returns_none_for_nonexistent(self):
        result = find_template_dir(str(TEMPLATES_ROOT), "no-such-device", "hard", "rear")
        assert result is None
