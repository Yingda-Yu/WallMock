"""Tests for the contract bundle validator and JSON Schema parity.

Covers:
- Bundle validator cross-object invariants
- JSON Schema parity (manual loader and schema agree)
- Production eligibility invariants
- ID consistency invariants
- Path safety invariants
- Content hash format invariants
"""
import copy
import json
import os
import pytest

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from core.bundle_validator import validate_contract_bundle
from core.catalog_models import CatalogValidationError
from core.contract_export import (
    build_render_manifest,
    build_render_manifest_entry,
    export_contract_bundle,
)
from core.contract_ids import (
    build_content_hash,
    CONTRACT_NAME,
    CONTRACT_VERSION,
)
from core.device_registry_loader import load_device_registry


EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples", "storefront-contract",
)
SCHEMAS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "schemas",
)


def _load_schema(name):
    path = os.path.join(SCHEMAS_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_minimal_bundle(tmp_path):
    """Create a minimal valid bundle for testing."""
    device_registry = {
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "devices": [
            {
                "device_id": "test-device",
                "brand": "test",
                "family": "test",
                "display_name": "Test Device",
                "sort_order": 100,
                "active_identity": True,
            },
        ],
    }
    render_caps = {
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "wallmock_commit": "abc123",
        "devices": {
            "test-device": {
                "device_id": "test-device",
                "templates": [
                    {
                        "template_id": "test-device__hard__rear",
                        "case_type": "hard",
                        "view": "rear",
                        "template_status": "prototype",
                        "renderable": True,
                        "production_publishable": False,
                        "provenance": {
                            "supplier_geometry": "none — prototype",
                        },
                    },
                ],
            },
        },
    }
    manifest = build_render_manifest(
        variants=[
            build_render_manifest_entry(
                design_id="test-design",
                device_id="test-device",
                case_type="hard",
                template_id="test-device__hard__rear",
                template_status="prototype",
                views={
                    "rear": {
                        800: {
                            "path": "test-design/test-device/hard/rear-800.webp",
                            "width": 800,
                            "height": 1000,
                            "format": "webp",
                            "content_hash": build_content_hash("a" * 64),
                            "renderer_version": "1.0.0",
                        },
                    },
                },
            ),
        ],
        wallmock_commit="abc123",
        generated_at="2025-01-01T00:00:00Z",
    )

    export_contract_bundle(
        output_dir=str(tmp_path),
        device_registry_data=device_registry,
        render_capabilities_data=render_caps,
        render_manifest_data=manifest,
        wallmock_commit="abc123",
        generated_at="2025-01-01T00:00:00Z",
        working_tree_dirty=False,
    )
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Bundle validator — valid cases
# ---------------------------------------------------------------------------

class TestBundleValidatorValid:
    def test_example_bundle_is_valid(self):
        """The checked-in example bundle passes validation."""
        report = validate_contract_bundle(EXAMPLES_DIR)
        assert report.valid, f"Expected valid, got errors: {report.errors}"
        assert report.info["devices_count"] >= 1
        assert report.info["templates_count"] >= 1
        assert report.info["variants_count"] >= 1
        assert report.info["render_assets_count"] >= 1

    def test_minimal_bundle_is_valid(self, tmp_path):
        bundle_dir = _make_minimal_bundle(tmp_path)
        report = validate_contract_bundle(bundle_dir)
        assert report.valid, f"Errors: {report.errors}"

    def test_prototype_template_renderable_not_publishable(self, tmp_path):
        """Prototype template can be renderable but not production-publishable."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        report = validate_contract_bundle(bundle_dir)
        assert report.valid


# ---------------------------------------------------------------------------
# Bundle validator — cross-object invariants
# ---------------------------------------------------------------------------

class TestBundleValidatorInvariants:
    def test_unknown_device_in_capabilities_rejected(self, tmp_path):
        """Capabilities referencing a device not in registry → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        caps_path = os.path.join(bundle_dir, "render_capabilities.v1.json")
        caps = _load_json(caps_path)
        caps["devices"]["unknown-device"] = {
            "device_id": "unknown-device",
            "templates": [],
        }
        with open(caps_path, "w") as f:
            json.dump(caps, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("unknown device_id" in e for e in report.errors)

    def test_manifest_unknown_device_rejected(self, tmp_path):
        """Manifest variant with unknown device_id → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        manifest_path = os.path.join(bundle_dir, "render_manifest.v1.json")
        manifest = _load_json(manifest_path)
        # Add variant with bad device_id
        manifest["variants"]["bad__unknown-device__hard"] = {
            "variant_id": "bad__unknown-device__hard",
            "design_id": "bad",
            "device_id": "unknown-device",
            "case_type": "hard",
            "template_id": "unknown-device__hard__rear",
            "template_status": "prototype",
            "views": {},
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("unknown device_id" in e for e in report.errors)

    def test_manifest_unknown_template_rejected(self, tmp_path):
        """Manifest variant with template_id not in capabilities → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        manifest_path = os.path.join(bundle_dir, "render_manifest.v1.json")
        manifest = _load_json(manifest_path)
        vid = "test-design__test-device__tough"
        manifest["variants"][vid] = {
            "variant_id": vid,
            "design_id": "test-design",
            "device_id": "test-device",
            "case_type": "tough",
            "template_id": "test-device__tough__rear",
            "template_status": "prototype",
            "views": {},
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("not in capabilities" in e for e in report.errors)

    def test_prototype_with_production_publishable_rejected(self, tmp_path):
        """Prototype template with production_publishable=true → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        caps_path = os.path.join(bundle_dir, "render_capabilities.v1.json")
        caps = _load_json(caps_path)
        tpl = caps["devices"]["test-device"]["templates"][0]
        tpl["production_publishable"] = True
        with open(caps_path, "w") as f:
            json.dump(caps, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("production_publishable=true" in e for e in report.errors)

    def test_duplicate_template_id_rejected(self, tmp_path):
        """Duplicate template_id in capabilities → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        caps_path = os.path.join(bundle_dir, "render_capabilities.v1.json")
        caps = _load_json(caps_path)
        # Add a second identical template entry
        tpl = copy.deepcopy(caps["devices"]["test-device"]["templates"][0])
        caps["devices"]["test-device"]["templates"].append(tpl)
        with open(caps_path, "w") as f:
            json.dump(caps, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("Duplicate template_id" in e for e in report.errors)

    def test_unsafe_asset_path_rejected(self, tmp_path):
        """Asset path with path traversal → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        manifest_path = os.path.join(bundle_dir, "render_manifest.v1.json")
        manifest = _load_json(manifest_path)
        vid = list(manifest["variants"].keys())[0]
        asset = manifest["variants"][vid]["views"]["rear"]["800"]
        asset["path"] = "../../etc/passwd"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("unsafe asset path" in e for e in report.errors)

    def test_invalid_content_hash_rejected(self, tmp_path):
        """Invalid content_hash format → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        manifest_path = os.path.join(bundle_dir, "render_manifest.v1.json")
        manifest = _load_json(manifest_path)
        vid = list(manifest["variants"].keys())[0]
        asset = manifest["variants"][vid]["views"]["rear"]["800"]
        asset["content_hash"] = "not-a-real-hash"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("invalid content_hash" in e for e in report.errors)

    def test_template_id_mismatch_rejected(self, tmp_path):
        """template_id components don't match device/case/view → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        caps_path = os.path.join(bundle_dir, "render_capabilities.v1.json")
        caps = _load_json(caps_path)
        tpl = caps["devices"]["test-device"]["templates"][0]
        tpl["template_id"] = "wrong-device__soft__angle"  # doesn't match
        tpl["case_type"] = "hard"
        tpl["view"] = "rear"
        with open(caps_path, "w") as f:
            json.dump(caps, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("does not match" in e for e in report.errors)

    def test_variant_id_mismatch_rejected(self, tmp_path):
        """variant_id components don't match design/device/case → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        manifest_path = os.path.join(bundle_dir, "render_manifest.v1.json")
        manifest = _load_json(manifest_path)
        vid = list(manifest["variants"].keys())[0]
        manifest["variants"][vid]["design_id"] = "different-design"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("does not match" in e for e in report.errors)

    def test_status_mismatch_between_caps_and_manifest(self, tmp_path):
        """Manifest template_status differs from capabilities → error."""
        bundle_dir = _make_minimal_bundle(tmp_path)
        manifest_path = os.path.join(bundle_dir, "render_manifest.v1.json")
        manifest = _load_json(manifest_path)
        vid = list(manifest["variants"].keys())[0]
        manifest["variants"][vid]["template_status"] = "production"
        # Also update the asset-level status to match
        for view_data in manifest["variants"][vid]["views"].values():
            for w_data in view_data.values():
                w_data["template_status"] = "production"
                w_data["production_publishable"] = True
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        report = validate_contract_bundle(bundle_dir)
        assert not report.valid
        assert any("mismatches capabilities status" in e for e in report.errors)


# ---------------------------------------------------------------------------
# JSON Schema parity
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
class TestJsonSchemaParity:
    """Verify that manual validators and JSON Schema agree."""

    def test_device_registry_schema_validates_example(self):
        """Valid registry passes both manual loader and JSON Schema."""
        schema = _load_schema("device_registry.schema.json")
        data = _load_json(os.path.join(EXAMPLES_DIR, "device_registry.v1.json"))
        # Should pass schema validation
        jsonschema.validate(instance=data, schema=schema)
        # Should also pass manual loader
        result = load_device_registry(
            os.path.join(EXAMPLES_DIR, "device_registry.v1.json")
        )
        assert result["contract_version"] == CONTRACT_VERSION

    def test_render_capabilities_schema_validates_example(self):
        """Valid capabilities passes JSON Schema."""
        schema = _load_schema("render_capabilities.schema.json")
        data = _load_json(
            os.path.join(EXAMPLES_DIR, "render_capabilities.v1.json")
        )
        jsonschema.validate(instance=data, schema=schema)

    def test_render_manifest_schema_validates_example(self):
        """Valid manifest passes JSON Schema."""
        schema = _load_schema("render_manifest.schema.json")
        data = _load_json(
            os.path.join(EXAMPLES_DIR, "render_manifest.v1.json")
        )
        jsonschema.validate(instance=data, schema=schema)

    def test_contract_bundle_schema_validates_example(self):
        """Valid bundle index passes JSON Schema."""
        schema = _load_schema("contract_bundle.schema.json")
        data = _load_json(
            os.path.join(EXAMPLES_DIR, "contract_bundle.v1.json")
        )
        jsonschema.validate(instance=data, schema=schema)

    def test_invalid_device_id_fails_schema(self):
        """Invalid device_id fails JSON Schema (matches manual rejection)."""
        schema = _load_schema("device_registry.schema.json")
        data = {
            "contract": CONTRACT_NAME,
            "contract_version": CONTRACT_VERSION,
            "devices": [
                {
                    "device_id": "bad__id",  # double underscore
                    "brand": "test",
                    "family": "test",
                    "display_name": "Test",
                },
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=schema)

    def test_invalid_case_type_fails_schema(self):
        """Invalid case_type fails JSON Schema (matches manual rejection)."""
        schema = _load_schema("render_capabilities.schema.json")
        data = {
            "contract": CONTRACT_NAME,
            "contract_version": CONTRACT_VERSION,
            "wallmock_commit": "abc",
            "devices": {
                "test-device": {
                    "device_id": "test-device",
                    "templates": [
                        {
                            "template_id": "test-device__badtype__rear",
                            "case_type": "badtype",  # not in enum
                            "view": "rear",
                            "template_status": "prototype",
                            "renderable": True,
                            "production_publishable": False,
                            "provenance": {"supplier_geometry": "none"},
                        },
                    ],
                },
            },
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=schema)

    def test_invalid_content_hash_fails_schema(self):
        """Invalid content_hash format fails JSON Schema."""
        schema = _load_schema("render_manifest.schema.json")
        # Build a minimal manifest with bad content_hash
        data = {
            "contract": CONTRACT_NAME,
            "contract_version": CONTRACT_VERSION,
            "generated_at": "2025-01-01T00:00:00Z",
            "wallmock_commit": "abc",
            "renderer_version": "1.0.0",
            "variants": {
                "d__dev__hard": {
                    "variant_id": "d__dev__hard",
                    "design_id": "d",
                    "device_id": "dev",
                    "case_type": "hard",
                    "template_id": "dev__hard__rear",
                    "template_status": "prototype",
                    "views": {
                        "rear": {
                            "800": {
                                "render_asset_id": "d__dev__hard__rear__w800",
                                "path": "d/dev/hard/rear-800.webp",
                                "width": 800,
                                "height": 1000,
                                "format": "webp",
                                "content_hash": "bad-hash",  # invalid
                                "view": "rear",
                                "template_id": "dev__hard__rear",
                                "template_status": "prototype",
                                "production_publishable": False,
                                "renderer_version": "1.0.0",
                            },
                        },
                    },
                },
            },
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=schema)

    def test_checked_in_iphone_17e_template_status(self):
        """iPhone 17e in example bundle is prototype (not production)."""
        caps = _load_json(
            os.path.join(EXAMPLES_DIR, "render_capabilities.v1.json")
        )
        tpl = caps["devices"]["iphone-17e"]["templates"][0]
        assert tpl["template_status"] == "prototype"
        assert tpl["production_publishable"] is False

    def test_example_manifest_prototype_status(self):
        """Example manifest assets have prototype status and not publishable."""
        manifest = _load_json(
            os.path.join(EXAMPLES_DIR, "render_manifest.v1.json")
        )
        for vid, variant in manifest["variants"].items():
            assert variant["template_status"] == "prototype"
            for view_data in variant["views"].values():
                for w_data in view_data.values():
                    assert w_data["template_status"] == "prototype"
                    assert w_data["production_publishable"] is False
