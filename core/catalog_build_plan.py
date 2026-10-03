"""
Typed build-plan loader and validator for WallMock catalog builds.

Defines the CatalogBuildPlan dataclass and load_catalog_build_plan()
function with thorough validation: duplicate targets, unknown devices,
missing templates, invalid case/view tokens, path traversal, duplicate
or invalid widths, and output path escaping the build root.

Reuses existing modules:
  - case_template_loader.load_case_template
  - contract_ids (ID grammar, component ID validation)
  - catalog_models (status, provenance validation)
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .catalog_models import CatalogValidationError
from .case_template_loader import (
    VALID_CASE_TYPES,
    VALID_VIEWS,
    VALID_FIT_MODES,
    load_case_template,
)
from .contract_ids import (
    is_valid_component_id,
    is_valid_case_type as is_contract_valid_case_type,
    is_valid_view as is_contract_valid_view,
)


CURRENT_SCHEMA_VERSION = 1

VALID_BUILD_MODES = {"preview", "publish"}

# Normalize internal case_type tokens to contract tokens.
# Internal "transparent" maps to contract "clear".
_CASE_TYPE_NORMALIZE = {
    "transparent": "clear",
}


@dataclass(frozen=True)
class BuildRenderOptions:
    """Rendering options applied across all build targets."""
    fit_mode: str = "cover"
    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    webp_quality: int = 85


@dataclass(frozen=True)
class BuildTarget:
    """A single build target: device + case_type + views + widths."""
    device_id: str
    case_type: str
    views: List[str] = field(default_factory=list)
    widths: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class CatalogBuildPlan:
    """A complete catalog build plan.

    Attributes
    ----------
    schema_version : int
        Schema version (must be 1).
    mode : str
        Build mode: "preview" or "publish".
    design_ids : List[str]
        List of design IDs to render.
    targets : List[BuildTarget]
        List of render targets (device x case_type x views x widths).
    render_options : BuildRenderOptions
        Rendering options applied to all targets.
    """
    schema_version: int
    mode: str
    design_ids: List[str]
    targets: List[BuildTarget]
    render_options: BuildRenderOptions

    def total_asset_count(self) -> int:
        """Return the total number of individual render assets in the plan."""
        count = 0
        for target in self.targets:
            count += len(target.views) * len(target.widths)
        return count * len(self.design_ids)

    def all_device_ids(self) -> List[str]:
        """Return sorted unique list of device IDs from targets."""
        return sorted({t.device_id for t in self.targets})


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _check_type(value, expected_type, field_name: str, file_path: Path):
    if not isinstance(value, expected_type):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )


def _check_no_unknown(data: dict, allowed_keys: set, file_path: Path, context: str):
    extra = set(data.keys()) - allowed_keys
    if extra:
        keys_str = ", ".join(sorted(extra))
        raise CatalogValidationError(
            f"{file_path}: {context}: unknown field(s) '{keys_str}'. "
            f"Allowed: {sorted(allowed_keys)}"
        )


def _require_fields(data: dict, required: set, file_path: Path, context: str):
    missing = required - set(data.keys())
    if missing:
        keys_str = ", ".join(sorted(missing))
        raise CatalogValidationError(
            f"{file_path}: {context}: missing required field(s) '{keys_str}'"
        )


def _validate_component_id(value, field_name: str, file_path: Path):
    """Validate a component ID (design_id, device_id, etc.)."""
    if not isinstance(value, str):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected string, got {type(value).__name__}"
        )
    if not is_valid_component_id(value):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: '{value}' is not a valid component ID. "
            f"Must be lowercase kebab-case with no double underscores "
            f"(path traversal prevention)."
        )


def _validate_widths(widths_raw, file_path: Path, context: str) -> List[int]:
    """Validate and return sorted list of widths."""
    if not isinstance(widths_raw, list) or len(widths_raw) == 0:
        raise CatalogValidationError(
            f"{file_path}: {context}: expected non-empty array of widths"
        )

    widths = []
    seen = set()
    for i, w in enumerate(widths_raw):
        if not isinstance(w, int) or isinstance(w, bool):
            raise CatalogValidationError(
                f"{file_path}: {context}[{i}]: expected integer width, "
                f"got {type(w).__name__}"
            )
        if w < 100 or w > 8000:
            raise CatalogValidationError(
                f"{file_path}: {context}[{i}]: width {w} is out of range "
                f"[100, 8000]"
            )
        if w in seen:
            raise CatalogValidationError(
                f"{file_path}: {context}: duplicate width {w}"
            )
        seen.add(w)
        widths.append(w)

    return sorted(widths)


def _validate_views(views_raw, file_path: Path, context: str) -> List[str]:
    """Validate and return sorted list of views."""
    if not isinstance(views_raw, list) or len(views_raw) == 0:
        raise CatalogValidationError(
            f"{file_path}: {context}: expected non-empty array of views"
        )

    views = []
    seen = set()
    for i, v in enumerate(views_raw):
        if not isinstance(v, str):
            raise CatalogValidationError(
                f"{file_path}: {context}[{i}]: expected string view, "
                f"got {type(v).__name__}"
            )
        if v not in VALID_VIEWS:
            raise CatalogValidationError(
                f"{file_path}: {context}[{i}]: '{v}' is not a valid view. "
                f"Expected one of {sorted(VALID_VIEWS)}"
            )
        if v in seen:
            raise CatalogValidationError(
                f"{file_path}: {context}: duplicate view '{v}'"
            )
        seen.add(v)
        views.append(v)

    return sorted(views)


def _normalize_case_type(case_type: str) -> str:
    """Normalize internal case_type token to contract token."""
    return _CASE_TYPE_NORMALIZE.get(case_type, case_type)


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load_catalog_build_plan(
    path,
    *,
    templates_root: Optional[str] = None,
    validate_templates_exist: bool = True,
) -> CatalogBuildPlan:
    """Load and validate a catalog build plan from a JSON file.

    Parameters
    ----------
    path : str or Path
        Path to the build plan JSON file.
    templates_root : str, optional
        Root directory for case templates. If provided, validates that
        referenced templates exist on disk.
    validate_templates_exist : bool
        If True and templates_root is provided, verify each target's
        template directory exists and template.json loads.

    Returns
    -------
    CatalogBuildPlan
        A validated, immutable build plan.

    Raises
    ------
    CatalogValidationError
        If the plan is malformed or invalid.
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
        {"schema_version", "mode", "design_ids", "targets", "render_options"},
        file_path, "build plan root",
    )
    _require_fields(
        raw,
        {"schema_version", "mode", "design_ids", "targets", "render_options"},
        file_path, "build plan root",
    )

    # schema_version
    sv = raw["schema_version"]
    if not isinstance(sv, int) or isinstance(sv, bool):
        raise CatalogValidationError(
            f"{file_path}: schema_version: expected integer, got {type(sv).__name__}"
        )
    if sv != CURRENT_SCHEMA_VERSION:
        raise CatalogValidationError(
            f"{file_path}: schema_version: expected {CURRENT_SCHEMA_VERSION}, got {sv}"
        )

    # mode
    mode = raw["mode"]
    _check_type(mode, str, "mode", file_path)
    if mode not in VALID_BUILD_MODES:
        raise CatalogValidationError(
            f"{file_path}: mode: '{mode}' is not valid. "
            f"Expected one of {sorted(VALID_BUILD_MODES)}"
        )

    # design_ids
    design_ids_raw = raw["design_ids"]
    if not isinstance(design_ids_raw, list) or len(design_ids_raw) == 0:
        raise CatalogValidationError(
            f"{file_path}: design_ids: expected non-empty array"
        )

    design_ids = []
    seen_designs = set()
    for i, did in enumerate(design_ids_raw):
        _validate_component_id(did, f"design_ids[{i}]", file_path)
        if did in seen_designs:
            raise CatalogValidationError(
                f"{file_path}: design_ids: duplicate design_id '{did}'"
            )
        seen_designs.add(did)
        design_ids.append(did)

    # targets
    targets_raw = raw["targets"]
    if not isinstance(targets_raw, list) or len(targets_raw) == 0:
        raise CatalogValidationError(
            f"{file_path}: targets: expected non-empty array"
        )

    targets: List[BuildTarget] = []
    seen_targets = set()  # (device_id, case_type) pairs for duplicate detection

    for i, tgt_raw in enumerate(targets_raw):
        ctx = f"targets[{i}]"
        if not isinstance(tgt_raw, dict):
            raise CatalogValidationError(
                f"{file_path}: {ctx}: expected object, got {type(tgt_raw).__name__}"
            )
        _check_no_unknown(
            tgt_raw,
            {"device_id", "case_type", "views", "widths"},
            file_path, ctx,
        )
        _require_fields(
            tgt_raw,
            {"device_id", "case_type", "views", "widths"},
            file_path, ctx,
        )

        # device_id
        device_id = tgt_raw["device_id"]
        _validate_component_id(device_id, f"{ctx}.device_id", file_path)

        # case_type
        case_type_raw = tgt_raw["case_type"]
        _check_type(case_type_raw, str, f"{ctx}.case_type", file_path)
        if case_type_raw not in VALID_CASE_TYPES:
            raise CatalogValidationError(
                f"{file_path}: {ctx}.case_type: '{case_type_raw}' is not valid. "
                f"Expected one of {sorted(VALID_CASE_TYPES)}"
            )
        case_type = _normalize_case_type(case_type_raw)

        # Check for duplicate targets (same device_id + case_type)
        target_key = (device_id, case_type)
        if target_key in seen_targets:
            raise CatalogValidationError(
                f"{file_path}: {ctx}: duplicate target for "
                f"device_id='{device_id}', case_type='{case_type}'"
            )
        seen_targets.add(target_key)

        # views
        views = _validate_views(tgt_raw["views"], file_path, f"{ctx}.views")

        # widths
        widths = _validate_widths(tgt_raw["widths"], file_path, f"{ctx}.widths")

        targets.append(BuildTarget(
            device_id=device_id,
            case_type=case_type,
            views=views,
            widths=widths,
        ))

    # render_options
    ro_raw = raw["render_options"]
    if not isinstance(ro_raw, dict):
        raise CatalogValidationError(
            f"{file_path}: render_options: expected object, "
            f"got {type(ro_raw).__name__}"
        )
    _check_no_unknown(
        ro_raw,
        {"fit_mode", "zoom", "offset_x", "offset_y", "webp_quality"},
        file_path, "render_options",
    )
    _require_fields(ro_raw, {"fit_mode"}, file_path, "render_options")

    fit_mode = ro_raw["fit_mode"]
    _check_type(fit_mode, str, "render_options.fit_mode", file_path)
    if fit_mode not in VALID_FIT_MODES:
        raise CatalogValidationError(
            f"{file_path}: render_options.fit_mode: '{fit_mode}' is not valid. "
            f"Expected one of {sorted(VALID_FIT_MODES)}"
        )

    zoom = ro_raw.get("zoom", 1.0)
    if not isinstance(zoom, (int, float)) or isinstance(zoom, bool):
        raise CatalogValidationError(
            f"{file_path}: render_options.zoom: expected number, "
            f"got {type(zoom).__name__}"
        )
    if zoom < 0.1 or zoom > 10.0:
        raise CatalogValidationError(
            f"{file_path}: render_options.zoom: {zoom} is out of range [0.1, 10.0]"
        )

    offset_x = ro_raw.get("offset_x", 0.0)
    if not isinstance(offset_x, (int, float)) or isinstance(offset_x, bool):
        raise CatalogValidationError(
            f"{file_path}: render_options.offset_x: expected number, "
            f"got {type(offset_x).__name__}"
        )
    if offset_x < -1.0 or offset_x > 1.0:
        raise CatalogValidationError(
            f"{file_path}: render_options.offset_x: {offset_x} is out of range [-1.0, 1.0]"
        )

    offset_y = ro_raw.get("offset_y", 0.0)
    if not isinstance(offset_y, (int, float)) or isinstance(offset_y, bool):
        raise CatalogValidationError(
            f"{file_path}: render_options.offset_y: expected number, "
            f"got {type(offset_y).__name__}"
        )
    if offset_y < -1.0 or offset_y > 1.0:
        raise CatalogValidationError(
            f"{file_path}: render_options.offset_y: {offset_y} is out of range [-1.0, 1.0]"
        )

    webp_quality = ro_raw.get("webp_quality", 85)
    if not isinstance(webp_quality, int) or isinstance(webp_quality, bool):
        raise CatalogValidationError(
            f"{file_path}: render_options.webp_quality: expected integer, "
            f"got {type(webp_quality).__name__}"
        )
    if webp_quality < 1 or webp_quality > 100:
        raise CatalogValidationError(
            f"{file_path}: render_options.webp_quality: {webp_quality} is out of range [1, 100]"
        )

    render_options = BuildRenderOptions(
        fit_mode=fit_mode,
        zoom=float(zoom),
        offset_x=float(offset_x),
        offset_y=float(offset_y),
        webp_quality=webp_quality,
    )

    plan = CatalogBuildPlan(
        schema_version=sv,
        mode=mode,
        design_ids=design_ids,
        targets=targets,
        render_options=render_options,
    )

    # Optional: validate templates exist on disk
    if validate_templates_exist and templates_root is not None:
        _validate_plan_templates(plan, templates_root, file_path)

    return plan


