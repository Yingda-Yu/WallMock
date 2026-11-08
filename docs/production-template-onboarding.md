# Production Template Onboarding Workflow (P7A)

End-to-end process for promoting a case template from **prototype** to
**production** status using a supplier-validated geometry package.

## Overview

Only templates with supplier-accurate geometry may be marked `production`.
Prototype templates (visually estimated geometry) are safe for preview and
review but must never be published to the storefront.

The onboarding workflow turns a supplier's raw geometry into a validated,
reviewed, production-ready template.

---

## Workflow

```
supplier geometry received
  → source hashes
    → normalize
      → validate
        → owner visual review
          → promote template
            → publish build
              → validate bundle
                → storefront import
```

### 1. Supplier Geometry Received

A supplier sends raw geometry files (dieline, PSD, CAD export, etc.).
Save everything to a working directory — do NOT modify anything in
`assets/case_templates/` yet.

### 2. Source Hashes

Compute SHA-256 hashes of every source file the supplier provided.
These hashes go into `package.json` and serve as the tamper-evident
record of what was received.

```bash
# Example: hash all source files
sha256sum source/*
```

### 3. Normalize

Convert the supplier's source geometry into the standard WallMock
normalized layer set:

| Layer | Role | Description |
|-------|------|-------------|
| `base.png` | base | Neutral case body (under artwork) |
| `print_mask.png` | print_mask | White = printable area, transparent = excluded |
| `overlay.png` | overlay | Camera, buttons, edges, non-print details |
| `highlight.png` | highlight | Gloss / lighting effects (optional) |
| `shadow.png` | shadow | Drop shadow (optional) |

All layers must be PNG, match `normalized_geometry.canvas`, and be aligned
pixel-perfect. Hard cases require base, print_mask, and overlay. Only supplier
layers are used after promotion; omitted optional layers are not inherited.

### 4. Validate

Run the supplier geometry package validator:

```bash
python scripts/validate_supplier_geometry.py <package_dir>
```

What it checks:
- `package.json` is valid and matches the schema
- Device ID exists in the device registry
- Case type is a valid Contract v1 token
- `target_template_id` follows `device_id__case_type__view` grammar
- All source files exist and SHA-256 hashes match
- All normalized layers exist and SHA-256 hashes match
- All normalized layers match `normalized_geometry.canvas`
- Print/camera regions are bounded inside the canvas
- Hard cases require base, print_mask, and overlay; highlight/shadow are optional
- Print mask has non-transparent pixels (not empty)
- No path traversal in any file references
- Package is owner-reviewed (`reviewed: true` + `verified_by` set)
- Supplier geometry reference is production-grade (not a sentinel)

Exit code 0 = valid, exit code 1 = invalid (with error details).

Use `--json` for machine-readable output.

### 5. Owner Visual Review

A human owner must visually verify the normalized layers against
the source geometry and a physical sample (when available).

Review checklist:
- [ ] Print mask covers the correct printable area
- [ ] Overlay correctly excludes camera, buttons, edges
- [ ] Case body shape matches the source dieline
- [ ] Dimensions are correct (cross-check with device specs)
- [ ] All layers are pixel-aligned

After review, set `reviewed: true` and `verified_by: <name/email>`
in `package.json`.

### 6. Promote Template

Run the onboarding tool to promote the prototype template to production:

```bash
python scripts/onboard_production_template.py <package_dir>
```

What it does:
1. Validates the supplier package (must pass all checks)
2. Rejects test/fixture packages by default (safety guard)
3. Finds the target template in `assets/case_templates/`
4. Verifies template ID matches the package target
5. Creates a sibling staging copy; canonical assets are not modified yet
6. Applies supplier `normalized_geometry` (canvas, print region, optional camera region)
   and supplier layers to staging. Omitted optional prototype layers and their
   references are removed; the print mask always references the supplier mask.
7. Sets `status: "production"` and the exact
   `provenance.supplier_geometry: "<package_id>@<revision>"` reference.
   Device-dimension provenance and estimated anchor wording remain unchanged:
   a dieline/CAD source format alone does not verify those claims.
8. Validates staged metadata and decodes every referenced raster, requiring
   its dimensions to match the supplier canvas.
9. Moves the original into a backup, then installs the validated staging copy.
   A failed final move restores the original; failed staged validation never
   alters the canonical directory.

**Idempotent:** Promoting an already-production template with the same
package is a safe no-op.

**Dry run:** Use `--dry-run` to preview changes.

**Fixture isolation:** The CLI has no fixture override. The programmatic
`allow_fixture=True` option exists only for tests in explicitly noncanonical
roots. Even with this option, canonical `assets/case_templates/` and its
subdirectories reject fixtures.

### 7. Publish Build

Run a publish-mode catalog build to generate production assets:

```bash
python scripts/build_catalog.py --plan build-plan.json --out build-output --mode publish
```

