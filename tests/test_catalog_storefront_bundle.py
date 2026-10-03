"""
Tests for Contract v1 bundle generation from catalog builds.

Verifies that:
  - Generated Contract v1 bundle validates
  - Contract v1 schema is unchanged
  - All bundle artifacts are present and correctly hashed
  - Manifest entries match actual rendered assets
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog_build_plan import (
    CatalogBuildPlan,
    BuildTarget,
    BuildRenderOptions,
)
from core.catalog_builder import CatalogBuilder
from core.bundle_validator import validate_contract_bundle
from core.contract_ids import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    build_variant_id,
    build_render_asset_id,
    is_valid_content_hash,
    is_safe_relative_path,
    parse_variant_id,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "assets" / "case_templates"
ARTWORKS_DIR = REPO_ROOT / "tests" / "fixtures" / "artworks"
DEVICE_REGISTRY = REPO_ROOT / "catalog" / "device_registry.v1.json"


def _make_p4b_plan(mode="preview") -> CatalogBuildPlan:
    targets = [
        BuildTarget(
            device_id=device,
            case_type="hard",
            views=["rear"],
            widths=[800, 1200, 1600],
        )
        for device in ["iphone-17e", "iphone-17", "iphone-air"]
    ]
    return CatalogBuildPlan(
        schema_version=1,
        mode=mode,
        design_ids=["color-block"],
        targets=targets,
        render_options=BuildRenderOptions(
            fit_mode="cover",
            zoom=1.0,
            offset_x=0.0,
            offset_y=0.0,
            webp_quality=85,
        ),
    )


# ---------------------------------------------------------------------------
# Bundle structure
# ---------------------------------------------------------------------------

class TestBundleStructure:
    def test_bundle_files_exist(self, tmp_path):
        """All four bundle files should be present after a build."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        assert (out_dir / "contract_bundle.v1.json").exists()
        assert (out_dir / "device_registry.v1.json").exists()
        assert (out_dir / "render_capabilities.v1.json").exists()
        assert (out_dir / "render_manifest.v1.json").exists()

    def test_bundle_index_structure(self, tmp_path):
        """Bundle index should have correct structure."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "contract_bundle.v1.json", "r") as f:
            bundle = json.load(f)

        assert bundle["contract"] == CONTRACT_NAME
        assert bundle["contract_version"] == CONTRACT_VERSION
        assert "artifacts" in bundle
        assert len(bundle["artifacts"]) == 3

        for fname, art_info in bundle["artifacts"].items():
            assert "filename" in art_info
            assert "sha256" in art_info
            assert len(art_info["sha256"]) == 64

    def test_device_registry_structure(self, tmp_path):
        """Device registry should have correct structure."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "device_registry.v1.json", "r") as f:
            reg = json.load(f)

        assert reg["contract"] == CONTRACT_NAME
        assert reg["contract_version"] == CONTRACT_VERSION
        assert "devices" in reg
        assert isinstance(reg["devices"], list)
        assert len(reg["devices"]) >= 3  # At least the 3 P4B devices

    def test_render_capabilities_structure(self, tmp_path):
        """Render capabilities should have correct structure."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_capabilities.v1.json", "r") as f:
            caps = json.load(f)

        assert caps["contract"] == CONTRACT_NAME
        assert caps["contract_version"] == CONTRACT_VERSION
        assert "devices" in caps
        assert isinstance(caps["devices"], dict)


# ---------------------------------------------------------------------------
# Bundle validation
# ---------------------------------------------------------------------------

class TestBundleValidation:
    def test_bundle_validates_cleanly(self, tmp_path):
        """Generated bundle should pass the full bundle validator."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        val_report = validate_contract_bundle(str(out_dir))
        assert val_report.valid is True, f"Validation errors: {val_report.errors}"
        assert len(val_report.errors) == 0

    def test_bundle_artifact_hashes_match(self, tmp_path):
        """Bundle index SHA-256 hashes should match actual file contents."""
        import hashlib
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "contract_bundle.v1.json", "r") as f:
            bundle = json.load(f)

        for fname, art_info in bundle["artifacts"].items():
            fpath = out_dir / fname
            assert fpath.exists()

            h = hashlib.sha256()
            with open(fpath, "rb") as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            actual_sha = h.hexdigest()
            assert actual_sha == art_info["sha256"], (
                f"Hash mismatch for {fname}: expected {art_info['sha256']}, "
                f"got {actual_sha}"
            )


