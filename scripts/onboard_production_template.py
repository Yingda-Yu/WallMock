"""
Production template onboarding / prototype→production promotion tool.

Takes a validated supplier geometry package and promotes the target
template from prototype to production status.

Workflow:
  1. Validate the supplier geometry package
  2. Reject test fixtures (programmatically allowable for tests only)
  3. Load the existing prototype template
  4. Verify template_id matches the package target
  5. Create a staging temp dir with existing template + new layers + new template.json
  6. Validate staged template via load_case_template()
  7. If valid: atomically move staging into place (backup → replace → delete backup)
  8. If any failure: delete staging, restore from backup if needed

Promotion is idempotent: promoting an already-production template with
the same package_id and revision is a no-op.

Usage:
    python scripts/onboard_production_template.py <package_dir> [options]

Options:
    --templates-root PATH   Root directory for case templates
                            (default: assets/case_templates)
    --dry-run               Show what would happen without making changes
    --json                  Output result as JSON

Exit codes:
    0 — success (promoted or already at target state)
    1 — error (validation failure, template not found, etc.)
"""

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# Add project root to path for imports
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
sys.path.insert(0, str(_project_root))

from core.case_template_loader import load_case_template
from core.catalog_models import (
    CatalogValidationError,
    TEMPLATE_STATUS_PRODUCTION,
    TEMPLATE_STATUS_PROTOTYPE,
)
from core.catalog_build_plan import find_template_dir
from core.supplier_geometry import (
    contract_to_filesystem_case_type,
    is_test_fixture_package,
    validate_supplier_geometry_package,
    SupplierGeometryPackage,
)


# Path to canonical templates root (for fixture-into-canonical protection).
_CANONICAL_TEMPLATES_ROOT = _project_root / "assets" / "case_templates"

# Source types that carry device dimension verification evidence.
# dieline and cad_export come from engineering-grade files that encode
# actual device dimensions. measured/normalized_export/psd_export provide
# case geometry but do NOT independently verify device dimensions.
_DEVICE_DIMENSION_VERIFYING_SOURCES = frozenset({"dieline", "cad_export"})

# Source types that provide accurate device anchor positions.
_DEVICE_ANCHOR_VERIFYING_SOURCES = frozenset({"dieline", "cad_export"})


# ---------------------------------------------------------------------------
# Core promotion logic (importable for testing)
# ---------------------------------------------------------------------------

@dataclass
class PromotionResult:
    """Result of a template promotion operation."""
    template_id: str
    old_status: str
    new_status: str
    package_id: str
    revision: str
    template_dir: str
    success: bool
    skipped: bool = False
    skip_reason: str = ""
    errors: list = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "template_id": self.template_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "package_id": self.package_id,
            "revision": self.revision,
            "template_dir": self.template_dir,
            "success": self.success,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "errors": self.errors,
        }


def _is_canonical_templates_root(templates_root: str) -> bool:
    """Return True if templates_root resolves to the canonical assets/case_templates.

    Used to prevent fixture promotion from ever touching canonical templates,
    even when allow_fixture=True is passed programmatically.
    """
    try:
        root_resolved = Path(templates_root).resolve()
        canonical_resolved = _CANONICAL_TEMPLATES_ROOT.resolve()
        # Check if templates_root is under the canonical directory
        # (same directory or a subdirectory of it)
        try:
            root_resolved.relative_to(canonical_resolved)
            return True
        except ValueError:
            return False
    except Exception:
        return False


