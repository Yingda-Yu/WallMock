"""
Catalog build orchestrator for WallMock.

Orchestrates the full catalog build pipeline:
  1. Load build plan
  2. Resolve templates and design artworks
  3. Render case images
  4. Generate responsive WebP variants
  5. Cache incrementally (skip unchanged assets)
  6. Build atomic output with Contract v1 bundle
  7. Validate the final bundle

Modes:
  - preview: prototype templates are allowed
  - publish: only production-grade templates are rendered

Incremental cache is stored at:
  <output_dir>/.wallmock-build-state.json

Atomic builds: render into a temp directory, validate, then move
into place as a complete snapshot.
"""
import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from .asset_store import LocalAssetStore, build_asset_path
from .catalog_build_plan import (
    CatalogBuildPlan,
    BuildTarget,
    find_template_dir,
)
from .catalog_hashing import (
    compute_render_fingerprint,
    fingerprint_prefix,
    RENDERER_VERSION,
)
from .catalog_models import (
    CatalogValidationError,
    TEMPLATE_STATUS_PRODUCTION,
    TEMPLATE_STATUS_PROTOTYPE,
)
from .case_renderer import render_case
from .case_template_loader import load_case_template
from .output_optimizer import generate_responsive_webp
from .contract_export import (
    build_render_manifest_entry,
    build_render_manifest,
    build_render_capabilities,
    build_contract_bundle,
    write_json_deterministic,
    sha256_file,
)
from .contract_ids import (
    build_variant_id,
    build_content_hash,
    CONTRACT_VERSION,
)
from .bundle_validator import validate_contract_bundle
from .device_registry_loader import load_device_registry


BUILD_STATE_FILENAME = ".wallmock-build-state.json"
BUILD_STATE_VERSION = 1


@dataclass
class BuildAssetResult:
    """Result for a single render asset."""
    path: str
    view: str
    width: int
    height: int
    status: str  # "generated" | "skipped_unchanged" | "skipped_publish_gate" | "error"
    fingerprint: str
    error: Optional[str] = None


@dataclass
class BuildVariantResult:
    """Result for a single variant (design x device x case_type)."""
    variant_id: str
    design_id: str
    device_id: str
    case_type: str
    template_id: str
    template_status: str
    assets: List[BuildAssetResult] = field(default_factory=list)


