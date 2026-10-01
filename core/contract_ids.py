"""Shared WallMock ↔ storefront contract: identity tokens, ID builders,
parsers, and validation.

All values in this module are part of the shared v1 contract.
Do not change them without incrementing contract_version and
reconciling with the storefront.
"""
import re
from dataclasses import dataclass
from typing import Tuple

# ---------------------------------------------------------------------------
# Contract identity
# ---------------------------------------------------------------------------

CONTRACT_NAME = "spartina-device-render-catalog"
CONTRACT_VERSION = 1

# ---------------------------------------------------------------------------
# Shared token vocabularies — frozen for v1
# ---------------------------------------------------------------------------

# Case type tokens shared between WallMock and storefront.
# NOTE: v1 uses "clear" not "transparent". Internal legacy "transparent"
# inputs must be normalized to "clear" before export.
CASE_TYPES_V1 = frozenset({"hard", "tough", "magsafe", "clear", "soft"})

# View tokens shared between WallMock and storefront.
VIEWS_V1 = frozenset({"rear", "angle", "front", "closeup"})

# Template status tokens (matches catalog_models VALID_TEMPLATE_STATUSES).
TEMPLATE_STATUSES_V1 = frozenset({"prototype", "production"})

# Render asset format for v1 storefront assets.
RENDER_ASSET_FORMAT_V1 = "webp"

# Content hash algorithm.
CONTENT_HASH_ALGORITHM = "sha256"
CONTENT_HASH_PREFIX = "sha256:"

# ---------------------------------------------------------------------------
# Component ID grammar
# ---------------------------------------------------------------------------

# Component IDs are lowercase kebab-case. No double underscores allowed
# because __ is the composite-ID separator.
_COMPONENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Render asset width: positive integer, used in w{width} suffix.
_WIDTH_RE = re.compile(r"^\d+$")

# Composite ID separator (must not appear in any component ID).
COMPOSITE_SEP = "__"


def is_valid_component_id(value: str) -> bool:
    """Return True if ``value`` is a valid component-level shared ID.

    Valid component IDs are lowercase kebab-case starting with a
    letter/digit and containing only letters, digits, and hyphens.
    Crucially, they may NOT contain ``__`` (the composite separator).
    """
    if not isinstance(value, str):
        return False
    if COMPOSITE_SEP in value:
        return False
    return bool(_COMPONENT_ID_RE.match(value))


def is_valid_case_type(value: str) -> bool:
    """Return True if ``value`` is a v1 shared case_type token."""
    return isinstance(value, str) and value in CASE_TYPES_V1


def is_valid_view(value: str) -> bool:
    """Return True if ``value`` is a v1 shared view token."""
    return isinstance(value, str) and value in VIEWS_V1


def is_valid_template_status(value: str) -> bool:
    """Return True if ``value`` is a v1 template status token."""
    return isinstance(value, str) and value in TEMPLATE_STATUSES_V1


# ---------------------------------------------------------------------------
# Composite ID builders
# ---------------------------------------------------------------------------

def build_template_id(device_id: str, case_type: str, view: str) -> str:
    """Build a template_id from its components.

    Format: ``{device_id}__{case_type}__{view}``
    Example: ``iphone-17e__hard__rear``
    """
    if not is_valid_component_id(device_id):
        raise ValueError(f"Invalid device_id for template_id: {device_id!r}")
    if not is_valid_case_type(case_type):
        raise ValueError(f"Invalid case_type for template_id: {case_type!r}")
    if not is_valid_view(view):
        raise ValueError(f"Invalid view for template_id: {view!r}")
    return f"{device_id}{COMPOSITE_SEP}{case_type}{COMPOSITE_SEP}{view}"


def build_variant_id(design_id: str, device_id: str, case_type: str) -> str:
    """Build a variant_id from its components.

    Format: ``{design_id}__{device_id}__{case_type}``
    Example: ``blue-hydrangea__iphone-17e__hard``
    """
    if not is_valid_component_id(design_id):
        raise ValueError(f"Invalid design_id for variant_id: {design_id!r}")
    if not is_valid_component_id(device_id):
        raise ValueError(f"Invalid device_id for variant_id: {device_id!r}")
    if not is_valid_case_type(case_type):
        raise ValueError(f"Invalid case_type for variant_id: {case_type!r}")
    return f"{design_id}{COMPOSITE_SEP}{device_id}{COMPOSITE_SEP}{case_type}"


