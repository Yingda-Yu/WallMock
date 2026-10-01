"""
Loader and validator for WallMock 2.0 catalog manifests.

Provides functions to load and validate case templates, designs, and
availability records from JSON files into the dataclass models defined
in ``catalog_models``.

Design goals:
  - No dependency on Flask, Pillow, or the jsonschema library.
  - Strict validation: unknown fields are rejected so they cannot
    silently change rendering behaviour.
  - Actionable error messages that always include the file path and
    the offending field.
  - Path-traversal protection on all IDs.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from .catalog_models import (
    Canvas,
    CaseTemplate,
    CaseTemplateLayer,
    CatalogValidationError,
    Design,
    Device,
    PrintRegion,
    VariantAvailability,
)

BASE_DIR = Path(__file__).resolve().parent.parent
CASE_TEMPLATES_DIR = BASE_DIR / "assets" / "case_templates"
DESIGNS_DIR = BASE_DIR / "catalog" / "designs"
AVAILABILITY_PATH = BASE_DIR / "catalog" / "availability.json"

CURRENT_SCHEMA_VERSION = 1

# IDs may contain lowercase alphanumerics, hyphens, and underscores.
# They must NOT contain dots, slashes, or other path-like characters.
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

VALID_CASE_TYPES = {"hard", "tough", "magsafe", "transparent", "soft"}
VALID_VIEWS = {"rear", "angle", "front", "closeup"}
VALID_FIT_MODES = {"cover", "contain", "tile"}
VALID_PRINT_MODES = {"mask", "quad"}
VALID_LAYER_TYPES = {"base", "artwork", "highlight", "overlay", "shadow"}
VALID_BLEND_MODES = {"normal", "multiply", "screen", "overlay", "darken", "lighten"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_no_unknown(data: dict, allowed_keys: set, file_path: Path, context: str):
    """Reject keys not in ``allowed_keys`` with an actionable message."""
    extra = set(data.keys()) - allowed_keys
    if extra:
        keys_str = ", ".join(sorted(extra))
        raise CatalogValidationError(
            f"{file_path}: {context}: unknown field(s) '{keys_str}'. "
            f"Allowed: {sorted(allowed_keys)}"
        )


def _require_fields(data: dict, required: set, file_path: Path, context: str):
    """Ensure all required keys exist."""
    missing = required - set(data.keys())
    if missing:
        keys_str = ", ".join(sorted(missing))
        raise CatalogValidationError(
            f"{file_path}: {context}: missing required field(s) '{keys_str}'"
        )


def _validate_id(value, field_name: str, file_path: Path):
    """Validate that an ID is safe (no path traversal)."""
    if not isinstance(value, str):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected string, got {type(value).__name__}"
        )
    if not _ID_PATTERN.match(value):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: '{value}' contains invalid characters. "
            f"Only lowercase alphanumerics, hyphens, and underscores are allowed "
            f"(path traversal prevention)."
        )


def _validate_file_path(value, field_name: str, file_path: Path):
    """Validate that a relative file path does not escape its directory."""
    if value is None:
        return
    if not isinstance(value, str):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected string or null, got {type(value).__name__}"
        )
    if ".." in Path(value).parts or Path(value).is_absolute():
        raise CatalogValidationError(
            f"{file_path}: {field_name}: '{value}' is not a safe relative path"
        )


def _check_type(value, expected_type, field_name: str, file_path: Path):
    if not isinstance(value, expected_type):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )


def _check_enum(value, valid_set: set, field_name: str, file_path: Path):
    if value not in valid_set:
        raise CatalogValidationError(
            f"{file_path}: {field_name}: '{value}' is not valid. "
            f"Expected one of {sorted(valid_set)}"
        )


def _check_int_range(value, field_name: str, file_path: Path, minimum=None, maximum=None):
    if not isinstance(value, int) or isinstance(value, bool):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected integer, got {type(value).__name__}"
        )
    if minimum is not None and value < minimum:
        raise CatalogValidationError(
            f"{file_path}: {field_name}: {value} is below minimum {minimum}"
        )
    if maximum is not None and value > maximum:
        raise CatalogValidationError(
            f"{file_path}: {field_name}: {value} is above maximum {maximum}"
        )


def _check_float_range(value, field_name: str, file_path: Path, minimum=0.0, maximum=1.0):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected number, got {type(value).__name__}"
        )
    if value < minimum or value > maximum:
        raise CatalogValidationError(
            f"{file_path}: {field_name}: {value} is out of range [{minimum}, {maximum}]"
        )


# ---------------------------------------------------------------------------
# Case template loader
# ---------------------------------------------------------------------------

def load_case_template(path) -> CaseTemplate:
    """Load and validate a single case template from a JSON file.

    Raises ``CatalogValidationError`` for any malformed or invalid input.
    The error message always includes the file path and offending field.
    """
    file_path = Path(path)

    if not file_path.exists():
        raise CatalogValidationError(f"{file_path}: file does not exist")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise CatalogValidationError(f"{file_path}: invalid JSON: {e}")

    if not isinstance(raw, dict):
        raise CatalogValidationError(
            f"{file_path}: root must be a JSON object, got {type(raw).__name__}"
        )

    # --- top-level fields ---
    _check_no_unknown(
        raw,
        {"schema_version", "id", "device_id", "case_type", "view",
         "canvas", "print_region", "layers",
         "status", "provenance"},
        file_path, "template root",
    )
    _require_fields(
        raw,
        {"schema_version", "id", "device_id", "case_type", "view",
         "canvas", "print_region", "layers"},
        file_path, "template root",
    )

    # status (optional — defaults to "production" for backward compat)
    status = raw.get("status", "production")
    _check_type(status, str, "status", file_path)

    # provenance (optional — geometry provenance metadata)
    provenance = raw.get("provenance")
    if provenance is not None:
        if not isinstance(provenance, dict):
            raise CatalogValidationError(
                f"{file_path}: provenance: expected object, got {type(provenance).__name__}"
            )
        # provenance fields are free-form metadata — no strict validation

    # schema_version
    sv = raw["schema_version"]
    if sv != CURRENT_SCHEMA_VERSION:
        raise CatalogValidationError(
            f"{file_path}: schema_version: expected {CURRENT_SCHEMA_VERSION}, got {sv}"
        )

    # id
    _validate_id(raw["id"], "id", file_path)

    # device_id
    _validate_id(raw["device_id"], "device_id", file_path)

    # case_type
    _check_type(raw["case_type"], str, "case_type", file_path)
    _check_enum(raw["case_type"], VALID_CASE_TYPES, "case_type", file_path)

    # view
    _check_type(raw["view"], str, "view", file_path)
    _check_enum(raw["view"], VALID_VIEWS, "view", file_path)

    # --- canvas ---
    canvas_raw = raw["canvas"]
    if not isinstance(canvas_raw, dict):
        raise CatalogValidationError(
            f"{file_path}: canvas: expected object, got {type(canvas_raw).__name__}"
        )
    _check_no_unknown(canvas_raw, {"width", "height"}, file_path, "canvas")
    _require_fields(canvas_raw, {"width", "height"}, file_path, "canvas")
    _check_int_range(canvas_raw["width"], "canvas.width", file_path, 100, 8000)
    _check_int_range(canvas_raw["height"], "canvas.height", file_path, 100, 8000)

    canvas = Canvas(width=canvas_raw["width"], height=canvas_raw["height"])

    # --- print_region ---
    pr_raw = raw["print_region"]
    if not isinstance(pr_raw, dict):
        raise CatalogValidationError(
            f"{file_path}: print_region: expected object, got {type(pr_raw).__name__}"
        )
    _check_no_unknown(
        pr_raw,
        {"mode", "x", "y", "width", "height", "fit", "mask"},
        file_path, "print_region",
    )
    _require_fields(
        pr_raw,
        {"mode", "x", "y", "width", "height", "fit"},
        file_path, "print_region",
    )
    _check_type(pr_raw["mode"], str, "print_region.mode", file_path)
    _check_enum(pr_raw["mode"], VALID_PRINT_MODES, "print_region.mode", file_path)
    _check_int_range(pr_raw["x"], "print_region.x", file_path, 0)
    _check_int_range(pr_raw["y"], "print_region.y", file_path, 0)
    _check_int_range(pr_raw["width"], "print_region.width", file_path, 1)
    _check_int_range(pr_raw["height"], "print_region.height", file_path, 1)
    _check_type(pr_raw["fit"], str, "print_region.fit", file_path)
    _check_enum(pr_raw["fit"], VALID_FIT_MODES, "print_region.fit", file_path)

    mask = pr_raw.get("mask")
    if mask is not None:
        _validate_file_path(mask, "print_region.mask", file_path)

    print_region = PrintRegion(
        mode=pr_raw["mode"],
        x=pr_raw["x"],
        y=pr_raw["y"],
        width=pr_raw["width"],
        height=pr_raw["height"],
        fit=pr_raw["fit"],
        mask=mask,
    )

    # --- layers ---
    layers_raw = raw["layers"]
    if not isinstance(layers_raw, list) or len(layers_raw) == 0:
        raise CatalogValidationError(
            f"{file_path}: layers: expected non-empty array"
        )

    layers: List[CaseTemplateLayer] = []
    has_artwork_layer = False
    for i, layer_raw in enumerate(layers_raw):
        ctx = f"layers[{i}]"
        if not isinstance(layer_raw, dict):
            raise CatalogValidationError(
                f"{file_path}: {ctx}: expected object, got {type(layer_raw).__name__}"
            )
        _check_no_unknown(
            layer_raw,
            {"type", "file", "blend", "opacity"},
            file_path, ctx,
        )
        _require_fields(layer_raw, {"type"}, file_path, ctx)
        _check_type(layer_raw["type"], str, f"{ctx}.type", file_path)
        _check_enum(layer_raw["type"], VALID_LAYER_TYPES, f"{ctx}.type", file_path)

        file_val = layer_raw.get("file")
        if file_val is not None:
            _validate_file_path(file_val, f"{ctx}.file", file_path)

        blend = layer_raw.get("blend", "normal")
        _check_type(blend, str, f"{ctx}.blend", file_path)
        _check_enum(blend, VALID_BLEND_MODES, f"{ctx}.blend", file_path)

        opacity = layer_raw.get("opacity", 1.0)
        _check_float_range(opacity, f"{ctx}.opacity", file_path, 0.0, 1.0)

        # artwork layer must not have a file (it's a placeholder for the design)
        if layer_raw["type"] == "artwork":
            has_artwork_layer = True
            if file_val is not None:
                raise CatalogValidationError(
                    f"{file_path}: {ctx}.file: artwork layer must not specify a file"
                )

        layers.append(CaseTemplateLayer(
            type=layer_raw["type"],
            file=file_val,
            blend=blend,
            opacity=opacity,
        ))

    if not has_artwork_layer:
        raise CatalogValidationError(
            f"{file_path}: layers: must contain at least one layer with type 'artwork'"
        )

    return CaseTemplate(
        schema_version=sv,
        id=raw["id"],
        device_id=raw["device_id"],
        case_type=raw["case_type"],
        view=raw["view"],
        canvas=canvas,
        print_region=print_region,
        layers=layers,
    )


# ---------------------------------------------------------------------------
# Design loader
# ---------------------------------------------------------------------------

def load_design(path) -> Design:
    """Load and validate a design manifest from a JSON file."""
    file_path = Path(path)

    if not file_path.exists():
        raise CatalogValidationError(f"{file_path}: file does not exist")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise CatalogValidationError(f"{file_path}: invalid JSON: {e}")

    if not isinstance(raw, dict):
        raise CatalogValidationError(
            f"{file_path}: root must be a JSON object, got {type(raw).__name__}"
        )

    _check_no_unknown(
        raw,
        {"schema_version", "id", "display_name", "case_artwork",
         "wallpaper_artwork", "case_fit_mode", "focal_point", "tags", "active"},
        file_path, "design root",
    )
    _require_fields(
        raw,
        {"schema_version", "id", "display_name"},
        file_path, "design root",
    )

    sv = raw["schema_version"]
    if sv != CURRENT_SCHEMA_VERSION:
        raise CatalogValidationError(
            f"{file_path}: schema_version: expected {CURRENT_SCHEMA_VERSION}, got {sv}"
        )

    _validate_id(raw["id"], "id", file_path)

    dn = raw["display_name"]
    _check_type(dn, str, "display_name", file_path)
    if len(dn.strip()) == 0:
        raise CatalogValidationError(
            f"{file_path}: display_name: must not be empty"
        )

    case_artwork = raw.get("case_artwork")
    if case_artwork is not None:
        _validate_file_path(case_artwork, "case_artwork", file_path)

    wallpaper_artwork = raw.get("wallpaper_artwork")
    if wallpaper_artwork is not None:
        _validate_file_path(wallpaper_artwork, "wallpaper_artwork", file_path)

    if case_artwork is None and wallpaper_artwork is None:
        raise CatalogValidationError(
            f"{file_path}: at least one of case_artwork or wallpaper_artwork must be set"
        )

    fit_mode = raw.get("case_fit_mode", "cover")
    _check_type(fit_mode, str, "case_fit_mode", file_path)
    _check_enum(fit_mode, VALID_FIT_MODES, "case_fit_mode", file_path)

    focal_point = raw.get("focal_point", [0.5, 0.5])
    if not isinstance(focal_point, list) or len(focal_point) != 2:
        raise CatalogValidationError(
            f"{file_path}: focal_point: expected [x, y] array of length 2"
        )
    for i, v in enumerate(focal_point):
        _check_float_range(v, f"focal_point[{i}]", file_path, 0.0, 1.0)
    focal_point = (float(focal_point[0]), float(focal_point[1]))

    tags = raw.get("tags", [])
    if not isinstance(tags, list):
        raise CatalogValidationError(
            f"{file_path}: tags: expected array, got {type(tags).__name__}"
        )
    for i, t in enumerate(tags):
        _check_type(t, str, f"tags[{i}]", file_path)

    active = raw.get("active", True)
    _check_type(active, bool, "active", file_path)

    return Design(
        schema_version=sv,
        id=raw["id"],
        display_name=dn,
        case_artwork=case_artwork,
        wallpaper_artwork=wallpaper_artwork,
        case_fit_mode=fit_mode,
        focal_point=focal_point,
        tags=tags,
        active=active,
    )


# ---------------------------------------------------------------------------
# Availability loader
# ---------------------------------------------------------------------------

def load_availability(path) -> List[VariantAvailability]:
    """Load and validate variant availability from a JSON file."""
    file_path = Path(path)

    if not file_path.exists():
        raise CatalogValidationError(f"{file_path}: file does not exist")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise CatalogValidationError(f"{file_path}: invalid JSON: {e}")

    if not isinstance(raw, list):
        raise CatalogValidationError(
            f"{file_path}: root must be a JSON array, got {type(raw).__name__}"
        )

    results: List[VariantAvailability] = []
    for i, item in enumerate(raw):
        ctx = f"availability[{i}]"
        if not isinstance(item, dict):
            raise CatalogValidationError(
                f"{file_path}: {ctx}: expected object, got {type(item).__name__}"
            )
        _check_no_unknown(
            item,
            {"variant_id", "design_id", "device_id", "case_type",
             "available", "supplier_sku", "supplier_id"},
            file_path, ctx,
        )
        _require_fields(
            item,
            {"variant_id", "design_id", "device_id", "case_type", "available"},
            file_path, ctx,
        )

        _validate_id(item["design_id"], f"{ctx}.design_id", file_path)
        _validate_id(item["device_id"], f"{ctx}.device_id", file_path)
        _check_type(item["case_type"], str, f"{ctx}.case_type", file_path)
        _check_enum(item["case_type"], VALID_CASE_TYPES, f"{ctx}.case_type", file_path)
        _check_type(item["available"], bool, f"{ctx}.available", file_path)

        # variant_id should match design_id__device_id__case_type
        expected_vid = f"{item['design_id']}__{item['device_id']}__{item['case_type']}"
        if item["variant_id"] != expected_vid:
            raise CatalogValidationError(
                f"{file_path}: {ctx}.variant_id: '{item['variant_id']}' does not match "
                f"expected '{expected_vid}'"
            )

        supplier_sku = item.get("supplier_sku")
        supplier_id = item.get("supplier_id")

        results.append(VariantAvailability(
            variant_id=item["variant_id"],
            design_id=item["design_id"],
            device_id=item["device_id"],
            case_type=item["case_type"],
            available=item["available"],
            supplier_sku=supplier_sku,
            supplier_id=supplier_id,
        ))

    return results


# ---------------------------------------------------------------------------
# Index-based listing
# ---------------------------------------------------------------------------

def list_case_templates() -> List[CaseTemplate]:
    """Load all case templates listed in ``assets/case_templates/index.json``.

    Returns a list of validated CaseTemplate objects. If the index or
    template directory does not exist yet, returns an empty list
    (the system boots cleanly before any templates have been authored).
    """
    index_path = CASE_TEMPLATES_DIR / "index.json"
    if not index_path.exists():
        return []

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    except json.JSONDecodeError as e:
        raise CatalogValidationError(f"{index_path}: invalid JSON: {e}")

    if not isinstance(index, dict):
        raise CatalogValidationError(
            f"{index_path}: root must be a JSON object"
        )

    _check_no_unknown(index, {"templates"}, index_path, "index root")

    templates_raw = index.get("templates", [])
    if not isinstance(templates_raw, list):
        raise CatalogValidationError(
            f"{index_path}: templates: expected array"
        )

    results: List[CaseTemplate] = []
    for i, entry in enumerate(templates_raw):
        ctx = f"templates[{i}]"
        if not isinstance(entry, dict):
            raise CatalogValidationError(
                f"{index_path}: {ctx}: expected object"
            )
        _check_no_unknown(entry, {"path"}, index_path, ctx)
        _require_fields(entry, {"path"}, index_path, ctx)

        rel_path = entry["path"]
        tpl_path = CASE_TEMPLATES_DIR / rel_path
        results.append(load_case_template(tpl_path))

    return results


def get_case_templates_for_device(device_id: str) -> List[CaseTemplate]:
    """Return all case templates that match a specific device ID."""
    _validate_id(device_id, "device_id", Path("<caller>"))
    return [t for t in list_case_templates() if t.device_id == device_id]