@dataclass
class BuildReport:
    """Complete build report."""
    success: bool
    mode: str
    total_assets: int
    generated: int
    skipped_unchanged: int
    skipped_publish_gate: int
    errors: List[str]
    output_dir: str
    variants: List[BuildVariantResult] = field(default_factory=list)
    bundle_path: Optional[str] = None
    bundle_valid: bool = False
    build_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to a JSON-serializable dict."""
        return {
            "schema_version": 1,
            "success": self.success,
            "mode": self.mode,
            "total_assets": self.total_assets,
            "generated": self.generated,
            "skipped_unchanged": self.skipped_unchanged,
            "skipped_publish_gate": self.skipped_publish_gate,
            "errors": list(self.errors),
            "output_dir": self.output_dir,
            "variants": [
                {
                    "variant_id": v.variant_id,
                    "design_id": v.design_id,
                    "device_id": v.device_id,
                    "case_type": v.case_type,
                    "assets": [
                        {
                            "path": a.path,
                            "view": a.view,
                            "width": a.width,
                            "height": a.height,
                            "status": a.status,
                            "fingerprint": a.fingerprint,
                            **({"error": a.error} if a.error else {}),
                        }
                        for a in v.assets
                    ],
                }
                for v in self.variants
            ],
            "bundle": {
                "path": self.bundle_path,
                "valid": self.bundle_valid,
            } if self.bundle_path else None,
            "build_duration_seconds": round(self.build_duration_seconds, 3),
        }


class CatalogBuilder:
    """Orchestrates catalog builds.

    Parameters
    ----------
    templates_root : str
        Root directory for case templates.
    designs_root : str
        Directory containing design artwork files. Design IDs map to
        `<design_id>.png` files in this directory.
    device_registry_path : str
        Path to the device registry JSON file.
    """

    def __init__(
        self,
        templates_root: str,
        designs_root: str,
        device_registry_path: str,
    ):
        self._templates_root = Path(templates_root).resolve()
        self._designs_root = Path(designs_root).resolve()
        self._device_registry_path = Path(device_registry_path).resolve()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def build(self, plan: CatalogBuildPlan, out_dir: str) -> BuildReport:
        """Execute a catalog build.

        Parameters
        ----------
        plan : CatalogBuildPlan
            The validated build plan.
        out_dir : str
            Output directory for the build artifacts.

        Returns
        -------
        BuildReport
            Summary of what was generated, skipped, and any errors.
        """
        start_time = time.time()
        out_path = Path(out_dir).resolve()

        # Load previous build state for incremental cache
        prev_state = self._load_build_state(out_path)

        # Build in a temp directory for atomicity
        tmp_dir = Path(tempfile.mkdtemp(prefix="wallmock_catalog_"))
        tmp_assets_dir = tmp_dir / "assets"

        errors: List[str] = []
        variant_results: List[BuildVariantResult] = []
        generated_count = 0
        skipped_unchanged_count = 0
        skipped_publish_count = 0

        try:
            # Process each design x target combination
            for design_id in plan.design_ids:
                design_artwork_path = self._resolve_design_artwork(design_id)
                if design_artwork_path is None:
                    errors.append(
                        f"Design '{design_id}': no artwork found in {self._designs_root}"
                    )
                    continue

                for target in plan.targets:
                    variant_result = self._build_variant(
                        design_id=design_id,
                        design_artwork_path=str(design_artwork_path),
                        target=target,
                        plan=plan,
                        tmp_assets_dir=tmp_assets_dir,
                        prev_state=prev_state,
                    )
                    variant_results.append(variant_result)

                    for asset in variant_result.assets:
                        if asset.status == "generated":
                            generated_count += 1
                        elif asset.status == "skipped_unchanged":
                            skipped_unchanged_count += 1
                        elif asset.status == "skipped_publish_gate":
                            skipped_publish_count += 1

            # Build the contract bundle
            bundle_result = self._build_contract_bundle(
                tmp_dir=tmp_dir,
                variant_results=variant_results,
                plan=plan,
            )
            bundle_valid = bundle_result.get("valid", False)
            if not bundle_valid:
                errors.extend(bundle_result.get("errors", []))

            # Validate the bundle
            val_report = validate_contract_bundle(str(tmp_dir))
            if not val_report.valid:
                errors.extend([f"bundle: {e}" for e in val_report.errors])
            bundle_valid = val_report.valid

            # Compute total assets
            total_assets = sum(
                len(v.assets) for v in variant_results
            )

            # If we have errors, the build failed
            success = len(errors) == 0

            # Finalize: move temp to final output (atomic)
            if success:
                self._finalize_build(tmp_dir, out_path)
                # Save build state for next incremental run
                self._save_build_state(out_path, variant_results, plan)
                bundle_path = str(out_path / "contract_bundle.v1.json")
            else:
                bundle_path = None

            report = BuildReport(
                success=success,
                mode=plan.mode,
                total_assets=total_assets,
                generated=generated_count,
                skipped_unchanged=skipped_unchanged_count,
                skipped_publish_gate=skipped_publish_count,
                errors=errors,
                output_dir=str(out_path),
                variants=variant_results,
                bundle_path=bundle_path,
                bundle_valid=bundle_valid and success,
                build_duration_seconds=time.time() - start_time,
            )
            return report

        finally:
            # Clean up temp directory
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Internal: design artwork resolution
    # -----------------------------------------------------------------------

    def _resolve_design_artwork(self, design_id: str) -> Optional[Path]:
        """Resolve a design ID to its artwork file path.

        Looks for `<design_id>.png` in the designs root directory.
        """
        candidate = self._designs_root / f"{design_id}.png"
        if candidate.exists() and candidate.is_file():
            return candidate
        return None

    # -----------------------------------------------------------------------
    # Internal: variant build
    # -----------------------------------------------------------------------

    def _build_variant(
        self,
        design_id: str,
        design_artwork_path: str,
        target: BuildTarget,
        plan: CatalogBuildPlan,
        tmp_assets_dir: Path,
        prev_state: dict,
    ) -> BuildVariantResult:
        """Build all assets for a single variant (design x device x case_type)."""
        variant_id = build_variant_id(design_id, target.device_id, target.case_type)
        assets: List[BuildAssetResult] = []

        # Load template for each view
        for view in target.views:
            # Find template directory
            tpl_dir_str = find_template_dir(
                str(self._templates_root),
                target.device_id,
                target.case_type,
                view,
            )
            if tpl_dir_str is None:
                for width in target.widths:
                    assets.append(BuildAssetResult(
                        path="",
                        view=view,
                        width=width,
                        height=0,
                        status="error",
                        fingerprint="",
                        error=f"Template not found for {target.device_id}/{target.case_type}/{view}",
                    ))
                continue

            # Load template
            try:
                template = load_case_template(
                    Path(tpl_dir_str) / "template.json"
                )
            except CatalogValidationError as e:
                for width in target.widths:
                    assets.append(BuildAssetResult(
                        path="",
                        view=view,
                        width=width,
                        height=0,
                        status="error",
                        fingerprint="",
                        error=f"Template error: {e}",
                    ))
                continue

            # Publish gate: in publish mode, skip prototype templates
            if plan.mode == "publish" and template.status != TEMPLATE_STATUS_PRODUCTION:
                for width in target.widths:
                    fp = compute_render_fingerprint(
                        design_path=design_artwork_path,
                        template=template,
                        template_dir=tpl_dir_str,
                        view=view,
                        width=width,
                        render_options={
                            "fit_mode": plan.render_options.fit_mode,
                            "zoom": plan.render_options.zoom,
                            "offset_x": plan.render_options.offset_x,
                            "offset_y": plan.render_options.offset_y,
                            "webp_quality": plan.render_options.webp_quality,
                        },
                    )
                    assets.append(BuildAssetResult(
                        path="",
                        view=view,
                        width=width,
                        height=0,
                        status="skipped_publish_gate",
                        fingerprint=fp,
                    ))
                continue

            # Render the master image
            try:
                artwork_img = Image.open(design_artwork_path).convert("RGBA")
            except Exception as e:
                for width in target.widths:
                    assets.append(BuildAssetResult(
                        path="",
                        view=view,
                        width=width,
                        height=0,
                        status="error",
                        fingerprint="",
                        error=f"Failed to load artwork: {e}",
                    ))
                continue

            try:
                master_img = render_case(
                    artwork_img=artwork_img,
                    template=template,
                    template_dir=tpl_dir_str,
                    fit_mode=plan.render_options.fit_mode,
                    zoom=plan.render_options.zoom,
                    offset_x=plan.render_options.offset_x,
                    offset_y=plan.render_options.offset_y,
                )
            except Exception as e:
                for width in target.widths:
                    assets.append(BuildAssetResult(
                        path="",
                        view=view,
                        width=width,
                        height=0,
                        status="error",
                        fingerprint="",
                        error=f"Render failed: {e}",
                    ))
                continue

            # Generate responsive WebP variants
            render_opts_dict = {
                "fit_mode": plan.render_options.fit_mode,
                "zoom": plan.render_options.zoom,
                "offset_x": plan.render_options.offset_x,
                "offset_y": plan.render_options.offset_y,
                "webp_quality": plan.render_options.webp_quality,
            }

            # Normalize widths: cap at master resolution (no upscaling)
            master_width = master_img.width
            # requested_width -> effective_width (capped at master_width)
            width_map = {}
            for width in target.widths:
                effective = min(width, master_width)
                width_map[width] = effective

            # Unique effective widths (what we actually render)
            unique_effective_widths = sorted(set(width_map.values()))

            # Compute fingerprints by effective width
            eff_width_fingerprints = {}
            for eff_w in unique_effective_widths:
                fp = compute_render_fingerprint(
                    design_path=design_artwork_path,
                    template=template,
                    template_dir=tpl_dir_str,
                    view=view,
                    width=eff_w,
                    render_options=render_opts_dict,
                )
                eff_width_fingerprints[eff_w] = fp

            # Map requested widths to fingerprints
            width_fingerprints = {}
            for req_w in target.widths:
                eff_w = width_map[req_w]
                width_fingerprints[req_w] = eff_width_fingerprints[eff_w]

            # Determine which effective widths need rendering vs can be copied from cache
            eff_widths_to_render = set()
            cached_assets = {}  # keyed by requested_width

            for req_width in target.widths:
                eff_width = width_map[req_width]
                fp = width_fingerprints[req_width]
                asset_rel_path = build_asset_path(
                    design_id=design_id,
                    device_id=target.device_id,
                    case_type=target.case_type,
                    view=view,
                    width=eff_width,
                    hash_prefix=fingerprint_prefix(fp),
                )

                # Check incremental cache (keyed by effective width)
                prev_fp = self._get_prev_fingerprint(
                    prev_state, variant_id, view, eff_width
                )
                if prev_fp == fp and self._cached_asset_exists(
                    prev_state, out_dir_path=None,
                    variant_id=variant_id, view=view, width=eff_width,
                    design_id=design_id, device_id=target.device_id,
                    case_type=target.case_type,
                ):
                    # Copy from previous output if it exists
                    prev_out = Path(prev_state.get("_output_dir", ""))
                    if prev_out.exists():
                        prev_asset_path = prev_out / asset_rel_path
                        if prev_asset_path.exists():
                            # Copy cached asset to temp dir
                            dest_path = tmp_assets_dir / design_id / target.device_id / target.case_type
                            dest_path.mkdir(parents=True, exist_ok=True)
                            dest_file = dest_path / prev_asset_path.name
                            if not dest_file.exists():
                                shutil.copy2(str(prev_asset_path), str(dest_file))
                            cached_assets[req_width] = {
                                "path": asset_rel_path,
                                "fingerprint": fp,
                                "width": eff_width,
                                "height": self._get_prev_height(
                                    prev_state, variant_id, view, eff_width
                                ),
                            }
                            continue

                eff_widths_to_render.add(eff_width)

            # Render needed effective widths from master
            if eff_widths_to_render:
                asset_dir = tmp_assets_dir / design_id / target.device_id / target.case_type
                asset_dir.mkdir(parents=True, exist_ok=True)

                base_filename = f"{view}"
                rendered = generate_responsive_webp(
                    master_image=master_img,
                    widths=sorted(eff_widths_to_render),
                    output_dir=str(asset_dir),
                    base_filename=base_filename,
                    quality=plan.render_options.webp_quality,
                )

                # Rename files to include hash prefix (content-addressed)
                rendered_by_eff_width = {}
                for rend in rendered:
                    w = rend["width"]
                    fp = eff_width_fingerprints[w]
                    h12 = fingerprint_prefix(fp)
                    old_name = rend["path"]
                    new_name = f"{view}-w{w}.{h12}.webp"
                    old_path = asset_dir / old_name
                    new_path = asset_dir / new_name
                    if old_path.exists():
                        if new_path.exists():
                            new_path.unlink()
                        old_path.rename(new_path)

                    rel_path = build_asset_path(
                        design_id=design_id,
                        device_id=target.device_id,
                        case_type=target.case_type,
                        view=view,
                        width=w,
                        hash_prefix=h12,
                    )
                    rendered_by_eff_width[w] = {
                        "path": rel_path,
                        "fingerprint": fp,
                        "width": w,
                        "height": rend["height"],
                        "rendered": True,
                    }

                # Map rendered effective widths back to requested widths
                for req_width in target.widths:
                    if req_width in cached_assets:
                        continue  # already from cache
                    eff_width = width_map[req_width]
                    if eff_width in rendered_by_eff_width:
                        cached_assets[req_width] = rendered_by_eff_width[eff_width]

            # Build asset results
            for width in target.widths:
                fp = width_fingerprints[width]
                asset_info = cached_assets.get(width)

                if asset_info is None:
                    assets.append(BuildAssetResult(
                        path="",
                        view=view,
                        width=width,
                        height=0,
                        status="error",
                        fingerprint=fp,
                        error="Asset generation failed",
                    ))
                    continue

                was_rendered = asset_info.get("rendered", False)
                eff_w = asset_info["width"]
                was_cached = not was_rendered and self._get_prev_fingerprint(
                    prev_state, variant_id, view, eff_w
                ) == fp

                if was_cached:
                    status = "skipped_unchanged"
                else:
                    status = "generated"

                assets.append(BuildAssetResult(
                    path=asset_info["path"],
                    view=view,
                    width=asset_info["width"],
                    height=asset_info.get("height", 0),
                    status=status,
                    fingerprint=fp,
                ))

        # Determine template_id and template_status from first view's template
        template_id = ""
        template_status = TEMPLATE_STATUS_PROTOTYPE
        if target.views:
            tpl_dir_str = find_template_dir(
                str(self._templates_root),
                target.device_id,
                target.case_type,
                target.views[0],
            )
            if tpl_dir_str:
                try:
                    tpl = load_case_template(Path(tpl_dir_str) / "template.json")
                    template_id = tpl.id
                    template_status = tpl.status
                except CatalogValidationError:
                    pass

        return BuildVariantResult(
            variant_id=variant_id,
            design_id=design_id,
            device_id=target.device_id,
            case_type=target.case_type,
            template_id=template_id,
            template_status=template_status,
            assets=assets,
        )

    # -----------------------------------------------------------------------
    # Internal: build state (incremental cache)
    # -----------------------------------------------------------------------

    def _load_build_state(self, out_dir: Path) -> dict:
        """Load the previous build state for incremental caching."""
        state_path = out_dir / BUILD_STATE_FILENAME
        if not state_path.exists():
            return {}
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            state["_output_dir"] = str(out_dir)
            return state
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_build_state(
        self,
        out_dir: Path,
        variant_results: List[BuildVariantResult],
        plan: CatalogBuildPlan,
    ):
        """Save build state for future incremental runs."""
        state = {
            "schema_version": BUILD_STATE_VERSION,
            "mode": plan.mode,
            "renderer_version": RENDERER_VERSION,
            "variants": {},
        }

        for v in variant_results:
            state["variants"][v.variant_id] = {
                "design_id": v.design_id,
                "device_id": v.device_id,
                "case_id": v.case_type,
                "template_id": v.template_id,
                "template_status": v.template_status,
                "assets": {},
            }
            for a in v.assets:
                state["variants"][v.variant_id]["assets"][f"{a.view}-w{a.width}"] = {
                    "fingerprint": a.fingerprint,
                    "path": a.path,
                    "status": a.status,
                    "height": a.height,
                }

        state_path = out_dir / BUILD_STATE_FILENAME
        write_json_deterministic(str(state_path), state)

    def _get_prev_fingerprint(
        self, state: dict, variant_id: str, view: str, width: int,
    ) -> Optional[str]:
        """Get the cached fingerprint for an asset from previous build."""
        variants = state.get("variants", {})
        variant = variants.get(variant_id, {})
        assets = variant.get("assets", {})
        asset = assets.get(f"{view}-w{width}", {})
        return asset.get("fingerprint")

    def _get_prev_height(
        self, state: dict, variant_id: str, view: str, width: int,
    ) -> int:
        """Get the cached height for an asset from previous build."""
        variants = state.get("variants", {})
        variant = variants.get(variant_id, {})
        assets = variant.get("assets", {})
        asset = assets.get(f"{view}-w{width}", {})
        return asset.get("height", 0) or 0

    def _cached_asset_exists(
        self, state: dict, out_dir_path, variant_id: str, view: str, width: int,
        design_id: str, device_id: str, case_type: str,
    ) -> bool:
        """Check if a cached asset file exists from previous build."""
        variants = state.get("variants", {})
        variant = variants.get(variant_id, {})
        assets = variant.get("assets", {})
        asset = assets.get(f"{view}-w{width}", {})
        path = asset.get("path", "")
        if not path:
            return False

        prev_out = Path(state.get("_output_dir", ""))
        if not prev_out.exists():
            return False

        asset_path = prev_out / path
        return asset_path.exists() and asset_path.is_file()

    # -----------------------------------------------------------------------
    # Internal: contract bundle
    # -----------------------------------------------------------------------

    def _build_contract_bundle(
        self,
        tmp_dir: Path,
        variant_results: List[BuildVariantResult],
        plan: CatalogBuildPlan,
    ) -> dict:
        """Build the Contract v1 bundle from rendered assets."""
        result = {"valid": False, "errors": []}

        try:
            # Load device registry
            dev_reg = load_device_registry(str(self._device_registry_path))
            device_registry_data = {
                "contract": dev_reg["contract"],
                "contract_version": dev_reg["contract_version"],
                "devices": [
                    {
                        "device_id": d.device_id,
                        "brand": d.brand,
                        "family": d.family,
                        "display_name": d.display_name,
                        "generation": d.generation,
                        "aliases": d.aliases,
                        "sort_order": d.sort_order,
                        "active_identity": d.active_identity,
                    }
                    for d in dev_reg["devices"]
                ],
            }
            write_json_deterministic(
                str(tmp_dir / "device_registry.v1.json"),
                device_registry_data,
            )

            # Build render capabilities
            render_caps = build_render_capabilities(
                templates_root=str(self._templates_root),
            )
            write_json_deterministic(
                str(tmp_dir / "render_capabilities.v1.json"),
                render_caps,
            )

            # Build render manifest from actual outputs
            manifest_entries = []
            for v in variant_results:
                # Group assets by view
                views_dict: Dict[str, Dict[int, Dict]] = {}
                for a in v.assets:
                    if a.status in ("generated", "skipped_unchanged") and a.path:
                        if a.view not in views_dict:
                            views_dict[a.view] = {}

                        # Compute content hash from the actual file
                        asset_full_path = tmp_dir / a.path
                        content_hash = ""
                        if asset_full_path.exists():
                            sha = sha256_file(str(asset_full_path))
                            content_hash = build_content_hash(sha)

                        views_dict[a.view][a.width] = {
                            "path": a.path,
                            "width": a.width,
                            "height": a.height,
                            "format": "webp",
                            "content_hash": content_hash,
                            "renderer_version": RENDERER_VERSION,
                        }

                if views_dict:
                    entry = build_render_manifest_entry(
                        design_id=v.design_id,
                        device_id=v.device_id,
                        case_type=v.case_type,
                        template_id=v.template_id,
                        template_status=v.template_status,
                        views=views_dict,
                    )
                    manifest_entries.append(entry)

            render_manifest = build_render_manifest(
                variants=manifest_entries,
                renderer_version=RENDERER_VERSION,
            )
            write_json_deterministic(
                str(tmp_dir / "render_manifest.v1.json"),
                render_manifest,
            )

            # Build the bundle index
            bundle = build_contract_bundle(
                device_registry_data=device_registry_data,
                render_capabilities_data=render_caps,
                render_manifest_data=render_manifest,
                renderer_version=RENDERER_VERSION,
            )
            write_json_deterministic(
                str(tmp_dir / "contract_bundle.v1.json"),
                bundle,
            )

            # Recompute hashes from actual written files (for accuracy)
            artifacts = {}
            for fname in [
                "device_registry.v1.json",
                "render_capabilities.v1.json",
                "render_manifest.v1.json",
            ]:
                fpath = tmp_dir / fname
                if fpath.exists():
                    artifacts[fname] = {
                        "filename": fname,
                        "sha256": sha256_file(str(fpath)),
                    }
            bundle["artifacts"] = artifacts
            write_json_deterministic(
                str(tmp_dir / "contract_bundle.v1.json"),
                bundle,
            )

            result["valid"] = True

        except Exception as e:
            result["errors"].append(f"Bundle build failed: {e}")

        return result

    # -----------------------------------------------------------------------
    # Internal: finalization (atomic move)
    # -----------------------------------------------------------------------

    def _finalize_build(self, tmp_dir: Path, out_dir: Path):
        """Move the temp build directory to the final output location.

        This is done atomically: remove old output, then rename.
        On Windows, we can't do a true atomic rename over an existing
        directory, so we remove-then-rename.
        """
        # If output directory exists, remove it first
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)

        # Ensure parent exists
        out_dir.parent.mkdir(parents=True, exist_ok=True)

        # Move temp dir to final location
        shutil.move(str(tmp_dir), str(out_dir))