# ---------------------------------------------------------------------------
# Manifest content
# ---------------------------------------------------------------------------

class TestManifestContent:
    def test_manifest_has_three_variants(self, tmp_path):
        """Render manifest should have 3 variants (one per device)."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)

        variants = manifest.get("variants", {})
        assert len(variants) == 3

        expected_variant_ids = {
            "color-block__iphone-17__hard",
            "color-block__iphone-17e__hard",
            "color-block__iphone-air__hard",
        }
        assert set(variants.keys()) == expected_variant_ids

    def test_manifest_each_variant_has_three_widths(self, tmp_path):
        """Each variant in the manifest should have 3 width assets."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)

        for vid, vdata in manifest["variants"].items():
            views = vdata.get("views", {})
            assert "rear" in views
            rear_widths = views["rear"]
            assert len(rear_widths) == 3
            assert "800" in rear_widths
            assert "1200" in rear_widths
            assert "1600" in rear_widths

    def test_manifest_asset_fields(self, tmp_path):
        """Each manifest asset entry should have all required fields."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)

        for vid, vdata in manifest["variants"].items():
            for view_name, widths in vdata["views"].items():
                for w_str, asset in widths.items():
                    # Required fields
                    assert "render_asset_id" in asset
                    assert "path" in asset
                    assert "width" in asset
                    assert "height" in asset
                    assert "format" in asset
                    assert "content_hash" in asset
                    assert "view" in asset
                    assert "template_id" in asset
                    assert "template_status" in asset
                    assert "production_publishable" in asset
                    assert "renderer_version" in asset

                    # Value validations
                    assert asset["format"] == "webp"
                    assert is_valid_content_hash(asset["content_hash"])
                    assert is_safe_relative_path(asset["path"])
                    assert isinstance(asset["width"], int)
                    assert isinstance(asset["height"], int)
                    assert asset["width"] > 0
                    assert asset["height"] > 0

    def test_manifest_prototype_status(self, tmp_path):
        """All assets should be marked as prototype (not production)."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)

        for vid, vdata in manifest["variants"].items():
            assert vdata["template_status"] == "prototype"
            for view_name, widths in vdata["views"].items():
                for w_str, asset in widths.items():
                    assert asset["production_publishable"] is False

    def test_manifest_render_asset_ids_are_valid(self, tmp_path):
        """All render_asset_id values should be correctly formatted."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)

        for vid, vdata in manifest["variants"].items():
            for view_name, widths in vdata["views"].items():
                for w_str, asset in widths.items():
                    # Verify render_asset_id matches expected format
                    expected_id = build_render_asset_id(
                        vid, view_name, int(w_str)
                    )
                    assert asset["render_asset_id"] == expected_id

    def test_manifest_asset_paths_match_files(self, tmp_path):
        """Asset paths in the manifest should correspond to actual files."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)

        total_assets = 0
        for vid, vdata in manifest["variants"].items():
            for view_name, widths in vdata["views"].items():
                for w_str, asset in widths.items():
                    fpath = out_dir / asset["path"]
                    assert fpath.exists(), f"Asset file not found: {asset['path']}"
                    assert fpath.stat().st_size > 0
                    total_assets += 1

        assert total_assets == 9

    def test_manifest_contract_version_unchanged(self, tmp_path):
        """Contract version in manifest should still be v1 (unchanged)."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)

        assert manifest["contract"] == CONTRACT_NAME
        assert manifest["contract_version"] == CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Contract version consistency across artifacts
# ---------------------------------------------------------------------------

class TestContractVersionConsistency:
    def test_all_artifacts_same_contract_version(self, tmp_path):
        """All four bundle artifacts should have the same contract version."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        versions = set()
        contracts = set()

        for fname in [
            "device_registry.v1.json",
            "render_capabilities.v1.json",
            "render_manifest.v1.json",
        ]:
            with open(out_dir / fname, "r") as f:
                data = json.load(f)
            versions.add(data.get("contract_version"))
            contracts.add(data.get("contract"))

        assert len(versions) == 1
        assert versions.pop() == CONTRACT_VERSION
        assert len(contracts) == 1
        assert contracts.pop() == CONTRACT_NAME
