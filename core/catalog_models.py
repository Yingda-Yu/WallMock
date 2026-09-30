"""
Domain models for the WallMock 2.0 case catalog.

These dataclasses represent business/catalog objects (Device, CaseTemplate,
Design, VariantAvailability). They are intentionally independent from Pillow
image objects — the rendering layer converts these into images later.

All models are frozen (immutable) to support deterministic rendering and
content hashing.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Device:
    """An exact sellable phone model.

    The registry is data-driven. Do not bake model names into Python conditionals.
    """
    id: str
    brand: str
    family: str
    display_name: str
    aliases: List[str] = field(default_factory=list)
    active: bool = True


# ---------------------------------------------------------------------------
# Case template
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Canvas:
    """Output canvas dimensions for a case template."""
    width: int
    height: int


@dataclass(frozen=True)
class PrintRegion:
    """Defines where artwork is placed on the case body.

    Phase 1 requires ``mode='mask'``. The schema is designed so Phase 2
    can add ``mode='quad'`` (perspective transform) without breaking
    existing templates.
    """
    mode: str          # "mask" | "quad"
    x: int
    y: int
    width: int
    height: int
    fit: str           # "cover" | "contain" | "tile"
    mask: Optional[str] = None   # filename relative to template dir


@dataclass(frozen=True)
class CaseTemplateLayer:
    """A single compositing layer in the case template stack.

    Layer types:
      - base:       neutral phone/case body underneath artwork
      - artwork:    placeholder for the design artwork (no file)
      - print_mask: alias for mask defined in print_region
      - highlight:  optional glossy/material lighting layer
      - overlay:    camera rings, edges, buttons, rim (non-print areas)
      - shadow:     optional precomputed transparent shadow
    """
    type: str          # "base" | "artwork" | "highlight" | "overlay" | "shadow"
    file: Optional[str] = None   # filename relative to template dir
    blend: str = "normal"
    opacity: float = 1.0


@dataclass(frozen=True)
class CaseTemplate:
    """A reusable case template representing ``device x case_type x view``.

    Example: ``iphone-17e x hard x rear``
    """
    schema_version: int
    id: str
    device_id: str
    case_type: str
    view: str
    canvas: Canvas
    print_region: PrintRegion
    layers: List[CaseTemplateLayer]


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Design:
    """Aesthetic/product design, independent of phone model.

    A design may have case artwork only, wallpaper only, or both.
    The system must not assume both are always present.
    """
    schema_version: int
    id: str
    display_name: str
    case_artwork: Optional[str] = None
    wallpaper_artwork: Optional[str] = None
    case_fit_mode: str = "cover"
    focal_point: Tuple[float, float] = (0.5, 0.5)
    tags: List[str] = field(default_factory=list)
    active: bool = True


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VariantAvailability:
    """Maps a design x device x case_type to availability.

    Rendering capability is NOT inventory availability.
    Do not publish a variant just because WallMock can render it.
    """
    variant_id: str
    design_id: str
    device_id: str
    case_type: str
    available: bool
    supplier_sku: Optional[str] = None
    supplier_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Validation error
# ---------------------------------------------------------------------------

class CatalogValidationError(ValueError):
    """Raised when a catalog manifest is malformed or invalid.

    The message always includes the file path and the specific field
    that caused the failure, so callers can fix the issue without
    guessing.
    """