def build_render_asset_id(variant_id: str, view: str, width: int) -> str:
    """Build a render_asset_id from variant_id + view + width.

    Format: ``{variant_id}__{view}__w{width}``
    Example: ``blue-hydrangea__iphone-17e__hard__rear__w1200``

    Render asset IDs are opaque deterministic values — consumers should
    store the ID and not split it to recover business semantics.
    """
    # Validate variant_id by attempting to parse it (ensures 3 components)
    parse_variant_id(variant_id)  # raises on invalid
    if not is_valid_view(view):
        raise ValueError(f"Invalid view for render_asset_id: {view!r}")
    if not isinstance(width, int) or width <= 0:
        raise ValueError(f"Invalid width for render_asset_id: {width!r}")
    return f"{variant_id}{COMPOSITE_SEP}{view}{COMPOSITE_SEP}w{width}"


# ---------------------------------------------------------------------------
# Composite ID parsers
# ---------------------------------------------------------------------------

def parse_template_id(template_id: str) -> Tuple[str, str, str]:
    """Parse a template_id into ``(device_id, case_type, view)``.

    Raises ValueError on invalid format.
    """
    if not isinstance(template_id, str):
        raise ValueError(f"template_id must be str, got {type(template_id).__name__}")
    parts = template_id.split(COMPOSITE_SEP)
    if len(parts) != 3:
        raise ValueError(
            f"Invalid template_id {template_id!r}: "
            f"expected 3 components separated by '{COMPOSITE_SEP}', got {len(parts)}"
        )
    device_id, case_type, view = parts
    if not is_valid_component_id(device_id):
        raise ValueError(f"Invalid device_id in template_id: {device_id!r}")
    if not is_valid_case_type(case_type):
        raise ValueError(f"Invalid case_type in template_id: {case_type!r}")
    if not is_valid_view(view):
        raise ValueError(f"Invalid view in template_id: {view!r}")
    return device_id, case_type, view


def parse_variant_id(variant_id: str) -> Tuple[str, str, str]:
    """Parse a variant_id into ``(design_id, device_id, case_type)``.

    Raises ValueError on invalid format.
    """
    if not isinstance(variant_id, str):
        raise ValueError(f"variant_id must be str, got {type(variant_id).__name__}")
    parts = variant_id.split(COMPOSITE_SEP)
    if len(parts) != 3:
        raise ValueError(
            f"Invalid variant_id {variant_id!r}: "
            f"expected 3 components separated by '{COMPOSITE_SEP}', got {len(parts)}"
        )
    design_id, device_id, case_type = parts
    if not is_valid_component_id(design_id):
        raise ValueError(f"Invalid design_id in variant_id: {design_id!r}")
    if not is_valid_component_id(device_id):
        raise ValueError(f"Invalid device_id in variant_id: {device_id!r}")
    if not is_valid_case_type(case_type):
        raise ValueError(f"Invalid case_type in variant_id: {case_type!r}")
    return design_id, device_id, case_type


# ---------------------------------------------------------------------------
# Content hash helpers
# ---------------------------------------------------------------------------

def build_content_hash(hexdigest: str) -> str:
    """Build a content_hash string from a lowercase hex digest."""
    if not isinstance(hexdigest, str):
        raise ValueError("hexdigest must be a string")
    hexdigest = hexdigest.strip().lower()
    if not re.match(r"^[0-9a-f]{64}$", hexdigest):
        raise ValueError(
            f"Invalid SHA-256 hex digest: expected 64 lowercase hex chars, "
            f"got {len(hexdigest)} chars"
        )
    return f"{CONTENT_HASH_PREFIX}{hexdigest}"


def is_valid_content_hash(value: str) -> bool:
    """Return True if ``value`` is a valid v1 content_hash string."""
    if not isinstance(value, str):
        return False
    if not value.startswith(CONTENT_HASH_PREFIX):
        return False
    hex_part = value[len(CONTENT_HASH_PREFIX):]
    return bool(re.match(r"^[0-9a-f]{64}$", hex_part))


# ---------------------------------------------------------------------------
# Asset path safety
# ---------------------------------------------------------------------------

_SAFE_PATH_RE = re.compile(
    r"^[a-z0-9][a-z0-9-_/.]*[a-z0-9](\.[a-z0-9]+)?$"
)


def is_safe_relative_path(path: str) -> bool:
    """Return True if ``path`` is a safe relative POSIX asset path.

    Safe means:
      - relative (no leading /)
      - no .. (no path traversal)
      - no absolute Windows-style paths (no drive letters)
      - only lowercase alphanumeric, hyphens, underscores, dots, and slashes
      - no empty path components (no //)
      - has a file extension
    """
    if not isinstance(path, str):
        return False
    if not path:
        return False
    # No absolute paths
    if path.startswith("/") or path.startswith("\\"):
        return False
    # No Windows drive letters
    if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
        return False
    # No path traversal
    if ".." in path.split("/"):
        return False
    # No empty components
    if "//" in path:
        return False
    # Must have a file extension
    if "." not in path.split("/")[-1]:
        return False
    # Character check: lowercase alphanumeric + - _ . /
    # (already implied by no-traversal, but explicit is safe)
    return bool(_SAFE_PATH_RE.match(path))
