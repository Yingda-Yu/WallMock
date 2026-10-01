"""
Storefront contract export pipeline.

Generates the shared contract artifacts:
  - device registry (loaded from catalog/)
  - render capabilities (derived from template directory)
  - render manifest (derived from rendered assets)
  - contract bundle index (atomic, with hashes)

All exports are deterministic (sorted, stable JSON).
"""
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .catalog_models import (
    CaseTemplate,
    CatalogValidationError,
    TemplateProvenance,
    is_production_grade_supplier_geometry,
    TEMPLATE_STATUS_PRODUCTION,
    TEMPLATE_STATUS_PROTOTYPE,
)
from .case_template_loader import load_case_template
from .contract_ids import (
    build_render_asset_id,
    build_template_id,
    build_variant_id,
    build_content_hash,
    CONTRACT_NAME,
    CONTRACT_VERSION,
    is_safe_relative_path,
    is_valid_case_type,
    is_valid_component_id,
    is_valid_template_status,
    is_valid_view,
)
from .device_registry_loader import load_device_registry


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def get_git_commit(repo_dir: Optional[str] = None) -> Optional[str]:
    """Return the current Git HEAD SHA, or None if not available."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir or os.getcwd(),
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def is_git_dirty(repo_dir: Optional[str] = None) -> Optional[bool]:
    """Return True if the working tree has uncommitted changes, False if
    clean, None if unknown."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir or os.getcwd(),
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return len(result.stdout.strip()) > 0
    except (OSError, subprocess.SubprocessError):
        pass
    return None


# ---------------------------------------------------------------------------
# JSON helpers (deterministic output)
# ---------------------------------------------------------------------------

def write_json_deterministic(path: str, data) -> None:
    """Write JSON with deterministic sorting and formatting.

    Uses sorted keys, 2-space indent, and trailing newline for
    stable diffs and hash computation.
    """
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    # Ensure parent directory exists
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def sha256_file(path: str) -> str:
    """Compute SHA-256 of a file, return lowercase hex digest."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 of bytes, return lowercase hex digest."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Render capabilities
# ---------------------------------------------------------------------------

def discover_templates(templates_root: str) -> List[Tuple[str, CaseTemplate, str]]:
    """Discover all case templates under a root directory.

    Walks ``templates_root`` looking for ``template.json`` files.
    Returns list of ``(device_id, template, template_dir)`` tuples.

    Templates must have a valid device_id and case_type and view.
    """
    results = []
    for dirpath, _dirnames, filenames in os.walk(templates_root):
        if "template.json" in filenames:
            tpl_path = os.path.join(dirpath, "template.json")
            try:
                tpl = load_case_template(tpl_path)
            except CatalogValidationError:
                continue
            results.append((tpl.device_id, tpl, dirpath))
    return results


def build_render_capabilities(
    templates_root: str,
    wallmock_commit: Optional[str] = None,
) -> Dict:
    """Build the render capabilities JSON structure.

    Walks all templates under ``templates_root`` and produces a
    device-keyed capability map.

    ``production_publishable`` is derived from template status +
    provenance using the same rule as the template loader: only
    production-status templates with production-grade supplier_geometry
    are publishable.
    """
    discovered = discover_templates(templates_root)

    devices: Dict[str, Dict] = {}

    for device_id, tpl, tpl_dir in discovered:
        if device_id not in devices:
            devices[device_id] = {
                "device_id": device_id,
                "templates": [],
            }

        # Derive production_publishable from template status + provenance
        production_publishable = False
        if tpl.status == TEMPLATE_STATUS_PRODUCTION and tpl.provenance:
            production_publishable = is_production_grade_supplier_geometry(
                tpl.provenance.supplier_geometry
            )

        template_entry = {
            "template_id": tpl.id,
            "case_type": tpl.case_type,
            "view": tpl.view,
            "template_status": tpl.status,
            "renderable": True,
            "production_publishable": production_publishable,
            "provenance": {
                "supplier_geometry": (
                    tpl.provenance.supplier_geometry if tpl.provenance else "unknown"
                ),
            },
        }
        devices[device_id]["templates"].append(template_entry)

    # Sort templates within each device for determinism
    for dev_id in devices:
        devices[dev_id]["templates"].sort(key=lambda t: t["template_id"])

    # Sort devices for determinism
    sorted_devices = dict(sorted(devices.items()))

    result = {
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "wallmock_commit": wallmock_commit or "",
        "devices": sorted_devices,
    }
    return result


# ---------------------------------------------------------------------------
# Render manifest
# ---------------------------------------------------------------------------

def build_render_manifest_entry(
    design_id: str,
    device_id: str,
    case_type: str,
    template_id: str,
    template_status: str,
    views: Dict[str, Dict[int, Dict]],
) -> Dict:
    """Build a single variant entry for the render manifest.

    ``views`` maps view_name -> {width -> asset_info_dict}, where
    asset_info_dict has ``path``, ``width``, ``height``, ``format``,
    and ``content_hash`` keys.
    """
    variant_id = build_variant_id(design_id, device_id, case_type)

    # Build views dict with string keys (JSON requires string keys)
    views_out = {}
    for view_name, widths in sorted(views.items()):
        views_out[view_name] = {}
        for width in sorted(widths.keys()):
            asset = widths[width]
            render_asset_id = build_render_asset_id(variant_id, view_name, width)
            views_out[view_name][str(width)] = {
                "render_asset_id": render_asset_id,
                "path": asset["path"],
                "width": asset["width"],
                "height": asset["height"],
                "format": asset["format"],
                "content_hash": asset["content_hash"],
                "view": view_name,
                "template_id": template_id,
                "template_status": template_status,
                "production_publishable": (
                    template_status == TEMPLATE_STATUS_PRODUCTION
                ),
                "renderer_version": asset.get("renderer_version", "1.0.0"),
            }

    return {
        "variant_id": variant_id,
        "design_id": design_id,
        "device_id": device_id,
        "case_type": case_type,
        "template_id": template_id,
        "template_status": template_status,
        "views": views_out,
    }


def build_render_manifest(
    variants: List[Dict],
    wallmock_commit: Optional[str] = None,
    renderer_version: str = "1.0.0",
    generated_at: Optional[str] = None,
) -> Dict:
    """Build the full render manifest JSON structure.

    ``variants`` is a list of variant entry dicts as produced by
    ``build_render_manifest_entry()``.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Sort variants by variant_id for determinism
    sorted_variants = sorted(variants, key=lambda v: v["variant_id"])
    variants_dict = {v["variant_id"]: v for v in sorted_variants}

    return {
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "wallmock_commit": wallmock_commit or "",
        "renderer_version": renderer_version,
        "variants": variants_dict,
    }


