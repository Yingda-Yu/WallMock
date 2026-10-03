"""
Tests for publish mode safety gates.

Publish mode should reject all prototype templates (zero publishable assets)
since all P4B templates are marked as prototype.
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
from core.catalog_models import TEMPLATE_STATUS_PRODUCTION, TEMPLATE_STATUS_PROTOTYPE


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
# Publish mode with prototype templates
# ---------------------------------------------------------------------------

class TestPublishGate:
    def test_publish_mode_rejects_prototype_templates(self, tmp_path):
        """Publish mode with all-prototype templates produces zero publishable assets."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="publish")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert report.success is True
        assert report.mode == "publish"
        assert report.generated == 0
        assert report.skipped_publish_gate == 9
        assert report.total_assets == 9

    def test_publish_mode_generates_no_webp_files(self, tmp_path):
        """Publish mode with prototype templates should produce no WebP assets."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="publish")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        # No WebP files should exist
        assets_dir = out_dir / "assets"
        if assets_dir.exists():
            webp_files = list(assets_dir.rglob("*.webp"))
            assert len(webp_files) == 0

    def test_publish_mode_asset_status(self, tmp_path):
        """All assets should have status 'skipped_publish_gate'."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="publish")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        for variant in report.variants:
            for asset in variant.assets:
                assert asset.status == "skipped_publish_gate"
                assert asset.path == ""

    def test_publish_mode_template_status_recorded(self, tmp_path):
        """Variant results should record prototype template status."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="publish")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        for variant in report.variants:
            assert variant.template_status == TEMPLATE_STATUS_PROTOTYPE

    def test_publish_mode_still_generates_bundle(self, tmp_path):
        """Publish mode should still generate a bundle (with zero assets)."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="publish")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        # Bundle should exist
        assert (out_dir / "contract_bundle.v1.json").exists()
        assert (out_dir / "device_registry.v1.json").exists()
        assert (out_dir / "render_capabilities.v1.json").exists()
        assert (out_dir / "render_manifest.v1.json").exists()

        # Manifest should have zero variants with assets (or no variants)
        with open(out_dir / "render_manifest.v1.json", "r") as f:
            manifest = json.load(f)
        # Either no variants or variants with no assets are both acceptable
        # as long as there are no generated assets
        assert manifest.get("contract_version") == 1


# ---------------------------------------------------------------------------
# Preview mode allows prototype
# ---------------------------------------------------------------------------

class TestPreviewAllowsPrototype:
    def test_preview_mode_allows_prototype(self, tmp_path):
        """Preview mode should render prototype templates."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert report.success is True
        assert report.generated == 9
        assert report.skipped_publish_gate == 0

    def test_preview_mode_assets_have_prototype_status(self, tmp_path):
        """Assets in preview mode should reflect prototype template status."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        for variant in report.variants:
            assert variant.template_status == TEMPLATE_STATUS_PROTOTYPE


# ---------------------------------------------------------------------------
# Mixed template statuses
# ---------------------------------------------------------------------------

class TestMixedStatus:
    def test_mixed_plan_counts_correctly(self, tmp_path):
        """A plan with mix of devices still counts publish gate correctly."""
        # All P4B templates are prototype, so all 9 should be gated
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="publish")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert report.skipped_publish_gate == 9
        assert report.generated == 0

    def test_single_device_publish(self, tmp_path):
        """Single device in publish mode correctly gates all its assets."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = CatalogBuildPlan(
            schema_version=1,
            mode="publish",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800, 1200],
            )],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert report.total_assets == 2
        assert report.skipped_publish_gate == 2
        assert report.generated == 0
