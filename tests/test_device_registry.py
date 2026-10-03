"""Tests for device registry loader and validation."""
import json
import os
import pytest

from core.catalog_models import CatalogValidationError, Device
from core.contract_ids import CONTRACT_NAME, CONTRACT_VERSION
from core.device_registry_loader import load_device_registry


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "device_registry")


def _write_tmp(tmp_path, data, filename="device_registry.v1.json"):
    path = os.path.join(str(tmp_path), filename)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _valid_registry():
    return {
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "devices": [
            {
                "device_id": "iphone-17e",
                "brand": "apple",
                "family": "iphone",
                "generation": "17",
                "display_name": "iPhone 17e",
                "aliases": [],
                "sort_order": 17050,
                "active_identity": True,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Valid loading
# ---------------------------------------------------------------------------

class TestDeviceRegistryValid:
    def test_loads_valid_registry(self, tmp_path):
        path = _write_tmp(tmp_path, _valid_registry())
        result = load_device_registry(path)
        assert result["contract"] == CONTRACT_NAME
        assert result["contract_version"] == CONTRACT_VERSION
        assert len(result["devices"]) == 1
        assert len(result["device_map"]) == 1

    def test_returns_device_objects(self, tmp_path):
        path = _write_tmp(tmp_path, _valid_registry())
        result = load_device_registry(path)
        d = result["devices"][0]
        assert isinstance(d, Device)
        assert d.device_id == "iphone-17e"
        assert d.brand == "apple"
        assert d.family == "iphone"
        assert d.generation == "17"
        assert d.display_name == "iPhone 17e"
        assert d.aliases == []
        assert d.sort_order == 17050
        assert d.active_identity is True

    def test_device_map_lookup(self, tmp_path):
        path = _write_tmp(tmp_path, _valid_registry())
        result = load_device_registry(path)
        d = result["device_map"]["iphone-17e"]
        assert d.device_id == "iphone-17e"

    def test_sorted_by_sort_order(self, tmp_path):
        data = _valid_registry()
        data["devices"].append({
            "device_id": "iphone-17-pro",
            "brand": "apple",
            "family": "iphone",
            "generation": "17",
            "display_name": "iPhone 17 Pro",
            "sort_order": 17090,
            "active_identity": True,
        })
        data["devices"].insert(0, {
            "device_id": "iphone-16",
            "brand": "apple",
            "family": "iphone",
            "generation": "16",
            "display_name": "iPhone 16",
            "sort_order": 16000,
            "active_identity": True,
        })
        path = _write_tmp(tmp_path, data)
        result = load_device_registry(path)
        ids = [d.device_id for d in result["devices"]]
        assert ids == ["iphone-16", "iphone-17e", "iphone-17-pro"]

    def test_aliases_preserved(self, tmp_path):
        data = _valid_registry()
        data["devices"][0]["aliases"] = ["iphone-se-4", "iphone-se4"]
        path = _write_tmp(tmp_path, data)
        result = load_device_registry(path)
        assert result["devices"][0].aliases == ["iphone-se-4", "iphone-se4"]

    def test_minimal_device(self, tmp_path):
        """Only required fields should work (optional ones default)."""
        data = {
            "contract": CONTRACT_NAME,
            "contract_version": CONTRACT_VERSION,
            "devices": [
                {
                    "device_id": "test-phone",
                    "brand": "test",
                    "family": "test",
                    "display_name": "Test Phone",
                },
            ],
        }
        path = _write_tmp(tmp_path, data)
        result = load_device_registry(path)
        d = result["devices"][0]
        assert d.generation == ""
        assert d.aliases == []
        assert d.sort_order == 0
        assert d.active_identity is True


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestDeviceRegistryErrors:
    def test_missing_file(self, tmp_path):
        with pytest.raises(CatalogValidationError, match="not found"):
            load_device_registry(os.path.join(str(tmp_path), "nope.json"))

    def test_wrong_contract_name(self, tmp_path):
        data = _valid_registry()
        data["contract"] = "wrong-contract"
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="contract name mismatch"):
            load_device_registry(path)

    def test_wrong_contract_version(self, tmp_path):
        data = _valid_registry()
        data["contract_version"] = 999
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="contract_version mismatch"):
            load_device_registry(path)

    def test_duplicate_device_id(self, tmp_path):
        data = _valid_registry()
        data["devices"].append(dict(data["devices"][0]))  # duplicate
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="duplicate device_id"):
            load_device_registry(path)

    def test_invalid_device_id_double_underscore(self, tmp_path):
        data = _valid_registry()
        data["devices"][0]["device_id"] = "bad__id"
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="invalid format"):
            load_device_registry(path)

    def test_invalid_device_id_uppercase(self, tmp_path):
        data = _valid_registry()
        data["devices"][0]["device_id"] = "IPhone-17e"
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="invalid format"):
            load_device_registry(path)

    def test_missing_required_field(self, tmp_path):
        data = _valid_registry()
        del data["devices"][0]["brand"]
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="missing required"):
            load_device_registry(path)

    def test_unknown_field(self, tmp_path):
        data = _valid_registry()
        data["devices"][0]["new_field"] = "should fail"
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="unknown field"):
            load_device_registry(path)

    def test_devices_not_a_list(self, tmp_path):
        data = _valid_registry()
        data["devices"] = "not-a-list"
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="expected list"):
            load_device_registry(path)

    def test_aliases_not_a_list(self, tmp_path):
        data = _valid_registry()
        data["devices"][0]["aliases"] = "not-a-list"
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="expected list"):
            load_device_registry(path)

    def test_sort_order_not_int(self, tmp_path):
        data = _valid_registry()
        data["devices"][0]["sort_order"] = "high"
        path = _write_tmp(tmp_path, data)
        with pytest.raises(CatalogValidationError, match="expected int"):
            load_device_registry(path)


# ---------------------------------------------------------------------------
# Real registry check
# ---------------------------------------------------------------------------

class TestRealDeviceRegistry:
    """Validate the actual checked-in device registry."""

    def test_real_registry_loads(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "catalog", "device_registry.v1.json",
        )
        result = load_device_registry(path)
        assert result["contract"] == CONTRACT_NAME
        assert result["contract_version"] == CONTRACT_VERSION
        # P4B Wave-1: exactly 3 devices
        assert len(result["devices"]) == 3
        assert "iphone-17e" in result["device_map"]
        assert "iphone-17" in result["device_map"]
        assert "iphone-air" in result["device_map"]
        for dev_id in ("iphone-17e", "iphone-17", "iphone-air"):
            d = result["device_map"][dev_id]
            assert d.brand == "apple"
            assert d.family == "iphone"
            assert d.active_identity is True
