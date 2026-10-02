"""
Deterministic render fingerprinting for WallMock catalog builds.

Computes a SHA-256 hash that uniquely identifies a render output based on:
  - Design source bytes
  - Template JSON
  - All template layer bytes (base.png, print_mask.png, overlay.png,
    highlight.png, shadow.png)
  - Renderer version
  - View name
  - Output width
  - Fit mode and other render options

Importantly, does NOT hash:
  - Timestamps, random values
  - Absolute paths or mtimes
  - Anything non-deterministic

This fingerprint is used for incremental build caching — if the
fingerprint hasn't changed and the output file exists, the render
can be skipped.
"""
import hashlib
import json
from pathlib import Path
from typing import Optional, Any

from .catalog_models import CaseTemplate


RENDERER_VERSION = "1.0.0"

# Standard template layer files to hash (in deterministic order).
# These are the common layer files referenced by case templates.
_TEMPLATE_LAYER_FILES = [
    "base.png",
    "print_mask.png",
    "overlay.png",
    "highlight.png",
    "shadow.png",
]


def _hash_file(h: Any, path: Path) -> bool:
    """Hash the contents of a file. Returns True if file exists, False otherwise.

    Missing files are skipped silently — the hash is of what exists.
    """
    if not path.exists():
        return False
    # Include filename in hash so the same bytes at different positions
    # produce different hashes.
    h.update(f"file:{path.name}:".encode("utf-8"))
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    h.update(b":endfile;")
    return True


def _hash_bytes(h: Any, label: str, data: bytes):
    """Hash labeled bytes into the hash context."""
    h.update(f"{label}:{len(data)}:".encode("utf-8"))
    h.update(data)
    h.update(b";")


def _hash_string(h: Any, label: str, value: str):
    """Hash a labeled string value."""
    _hash_bytes(h, label, value.encode("utf-8"))


def _hash_float(h: Any, label: str, value: float):
    """Hash a labeled float value with fixed precision to avoid
    floating-point representation issues.
    """
    # Use repr with 10 decimal digits of precision — more than enough
    # for render parameters which are typically 1-2 decimal digits.
    _hash_string(h, label, f"{value:.10f}")


def _hash_int(h: Any, label: str, value: int):
    """Hash a labeled integer value."""
    _hash_string(h, label, str(value))


def compute_render_fingerprint(
    design_path: str,
    template: CaseTemplate,
    template_dir: str,
    view: str,
    width: int,
    render_options: dict,
) -> str:
    """Compute a deterministic SHA-256 fingerprint for a render.

    The fingerprint captures everything that affects the visual output,
    so two renders with the same fingerprint will produce identical
    image bytes.

    Parameters
    ----------
    design_path : str
        Path to the design artwork file.
    template : CaseTemplate
        The loaded case template dataclass.
    template_dir : str
        Directory containing the template's layer files.
    view : str
        View name (rear, angle, front, closeup).
    width : int
        Output width in pixels.
    render_options : dict
        Dict of render options (fit_mode, zoom, offset_x, offset_y, etc.).

    Returns
    -------
    str
        "sha256:<64 hex chars>" fingerprint string.
    """
    h = hashlib.sha256()

    tpl_dir = Path(template_dir)

    # Renderer version (bump this if the rendering algorithm changes)
    _hash_string(h, "renderer_version", RENDERER_VERSION)

    # Design source bytes
    design_p = Path(design_path)
    _hash_string(h, "design_filename", design_p.name)
    _hash_file(h, design_p)

    # Template JSON (serialized deterministically)
    # We serialize the template dict in a sorted way for determinism.
    tpl_dict = _template_to_dict(template)
    tpl_json = json.dumps(tpl_dict, sort_keys=True, separators=(",", ":"))
    _hash_bytes(h, "template_json", tpl_json.encode("utf-8"))

    # Template layer files (in deterministic order)
    for layer_file in _TEMPLATE_LAYER_FILES:
        layer_path = tpl_dir / layer_file
        if layer_path.exists():
            _hash_file(h, layer_path)

    # View
    _hash_string(h, "view", view)

    # Output width
    _hash_int(h, "width", width)

    # Render options (deterministic order)
    fit_mode = render_options.get("fit_mode", "cover")
    zoom = render_options.get("zoom", 1.0)
    offset_x = render_options.get("offset_x", 0.0)
    offset_y = render_options.get("offset_y", 0.0)
    webp_quality = render_options.get("webp_quality", 85)

    _hash_string(h, "fit_mode", fit_mode)
    _hash_float(h, "zoom", float(zoom))
    _hash_float(h, "offset_x", float(offset_x))
    _hash_float(h, "offset_y", float(offset_y))
    _hash_int(h, "webp_quality", int(webp_quality))

    return f"sha256:{h.hexdigest()}"


def _template_to_dict(template: CaseTemplate) -> dict:
    """Convert a CaseTemplate to a JSON-serializable dict for hashing.

    Only includes fields that affect rendering output.
    """
    return {
        "schema_version": template.schema_version,
        "id": template.id,
        "device_id": template.device_id,
        "case_type": template.case_type,
        "view": template.view,
        "canvas": {
            "width": template.canvas.width,
            "height": template.canvas.height,
        },
        "print_region": {
            "mode": template.print_region.mode,
            "x": template.print_region.x,
            "y": template.print_region.y,
            "width": template.print_region.width,
            "height": template.print_region.height,
            "fit": template.print_region.fit,
            "mask": template.print_region.mask or "",
        },
        "layers": [
            {
                "type": layer.type,
                "file": layer.file or "",
                "blend": layer.blend,
                "opacity": layer.opacity,
            }
            for layer in template.layers
        ],
    }


def fingerprint_prefix(fingerprint: str, length: int = 12) -> str:
    """Extract a short hash prefix from a fingerprint string.

    Parameters
    ----------
    fingerprint : str
        Full fingerprint like "sha256:abc123def456..."
    length : int
        Number of hex characters to use (default 12).

    Returns
    -------
    str
        The first `length` hex characters of the hash.
    """
    if not fingerprint.startswith("sha256:"):
        raise ValueError(f"Invalid fingerprint format: {fingerprint}")
    hex_part = fingerprint[len("sha256:"):]
    if len(hex_part) < length:
        raise ValueError(
            f"Fingerprint hex part too short ({len(hex_part)} chars) "
            f"for prefix length {length}"
        )
    return hex_part[:length]
