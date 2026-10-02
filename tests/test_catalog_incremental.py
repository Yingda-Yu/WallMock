"""
Tests for incremental build caching.

Second identical build should have:
  - 0 generated
  - 9 skipped_unchanged
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog_build_plan import (
    CatalogBuildPlan,
    BuildTarget,
    BuildRenderOptions,
)
from core.catalog_builder import CatalogBuilder, BUILD_STATE_FILENAME


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
# Incremental cache: second identical build
# ---------------------------------------------------------------------------

class TestIncrementalCache:
    def test_second_build_skips_all(self, tmp_path):
        """Second identical build should skip all 9 assets as unchanged."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        # First build
        report1 = builder.build(plan, str(out_dir))
        assert report1.success
        assert report1.generated == 9
        assert report1.skipped_unchanged == 0

        # Record file modification times
        webp_files_before = {}
        for f in out_dir.rglob("*.webp"):
            webp_files_before[str(f)] = f.stat().st_mtime

        # Second build (same plan, same output)
        report2 = builder.build(plan, str(out_dir))
        assert report2.success
        assert report2.generated == 0
        assert report2.skipped_unchanged == 9
        assert report2.skipped_publish_gate == 0
        assert report2.total_assets == 9

        # File mtimes should be unchanged (files weren't rewritten)
        for fpath, old_mtime in webp_files_before.items():
            f = Path(fpath)
            assert f.exists()
            # mtime should be the same (or very close — we use copy which
            # preserves mtime, but some filesystems may have slight differences)
            new_mtime = f.stat().st_mtime
            assert new_mtime == old_mtime

    def test_build_state_file_created(self, tmp_path):
        """Build state file should be created after a successful build."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        state_path = out_dir / BUILD_STATE_FILENAME
        assert state_path.exists()

        with open(state_path, "r") as f:
            state = json.load(f)

        assert state["schema_version"] == 1
        assert state["mode"] == "preview"
        assert "variants" in state
        assert len(state["variants"]) == 3

    def test_build_state_has_all_assets(self, tmp_path):
        """Build state should contain all 9 assets."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        builder.build(plan, str(out_dir))

        state_path = out_dir / BUILD_STATE_FILENAME
        with open(state_path, "r") as f:
            state = json.load(f)

        total_assets = 0
        for vid, vdata in state["variants"].items():
            total_assets += len(vdata["assets"])
            for key, asset in vdata["assets"].items():
                assert "fingerprint" in asset
                assert "path" in asset
                assert asset["fingerprint"].startswith("sha256:")

        assert total_assets == 9


# ---------------------------------------------------------------------------
# Incremental cache: changed inputs
# ---------------------------------------------------------------------------

class TestIncrementalCacheChanges:
    def test_changed_design_triggers_rebuild(self, tmp_path):
        """Changing the design artwork should trigger a rebuild."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )

        # First build with color-block
        plan1 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        out_dir = tmp_path / "catalog"
        report1 = builder.build(plan1, str(out_dir))
        assert report1.generated == 1

        # Second build with tile-pattern (different design)
        plan2 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["tile-pattern"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        report2 = builder.build(plan2, str(out_dir))
        # Different design -> new asset should be generated
        assert report2.generated >= 1

    def test_changed_width_triggers_rebuild(self, tmp_path):
        """Adding a new width should generate that asset, skip existing."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )

        # First build with one width
        plan1 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        out_dir = tmp_path / "catalog"
        report1 = builder.build(plan1, str(out_dir))
        assert report1.generated == 1

        # Second build with two widths
        plan2 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800, 1200],
            )],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        report2 = builder.build(plan2, str(out_dir))
        # 800 should be skipped, 1200 should be generated
        assert report2.generated == 1
        assert report2.skipped_unchanged == 1

    def test_changed_fit_mode_triggers_rebuild(self, tmp_path):
        """Changing fit_mode should trigger a rebuild."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )

        plan1 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        out_dir = tmp_path / "catalog"
        report1 = builder.build(plan1, str(out_dir))
        assert report1.generated == 1

        plan2 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(fit_mode="contain"),
        )
        report2 = builder.build(plan2, str(out_dir))
        assert report2.generated == 1
        assert report2.skipped_unchanged == 0

    def test_changed_zoom_triggers_rebuild(self, tmp_path):
        """Changing zoom should trigger a rebuild."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )

        plan1 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(fit_mode="cover", zoom=1.0),
        )
        out_dir = tmp_path / "catalog"
        report1 = builder.build(plan1, str(out_dir))
        assert report1.generated == 1

        plan2 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[BuildTarget(
                device_id="iphone-17",
                case_type="hard",
                views=["rear"],
                widths=[800],
            )],
            render_options=BuildRenderOptions(fit_mode="cover", zoom=1.2),
        )
        report2 = builder.build(plan2, str(out_dir))
        assert report2.generated == 1
        assert report2.skipped_unchanged == 0


# ---------------------------------------------------------------------------
# Full-snapshot semantics
# ---------------------------------------------------------------------------

class TestFullSnapshot:
    def test_removed_assets_are_gone_after_rebuild(self, tmp_path):
        """If a design/target is removed, its assets are gone after rebuild.

        Full-snapshot semantics: each build is a complete snapshot.
        """
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )

        # First build with 2 devices
        plan1 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[
                BuildTarget(
                    device_id="iphone-17",
                    case_type="hard",
                    views=["rear"],
                    widths=[800],
                ),
                BuildTarget(
                    device_id="iphone-17e",
                    case_type="hard",
                    views=["rear"],
                    widths=[800],
                ),
            ],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        out_dir = tmp_path / "catalog"
        report1 = builder.build(plan1, str(out_dir))
        assert report1.generated == 2

        # Check both device dirs exist
        assert (out_dir / "assets" / "color-block" / "iphone-17").exists()
        assert (out_dir / "assets" / "color-block" / "iphone-17e").exists()

        # Second build with only 1 device
        plan2 = CatalogBuildPlan(
            schema_version=1,
            mode="preview",
            design_ids=["color-block"],
            targets=[
                BuildTarget(
                    device_id="iphone-17",
                    case_type="hard",
                    views=["rear"],
                    widths=[800],
                ),
            ],
            render_options=BuildRenderOptions(fit_mode="cover"),
        )
        report2 = builder.build(plan2, str(out_dir))
        # iphone-17 is unchanged from previous build, so it's skipped
        assert report2.skipped_unchanged == 1
        assert report2.generated == 0
        assert report2.total_assets == 1

        # iphone-17e should be gone
        assert (out_dir / "assets" / "color-block" / "iphone-17").exists()
        assert not (out_dir / "assets" / "color-block" / "iphone-17e").exists()

    def test_complete_output_on_success(self, tmp_path):
        """On success, output dir has a complete, consistent snapshot."""
        builder = CatalogBuilder(
            templates_root=str(TEMPLATES_ROOT),
            designs_root=str(ARTWORKS_DIR),
            device_registry_path=str(DEVICE_REGISTRY),
        )
        plan = _make_p4b_plan(mode="preview")
        out_dir = tmp_path / "catalog"

        report = builder.build(plan, str(out_dir))
        assert report.success

        # All expected files should be present
        assert (out_dir / "contract_bundle.v1.json").exists()
        assert (out_dir / "device_registry.v1.json").exists()
        assert (out_dir / "render_capabilities.v1.json").exists()
        assert (out_dir / "render_manifest.v1.json").exists()
        assert (out_dir / BUILD_STATE_FILENAME).exists()

        webp_count = len(list(out_dir.rglob("*.webp")))
        assert webp_count == 9