def promote_template(
    package_dir: str,
    *,
    templates_root: Optional[str] = None,
    allow_fixture: bool = False,
    dry_run: bool = False,
) -> PromotionResult:
    """Promote a prototype template to production using a supplier package.

    Parameters
    ----------
    package_dir : str
        Path to the supplier geometry package directory.
    templates_root : str, optional
        Root directory for case templates. Defaults to
        assets/case_templates relative to project root.
    allow_fixture : bool
        If True, allow test/fixture packages to promote templates.
        INTERNAL USE ONLY — not exposed on CLI. Even when True,
        fixture promotion into the canonical assets/case_templates
        root is always rejected.
    dry_run : bool
        If True, simulate the promotion without making any changes.

    Returns
    -------
    PromotionResult
        Result of the promotion operation.
    """
    if templates_root is None:
        templates_root = str(_project_root / "assets" / "case_templates")

    # Step 1: Validate the supplier package
    validation = validate_supplier_geometry_package(package_dir)
    if not validation.valid or validation.package is None:
        return PromotionResult(
            template_id="",
            old_status="",
            new_status="",
            package_id="",
            revision="",
            template_dir="",
            success=False,
            errors=list(validation.errors),
        )

    pkg = validation.package

    # Step 2: Reject test fixtures unless allowed
    if is_test_fixture_package(pkg.package_id) and not allow_fixture:
        return PromotionResult(
            template_id=pkg.target_template_id,
            old_status="",
            new_status="",
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir="",
            success=False,
            errors=[
                f"Refusing to promote with test/fixture package "
                f"'{pkg.package_id}'. Test fixtures must NOT be used "
                f"for real production templates."
            ],
        )

    # Step 2b: Even with allow_fixture=True, NEVER promote fixtures
    # into the canonical assets/case_templates root.
    if is_test_fixture_package(pkg.package_id) and _is_canonical_templates_root(templates_root):
        return PromotionResult(
            template_id=pkg.target_template_id,
            old_status="",
            new_status="",
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir="",
            success=False,
            errors=[
                f"Refusing to promote test/fixture package '{pkg.package_id}' "
                f"into the canonical templates root "
                f"({_CANONICAL_TEMPLATES_ROOT}). Fixture promotion is "
                f"only allowed in non-canonical test directories."
            ],
        )

    # Step 3: Find and load the existing template
    # Parse target_template_id to get components
    from core.contract_ids import parse_template_id
    try:
        device_id, case_type_contract, view = parse_template_id(
            pkg.target_template_id
        )
    except ValueError as e:
        return PromotionResult(
            template_id=pkg.target_template_id,
            old_status="",
            new_status="",
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir="",
            success=False,
            errors=[f"Invalid target_template_id: {e}"],
        )

    # Map contract case_type to filesystem directory name
    # (e.g. "clear" → "transparent" for directory lookup only)
    case_type_filesystem = contract_to_filesystem_case_type(case_type_contract)

    # Find the template directory
    tpl_dir_str = find_template_dir(
        templates_root, device_id, case_type_filesystem, view
    )
    if tpl_dir_str is None:
        return PromotionResult(
            template_id=pkg.target_template_id,
            old_status="",
            new_status="",
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir="",
            success=False,
            errors=[
                f"Template not found for device='{device_id}', "
                f"case_type='{case_type_filesystem}', view='{view}' "
                f"under {templates_root}"
            ],
        )

    tpl_dir = Path(tpl_dir_str)
    tpl_json_path = tpl_dir / "template.json"

    try:
        template = load_case_template(str(tpl_json_path))
    except CatalogValidationError as e:
        return PromotionResult(
            template_id=pkg.target_template_id,
            old_status="",
            new_status="",
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir=str(tpl_dir),
            success=False,
            errors=[f"Failed to load existing template: {e}"],
        )

    old_status = template.status

    # Step 4: Verify template_id matches
    if template.id != pkg.target_template_id:
        return PromotionResult(
            template_id=template.id,
            old_status=old_status,
            new_status=old_status,
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir=str(tpl_dir),
            success=False,
            errors=[
                f"Template ID mismatch: package targets "
                f"'{pkg.target_template_id}' but found template "
                f"'{template.id}' at {tpl_dir}"
            ],
        )

    # Idempotency: already production with same package?
    supplier_geometry_ref = f"{pkg.package_id}@{pkg.revision}"
    if (
        old_status == TEMPLATE_STATUS_PRODUCTION
        and template.provenance is not None
        and template.provenance.supplier_geometry == supplier_geometry_ref
    ):
        return PromotionResult(
            template_id=template.id,
            old_status=TEMPLATE_STATUS_PRODUCTION,
            new_status=TEMPLATE_STATUS_PRODUCTION,
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir=str(tpl_dir),
            success=True,
            skipped=True,
            skip_reason="Already at production with same supplier package",
        )

    # Step 5: Perform the promotion (atomic with staging + backup)
    if dry_run:
        return PromotionResult(
            template_id=template.id,
            old_status=old_status,
            new_status=TEMPLATE_STATUS_PRODUCTION,
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir=str(tpl_dir),
            success=True,
            skipped=True,
            skip_reason="Dry run — no changes made",
        )

    try:
        _do_promote_atomic(tpl_dir, template, pkg)
    except Exception as e:
        return PromotionResult(
            template_id=template.id,
            old_status=old_status,
            new_status=old_status,
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir=str(tpl_dir),
            success=False,
            errors=[f"Promotion failed: {e}"],
        )

    # Step 6: Validate the promoted template
    try:
        promoted = load_case_template(str(tpl_json_path))
        if promoted.status != TEMPLATE_STATUS_PRODUCTION:
            return PromotionResult(
                template_id=template.id,
                old_status=old_status,
                new_status=promoted.status,
                package_id=pkg.package_id,
                revision=pkg.revision,
                template_dir=str(tpl_dir),
                success=False,
                errors=["Promoted template does not have status='production'"],
            )
    except CatalogValidationError as e:
        return PromotionResult(
            template_id=template.id,
            old_status=old_status,
            new_status=old_status,
            package_id=pkg.package_id,
            revision=pkg.revision,
            template_dir=str(tpl_dir),
            success=False,
            errors=[f"Promoted template failed validation: {e}"],
        )

    return PromotionResult(
        template_id=template.id,
        old_status=old_status,
        new_status=TEMPLATE_STATUS_PRODUCTION,
        package_id=pkg.package_id,
        revision=pkg.revision,
        template_dir=str(tpl_dir),
        success=True,
    )


