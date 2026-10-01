"""
Canonical device registry loader.

Loads and validates ``device_registry.v1.json``, producing a list of
``Device`` domain objects. The registry is the authoritative source of
shared device identities between WallMock and the storefront.
"""
import json
import os
from typing import Dict, List

from .catalog_models import CatalogValidationError, Device
from .contract_ids import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    is_valid_component_id,
)


def _check_type(value, expected_type, field_name, file_path):
    if not isinstance(value, expected_type):
        raise CatalogValidationError(
            f"{file_path}: {field_name}: expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )


def _check_no_unknown(obj, allowed_keys, file_path, obj_name):
    unknown = set(obj.keys()) - allowed_keys
    if unknown:
        raise CatalogValidationError(
            f"{file_path}: {obj_name}: unknown field(s): {sorted(unknown)}"
        )


def _require_fields(obj, required_fields, file_path, obj_name):
    missing = set(required_fields) - set(obj.keys())
    if missing:
        raise CatalogValidationError(
            f"{file_path}: {obj_name}: missing required field(s): {sorted(missing)}"
        )


def load_device_registry(file_path: str) -> Dict:
    """Load and validate a device registry JSON file.

    Returns a dict with keys:
      - ``contract`` (str) — contract name
      - ``contract_version`` (int) — contract version
      - ``devices`` (List[Device]) — list of Device objects
      - ``device_map`` (Dict[str, Device]) — devices keyed by device_id

    Raises CatalogValidationError on any validation failure.
    """
    if not os.path.isfile(file_path):
        raise CatalogValidationError(
            f"{file_path}: device registry file not found"
        )

    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    _check_type(raw, dict, "root", file_path)

    # Top-level validation
    _check_no_unknown(
        raw,
        {"contract", "contract_version", "devices"},
        file_path, "device registry",
    )
    _require_fields(
        raw, {"contract", "contract_version", "devices"},
        file_path, "device registry",
    )

    # Contract identity
    contract = raw["contract"]
    _check_type(contract, str, "contract", file_path)
    if contract != CONTRACT_NAME:
        raise CatalogValidationError(
            f"{file_path}: contract name mismatch: expected '{CONTRACT_NAME}', "
            f"got '{contract}'"
        )

    cv = raw["contract_version"]
    _check_type(cv, int, "contract_version", file_path)
    if cv != CONTRACT_VERSION:
        raise CatalogValidationError(
            f"{file_path}: contract_version mismatch: expected "
            f"{CONTRACT_VERSION}, got {cv}"
        )

    # Devices array
    devices_raw = raw["devices"]
    _check_type(devices_raw, list, "devices", file_path)

    devices: List[Device] = []
    seen_ids = set()

    for i, dev_raw in enumerate(devices_raw):
        ctx = f"devices[{i}]"
        _check_type(dev_raw, dict, ctx, file_path)

        _check_no_unknown(
            dev_raw,
            {"device_id", "brand", "family", "display_name",
             "generation", "aliases", "sort_order", "active_identity"},
            file_path, ctx,
        )
        _require_fields(
            dev_raw, {"device_id", "brand", "family", "display_name"},
            file_path, ctx,
        )

        device_id = dev_raw["device_id"]
        _check_type(device_id, str, f"{ctx}.device_id", file_path)
        if not is_valid_component_id(device_id):
            raise CatalogValidationError(
                f"{file_path}: {ctx}.device_id: invalid format '{device_id}'. "
                f"Must be lowercase kebab-case, no double underscores."
            )

        if device_id in seen_ids:
            raise CatalogValidationError(
                f"{file_path}: {ctx}.device_id: duplicate device_id '{device_id}'"
            )
        seen_ids.add(device_id)

        brand = dev_raw["brand"]
        _check_type(brand, str, f"{ctx}.brand", file_path)

        family = dev_raw["family"]
        _check_type(family, str, f"{ctx}.family", file_path)

        display_name = dev_raw["display_name"]
        _check_type(display_name, str, f"{ctx}.display_name", file_path)

        generation = dev_raw.get("generation", "")
        _check_type(generation, str, f"{ctx}.generation", file_path)

        aliases = dev_raw.get("aliases", [])
        _check_type(aliases, list, f"{ctx}.aliases", file_path)
        for j, alias in enumerate(aliases):
            _check_type(alias, str, f"{ctx}.aliases[{j}]", file_path)

        sort_order = dev_raw.get("sort_order", 0)
        _check_type(sort_order, int, f"{ctx}.sort_order", file_path)

        active_identity = dev_raw.get("active_identity", True)
        _check_type(active_identity, bool, f"{ctx}.active_identity", file_path)

        devices.append(Device(
            device_id=device_id,
            brand=brand,
            family=family,
            display_name=display_name,
            generation=generation,
            aliases=list(aliases),
            sort_order=sort_order,
            active_identity=active_identity,
        ))

    # Sort by sort_order for deterministic output
    devices.sort(key=lambda d: (d.sort_order, d.device_id))

    device_map = {d.device_id: d for d in devices}

    return {
        "contract": contract,
        "contract_version": cv,
        "devices": devices,
        "device_map": device_map,
    }
