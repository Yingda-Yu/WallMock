# Phone Case Template Authoring Guide

This document describes the repeatable process for adding new phone case
templates to WallMock 2.0. Once the renderer and fitter are in place, adding
a new phone model is primarily an **asset and data task** — no renderer
engineering is required.

## Template Structure

```
assets/case_templates/
├── index.json                          # registry of all templates
└── apple/
    └── iphone-17e/
        └── hard/
            └── rear/
                ├── template.json       # metadata + layer definitions
                ├── base.png            # neutral case body
                ├── print_mask.png      # L-mode mask: where artwork may print
                ├── overlay.png         # camera rings, rim, buttons (non-print)
                ├── highlight.png       # optional: subtle material/light
                └── shadow.png          # optional: contact/drop shadow
```

## Layer Responsibilities

### Required Layers

| Layer | File | Purpose |
|-------|------|---------|
| `base` | `base.png` | Neutral physical case body beneath the print. Must not contain any design artwork. |
| `print_mask` | `print_mask.png` | L-mode (grayscale) mask defining where artwork is allowed. 255 = printable, 0 = excluded (camera, edges). |
| `overlay` | `overlay.png` | Non-printable geometry above artwork: camera rings, rim, buttons, edge details. |
| `artwork` | (none) | Placeholder layer in `template.json`. No file — the renderer fills this with the source artwork at render time. |

### Optional Layers

| Layer | File | Purpose |
|-------|------|---------|
| `highlight` | `highlight.png` | Subtle material/light behavior. Must not make the case look CGI or plastic-wrapped. |
| `shadow` | `shadow.png` | Physically believable contact/drop shadow. Independent from artwork. |

**Missing optional layers are skipped gracefully** — the renderer will not crash.

### Layer Constraints

- All layers share the same canvas dimensions.
- All layers have clean alpha (no white halo).
- No artwork contamination in any reusable layer.
- Consistent alignment across layers.
- Camera/cutout geometry in `print_mask.png` must match `overlay.png`.

## template.json Schema

```json
{
  "schema_version": 1,
  "id": "iphone-17e__hard__rear",
  "device_id": "iphone-17e",
  "case_type": "hard",
  "view": "rear",
  "canvas": {
    "width": 1600,
    "height": 2000
  },
  "print_region": {
    "mode": "mask",
    "x": 335,
    "y": 45,
    "width": 930,
    "height": 1910,
    "fit": "cover",
    "mask": "print_mask.png"
  },
  "layers": [
    {"type": "base", "file": "base.png"},
    {"type": "artwork", "blend": "normal"},
    {"type": "highlight", "file": "highlight.png", "opacity": 1.0},
    {"type": "overlay", "file": "overlay.png"},
    {"type": "shadow", "file": "shadow.png"}
  ]
}
```

### Key Fields

- **`id`**: `{device_id}__{case_type}__{view}` — must be unique.
- **`device_id`**: Lowercase alphanumerics, hyphens, underscores only.
- **`case_type`**: `hard` | `tough` | `magsafe` | `transparent` | `soft`.
- **`view`**: `rear` | `angle` | `front` | `closeup`.
- **`print_region.mode`**: `mask` (pixel-precise) or `quad` (perspective, future).
- **`print_region.fit`**: `cover` | `contain` | `tile` — default artwork fit mode.
- **`layers[].opacity`**: 0.0–1.0, defaults to 1.0.

## Authoring Process

### 1. Verify Exact Device Geometry

Obtain official dimensions from the manufacturer's spec page. For Apple
devices, use `https://support.apple.com/` and locate the tech specs page.

Record:
- Body dimensions (H x W x D in mm)
- Camera module position and dimensions
- Button positions (if visible in the chosen view)
- Corner radius

**Do not invent geometry.** Do not label a generic rounded rectangle as a
specific phone model.

### 2. Create Neutral Template Canvas

Choose a scale (pixels per mm) that gives good detail at reasonable file
size. 13 px/mm is a good starting point for phones.