def _do_promote_atomic(
    tpl_dir: Path,
    template,
    pkg: SupplierGeometryPackage,
):
    """Perform atomic promotion using staging + backup pattern.

    Steps:
    1. Create a staging temp directory
    2. Copy existing template into staging
    3. Apply promotion changes (layers + template.json) to staging
    4. Validate staged template via load_case_template()
    5. If valid: backup original → move staging into place → delete backup
    6. If ANY failure: delete staging, restore from backup if needed

    The original template directory bytes are unchanged on any failure.
    """
    import json as _json
    import tempfile as _tempfile

    parent_dir = tpl_dir.parent

    # --- Step 1: Create staging directory ---
    staging_dir = Path(_tempfile.mkdtemp(
        prefix=".promote_staging_",
        dir=str(parent_dir),
    ))

    backup_dir = None

    try:
        # --- Step 2: Copy existing template into staging ---
        shutil.copytree(str(tpl_dir), str(staging_dir / tpl_dir.name), dirs_exist_ok=True)
        staging_tpl_dir = staging_dir / tpl_dir.name
        staging_tpl_json = staging_tpl_dir / "template.json"

        # --- Step 3: Apply promotion changes to staging ---
        _apply_promotion_changes(staging_tpl_dir, template, pkg)

        # --- Step 4: Validate staged template ---
        try:
            load_case_template(str(staging_tpl_json))
        except CatalogValidationError as e:
            raise ValueError(
                f"Staged template failed validation: {e}"
            )

        # --- Step 5: Backup original, then replace with staged ---
        backup_dir = Path(_tempfile.mkdtemp(
            prefix=".promote_backup_",
            dir=str(parent_dir),
        ))

        # Move original to backup
        backup_tpl_dir = backup_dir / tpl_dir.name
        shutil.move(str(tpl_dir), str(backup_tpl_dir))

        try:
            # Move staged template into place
            shutil.move(str(staging_tpl_dir), str(tpl_dir))
        except Exception:
            # Restore from backup on failure
            if backup_tpl_dir.exists():
                shutil.move(str(backup_tpl_dir), str(tpl_dir))
            raise

    finally:
        # Clean up staging dir (always)
        if staging_dir.exists():
            shutil.rmtree(str(staging_dir), ignore_errors=True)

        # Clean up backup dir (on success, or after restore on failure)
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(str(backup_dir), ignore_errors=True)


