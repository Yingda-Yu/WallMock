"""Generate the P4A example storefront contract bundle.

Uses the existing iPhone 17e prototype template and a test artwork to
produce a complete contract bundle with one real WebP render asset.

Output:
  examples/storefront-contract/
    contract_bundle.v1.json
    device_registry.v1.json
    render_capabilities.v1.json
    render_manifest.v1.json
    assets/
      color-block/iphone-17e/hard/rear-800.webp

The fixture is intentionally a prototype (production_publishable=false)
and uses internally safe test art — no production template faking.
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
    write_json_deterministic,
)
from core.contract_ids import (
    build_render_asset_id,
    build_variant_id,
    CONTRACT_NAME,
    CONTRACT_VERSION,
    RENDER_ASSET_FORMAT_V1,
)
from core.device_registry_loader import load_device_registry

# Paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(
    "assets", "case_templates", "apple", "iphone-17e", "hard", "rear"
)
TEMPLATE_JSON = os.path.join(TEMPLATE_DIR, "template.json")
DEVICE_REGISTRY_PATH = os.path.join("catalog", "device_registry.v1.json")
ARTWORK_PATH = os.path.join("tests", "fixtures", "artworks", "color-block.png")
OUTPUT_DIR = os.path.join("examples", "storefront-contract")
ASSETS_SUBDIR = "assets"

# Render size for the example fixture (storefront-friendly 800px wide)
RENDER_WIDTH = 800

# Design identity — shared with storefront, merchandising-owned
DESIGN_ID = "color-block"


def main():
    os.chdir(REPO_ROOT)

    wallmock_commit = get_git_commit(REPO_ROOT) or "0000000000000000000000000000000000000000"
    dirty = is_git_dirty(REPO_ROOT)

    print(f"Contract: {CONTRACT_NAME} v{CONTRACT_VERSION}")
    print(f"WallMock commit: {wallmock_commit}")
    print(f"Dirty: {dirty}")
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

    # 2. Build render capabilities
    print("Building render capabilities...")
    templates_root = os.path.join("assets", "case_templates")
    caps_data = build_render_capabilities(
        templates_root, wallmock_commit=wallmock_commit,
    )
    tpl_count = sum(
        len(d["templates"]) for d in caps_data["devices"].values()
    )
    print(f"  {len(caps_data['devices'])} device(s), {tpl_count} template(s)")

    # 3. Render the example asset
    print("Rendering example asset...")
    template = load_case_template(TEMPLATE_JSON)
    art = Image.open(ARTWORK_PATH).convert("RGBA")
    result = render_case(
        art, template, template_dir=TEMPLATE_DIR, fit_mode="cover",
    )

    # Resize to target width
    w_percent = RENDER_WIDTH / float(result.width)
    h_size = int(float(result.height) * w_percent)
    result_resized = result.resize((RENDER_WIDTH, h_size), Image.LANCZOS)

    # Save as WebP
    asset_rel_path = os.path.join(
        ASSETS_SUBDIR, DESIGN_ID, "iphone-17e", "hard", "rear-800.webp"
    ).replace("\\", "/")
    asset_abs_path = os.path.join(OUTPUT_DIR, asset_rel_path)
    os.makedirs(os.path.dirname(asset_abs_path), exist_ok=True)

    # Save WebP to bytes first for content hash
    buf = io.BytesIO()
    result_resized.save(buf, format="WEBP", quality=85)
    webp_bytes = buf.getvalue()

    # Compute content hash
    content_hash_hex = hashlib.sha256(webp_bytes).hexdigest()
    content_hash = build_content_hash(content_hash_hex)

    # Write the file
    with open(asset_abs_path, "wb") as f:
        f.write(webp_bytes)

    size_kb = len(webp_bytes) / 1024
    print(f"  {asset_rel_path} ({result_resized.size[0]}x{result_resized.size[1]}, {size_kb:.1f} KB)")

    # 4. Build render manifest
    print("Building render manifest...")
    variant_entry = build_render_manifest_entry(
        design_id=DESIGN_ID,
        device_id="iphone-17e",
        case_type="hard",
        template_id=template.id,
        template_status=template.status,
        views={
            "rear": {
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
    manifest_data = build_render_manifest(
        variants=[variant_entry],
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
    else:
        print("  INVALID ❌")
        for err in report.errors:
            print(f"    ERROR: {err}")
        sys.exit(1)

    print()
    print("Done. Example contract bundle generated successfully.")


if __name__ == "__main__":
    main()
