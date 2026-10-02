"""
Tests for the core catalog builder functionality.

Tests the CatalogBuilder with the P4B matrix:
- design: color-block
- devices: iphone-17e, iphone-17, iphone-air
- case: hard
- view: rear
- widths: 800, 1200, 1600

Expected: 3 variants, 9 WebP assets, valid Contract v1 bundle.
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
)
from core.catalog_builder import CatalogBuilder, BuildReport
from core.bundle_validator import validate_contract_bundle


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "assets" / "case_templates"
ARTWORKS_DIR = REPO_ROOT / "tests" / "fixtures" / "artworks"
DEVICE_REGISTRY = REPO_ROOT / "catalog" / "device_registry.v1.json"


def _make_p4b_plan(mode="preview") -> CatalogBuildPlan:
    """Create a build plan matching the approved P4B matrix."""
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
# Basic build tests
# ---------------------------------------------------------------------------

class TestCatalogBuilderBasic:
    def test_preview_build_generates_9_assets(self, tmp_path):
        """Preview build with P4B matrix generates 9 WebP assets."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert isinstance(report, BuildReport)
        assert report.success is True
        assert report.mode == "preview"
        assert report.total_assets == 9
        assert report.generated == 9
        assert report.skipped_unchanged == 0
        assert report.skipped_publish_gate == 0
        assert len(report.errors) == 0

    def test_preview_build_creates_webp_files(self, tmp_path):
        """Verify actual WebP files are created on disk."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        # Count WebP files in the assets directory
        assets_dir = out_dir / "assets"
        webp_files = list(assets_dir.rglob("*.webp"))
        assert len(webp_files) == 9

        # Each file should be a valid WebP (non-zero size)
        for f in webp_files:
            assert f.stat().st_size > 0
            # Check WebP header
            with open(f, "rb") as fh:
                header = fh.read(12)
                assert header[:4] == b"RIFF"
                assert header[8:12] == b"WEBP"

    def test_three_variants_generated(self, tmp_path):
        """Verify 3 variants (one per device) are generated."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert len(report.variants) == 3
        variant_ids = sorted([v.variant_id for v in report.variants])
        assert variant_ids == [
            "color-block__iphone-17__hard",
            "color-block__iphone-17e__hard",
            "color-block__iphone-air__hard",
        ]

    def test_each_variant_has_3_width_assets(self, tmp_path):
        """Each variant should have 3 assets (3 widths x 1 view)."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        for variant in report.variants:
            assert len(variant.assets) == 3
            widths = sorted([a.width for a in variant.assets])
            assert widths == [800, 1200, 1600]

    def test_assets_have_correct_status(self, tmp_path):
        """All assets should have status 'generated' on first build."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        for variant in report.variants:
            for asset in variant.assets:
                assert asset.status == "generated"
                assert asset.path != ""
                assert asset.height > 0

    def test_asset_paths_are_content_addressed(self, tmp_path):
        """Asset paths should follow content-addressed format."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        for variant in report.variants:
            for asset in variant.assets:
                # Format: assets/<design_id>/<device_id>/<case_type>/<view>-w<width>.<hash12>.webp
                assert asset.path.startswith("assets/")
                assert asset.path.endswith(".webp")
                assert variant.design_id in asset.path
                assert variant.device_id in asset.path
                assert variant.case_type in asset.path
                assert f"rear-w{asset.width}." in asset.path

    def test_build_report_to_dict(self, tmp_path):
        """BuildReport.to_dict() produces a valid serializable dict."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))
        report_dict = report.to_dict()

        assert report_dict["schema_version"] == 1
        assert report_dict["success"] is True
        assert report_dict["mode"] == "preview"
        assert report_dict["total_assets"] == 9
        assert report_dict["generated"] == 9
        assert len(report_dict["variants"]) == 3
        # Should be JSON-serializable
        json_str = json.dumps(report_dict)
        assert len(json_str) > 0


# ---------------------------------------------------------------------------
# Output quality / properties
# ---------------------------------------------------------------------------

class TestOutputQuality:
    def test_webp_quality_setting(self, tmp_path):
        """WebP quality from render_options is used."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        # High quality
        plan_hq = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(
                fit_mode="cover",
                webp_quality=95,
            ),
        )
        out_hq = tmp_path / "hq"
        report_hq = builder.build(plan_hq, str(out_hq))

        # Low quality
        plan_lq = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(
                fit_mode="cover",
                webp_quality=10,
            ),
        )
        out_lq = tmp_path / "lq"
        report_lq = builder.build(plan_lq, str(out_lq))

        # High quality should be larger file
        hq_files = list(out_hq.rglob("*.webp"))
        lq_files = list(out_lq.rglob("*.webp"))
        assert len(hq_files) == 1
        assert len(lq_files) == 1
        assert hq_files[0].stat().st_size > lq_files[0].stat().st_size

    def test_no_upscaling(self, tmp_path):
        """Widths larger than source should not be upscaled."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        # Request very wide output - should be capped at master resolution
        plan = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[4000],  # Wider than template canvas
            )],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        out_dir = tmp_path / "catalog"
        report = builder.build(plan, str(out_dir))

        # The asset width should be the master width, not 4000
        assert len(report.variants) == 1
        assert len(report.variants[0].assets) == 1
        # Master is at template canvas width, which is 1600 for iphone-17
        asset = report.variants[0].assets[0]
        assert asset.width <= 1600  # Should not exceed canvas width

    def test_aspect_ratio_preserved(self, tmp_path):
        """Responsive variants preserve the aspect ratio of the master."""
        from PIL import Image
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"
        report = builder.build(plan, str(out_dir))

        # Get all webp files for one variant
        variant = report.variants[0]
        assets_dir = out_dir / "assets" / variant.design_id / variant.device_id / variant.case_type
        webp_files = sorted(assets_dir.glob("*.webp"), key=lambda f: f.stat().st_size)

        if len(webp_files) >= 2:
            ratios = []
            for f in webp_files:
                img = Image.open(str(f))
                ratios.append(img.width / img.height)

            # All ratios should be approximately equal
            for r in ratios[1:]:
                assert abs(r - ratios[0]) < 0.01


# ---------------------------------------------------------------------------
# Contract bundle tests are in test_catalog_storefront_bundle.py
# These are just basic smoke tests
# ---------------------------------------------------------------------------

class TestBundleSmoke:
    def test_bundle_files_created(self, tmp_path):
        """Build should create contract bundle files."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert report.bundle_path is not None
        assert Path(report.bundle_path).exists()
        assert (out_dir / "device_registry.v1.json").exists()
        assert (out_dir / "render_capabilities.v1.json").exists()
        assert (out_dir / "render_manifest.v1.json").exists()

    def test_bundle_validates(self, tmp_path):
        """Generated bundle should pass bundle validation."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))

        assert report.bundle_valid is True

        val_report = validate_contract_bundle(str(out_dir))
        assert val_report.valid is True
        assert len(val_report.errors) == 0