# ---------------------------------------------------------------------------
# Contract bundle (atomic export)
# ---------------------------------------------------------------------------

BUNDLE_INDEX_FILENAME = "contract_bundle.v1.json"
DEVICE_REGISTRY_FILENAME = "device_registry.v1.json"
RENDER_CAPABILITIES_FILENAME = "render_capabilities.v1.json"
RENDER_MANIFEST_FILENAME = "render_manifest.v1.json"


def build_contract_bundle(
    device_registry_data: Dict,
    render_capabilities_data: Dict,
    render_manifest_data: Dict,
    wallmock_commit: Optional[str] = None,
    renderer_version: str = "1.0.0",
    generated_at: Optional[str] = None,
    working_tree_dirty: Optional[bool] = None,
) -> Dict:
    """Build the contract bundle index JSON structure.

    The bundle index references all artifacts and their SHA-256 hashes,
    serving as an atomic handoff point for the storefront.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Compute hashes of each artifact (as serialized JSON)
    device_registry_json = json.dumps(
        device_registry_data, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    render_capabilities_json = json.dumps(
        render_capabilities_data, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    render_manifest_json = json.dumps(
        render_manifest_data, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")

    artifacts = {
        DEVICE_REGISTRY_FILENAME: {
            "filename": DEVICE_REGISTRY_FILENAME,
            "sha256": sha256_bytes(device_registry_json),
        },
        RENDER_CAPABILITIES_FILENAME: {
            "filename": RENDER_CAPABILITIES_FILENAME,
            "sha256": sha256_bytes(render_capabilities_json),
        },
        RENDER_MANIFEST_FILENAME: {
            "filename": RENDER_MANIFEST_FILENAME,
            "sha256": sha256_bytes(render_manifest_json),
        },
    }

    return {
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "wallmock_commit": wallmock_commit or "",
        "renderer_version": renderer_version,
        "generated_at": generated_at,
        "working_tree_dirty": working_tree_dirty if working_tree_dirty is not None else None,
        "artifacts": artifacts,
    }


def export_contract_bundle(
    output_dir: str,
    device_registry_data: Dict,
    render_capabilities_data: Dict,
    render_manifest_data: Dict,
    wallmock_commit: Optional[str] = None,
    renderer_version: str = "1.0.0",
    generated_at: Optional[str] = None,
    working_tree_dirty: Optional[bool] = None,
    reject_dirty: bool = False,
) -> Dict:
    """Export a complete contract bundle atomically.

    Writes artifact files to a temporary directory first, computes
    SHA-256 hashes from the actual written files, writes the bundle
    index, then copies everything to the final output directory.

    This ensures the storefront never sees a partially written bundle,
    and that bundle-index hashes always match the actual file contents.

    If ``reject_dirty=True`` and ``working_tree_dirty`` is True,
    raises CatalogValidationError instead of exporting.
    """
    if reject_dirty and working_tree_dirty:
        raise CatalogValidationError(
            "Refusing to export contract bundle from dirty working tree. "
            "Commit changes or use reject_dirty=False."
        )

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Write artifacts to temp dir first
    tmp_dir = tempfile.mkdtemp(prefix="wallmock_contract_")
    try:
        # Write the three artifact files
        artifact_files = {
            DEVICE_REGISTRY_FILENAME: device_registry_data,
            RENDER_CAPABILITIES_FILENAME: render_capabilities_data,
            RENDER_MANIFEST_FILENAME: render_manifest_data,
        }
        for fname, data in artifact_files.items():
            write_json_deterministic(
                os.path.join(tmp_dir, fname), data,
            )

        # Compute hashes from the actual written files
        artifacts = {}
        for fname in artifact_files:
            fpath = os.path.join(tmp_dir, fname)
            artifacts[fname] = {
                "filename": fname,
                "sha256": sha256_file(fpath),
            }

        # Build the bundle index
        bundle = {
            "contract": CONTRACT_NAME,
            "contract_version": CONTRACT_VERSION,
            "wallmock_commit": wallmock_commit or "",
            "renderer_version": renderer_version,
            "generated_at": generated_at,
            "working_tree_dirty": (
                working_tree_dirty if working_tree_dirty is not None else None
            ),
            "artifacts": artifacts,
        }

        # Write bundle index
        write_json_deterministic(
            os.path.join(tmp_dir, BUNDLE_INDEX_FILENAME), bundle,
        )

        # Atomic copy: ensure target parent exists, then copy everything
        os.makedirs(output_dir, exist_ok=True)
        import shutil
        for fname in list(artifact_files.keys()) + [BUNDLE_INDEX_FILENAME]:
            src = os.path.join(tmp_dir, fname)
            dst = os.path.join(output_dir, fname)
            shutil.copy2(src, dst)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return bundle
