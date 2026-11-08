"""
Supplier geometry package validation for WallMock production templates.

A supplier geometry package is a self-contained directory containing:
  - package.json — manifest with metadata, hashes, and layer descriptions
  - source/ — original supplier files (dieline, PSD, CAD, etc.)
  - normalized/ — PNG layers normalized to template dimensions

This module validates that a package is complete, internally consistent,
and safe to use for promoting a template from prototype to production.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PIL import Image

from .catalog_models import (
    CatalogValidationError,
    is_production_grade_supplier_geometry,
)
from .contract_ids import (
    CASE_TYPES_V1 as CONTRACT_CASE_TYPES,
    is_valid_component_id,
    parse_template_id,
)
from .device_registry_loader import load_device_registry


# Path to the canonical device registry (relative to project root).
_BASE_DIR = Path(__file__).resolve().parent.parent
_DEVICE_REGISTRY_PATH = _BASE_DIR / "catalog" / "device_registry.v1.json"

# Mapping from Contract v1 case_type tokens to filesystem directory names.
# The package domain identity always uses Contract v1 tokens (e.g. "clear"),
# but template directories on disk use internal names (e.g. "transparent").
_CONTRACT_TO_FILESYSTEM_CASE_TYPE = {
    "clear": "transparent",
}

# Filesystem case type tokens (internal directory names).
_FILESYSTEM_CASE_TYPES = {"hard", "tough", "magsafe", "transparent", "soft"}

# Normalized layer roles that must all share the same dimensions.
_NORMALIZED_LAYER_ROLES = {"base", "print_mask", "overlay", "highlight", "shadow"}

# Roles required for hard case type (base, print_mask, overlay are essential).
_HARD_CASE_REQUIRED_ROLES = {"base", "print_mask", "overlay"}

# Sentinel values for verified_by that indicate no real review happened.
_REVIEW_SENTINELS = frozenset({
    "none",
    "n/a",
    "na",
    "unknown",
    "tbd",
    "tbc",
    "pending",
    "provisional",
    "placeholder",
    "not reviewed",
    "unreviewed",
    "auto",
    "automatic",
    "bot",
    "ci",
    "system",
    "test",
    "fixture",
})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedGeometry:
    """Normalized geometry metadata from a supplier package.

    Attributes
    ----------
    canvas_width : int
        Pixel width of normalized layers.
    canvas_height : int
        Pixel height of normalized layers.
    canvas_units : str
        Units of canvas dimensions (always "px").
    print_region_x : int
        X offset of printable area within canvas.
    print_region_y : int
        Y offset of printable area within canvas.
    print_region_width : int
        Width of printable area.
    print_region_height : int
        Height of printable area.
    camera_region : dict or None
        Optional camera/module exclusion area {x, y, width, height}.
    """
    canvas_width: int
    canvas_height: int
    canvas_units: str
    print_region_x: int
    print_region_y: int
    print_region_width: int
    print_region_height: int
    camera_region: Optional[dict] = None


@dataclass(frozen=True)
class SupplierGeometryPackage:
    """A validated supplier geometry package.

    Attributes
    ----------
    package_dir : str
        Absolute path to the package directory.
    package_id : str
        Unique identifier for this geometry package.
    supplier_id : str
        Supplier identifier.
    supplier_reference : str
        Supplier's SKU or file reference.
    device_id : str
        Device ID from the device registry.
    case_type : str
        Case type token (Contract v1: hard, tough, magsafe, clear, soft).
    revision : str
        Revision of this geometry package.
    target_template_id : str
        Template ID this package targets (device_id__case_type__view).
    reviewed : bool
        Whether an owner has reviewed this package.
    verified_by : str
        Owner who reviewed the package.
    source_type : str
        Type of source geometry.
    normalized_geometry : NormalizedGeometry
        Normalized geometry metadata (canvas, print_region, camera_region).
    normalized_layers : list of dict
        List of normalized layer descriptors (name, file, sha256, role).
    """
    package_dir: str
    package_id: str
    supplier_id: str
    supplier_reference: str
    device_id: str
    case_type: str
    revision: str
    target_template_id: str
    reviewed: bool
    verified_by: str
    source_type: str
    normalized_geometry: NormalizedGeometry
    normalized_layers: list = field(default_factory=list)


@dataclass
class SupplierGeometryValidationResult:
    """Result of validating a supplier geometry package.

    Attributes
    ----------
    valid : bool
        True if the package passes all validation checks.
    errors : list of str
        List of error messages (empty if valid).
    warnings : list of str
        List of warning messages (non-fatal issues).
    package : SupplierGeometryPackage or None
        The parsed package object, if parsing succeeded far enough.
    """
    valid: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    package: Optional[SupplierGeometryPackage] = None

    def error(self, msg: str):
        """Add an error message."""
        self.errors.append(msg)
        self.valid = False

    def warning(self, msg: str):
        """Add a warning message."""
        self.warnings.append(msg)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_test_fixture_package(package_id: str) -> bool:
    """Return True if ``package_id`` identifies a test fixture.

    Test fixture packages have IDs starting with ``test-`` or ``fixture-``.
    They are never suitable for real production promotion.
    """
    if not isinstance(package_id, str):
        return False
    return (
        package_id.startswith("test-")
        or package_id.startswith("fixture-")
    )


def contract_to_filesystem_case_type(contract_case: str) -> str:
    """Convert a Contract v1 case_type token to filesystem directory name.

    The package's domain identity is always the Contract v1 token
    (e.g. "clear"), but template directories on disk use internal
    names (e.g. "transparent"). This mapping is for filesystem path
    lookup only.
    """
    return _CONTRACT_TO_FILESYSTEM_CASE_TYPE.get(contract_case, contract_case)


def validate_supplier_geometry_package(
    package_dir: str,
    *,
    device_registry_path: Optional[str] = None,
) -> SupplierGeometryValidationResult:
    """Validate a supplier geometry package directory.

    Runs all validation checks and returns a result object with
    errors, warnings, and (if successful) the parsed package.

    Parameters
    ----------
    package_dir : str
        Path to the supplier geometry package directory.
    device_registry_path : str, optional
        Path to the device registry JSON file. Defaults to the canonical
        registry in catalog/device_registry.v1.json.

    Returns
    -------
    SupplierGeometryValidationResult
        Validation result with errors, warnings, and parsed package.
    """
    result = SupplierGeometryValidationResult(valid=True)
    pkg_dir = Path(package_dir).resolve()

    # --- Check a: package.json exists and is valid JSON ---
    pkg_json_path = pkg_dir / "package.json"
    if not pkg_json_path.exists():
        result.error(f"package.json not found: {pkg_json_path}")
        return result

    try:
        with open(pkg_json_path, "r", encoding="utf-8") as f:
            pkg_data = json.load(f)
    except json.JSONDecodeError as e:
        result.error(f"package.json: invalid JSON: {e}")
        return result

    if not isinstance(pkg_data, dict):
        result.error("package.json: root must be a JSON object")
        return result

    # --- Check b: schema validation (required fields, types) ---
    _validate_package_schema(pkg_data, pkg_json_path, result)
    if not result.valid:
        return result

    package_id = pkg_data["package_id"]
    device_id = pkg_data["device_id"]
    case_type = pkg_data["case_type"]
    target_template_id = pkg_data["target_template_id"]
    reviewed = pkg_data["reviewed"]
    verified_by = pkg_data["verified_by"]
    source_files = pkg_data["source_files"]
    normalized_geometry_data = pkg_data["normalized_geometry"]
    normalized_layers = pkg_data["normalized_layers"]

    # --- Check c: device_id exists in device registry ---
    if device_registry_path is None:
        device_registry_path = str(_DEVICE_REGISTRY_PATH)

    try:
        reg = load_device_registry(device_registry_path)
        device_map = reg["device_map"]
    except (CatalogValidationError, OSError) as e:
        result.error(f"Failed to load device registry: {e}")
        return result

    if device_id not in device_map:
        result.error(
            f"device_id '{device_id}' not found in device registry"
        )

    # --- Check d: case_type is valid Contract v1 case type token ---
    if case_type not in CONTRACT_CASE_TYPES:
        result.error(
            f"case_type '{case_type}' is not a valid Contract v1 token. "
            f"Expected one of {sorted(CONTRACT_CASE_TYPES)}"
        )

    # --- Check e: target_template_id matches device_id__case_type__view grammar ---
    try:
        tpl_device, tpl_case, tpl_view = parse_template_id(target_template_id)
        if tpl_device != device_id:
            result.error(
                f"target_template_id '{target_template_id}': device component "
                f"'{tpl_device}' does not match package device_id '{device_id}'"
            )
        if tpl_case != case_type:
            result.error(
                f"target_template_id '{target_template_id}': case_type component "
                f"'{tpl_case}' does not match package case_type '{case_type}'"
            )
    except ValueError as e:
        result.error(f"target_template_id: {e}")
        tpl_view = None

    # --- Check f: normalized_geometry is valid ---
    norm_geom = _validate_normalized_geometry(
        normalized_geometry_data, pkg_json_path, result
    )

    # --- Check g (early): no path traversal in file references ---
    # Source files
    for i, sf in enumerate(source_files):
        name = sf.get("name", "")
        if _is_path_traversal(name):
            result.error(
                f"source_files[{i}].name: '{name}' contains path traversal"
            )

    # Normalized layers
    for i, nl in enumerate(normalized_layers):
        fname = nl.get("file", "")
        if _is_path_traversal(fname):
            result.error(
                f"normalized_layers[{i}].file: '{fname}' contains path traversal"
            )

    if not result.valid:
        # Don't proceed to file checks if there are fundamental errors
        pass

    # --- Check h: all source_files exist in source/ and hashes match ---
    source_dir = pkg_dir / "source"
    for i, sf in enumerate(source_files):
        name = sf.get("name", "")
        expected_sha = sf.get("sha256", "")
        file_path = source_dir / name

        if not file_path.exists():
            result.error(
                f"source_files[{i}]: file 'source/{name}' not found"
            )
            continue

        actual_sha = _sha256_file(str(file_path))
        if actual_sha != expected_sha:
            result.error(
                f"source_files[{i}]: SHA-256 mismatch for 'source/{name}'. "
                f"Expected {expected_sha}, got {actual_sha}"
            )

    # --- Check i: all normalized_layers exist in normalized/ and hashes match ---
    normalized_dir = pkg_dir / "normalized"
    layer_images = {}  # role -> (file_path, image)

    for i, nl in enumerate(normalized_layers):
        fname = nl.get("file", "")
        expected_sha = nl.get("sha256", "")
        role = nl.get("role", "")
        file_path = normalized_dir / fname

        if not file_path.exists():
            result.error(
                f"normalized_layers[{i}]: file 'normalized/{fname}' not found"
            )
            continue

        actual_sha = _sha256_file(str(file_path))
        if actual_sha != expected_sha:
            result.error(
                f"normalized_layers[{i}]: SHA-256 mismatch for "
                f"'normalized/{fname}'. Expected {expected_sha}, got {actual_sha}"
            )
            continue

        # Load the image for later dimension/transparency checks
        try:
            img = Image.open(str(file_path))
            img.load()  # force full load
            layer_images[role] = (file_path, img)
        except Exception as e:
            result.error(
                f"normalized_layers[{i}]: failed to open 'normalized/{fname}' "
                f"as image: {e}"
            )

    # --- Check j: all normalized layers have same dimensions ---
    if layer_images:
        first_role = next(iter(layer_images))
        first_w, first_h = layer_images[first_role][1].size

        for role, (fpath, img) in layer_images.items():
            if img.size != (first_w, first_h):
                result.error(
                    f"normalized layer '{role}' ({fpath.name}) has dimensions "
                    f"{img.size}, expected {first_w}x{first_h} (mismatch with "
                    f"'{first_role}' layer)"
                )

    # --- Check k: normalized layer dimensions match normalized_geometry.canvas ---
    if layer_images and norm_geom is not None:
        first_role = next(iter(layer_images))
        first_w, first_h = layer_images[first_role][1].size
        if first_w != norm_geom.canvas_width or first_h != norm_geom.canvas_height:
            result.error(
                f"normalized layer dimensions ({first_w}x{first_h}) do not "
                f"match normalized_geometry.canvas "
                f"({norm_geom.canvas_width}x{norm_geom.canvas_height})"
            )

    # --- Check l: print_mask layer exists and is non-empty ---
    if "print_mask" not in layer_images:
        result.error(
            "normalized_layers: missing 'print_mask' role layer"
        )
    else:
        mask_img = layer_images["print_mask"][1]
        if not _image_has_non_transparent_pixels(mask_img):
            result.error(
                "print_mask layer is entirely transparent — "
                "print mask must have non-empty printable area"
            )

    # --- Check m: required roles per case type ---
    # For hard case: base, print_mask, AND overlay are required (essential roles)
    layer_roles = set(layer_images.keys())
    if case_type == "hard":
        missing_required = _HARD_CASE_REQUIRED_ROLES - layer_roles
        if missing_required:
            result.error(
                f"hard case type: missing required layer role(s): "
                f"{sorted(missing_required)}. "
                f"Hard cases require base, print_mask, and overlay layers."
            )

    # --- Check n: owner review (reviewed=true AND verified_by non-sentinel) ---
    if not reviewed:
        result.error(
            "package is not owner-reviewed: reviewed=false. "
            "Production promotion requires explicit owner review."
        )

    if _is_review_sentinel(verified_by):
        result.error(
            f"verified_by '{verified_by}' is a sentinel value, not a real "
            f"reviewer. Production promotion requires a named reviewer."
        )

    # --- Check o: supplier_geometry string is production-grade ---
    # The package_id + revision forms the supplier_geometry reference
    # that will be written to template provenance.
    supplier_geometry_ref = f"{package_id}@{pkg_data['revision']}"
    if not is_production_grade_supplier_geometry(supplier_geometry_ref):
        result.error(
            f"supplier_geometry reference '{supplier_geometry_ref}' is not "
            f"production-grade (matches a non-production sentinel)."
        )

    # --- Check p: test fixture detection (informational) ---
    if is_test_fixture_package(package_id):
        result.warning(
            f"package_id '{package_id}' is a test/fixture package. "
            f"Test fixtures must NOT be used for real production templates."
        )

    # --- Build the package object if valid ---
    if result.valid:
        try:
            result.package = SupplierGeometryPackage(
                package_dir=str(pkg_dir),
                package_id=package_id,
                supplier_id=pkg_data["supplier_id"],
                supplier_reference=pkg_data["supplier_reference"],
                device_id=device_id,
                case_type=case_type,
                revision=pkg_data["revision"],
                target_template_id=target_template_id,
                reviewed=reviewed,
                verified_by=verified_by,
                source_type=pkg_data["source_type"],
                normalized_geometry=norm_geom,
                normalized_layers=list(normalized_layers),
            )
        except Exception as e:
            result.error(f"Failed to construct package object: {e}")

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_package_schema(
    pkg_data: dict,
    pkg_json_path: Path,
    result: SupplierGeometryValidationResult,
):
    """Validate required fields and basic types in package.json."""
    required_fields = {
        "schema_version", "package_id", "supplier_id", "supplier_reference",
        "device_id", "case_type", "revision", "source_type",
        "source_files", "dimensions", "geometry_notes",
        "obtained_from", "verified_by", "reviewed",
        "target_template_id", "normalized_geometry", "normalized_layers",
    }

    # Check required fields
    missing = required_fields - set(pkg_data.keys())
    if missing:
        for field in sorted(missing):
            result.error(f"package.json: missing required field '{field}'")
        return

    # schema_version
    sv = pkg_data["schema_version"]
    if not isinstance(sv, int) or isinstance(sv, bool):
        result.error("package.json: schema_version must be integer")
    elif sv != 1:
        result.error(f"package.json: schema_version must be 1, got {sv}")

    # package_id
    pid = pkg_data["package_id"]
    if not isinstance(pid, str) or not pid:
        result.error("package.json: package_id must be non-empty string")
    elif not is_valid_component_id(pid):
        result.error(
            f"package.json: package_id '{pid}' contains invalid characters. "
            f"Must be lowercase alphanumeric with hyphens/underscores."
        )

    # supplier_id
    if not isinstance(pkg_data["supplier_id"], str) or not pkg_data["supplier_id"]:
        result.error("package.json: supplier_id must be non-empty string")

    # supplier_reference
    if not isinstance(pkg_data["supplier_reference"], str) or not pkg_data["supplier_reference"]:
        result.error("package.json: supplier_reference must be non-empty string")

    # device_id
    did = pkg_data["device_id"]
    if not isinstance(did, str) or not did:
        result.error("package.json: device_id must be non-empty string")
    elif not is_valid_component_id(did):
        result.error(
            f"package.json: device_id '{did}' contains invalid characters."
        )

    # case_type
    ct = pkg_data["case_type"]
    if not isinstance(ct, str):
        result.error("package.json: case_type must be string")
    elif ct not in CONTRACT_CASE_TYPES:
        result.error(
            f"package.json: case_type '{ct}' is not a valid Contract v1 token. "
            f"Expected one of {sorted(CONTRACT_CASE_TYPES)}"
        )

    # revision
    if not isinstance(pkg_data["revision"], str) or not pkg_data["revision"]:
        result.error("package.json: revision must be non-empty string")

    # source_type
    valid_source_types = {
        "dieline", "psd_export", "cad_export", "measured", "normalized_export"
    }
    st = pkg_data["source_type"]
    if not isinstance(st, str):
        result.error("package.json: source_type must be string")
    elif st not in valid_source_types:
        result.error(
            f"package.json: source_type '{st}' is not valid. "
            f"Expected one of {sorted(valid_source_types)}"
        )

    # source_files
    sf = pkg_data["source_files"]
    if not isinstance(sf, list) or len(sf) == 0:
        result.error("package.json: source_files must be non-empty array")
    else:
        for i, item in enumerate(sf):
            if not isinstance(item, dict):
                result.error(f"package.json: source_files[{i}] must be object")
                continue
            if "name" not in item:
                result.error(f"package.json: source_files[{i}] missing 'name'")
            if "sha256" not in item:
                result.error(f"package.json: source_files[{i}] missing 'sha256'")
            elif not isinstance(item["sha256"], str):
                result.error(f"package.json: source_files[{i}].sha256 must be string")
            elif not _is_valid_sha256(item["sha256"]):
                result.error(
                    f"package.json: source_files[{i}].sha256 has invalid format"
                )

    # dimensions
    dims = pkg_data["dimensions"]
    if not isinstance(dims, dict):
        result.error("package.json: dimensions must be object")
    else:
        for fld in ("width", "height", "units"):
            if fld not in dims:
                result.error(f"package.json: dimensions missing '{fld}'")
        if "width" in dims and not isinstance(dims["width"], (int, float)):
            result.error("package.json: dimensions.width must be number")
        if "height" in dims and not isinstance(dims["height"], (int, float)):
            result.error("package.json: dimensions.height must be number")
        if "units" in dims:
            valid_units = {"mm", "cm", "in", "px"}
            if dims["units"] not in valid_units:
                result.error(
                    f"package.json: dimensions.units '{dims['units']}' not valid. "
                    f"Expected one of {sorted(valid_units)}"
                )

    # geometry_notes
    if not isinstance(pkg_data["geometry_notes"], str):
        result.error("package.json: geometry_notes must be string")

    # obtained_from
    if not isinstance(pkg_data["obtained_from"], str) or not pkg_data["obtained_from"]:
        result.error("package.json: obtained_from must be non-empty string")

    # verified_by
    if not isinstance(pkg_data["verified_by"], str):
        result.error("package.json: verified_by must be string")

    # reviewed
    if not isinstance(pkg_data["reviewed"], bool):
        result.error("package.json: reviewed must be boolean")

    # target_template_id
    ttid = pkg_data["target_template_id"]
    if not isinstance(ttid, str) or not ttid:
        result.error("package.json: target_template_id must be non-empty string")

    # normalized_geometry
    ng = pkg_data["normalized_geometry"]
    if not isinstance(ng, dict):
        result.error("package.json: normalized_geometry must be object")

    # normalized_layers
    nl = pkg_data["normalized_layers"]
    if not isinstance(nl, list) or len(nl) == 0:
        result.error("package.json: normalized_layers must be non-empty array")
    else:
        seen_roles = set()
        for i, item in enumerate(nl):
            if not isinstance(item, dict):
                result.error(f"package.json: normalized_layers[{i}] must be object")
                continue
            for fld in ("name", "file", "sha256", "role"):
                if fld not in item:
                    result.error(
                        f"package.json: normalized_layers[{i}] missing '{fld}'"
                    )
            if "role" in item:
                role = item["role"]
                valid_roles = {"base", "print_mask", "overlay", "highlight", "shadow"}
                if role not in valid_roles:
                    result.error(
                        f"package.json: normalized_layers[{i}].role "
                        f"'{role}' is not valid. Expected one of {sorted(valid_roles)}"
                    )
                elif role in seen_roles:
                    result.error(
                        f"package.json: normalized_layers[{i}]: duplicate role '{role}'"
                    )
                seen_roles.add(role)
            if "sha256" in item:
                if not isinstance(item["sha256"], str):
                    result.error(
                        f"package.json: normalized_layers[{i}].sha256 must be string"
                    )
                elif not _is_valid_sha256(item["sha256"]):
                    result.error(
                        f"package.json: normalized_layers[{i}].sha256 has invalid format"
                    )


def _validate_normalized_geometry(
    ng_data: dict,
    pkg_json_path: Path,
    result: SupplierGeometryValidationResult,
) -> Optional[NormalizedGeometry]:
    """Validate the normalized_geometry object and return a NormalizedGeometry.

    Validates:
    - canvas with width, height, units (units must be "px")
    - print_region with x, y, width, height (within canvas bounds)
    - optional camera_region with x, y, width, height (within canvas bounds)
    """
    if not isinstance(ng_data, dict):
        return None

    # --- canvas ---
    canvas = ng_data.get("canvas")
    if not isinstance(canvas, dict):
        result.error("package.json: normalized_geometry.canvas must be object")
        return None

    canvas_required = {"width", "height", "units"}
    canvas_missing = canvas_required - set(canvas.keys())
    if canvas_missing:
        for fld in sorted(canvas_missing):
            result.error(
                f"package.json: normalized_geometry.canvas missing '{fld}'"
            )
        return None

    cw = canvas.get("width")
    ch = canvas.get("height")
    cu = canvas.get("units")

    if not isinstance(cw, int) or isinstance(cw, bool):
        result.error("package.json: normalized_geometry.canvas.width must be integer")
    elif cw < 100 or cw > 8000:
        result.error(
            f"package.json: normalized_geometry.canvas.width {cw} out of range [100, 8000]"
        )

    if not isinstance(ch, int) or isinstance(ch, bool):
        result.error("package.json: normalized_geometry.canvas.height must be integer")
    elif ch < 100 or ch > 8000:
        result.error(
            f"package.json: normalized_geometry.canvas.height {ch} out of range [100, 8000]"
        )

    if cu != "px":
        result.error(
            f"package.json: normalized_geometry.canvas.units must be 'px', got '{cu}'"
        )

    # --- print_region ---
    pr = ng_data.get("print_region")
    if not isinstance(pr, dict):
        result.error("package.json: normalized_geometry.print_region must be object")
        return None

    pr_required = {"x", "y", "width", "height"}
    pr_missing = pr_required - set(pr.keys())
    if pr_missing:
        for fld in sorted(pr_missing):
            result.error(
                f"package.json: normalized_geometry.print_region missing '{fld}'"
            )
        return None

    pr_x = pr.get("x")
    pr_y = pr.get("y")
    pr_w = pr.get("width")
    pr_h = pr.get("height")

    for val, name in [(pr_x, "x"), (pr_y, "y")]:
        if not isinstance(val, int) or isinstance(val, bool):
            result.error(
                f"package.json: normalized_geometry.print_region.{name} must be integer"
            )
        elif val < 0:
            result.error(
                f"package.json: normalized_geometry.print_region.{name} must be >= 0"
            )

    for val, name in [(pr_w, "width"), (pr_h, "height")]:
        if not isinstance(val, int) or isinstance(val, bool):
            result.error(
                f"package.json: normalized_geometry.print_region.{name} must be integer"
            )
        elif val < 1:
            result.error(
                f"package.json: normalized_geometry.print_region.{name} must be >= 1"
            )

    # Validate print_region is within canvas bounds
    if (isinstance(cw, int) and not isinstance(cw, bool) and
        isinstance(ch, int) and not isinstance(ch, bool) and
        isinstance(pr_x, int) and not isinstance(pr_x, bool) and
        isinstance(pr_y, int) and not isinstance(pr_y, bool) and
        isinstance(pr_w, int) and not isinstance(pr_w, bool) and
        isinstance(pr_h, int) and not isinstance(pr_h, bool)):
        if pr_x + pr_w > cw:
            result.error(
                f"package.json: normalized_geometry.print_region extends "
                f"beyond canvas width (x+width={pr_x + pr_w} > canvas.width={cw})"
            )
        if pr_y + pr_h > ch:
            result.error(
                f"package.json: normalized_geometry.print_region extends "
                f"beyond canvas height (y+height={pr_y + pr_h} > canvas.height={ch})"
            )

    # --- camera_region (optional) ---
    camera_region = None
    cr = ng_data.get("camera_region")
    if cr is not None:
        if not isinstance(cr, dict):
            result.error("package.json: normalized_geometry.camera_region must be object")
        else:
            cr_required = {"x", "y", "width", "height"}
            cr_missing = cr_required - set(cr.keys())
            if cr_missing:
                for fld in sorted(cr_missing):
                    result.error(
                        f"package.json: normalized_geometry.camera_region missing '{fld}'"
                    )
            else:
                cr_x = cr.get("x")
                cr_y = cr.get("y")
                cr_w = cr.get("width")
                cr_h = cr.get("height")

                for val, name in [(cr_x, "x"), (cr_y, "y")]:
                    if not isinstance(val, int) or isinstance(val, bool):
                        result.error(
                            f"package.json: normalized_geometry.camera_region.{name} must be integer"
                        )
                    elif val < 0:
                        result.error(
                            f"package.json: normalized_geometry.camera_region.{name} must be >= 0"
                        )

                for val, name in [(cr_w, "width"), (cr_h, "height")]:
                    if not isinstance(val, int) or isinstance(val, bool):
                        result.error(
                            f"package.json: normalized_geometry.camera_region.{name} must be integer"
                        )
                    elif val < 1:
                        result.error(
                            f"package.json: normalized_geometry.camera_region.{name} must be >= 1"
                        )

                # Validate camera_region is within canvas bounds
                if (isinstance(cw, int) and not isinstance(cw, bool) and
                    isinstance(ch, int) and not isinstance(ch, bool) and
                    isinstance(cr_x, int) and not isinstance(cr_x, bool) and
                    isinstance(cr_y, int) and not isinstance(cr_y, bool) and
                    isinstance(cr_w, int) and not isinstance(cr_w, bool) and
                    isinstance(cr_h, int) and not isinstance(cr_h, bool)):
                    if cr_x + cr_w > cw:
                        result.error(
                            f"package.json: normalized_geometry.camera_region extends "
                            f"beyond canvas width (x+width={cr_x + cr_w} > canvas.width={cw})"
                        )
                    if cr_y + cr_h > ch:
                        result.error(
                            f"package.json: normalized_geometry.camera_region extends "
                            f"beyond canvas height (y+height={cr_y + cr_h} > canvas.height={ch})"
                        )

                camera_region = {
                    "x": cr_x,
                    "y": cr_y,
                    "width": cr_w,
                    "height": cr_h,
                }

    if not result.valid:
        return None

    return NormalizedGeometry(
        canvas_width=cw,
        canvas_height=ch,
        canvas_units=cu,
        print_region_x=pr_x,
        print_region_y=pr_y,
        print_region_width=pr_w,
        print_region_height=pr_h,
        camera_region=camera_region,
    )


def _sha256_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _is_valid_sha256(value: str) -> bool:
    """Return True if value is a valid 64-char lowercase hex SHA-256 digest."""
    if not isinstance(value, str):
        return False
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _is_path_traversal(filename: str) -> bool:
    """Return True if filename contains path traversal attempts."""
    if not isinstance(filename, str):
        return True
    p = Path(filename)
    if p.is_absolute():
        return True
    parts = p.parts
    if ".." in parts:
        return True
    # Also check for backslash-based traversal on Windows
    if "\\" in filename and "/" not in filename:
        # Windows-style path
        return ".." in filename.split("\\")
    return False


def _image_has_non_transparent_pixels(img: Image.Image) -> bool:
    """Return True if the image has at least one non-transparent pixel.

    Works with RGBA, RGB, L, and other modes. RGB images are always
    considered non-transparent.
    """
    if img.mode not in ("RGBA", "LA") and "A" not in img.mode:
        # No alpha channel = fully opaque = has non-transparent pixels
        return True

    # Get the alpha channel
    if img.mode == "RGBA":
        alpha = img.split()[3]
    elif img.mode == "LA":
        alpha = img.split()[1]
    else:
        alpha = img.getchannel("A")

    # Check if any alpha pixel is > threshold
    # Use getextrema for a fast check — if max alpha <= threshold, it's empty
    threshold = 10  # account for anti-aliasing edges
    alpha_extrema = alpha.getextrema()
    if alpha_extrema[1] <= threshold:
        return False
    return True


def _is_review_sentinel(value: str) -> bool:
    """Return True if verified_by is a sentinel value (not a real reviewer).

    Uses exact match (case-insensitive, after stripping whitespace)
    against known sentinel values. Unlike supplier_geometry sentinel
    detection which uses prefix matching (for phrases like "none — ..."),
    review sentinels are standalone placeholder tokens.
    """
    if not isinstance(value, str):
        return True
    stripped = value.strip().lower()
    if not stripped:
        return True
    # Exact match only — email addresses like "test-owner@example.com"
    # are valid reviewer identifiers, even if they contain "test".
    return stripped in _REVIEW_SENTINELS