def _apply_promotion_changes(
    tpl_dir: Path,
    template,
    pkg: SupplierGeometryPackage,
):
    """Apply promotion changes to a template directory.

    Modifies files in-place. Caller is responsible for atomicity
    (this function should only be called on a staging copy).

    Changes:
    - Copy normalized layers from the supplier package
    - Update template.json with:
      - status=production
      - canvas/print_region/camera_region from supplier normalized_geometry
      - provenance with supplier_geometry reference and appropriately
        updated verified/estimated/assumed fields
    """
    import json as _json

    pkg_dir = Path(pkg.package_dir)
    normalized_dir = pkg_dir / "normalized"

    # Copy normalized layers into the template directory
    # Map role -> filename from package normalized_layers
    layer_files = {}
    for nl in pkg.normalized_layers:
        role = nl["role"]
        fname = nl["file"]
        layer_files[role] = fname

    # Copy each layer file, using the role-based expected filename
    # (base.png, print_mask.png, overlay.png, highlight.png, shadow.png)
    for role, src_fname in layer_files.items():
        src_path = normalized_dir / src_fname
        # Destination uses the standard role-based filename
        dst_fname = f"{role}.png"
        dst_path = tpl_dir / dst_fname
        shutil.copy2(str(src_path), str(dst_path))

    # Update template.json
    tpl_json_path = tpl_dir / "template.json"
    with open(tpl_json_path, "r", encoding="utf-8") as f:
        tpl_data = _json.load(f)

    # Update status to production
    tpl_data["status"] = TEMPLATE_STATUS_PRODUCTION

    # Update canvas, print_region, and camera_region from supplier package
    # (BLOCKER 2: geometry comes from the supplier, not the prototype)
    norm_geom = pkg.normalized_geometry
    tpl_data["canvas"] = {
        "width": norm_geom.canvas_width,
        "height": norm_geom.canvas_height,
    }

    # Preserve existing print_region mode, fit, and mask settings
    # but update x, y, width, height from supplier geometry
    existing_pr = tpl_data.get("print_region", {})
    tpl_data["print_region"] = {
        "mode": existing_pr.get("mode", "mask"),
        "x": norm_geom.print_region_x,
        "y": norm_geom.print_region_y,
        "width": norm_geom.print_region_width,
        "height": norm_geom.print_region_height,
        "fit": existing_pr.get("fit", "cover"),
        "mask": existing_pr.get("mask", "print_mask.png"),
    }

    # Update camera_region from supplier geometry (if present)
    if norm_geom.camera_region is not None:
        cr = norm_geom.camera_region
        tpl_data["camera_region"] = {
            "x": cr["x"],
            "y": cr["y"],
            "w": cr["width"],
            "h": cr["height"],
        }
    elif "camera_region" in tpl_data:
        # Remove camera_region if supplier doesn't provide one
        del tpl_data["camera_region"]

    # Update provenance (BLOCKER 6: accurate provenance claims)
    supplier_geometry_ref = f"{pkg.package_id}@{pkg.revision}"

    existing_provenance = tpl_data.get("provenance") or {}
    existing_verified = existing_provenance.get(
        "verified_device_dimensions", ""
    )
    existing_anchors = existing_provenance.get(
        "estimated_device_anchors", ""
    )

    # Determine what the supplier package actually verifies:
    # - dieline/cad_export: can verify device dimensions and anchors
    # - measured/normalized_export/psd_export: case geometry only,
    #   device dimensions remain from prototype source
    source_type = pkg.source_type
    verifies_device_dims = source_type in _DEVICE_DIMENSION_VERIFYING_SOURCES
    verifies_device_anchors = source_type in _DEVICE_ANCHOR_VERIFYING_SOURCES

    # verified_device_dimensions:
    # - Only claim supplier-verified if source actually verifies device dims
    # - Otherwise preserve the existing verified_device_dimensions text
    if verifies_device_dims:
        verified_device_dimensions = (
            f"Supplier-verified via {pkg.supplier_id} ({pkg.supplier_reference})"
        )
    else:
        # Preserve existing official device-dimension provenance
        # (e.g. from manufacturer spec pages). The supplier package
        # provides case geometry but does not independently verify
        # device dimensions.
        verified_device_dimensions = existing_verified

    # estimated_device_anchors:
    # - If supplier provides accurate anchors (dieline/cad), update
    # - Otherwise keep existing estimation
    if verifies_device_anchors:
        estimated_device_anchors = (
            f"Supplier-accurate from {source_type} ({pkg.supplier_id})"
        )
    else:
        # Keep existing estimated anchors from prototype
        estimated_device_anchors = existing_anchors

    # assumed_case_parameters:
    # - Always update to reflect supplier-provided case geometry
    assumed_case_parameters = (
        f"Supplier-provided — {source_type} ({pkg.supplier_id})"
    )

    tpl_data["provenance"] = {
        "verified_device_dimensions": verified_device_dimensions,
        "estimated_device_anchors": estimated_device_anchors,
        "assumed_case_parameters": assumed_case_parameters,
        "supplier_geometry": supplier_geometry_ref,
    }

    # Write updated template.json
    with open(tpl_json_path, "w", encoding="utf-8") as f:
        _json.dump(tpl_data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Promote a prototype case template to production using "
                    "a validated supplier geometry package."
    )
    parser.add_argument(
        "package_dir",
        help="Path to the supplier geometry package directory.",
    )
    parser.add_argument(
        "--templates-root",
        default=None,
        help="Root directory for case templates (default: assets/case_templates).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON.",
    )
    args = parser.parse_args()

    result = promote_template(
        args.package_dir,
        templates_root=args.templates_root,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"Package:    {result.package_id}@{result.revision}")
        print(f"Template:   {result.template_id}")
        print(f"Directory:  {result.template_dir}")
        print(f"Status:     {result.old_status} → {result.new_status}")
        print()

        if result.success:
            if result.skipped:
                print(f"SKIPPED: {result.skip_reason}")
            else:
                print("SUCCESS: Template promoted to production.")
        else:
            print("FAILED:")
            for err in result.errors:
                print(f"  - {err}")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
