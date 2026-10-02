"""Generate the P4B storefront contract bundle (3 devices × color-block).

Refreshes the Contract v1 example snapshot to include all three Wave-1
devices (iphone-17e, iphone-17, iphone-air) with color-block prototype
renders. Contract schema remains frozen at v1 — this is a data-only refresh.

Output:
  examples/storefront-contract/
    contract_bundle.v1.json
    device_registry.v1.json
    render_capabilities.v1.json
    render_manifest.v1.json
    assets/
      color-block/<device_id>/hard/rear-800.webp  (×3 devices)
"""
import hashlib
import io
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.case_renderer import render_case
from core.case_template_loader import load_case_template
from core.contract_export import (
    build_render_capabilities,
    build_render_manifest,
    build_render_manifest_entry,
    build_content_hash,
    export_contract_bundle,
    get_git_commit,
    is_git_dirty,
)
from core.contract_ids import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    RENDER_ASSET_FORMAT_V1,
)
from core.device_registry_loader import load_device_registry

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICE_REGISTRY_PATH = os.path.join("catalog", "device_registry.v1.json")
ARTWORK_PATH = os.path.join("tests", "fixtures", "artworks", "color-block.png")
OUTPUT_DIR = os.path.join("examples", "storefront-contract")
ASSETS_SUBDIR = "assets"

RENDER_WIDTH = 800
DESIGN_ID = "color-block"
CASE_TYPE = "hard"
VIEW = "rear"

WAVE_1_DEVICES = ["iphone-17e", "iphone-17", "iphone-air"]


def render_device_asset(device_id):
    """Render a single device's color-block prototype asset.
    Returns (variant_entry_dict, asset_rel_path, webp_bytes)."""
    template_dir = os.path.join(
        "assets", "case_templates", "apple", device_id, CASE_TYPE, VIEW
    )
    template_json = os.path.join(template_dir, "template.json")
    template = load_case_template(template_json)

    art = Image.open(ARTWORK_PATH).convert("RGBA")
    result = render_case(
        art, template, template_dir=template_dir, fit_mode="cover",
    )

    # Resize to target width
    w_percent = RENDER_WIDTH / float(result.width)
    h_size = int(float(result.height) * w_percent)
    result_resized = result.resize((RENDER_WIDTH, h_size), Image.LANCZOS)

    # Save as WebP to bytes for content hash
    buf = io.BytesIO()
    result_resized.save(buf, format="WEBP", quality=85)
    webp_bytes = buf.getvalue()

    content_hash_hex = hashlib.sha256(webp_bytes).hexdigest()
    content_hash = build_content_hash(content_hash_hex)

    asset_rel_path = os.path.join(
        ASSETS_SUBDIR, DESIGN_ID, device_id, CASE_TYPE, f"{VIEW}-{RENDER_WIDTH}.webp"
    ).replace("\\", "/")

    variant_entry = build_render_manifest_entry(
        design_id=DESIGN_ID,
        device_id=device_id,
        case_type=CASE_TYPE,
        template_id=template.id,
        template_status=template.status,
        views={
            VIEW: {
                RENDER_WIDTH: {
                    "path": asset_rel_path,
                    "width": RENDER_WIDTH,
                    "height": result_resized.size[1],
                    "format": RENDER_ASSET_FORMAT_V1,
                    "content_hash": content_hash,
                    "renderer_version": "1.0.0",
                },
            },
        },
    )

    return variant_entry, asset_rel_path, webp_bytes, result_resized.size