Publish mode only renders templates with `status: "production"`.
Prototype templates are skipped (gated).

### 8. Validate Bundle

Validate the output contract bundle:

```bash
python scripts/validate_storefront_contract.py --bundle <bundle_dir>
```

Checks cross-object invariants across device registry, render
capabilities, and render manifest.

### 9. Storefront Import

The validated bundle is ready for import by the storefront.

---

## Supplier Geometry Package Structure

```
supplier-geometry-package/
├── package.json          # Manifest with metadata, hashes, layer list
├── source/               # Original supplier files (dieline, PSD, etc.)
│   ├── dieline.svg
│   └── source-notes.txt
└── normalized/           # Normalized PNG layers for template use
    ├── base.png
    ├── print_mask.png
    ├── overlay.png
    ├── highlight.png
    └── shadow.png
```

### package.json Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Must be `1` |
| `package_id` | str | Unique ID (lowercase, hyphens/underscores) |
| `supplier_id` | str | Supplier identifier |
| `supplier_reference` | str | Supplier's SKU or file reference |
| `device_id` | str | Device registry ID |
| `case_type` | str | `hard` / `tough` / `magsafe` / `clear` / `soft` |
| `revision` | str | Revision string |
| `source_type` | enum | `dieline` / `psd_export` / `cad_export` / `measured` / `normalized_export` |
| `source_files` | array | `[{name, sha256}]` — source file inventory |
| `dimensions` | object | `{width, height, units}` — case dimensions |
| `geometry_notes` | str | Free-form notes |
| `obtained_from` | str | How geometry was obtained |
| `verified_by` | str | Reviewer name/email (non-sentinel) |
| `reviewed` | bool | Must be `true` for production |
| `target_template_id` | str | Target template: `device_id__case_type__view` |
| `normalized_geometry` | object | Pixel `canvas: {width, height, units: "px"}`, bounded `print_region: {x, y, width, height}`, optional `camera_region` with the same region fields |
| `normalized_layers` | array | `[{name, file, sha256, role}]` — layer inventory |

---

## What to Request from Suppliers

When requesting geometry from a new supplier, send this checklist:

### Must-have

- [ ] Vector dieline (AI, PDF, or SVG) with exact physical dimensions
- [ ] Clear indication of print area vs. non-print areas
- [ ] Camera, button, and port cutout positions and sizes
- [ ] Case material type (hard, tough, clear, etc.)
- [ ] File format that preserves vector paths (not just raster)
- [ ] SKU / part number for our records

### Nice-to-have

- [ ] PSD/PNG mockup of the case body color
- [ ] 3D CAD file (STEP) for cross-checking
- [ ] Physical sample for measurement verification
- [ ] Layered source files (separate layers for print area, cut lines, etc.)

### Questions to ask

- What tolerance should we expect? (+/- how many mm)
- Are there any special print constraints (wrap-around edges, etc.)?
- Is the dieline for the inner print area or outer case edge?
- What's the bleed / safe margin around the print area?

---

## Safety Guards

### Test Fixture Isolation

Test packages have IDs starting with `test-` or `fixture-`. They:
- Live only in `tests/fixtures/supplier_geometry/`
- Are always rejected by the production CLI; no fixture override is exposed
- Generate a warning during validation
- Must NEVER be used to promote real production templates

### Production Gate

- `load_case_template()` rejects `status: "production"` unless
  `provenance.supplier_geometry` is production-grade
- Publish-mode catalog builds skip prototype templates
- `validate_supplier_geometry.py` checks 14+ invariants before
  a package is considered valid

### Contract v1 Immutability

The production template onboarding system does NOT modify the
Contract v1 schema. `contract_version` stays `1`. No new fields
are added to contract bundle output. The storefront contract
remains stable.

---

## Related Files

- Schema: `schemas/supplier_geometry_package.schema.json`
- Validation module: `core/supplier_geometry.py`
- Validation CLI: `scripts/validate_supplier_geometry.py`
- Promotion CLI: `scripts/onboard_production_template.py`
- Template loader: `core/case_template_loader.py`
- Domain models: `core/catalog_models.py`
- Test fixture: `tests/fixtures/supplier_geometry/test-fixture-hardcase-iphone-17e/`
- Tests: `tests/test_supplier_geometry.py`

## Current Production Readiness

REAL PRODUCTION TEMPLATE: BLOCKED — SUPPLIER GEOMETRY REQUIRED.
Synthetic fixtures only prove tooling behavior; they are not supplier evidence.
Do not promote a real canonical template without genuine supplier geometry and
owner review. This workflow does not authorize a merge or production deployment.

Before review, run the full `python -m pytest -q` suite, the supplier validator
on the clearly marked fixture, and the positive publish-mode and different-canvas
regressions. Confirm canonical templates remain prototype and Contract v1 is
unchanged. A successful fixture validator result is not production approval.
