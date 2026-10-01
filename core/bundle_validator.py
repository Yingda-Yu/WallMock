"""
Bundle-level validator for the storefront contract.

Validates cross-object invariants across device registry, render
capabilities, and render manifest. Returns a machine-readable report.
"""
import json
import os
from typing import Dict, List, Optional, Tuple

from .catalog_models import CatalogValidationError, is_production_grade_supplier_geometry
from .contract_ids import (
    build_content_hash,
    build_render_asset_id,
    build_template_id,
    build_variant_id,
    CONTRACT_NAME,
    CONTRACT_VERSION,
    is_safe_relative_path,
    is_valid_case_type,
    is_valid_component_id,
    is_valid_content_hash,
    is_valid_template_status,
    is_valid_view,
    parse_template_id,
    parse_variant_id,
)
from .device_registry_loader import load_device_registry

# Template status constants (from catalog_models)
TEMPLATE_STATUS_PROTOTYPE = "prototype"
TEMPLATE_STATUS_PRODUCTION = "production"


class BundleValidationReport:
    """Machine-readable validation report."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: Dict = {}

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def error(self, msg: str):
        self.errors.append(msg)

    def warning(self, msg: str):
        self.warnings.append(msg)

    def to_dict(self) -> Dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
        }


def _load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_contract_bundle(
    bundle_dir: str,
    bundle_index_filename: str = "contract_bundle.v1.json",
) -> BundleValidationReport:
    """Validate a contract bundle directory end-to-end.

    Checks:
      - bundle index loads and has correct contract version
      - device registry loads and validates
      - render capabilities loads and validates
      - render manifest loads and validates
      - cross-object invariants (device refs, template refs, ID consistency,
        production eligibility, path safety, content hash format, etc.)

    Returns a BundleValidationReport with errors/warnings/info.
    """
    report = BundleValidationReport()

    bundle_path = os.path.join(bundle_dir, bundle_index_filename)
    if not os.path.isfile(bundle_path):
        report.error(f"Bundle index not found: {bundle_path}")
        return report

    try:
        bundle = _load_json(bundle_path)
    except (json.JSONDecodeError, OSError) as e:
        report.error(f"Failed to parse bundle index: {e}")
        return report

    # --- Bundle index basics ---
    if bundle.get("contract") != CONTRACT_NAME:
        report.error(
            f"Bundle contract mismatch: expected '{CONTRACT_NAME}', "
            f"got '{bundle.get('contract')}'"
        )
    if bundle.get("contract_version") != CONTRACT_VERSION:
        report.error(
            f"Bundle contract_version mismatch: expected {CONTRACT_VERSION}, "
            f"got {bundle.get('contract_version')}"
        )

    artifacts = bundle.get("artifacts", {})
    if not isinstance(artifacts, dict):
        report.error("Bundle artifacts must be an object")
        return report

    report.info["artifacts_count"] = len(artifacts)

    # --- Verify artifact files exist and hashes match ---
    for fname, art_info in artifacts.items():
        fpath = os.path.join(bundle_dir, fname)
        if not os.path.isfile(fpath):
            report.error(f"Missing artifact file: {fname}")
            continue
        expected_sha = art_info.get("sha256", "")
        if len(expected_sha) != 64:
            report.error(f"Invalid sha256 for {fname}: {expected_sha}")
            continue
        # Compute actual hash
        import hashlib
        h = hashlib.sha256()
        try:
            with open(fpath, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            actual_sha = h.hexdigest()
            if actual_sha != expected_sha:
                report.error(
                    f"SHA-256 mismatch for {fname}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )
        except OSError as e:
            report.error(f"Failed to read {fname}: {e}")

    # --- Load device registry ---
    dev_reg_path = os.path.join(bundle_dir, "device_registry.v1.json")
    device_map = {}
    try:
        reg_result = load_device_registry(dev_reg_path)
        device_map = reg_result["device_map"]
        report.info["devices_count"] = len(device_map)
    except CatalogValidationError as e:
        report.error(f"Device registry validation failed: {e}")
    except (json.JSONDecodeError, OSError) as e:
        report.error(f"Failed to load device registry: {e}")

    # --- Load render capabilities ---
    caps_path = os.path.join(bundle_dir, "render_capabilities.v1.json")
    caps = {}
    try:
        caps = _load_json(caps_path)
        if caps.get("contract") != CONTRACT_NAME:
            report.error(
                f"Render capabilities contract mismatch: "
                f"expected '{CONTRACT_NAME}', got '{caps.get('contract')}'"
            )
        if caps.get("contract_version") != CONTRACT_VERSION:
            report.error(
                f"Render capabilities contract_version mismatch: "
                f"expected {CONTRACT_VERSION}, got {caps.get('contract_version')}"
            )
    except (json.JSONDecodeError, OSError) as e:
        report.error(f"Failed to load render capabilities: {e}")

    caps_devices = caps.get("devices", {}) if isinstance(caps, dict) else {}

    # --- Load render manifest ---
    manifest_path = os.path.join(bundle_dir, "render_manifest.v1.json")
    manifest = {}
    try:
        manifest = _load_json(manifest_path)
        if manifest.get("contract") != CONTRACT_NAME:
            report.error(
                f"Render manifest contract mismatch: "
                f"expected '{CONTRACT_NAME}', got '{manifest.get('contract')}'"
            )
        if manifest.get("contract_version") != CONTRACT_VERSION:
            report.error(
                f"Render manifest contract_version mismatch: "
                f"expected {CONTRACT_VERSION}, got {manifest.get('contract_version')}"
            )
    except (json.JSONDecodeError, OSError) as e:
        report.error(f"Failed to load render manifest: {e}")

    manifest_variants = manifest.get("variants", {}) if isinstance(manifest, dict) else {}

    # --- Cross-object: every capability device exists in registry ---
    template_ids_seen = set()
    for dev_id, dev_data in caps_devices.items():
        if dev_id not in device_map:
            report.error(
                f"Render capabilities references unknown device_id: {dev_id}"
            )

        templates = dev_data.get("templates", []) if isinstance(dev_data, dict) else []
        for tpl in templates:
            tpl_id = tpl.get("template_id", "")
            if tpl_id in template_ids_seen:
                report.error(f"Duplicate template_id in capabilities: {tpl_id}")
            template_ids_seen.add(tpl_id)

            # Validate template_id components
            try:
                td, tc, tv = parse_template_id(tpl_id)
                if td != dev_id:
                    report.error(
                        f"Template {tpl_id}: device_id component '{td}' "
                        f"does not match parent device '{dev_id}'"
                    )
                if tc != tpl.get("case_type"):
                    report.error(
                        f"Template {tpl_id}: case_type component '{tc}' "
                        f"does not match template.case_type '{tpl.get('case_type')}'"
                    )
                if tv != tpl.get("view"):
                    report.error(
                        f"Template {tpl_id}: view component '{tv}' "
                        f"does not match template.view '{tpl.get('view')}'"
                    )
            except ValueError as e:
                report.error(f"Invalid template_id {tpl_id}: {e}")

            # Validate status
            status = tpl.get("template_status", "")
            if not is_valid_template_status(status):
                report.error(
                    f"Template {tpl_id}: invalid template_status '{status}'"
                )

            # Production eligibility invariant
            if tpl.get("production_publishable"):
                if status != TEMPLATE_STATUS_PRODUCTION:
                    report.error(
                        f"Template {tpl_id}: production_publishable=true "
                        f"but template_status='{status}' (must be 'production')"
                    )
                prov = tpl.get("provenance", {})
                sg = prov.get("supplier_geometry", "") if isinstance(prov, dict) else ""
                if not is_production_grade_supplier_geometry(sg):
                    report.error(
                        f"Template {tpl_id}: production_publishable=true "
                        f"but supplier_geometry='{sg}' is not production-grade"
                    )

    report.info["templates_count"] = len(template_ids_seen)

    # --- Cross-object: every manifest variant/template exists ---
    variant_ids_seen = set()
    asset_paths_seen = set()
    render_asset_ids_seen = set()

    for var_id, var_data in manifest_variants.items():
        if var_id in variant_ids_seen:
            report.error(f"Duplicate variant_id in manifest: {var_id}")
        variant_ids_seen.add(var_id)

        # Validate variant_id components
        try:
            vd, vdev, vct = parse_variant_id(var_id)
            if vd != var_data.get("design_id"):
                report.error(
                    f"Variant {var_id}: design_id component '{vd}' "
                    f"does not match variant.design_id '{var_data.get('design_id')}'"
                )
            if vdev != var_data.get("device_id"):
                report.error(
                    f"Variant {var_id}: device_id component '{vdev}' "
                    f"does not match variant.device_id '{var_data.get('device_id')}'"
                )
            if vct != var_data.get("case_type"):
                report.error(
                    f"Variant {var_id}: case_type component '{vct}' "
                    f"does not match variant.case_type '{var_data.get('case_type')}'"
                )
        except ValueError as e:
            report.error(f"Invalid variant_id {var_id}: {e}")

        # Device must exist in registry
        dev_id = var_data.get("device_id", "")
        if dev_id and dev_id not in device_map:
            report.error(
                f"Variant {var_id}: references unknown device_id '{dev_id}'"
            )

        # Template must exist in capabilities
        tpl_id = var_data.get("template_id", "")
        if tpl_id and tpl_id not in template_ids_seen:
            report.error(
                f"Variant {var_id}: template_id '{tpl_id}' not in capabilities"
            )

        # Template status consistency
        tpl_status = var_data.get("template_status", "")
        if not is_valid_template_status(tpl_status):
            report.error(
                f"Variant {var_id}: invalid template_status '{tpl_status}'"
            )

        # Check against capabilities template status
        if tpl_id in template_ids_seen:
            # Find the matching template in capabilities
            caps_tpl_status = None
            for cdev_id, cdev_data in caps_devices.items():
                for ctpl in cdev_data.get("templates", []):
                    if ctpl.get("template_id") == tpl_id:
                        caps_tpl_status = ctpl.get("template_status")
                        break
            if caps_tpl_status and caps_tpl_status != tpl_status:
                report.error(
                    f"Variant {var_id}: template_status '{tpl_status}' "
                    f"mismatches capabilities status '{caps_tpl_status}'"
                )

        # Validate views
        views = var_data.get("views", {}) if isinstance(var_data, dict) else {}
        for view_name, widths in views.items():
            if not is_valid_view(view_name):
                report.error(
                    f"Variant {var_id}: invalid view '{view_name}'"
                )

            if not isinstance(widths, dict):
                report.error(
                    f"Variant {var_id} view {view_name}: widths must be object"
                )
                continue

            widths_seen = set()
            for w_str, asset in widths.items():
                # Validate width
                try:
                    width = int(w_str)
                    if width <= 0:
                        report.error(
                            f"Variant {var_id} view {view_name}: "
                            f"non-positive width {w_str}"
                        )
                except (ValueError, TypeError):
                    report.error(
                        f"Variant {var_id} view {view_name}: "
                        f"invalid width key '{w_str}'"
                    )
                    continue

                if width in widths_seen:
                    report.error(
                        f"Variant {var_id} view {view_name}: "
                        f"duplicate width {width}"
                    )
                widths_seen.add(width)

                # Validate render_asset_id
                expected_raid = build_render_asset_id(var_id, view_name, width)
                actual_raid = asset.get("render_asset_id", "")
                if actual_raid != expected_raid:
                    report.error(
                        f"Variant {var_id} view {view_name} w{width}: "
                        f"render_asset_id mismatch. Expected {expected_raid}, "
                        f"got {actual_raid}"
                    )
                if actual_raid in render_asset_ids_seen:
                    report.error(
                        f"Duplicate render_asset_id: {actual_raid}"
                    )
                render_asset_ids_seen.add(actual_raid)

                # Validate path
                path = asset.get("path", "")
                if not is_safe_relative_path(path):
                    report.error(
                        f"Variant {var_id} view {view_name} w{width}: "
                        f"unsafe asset path '{path}'"
                    )
                if path in asset_paths_seen:
                    report.error(
                        f"Duplicate asset path: {path}"
                    )
                asset_paths_seen.add(path)

                # Validate content_hash
                ch = asset.get("content_hash", "")
                if not is_valid_content_hash(ch):
                    report.error(
                        f"Variant {var_id} view {view_name} w{width}: "
                        f"invalid content_hash '{ch}'"
                    )

                # Validate dimensions
                if not isinstance(asset.get("width"), int) or asset["width"] <= 0:
                    report.error(
                        f"Variant {var_id} view {view_name} w{width}: "
                        f"invalid asset width"
                    )
                if not isinstance(asset.get("height"), int) or asset["height"] <= 0:
                    report.error(
                        f"Variant {var_id} view {view_name} w{width}: "
                        f"invalid asset height"
                    )

                # Production publishable consistency
                prod_pub = asset.get("production_publishable")
                if prod_pub is None:
                    report.error(
                        f"Variant {var_id} view {view_name} w{width}: "
                        f"missing production_publishable"
                    )
                elif prod_pub and tpl_status != TEMPLATE_STATUS_PRODUCTION:
                    report.error(
                        f"Variant {var_id} view {view_name} w{width}: "
                        f"production_publishable=true but template_status="
                        f"'{tpl_status}'"
                    )

    report.info["variants_count"] = len(variant_ids_seen)
    report.info["render_assets_count"] = len(render_asset_ids_seen)

    # --- Check contract version consistency across all artifacts ---
    versions = set()
    for data in [bundle, caps, manifest]:
        v = data.get("contract_version") if isinstance(data, dict) else None
        if v is not None:
            versions.add(v)
    if len(versions) > 1:
        report.error(
            f"Inconsistent contract versions across bundle artifacts: {sorted(versions)}"
        )

    # --- Check wallmock_commit consistency ---
    commits = set()
    for data in [bundle, caps, manifest]:
        c = data.get("wallmock_commit") if isinstance(data, dict) else None
        if c:
            commits.add(c)
    if len(commits) > 1:
        report.warning(
            f"Inconsistent wallmock_commit across bundle artifacts: {sorted(commits)}"
        )

    return report