```
canvas_width  = (body_width_mm + 2 * case_thickness_mm) * scale + padding
canvas_height = (body_height_mm + 2 * case_thickness_mm) * scale + padding
```

Center the case body in the canvas.

### 3. Author base.png

The case body beneath the print. This should be:
- A neutral, premium surface (not gray — avoids halo)
- Free of any design artwork
- Shaped as a rounded rectangle matching the device silhouette
- With subtle 3D depth (cylindrical curvature, edge elevation)

### 4. Author print_mask.png

An **L-mode (grayscale)** PNG where:
- 255 (white) = printable area
- 0 (black) = excluded area (camera module, edges, buttons)

This is the most critical layer for artwork correctness. Artwork will
never appear in areas where the mask is 0.

The mask must exclude:
- Camera module (including lens, ring, and surrounding buffer)
- Case edges (bezel — typically 1–1.5mm from case edge)
- Any non-printable physical features

### 5. Author overlay.png

Non-printable geometry that sits **above** the artwork:
- Camera housing (square/rounded rectangle)
- Camera ring (metallic bezel around lens)
- Lens (dark circle with subtle gradient)
- Case rim/edge highlights
- Buttons (if visible)

The overlay must align with the `print_mask.png` cutouts.

### 6. Optionally Author highlight.png

Subtle material/light behavior:
- Horizontal gradient for cylindrical body curvature
- Edge highlights for raised rim
- Must not make the case look obviously CGI or plastic-wrapped

### 7. Optionally Author shadow.png

Physically believable shadow:
- Contact shadow beneath the case (darker at contact points)
- Directional drop shadow (soft, offset)
- Must remain independent from artwork

### 8. Write template.json

Create the `template.json` file following the schema above. Ensure:
- All required fields are present
- Layer order is correct: base → artwork → highlight → overlay → shadow
- The artwork layer has no `file` field
- Print region coordinates match the actual layer positions

### 9. Register in index.json

Add the template path to `assets/case_templates/index.json`:

```json
{
  "templates": [
    {"path": "apple/iphone-17e/hard/rear/template.json"}
  ]
}
```

### 10. Run Validator

```python
from core.case_template_loader import load_case_template, list_case_templates

# Validate single template
template = load_case_template("assets/case_templates/apple/iphone-17e/hard/rear/template.json")
print(f"Loaded: {template.id}")

# Validate via index
templates = list_case_templates()
print(f"Found {len(templates)} templates")

# Verify device lookup
device_templates = get_case_templates_for_device("iphone-17e")
assert len(device_templates) >= 1
```

### 11. Render Fixture Designs

Use the review script to render all three test artworks:

```bash
python scripts/generate_p2p3_review.py
```

Inspect outputs in `output/review/p2-p3/<device-id>/hard/rear/`.

### 12. Run Visual Tests

```bash
python -m pytest tests/test_case_renderer.py tests/test_visual_case_rendering.py -v
```

### 13. Inspect Camera Crop

Open the `-camera-crop.png` files and verify:
- Camera module is fully opaque (no artwork bleed)
- Lens is dark (not artwork color)
- Ring/bezel is visible
- No white halo around alpha edges

### 14. Commit Provenance/Reference Notes

Include in the commit message:
- Device model name
- Official dimensions source (URL)
- Scale used (px/mm)
- Any geometry simplifications or assumptions

## Visual Quality Priority

When authoring or refining templates, use this priority order:

1. **Exact geometry / silhouette** — must look like the real device
2. **Camera and cutout correctness** — no artwork in camera region
3. **Print mask correctness** — artwork reaches correct physical boundaries
4. **Artwork sharpness** — high-quality Lanczos resampling
5. **Physical edge/rim realism** — subtle elevation, not flat
6. **Contact shadow** — grounds the product visually
7. **Subtle highlight/material effect** — premium, not CGI

Do not compensate for weak geometry by adding excessive shadows or shiny effects.