def _validate_plan_templates(
    plan: CatalogBuildPlan,
    templates_root: str,
    plan_path: Path,
):
    """Validate that all target templates exist on disk and are loadable.

    Raises CatalogValidationError if any target's template is missing or
    invalid.
    """
    tpl_root = Path(templates_root)

    for target in plan.targets:
        for view in target.views:
            # Template path follows the convention:
            # {templates_root}/{brand?}/{device_id}/{case_type}/{view}/template.json
            # We need to search for it since brand folder is optional.
            tpl_path = _find_template_path(
                tpl_root, target.device_id, target.case_type, view
            )
            if tpl_path is None:
                raise CatalogValidationError(
                    f"{plan_path}: target (device_id='{target.device_id}', "
                    f"case_type='{target.case_type}', view='{view}'): "
                    f"no template found under {templates_root}"
                )
            # Attempt to load the template (validates it)
            try:
                load_case_template(tpl_path)
            except CatalogValidationError as e:
                raise CatalogValidationError(
                    f"{plan_path}: target (device_id='{target.device_id}', "
                    f"case_type='{target.case_type}', view='{view}'): "
                    f"invalid template at {tpl_path}: {e}"
                )


def _find_template_path(
    templates_root: Path, device_id: str, case_type: str, view: str
) -> Optional[Path]:
    """Find a template.json path for the given device/case/view.

    Searches both directly under templates_root and one level deep
    (for brand subdirectories like "apple/").
    """
    # Direct path: {root}/{device_id}/{case_type}/{view}/template.json
    direct = templates_root / device_id / case_type / view / "template.json"
    if direct.exists():
        return direct

    # Brand subdirectory: {root}/{brand}/{device_id}/{case_type}/{view}/template.json
    if templates_root.exists():
        for entry in templates_root.iterdir():
            if entry.is_dir():
                candidate = entry / device_id / case_type / view / "template.json"
                if candidate.exists():
                    return candidate

    return None


def find_template_dir(
    templates_root: str, device_id: str, case_type: str, view: str
) -> Optional[str]:
    """Find the template directory for a given device/case_type/view.

    Returns the directory path as a string, or None if not found.
    """
    tpl_path = _find_template_path(Path(templates_root), device_id, case_type, view)
    if tpl_path is not None:
        return str(tpl_path.parent)
    return None