def main():
    os.chdir(REPO_ROOT)

    wallmock_commit = get_git_commit(REPO_ROOT) or "0000000000000000000000000000000000000000"
    dirty = is_git_dirty(REPO_ROOT)

    print(f"Contract: {CONTRACT_NAME} v{CONTRACT_VERSION}")
    print(f"WallMock commit: {wallmock_commit}")
    print(f"Dirty: {dirty}")
    print(f"P4B Wave-1 devices: {len(WAVE_1_DEVICES)} ({', '.join(WAVE_1_DEVICES)})")
    print()

    # 1. Load device registry
    print("Loading device registry...")
    reg_result = load_device_registry(DEVICE_REGISTRY_PATH)
    device_registry_data = {
        "contract": reg_result["contract"],
        "contract_version": reg_result["contract_version"],
        "devices": [
            {
                "device_id": d.device_id,
                "brand": d.brand,
                "family": d.family,
                "generation": d.generation,
                "display_name": d.display_name,
                "aliases": list(d.aliases),
                "sort_order": d.sort_order,
                "active_identity": d.active_identity,
            }
            for d in reg_result["devices"]
        ],
    }
    print(f"  {len(device_registry_data['devices'])} device(s)")

    # 2. Build render capabilities (all templates from all devices)
    print("Building render capabilities...")
    templates_root = os.path.join("assets", "case_templates")
    caps_data = build_render_capabilities(
        templates_root, wallmock_commit=wallmock_commit,
    )
    tpl_count = sum(
        len(d["templates"]) for d in caps_data["devices"].values()
    )
    print(f"  {len(caps_data['devices'])} device(s), {tpl_count} template(s)")

    # 3. Render assets for all Wave-1 devices
    print("Rendering assets for all devices...")
    variant_entries = []
    asset_files = {}  # rel_path -> bytes

    for device_id in WAVE_1_DEVICES:
        variant_entry, asset_rel_path, webp_bytes, size = render_device_asset(device_id)
        variant_entries.append(variant_entry)
        asset_files[asset_rel_path] = webp_bytes
        size_kb = len(webp_bytes) / 1024
        print(f"  {device_id}: {asset_rel_path} ({size[0]}x{size[1]}, {size_kb:.1f} KB)")

    # Write all asset files
    for rel_path, webp_bytes in asset_files.items():
        abs_path = os.path.join(OUTPUT_DIR, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(webp_bytes)

    # 4. Build render manifest
    print("Building render manifest...")
    manifest_data = build_render_manifest(
        variants=variant_entries,
        wallmock_commit=wallmock_commit,
        renderer_version="1.0.0",
    )
    print(f"  {len(manifest_data['variants'])} variant(s)")

    # 5. Export contract bundle atomically
    print("Exporting contract bundle...")
    bundle = export_contract_bundle(
        output_dir=OUTPUT_DIR,
        device_registry_data=device_registry_data,
        render_capabilities_data=caps_data,
        render_manifest_data=manifest_data,
        wallmock_commit=wallmock_commit,
        renderer_version="1.0.0",
        working_tree_dirty=dirty,
        reject_dirty=False,  # example fixture, OK to be dirty
    )
    print(f"  Exported to: {OUTPUT_DIR}/")
    for fname, art in bundle["artifacts"].items():
        print(f"    {fname}: sha256={art['sha256'][:16]}...")

    # 6. Validate
    print()
    print("Validating bundle...")
    from core.bundle_validator import validate_contract_bundle
    report = validate_contract_bundle(OUTPUT_DIR)
    if report.valid:
        print("  VALID ✅")
        print(f"  devices={report.info.get('devices_count')}")
        print(f"  templates={report.info.get('templates_count')}")
        print(f"  variants={report.info.get('variants_count')}")
        print(f"  assets={report.info.get('render_assets_count')}")
        prototype_count = report.info.get("prototype_templates", 0)
        production_count = report.info.get("production_templates", 0)
        print(f"  prototype_templates={prototype_count}")
        print(f"  production_templates={production_count}")
    else:
        print("  INVALID ❌")
        for err in report.errors:
            print(f"    ERROR: {err}")
        sys.exit(1)

    print()
    print("Done. P4B Contract v1 bundle refreshed successfully.")
    print("Schema unchanged — this is a data-only expansion.")


if __name__ == "__main__":
    main()
