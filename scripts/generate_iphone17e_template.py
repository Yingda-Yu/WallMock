"""
Generate iPhone 17e phone-case template layers for WallMock 2.0.

===========================================================================
GEOMETRY PROVENANCE — classification of every dimension
===========================================================================

CATEGORY 1 — VERIFIED OFFICIAL DEVICE DIMENSIONS
  Source: https://support.apple.com/zh-cn/126470 (Apple Inc.)
  - Body height: 146.7 mm
  - Body width:  71.5 mm
  - Body depth:  7.80 mm
  - Single 48MP Fusion rear camera (confirmed, but exact module
    geometry not published)

CATEGORY 2 — VISUALLY ESTIMATED DEVICE ANCHORS
  Derived from Apple product imagery and common iPhone design language.
  Not verified by published engineering drawings.
  - Single rear lens + flash + microphone layout (no large camera island)
  - Approximate lens position: upper-left region of back panel
  - Corner radius: ~11.5 mm (estimated from iPhone SE / 17e design language)
  - Button positions (volume up/down, side button)

CATEGORY 3 — ASSUMED PROTOTYPE CASE PARAMETERS
  Standard hard-case assumptions, not supplier-verified.
  - Case thickness: 1.5 mm per side (typical polycarbonate hard case)
  - Print bezel: ~1.5 mm from case edge (tight full-bleed print)
  - Camera cutout clearance: ~1 mm around lens

CATEGORY 4 — SUPPLIER-PROVIDED CASE GEOMETRY
  None yet. When a real supplier dieline/CAD becomes available,
  replace category 2/3 values with verified measurements.

STATUS: PROTOTYPE / REFERENCE TEMPLATE
  This template is NOT a production-exact SKU template. It is a
  reference template built from verified body dimensions +
  estimated camera layout + assumed case parameters. It is
  suitable for pipeline development and visual prototyping.
  It must be replaced with supplier-accurate geometry before
  being used for production SKUs.
===========================================================================

Scale: 13 px/mm (chosen for good detail at reasonable file size)

Produces: base.png, print_mask.png, overlay.png, highlight.png, shadow.png
"""

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ═════════════════════════════════════════════════════════════════════════
# Canvas
# ═════════════════════════════════════════════════════════════════════════
CANVAS_W = 1600
CANVAS_H = 2000

# ─── Scale ───────────────────────────────────────────────────────────────
SCALE = 13  # px per mm

# ─── iPhone 17e dimensions (Apple official — VERIFIED) ───────────────────
PHONE_H_MM = 146.7
PHONE_W_MM = 71.5
PHONE_D_MM = 7.80

# ─── Case dimensions (phone + case thickness) ────────────────────────────
# Case thickness: 1.5 mm per side (ASSUMED — prototype hard-case parameter)
CASE_THICKNESS_MM = 1.5
CASE_W = 970     # ~74.6 mm at 13 px/mm
CASE_H = 1950    # ~150 mm at 13 px/mm

# ─── Case position (centered in canvas) ──────────────────────────────────
CASE_X = (CANVAS_W - CASE_W) // 2   # 315
CASE_Y = (CANVAS_H - CASE_H) // 2   # 25

# ─── Corner radius (~11.5mm — VISUALLY ESTIMATED from iPhone design) ────
CORNER_R = 150  # ~11.5 mm at 13 px/mm

# ─── Bezel / print margin (~1.5mm — ASSUMED prototype case parameter) ──
BEZEL = 20  # ~1.5mm * 13

# ─── Print region bounding box ────────────────────────────────────────────
PRINT_X = CASE_X + BEZEL       # 335
PRINT_Y = CASE_Y + BEZEL       # 45
PRINT_W = CASE_W - 2 * BEZEL   # 930
PRINT_H = CASE_H - 2 * BEZEL   # 1910
PRINT_CORNER_R = CORNER_R - BEZEL  # 130

# ═════════════════════════════════════════════════════════════════════════
# Camera — single lens + flash + mic (VISUALLY ESTIMATED layout)
#
# iPhone 17e has a single 48MP Fusion camera on the back, not a large
# square camera island. The lens sits nearly flush with the back glass
# with a surrounding ring. Nearby are the flash and a microphone hole.
# ═════════════════════════════════════════════════════════════════════════

# Lens position: upper-left region of back panel
LENS_CX = CASE_X + int(CASE_W * 0.22)   # ~22% from left edge
LENS_CY = CASE_Y + int(CASE_H * 0.13)   # ~13% from top
LENS_RADIUS = 70                         # ~5.4mm lens radius
LENS_RING_WIDTH = 12                     # metallic ring around lens

# Flash: to the right of lens, slightly above
FLASH_CX = LENS_CX + 140
FLASH_CY = LENS_CY - 20
FLASH_SIZE = 48

# Microphone hole: below flash
MIC_CX = FLASH_CX
MIC_CY = LENS_CY + 55
MIC_RADIUS = 12

# Camera exclusion zone (for print mask) — includes lens + flash + mic
# with a small safety margin
CAM_EXCLUDE_PAD = 18  # ~1.4mm margin around camera components

# ─── Button positions (VISUALLY ESTIMATED) ────────────────────────────────
BTN_H = 60
BTN_RIGHT_X = CASE_X + CASE_W - 4
BTN_LEFT_X = CASE_X - 4
BTN_VOL_UP_Y = CASE_Y + int(CASE_H * 0.28)
BTN_VOL_DN_Y = CASE_Y + int(CASE_H * 0.36)
BTN_PWR_Y = CASE_Y + int(CASE_H * 0.32)


# ═════════════════════════════════════════════════════════════════════════
# Helper
# ═════════════════════════════════════════════════════════════════════════
def rounded_rect_mask(w, h, x, y, rw, rh, radius):
    """Create an L-mode mask of a rounded rectangle."""
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([x, y, x + rw, y + rh], radius=radius, fill=255)
    return mask


def case_body_mask():
    """Return L-mode mask of the full case body silhouette."""
    return rounded_rect_mask(
        CANVAS_W, CANVAS_H, CASE_X, CASE_Y, CASE_W, CASE_H, CORNER_R
    )


def camera_exclusion_mask():
    """Return L-mode mask where camera components are (0=excluded, 255=clear).

    Excludes lens, flash, and mic with a surrounding margin.
    """
    mask = Image.new("L", (CANVAS_W, CANVAS_H), 255)
    d = ImageDraw.Draw(mask)

    # Lens exclusion (circle)
    d.ellipse(
        [LENS_CX - LENS_RADIUS - LENS_RING_WIDTH - CAM_EXCLUDE_PAD,
         LENS_CY - LENS_RADIUS - LENS_RING_WIDTH - CAM_EXCLUDE_PAD,
         LENS_CX + LENS_RADIUS + LENS_RING_WIDTH + CAM_EXCLUDE_PAD,
         LENS_CY + LENS_RADIUS + LENS_RING_WIDTH + CAM_EXCLUDE_PAD],
        fill=0
    )

    # Flash exclusion (rounded rect)
    flash_half = FLASH_SIZE // 2 + CAM_EXCLUDE_PAD
    d.rounded_rectangle(
        [FLASH_CX - flash_half, FLASH_CY - flash_half,
         FLASH_CX + flash_half, FLASH_CY + flash_half],
        radius=flash_half // 2, fill=0
    )

    # Mic exclusion (small circle)
    d.ellipse(
        [MIC_CX - MIC_RADIUS - CAM_EXCLUDE_PAD,
         MIC_CY - MIC_RADIUS - CAM_EXCLUDE_PAD,
         MIC_CX + MIC_RADIUS + CAM_EXCLUDE_PAD,
         MIC_CY + MIC_RADIUS + CAM_EXCLUDE_PAD],
        fill=0
    )

    return mask


# ═════════════════════════════════════════════════════════════════════════
# BASE — premium case body with depth and edge elevation
# ═════════════════════════════════════════════════════════════════════════
def generate_base():
    """Case body: clean premium surface with 3D edge depth.

    The base is the physical case material beneath the printed artwork.
    No artwork, no camera details — just the case body shape with
    subtle curvature and edge elevation.
    """
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    shape_mask = case_body_mask()

    # Premium matte white base (not gray — avoids halo)
    base_rgb = np.array([248, 247, 245], dtype=np.float32)

    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    cx = CASE_X + CASE_W / 2
    cy = CASE_Y + CASE_H / 2

    # Horizontal gradient for cylindrical body curvature (stronger at edges)
    x_norm = (xx - cx) / (CASE_W / 2)
    # Cylindrical curvature: darker at left/right edges, brighter at center
    cyl_darken = 1.0 - (np.abs(x_norm) ** 2) * 0.12

    # Radial darkening (subtle, for corner depth)
    dy = (yy - cy) / (CASE_H / 2)
    dist = np.sqrt(x_norm**2 + dy**2).clip(0, 1)
    rad_darken = 1.0 - dist * 0.05

    darken = cyl_darken * rad_darken

    # Top/bottom edge shadow (8% darker at very top/bottom for depth)
    y_frac = (yy - CASE_Y) / CASE_H
    edge_shadow = np.where(
        (y_frac < 0.03) | (y_frac > 0.97), 0.92, 1.0
    )

    r = (base_rgb[0] * darken * edge_shadow).clip(0, 255)
    g = (base_rgb[1] * darken * edge_shadow).clip(0, 255)
    b = (base_rgb[2] * darken * edge_shadow).clip(0, 255)

    pixels = np.stack([r, g, b], axis=-1).clip(0, 255).astype(np.uint8)
    alpha = np.array(shape_mask, dtype=np.uint8)
    rgba = np.dstack([pixels, alpha])
    img = Image.fromarray(rgba, "RGBA")

    # Outer edge: dark line for case thickness/depth
    edge_line = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    el = ImageDraw.Draw(edge_line)
    el.rounded_rectangle(
        [CASE_X, CASE_Y, CASE_X + CASE_W, CASE_Y + CASE_H],
        radius=CORNER_R,
        outline=(150, 148, 145, 230), width=3
    )
    img = Image.alpha_composite(img, edge_line)

    # Inner edge highlight: bright line just inside rim (raised edge effect)
    inner_highlight = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ih = ImageDraw.Draw(inner_highlight)
    ih.rounded_rectangle(
        [CASE_X + 3, CASE_Y + 3, CASE_X + CASE_W - 3, CASE_Y + CASE_H - 3],
        radius=CORNER_R - 3,
        outline=(255, 255, 255, 220), width=3
    )
    inner_highlight = inner_highlight.filter(ImageFilter.GaussianBlur(1.0))
    img = Image.alpha_composite(img, inner_highlight)

    # Inner edge shadow: deeper shadow below highlight (depth from raised edge to print)
    inner_shadow = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ish = ImageDraw.Draw(inner_shadow)
    ish.rounded_rectangle(
        [CASE_X + 7, CASE_Y + 7, CASE_X + CASE_W - 7, CASE_Y + CASE_H - 7],
        radius=CORNER_R - 7,
        outline=(0, 0, 0, 55), width=3
    )
    inner_shadow = inner_shadow.filter(ImageFilter.GaussianBlur(1.5))
    img = Image.alpha_composite(img, inner_shadow)

    return img


# ═════════════════════════════════════════════════════════════════════════
# PRINT MASK — intersection of rounded print region + case body + camera exclusion
# ═════════════════════════════════════════════════════════════════════════
def generate_print_mask():
    """L-mode mask where white = printable, black = excluded.

    The printable area is the INTERSECTION of three regions:
    1. Rounded print region (inside the bezel)
    2. Case body silhouette (the physical case surface)
    3. NOT the camera/lens/flash/mic exclusion zone

    This ensures artwork never appears:
      - outside the rounded case body (corner leak prevention)
      - in the camera/flash/mic areas
      - beyond the print bezel
    """
    # 1. Rounded print region mask
    print_region = rounded_rect_mask(
        CANVAS_W, CANVAS_H,
        PRINT_X, PRINT_Y, PRINT_W, PRINT_H, PRINT_CORNER_R
    )

    # 2. Case body mask
    body = case_body_mask()

    # 3. Camera exclusion (255 = printable, 0 = excluded)
    cam_clear = camera_exclusion_mask()

    # Intersection: print_region AND body AND cam_clear
    # Use uint32 to avoid overflow during multiplication
    pr_arr = np.array(print_region, dtype=np.uint32)
    body_arr = np.array(body, dtype=np.uint32)
    cam_arr = np.array(cam_clear, dtype=np.uint32)

    # For L-mode masks, intersection = product / (255^(n-1)) where n = number of masks
    result_arr = (pr_arr * body_arr * cam_arr) // (255 * 255)
    result_arr = result_arr.clip(0, 255).astype(np.uint8)

    return Image.fromarray(result_arr, "L")


# ═════════════════════════════════════════════════════════════════════════
# OVERLAY — camera lens, ring, flash, mic, rim, buttons (above artwork)
# ═════════════════════════════════════════════════════════════════════════
def generate_overlay():
    """Non-printable geometry that sits ABOVE the artwork.

    For iPhone 17e (single camera, no large island):
    - Single lens with metallic ring
    - Flash (rounded square, warm white)
    - Microphone hole
    - Case edge rim (raised border above print)
    - Side buttons
    """
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── Lens: outer metallic ring ─────────────────────────────────────
    ring_outer = LENS_RADIUS + LENS_RING_WIDTH
    # Ring shadow (subtle depth beneath ring)
    ring_shadow = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    rs = ImageDraw.Draw(ring_shadow)
    rs.ellipse(
        [LENS_CX - ring_outer - 2, LENS_CY - ring_outer + 3,
         LENS_CX + ring_outer + 2, LENS_CY + ring_outer + 3],
        fill=80
    )
    ring_shadow = ring_shadow.filter(ImageFilter.GaussianBlur(3))
    ring_shadow_img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ring_shadow_img.paste(
        Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 100)),
        (0, 0), ring_shadow
    )
    img = Image.alpha_composite(img, ring_shadow_img)

    # Metallic ring body
    d.ellipse(
        [LENS_CX - ring_outer, LENS_CY - ring_outer,
         LENS_CX + ring_outer, LENS_CY + ring_outer],
        fill=(130, 130, 133, 255)
    )

    # Ring highlight (top-left arc — light source)
    d.arc(
        [LENS_CX - ring_outer + 2, LENS_CY - ring_outer + 2,
         LENS_CX + ring_outer - 2, LENS_CY + ring_outer - 2],
        start=200, end=340, fill=(200, 200, 203, 230), width=4
    )
    # Ring shadow (bottom-right arc)
    d.arc(
        [LENS_CX - ring_outer + 2, LENS_CY - ring_outer + 2,
         LENS_CX + ring_outer - 2, LENS_CY + ring_outer - 2],
        start=20, end=160, fill=(70, 70, 73, 200), width=3
    )

    # ── Lens glass (dark) ─────────────────────────────────────────────
    # Lens housing (slight recess inside ring)
    d.ellipse(
        [LENS_CX - LENS_RADIUS, LENS_CY - LENS_RADIUS,
         LENS_CX + LENS_RADIUS, LENS_CY + LENS_RADIUS],
        fill=(15, 15, 18, 255)
    )

    # Lens glass gradient (subtle radial)
    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    ldx = (xx - LENS_CX) / LENS_RADIUS
    ldy = (yy - LENS_CY) / LENS_RADIUS
    ldist = np.sqrt(ldx**2 + ldy**2).clip(0, 1)
    r = (15 + 10 * (1 - ldist)).clip(0, 255)
    g = (15 + 5 * (1 - ldist)).clip(0, 255)
    b = (22 + 15 * (1 - ldist)).clip(0, 255)
    lens_px = np.stack([r, g, b], axis=-1).clip(0, 255).astype(np.uint8)

    lens_mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    lm = ImageDraw.Draw(lens_mask)
    lm.ellipse(
        [LENS_CX - LENS_RADIUS + 3, LENS_CY - LENS_RADIUS + 3,
         LENS_CX + LENS_RADIUS - 3, LENS_CY + LENS_RADIUS - 3],
        fill=255
    )
    lens_mask = lens_mask.filter(ImageFilter.GaussianBlur(0.5))
    lens_a = np.array(lens_mask, dtype=np.uint8)
    lens_rgba = np.dstack([lens_px, lens_a])
    lens_grad = Image.fromarray(lens_rgba, "RGBA")
    img = Image.alpha_composite(img, lens_grad)

    # Specular highlight on lens (top-left)
    spec_x = LENS_CX + int(LENS_RADIUS * 0.35)
    spec_y = LENS_CY - int(LENS_RADIUS * 0.3)
    spec_r = int(LENS_RADIUS * 0.25)
    for i in range(spec_r, 0, -1):
        alpha = int(100 * (1 - i / spec_r))
        d.ellipse(
            [spec_x - i, spec_y - i, spec_x + i, spec_y + i],
            fill=(140, 140, 150, alpha)
        )

    # ── Flash ─────────────────────────────────────────────────────────
    flash_half = FLASH_SIZE // 2
    # Flash housing
    d.rounded_rectangle(
        [FLASH_CX - flash_half, FLASH_CY - flash_half,
         FLASH_CX + flash_half, FLASH_CY + flash_half],
        radius=flash_half // 2, fill=(235, 230, 210, 255)
    )
    # Flash inner glow
    d.rounded_rectangle(
        [FLASH_CX - flash_half + 4, FLASH_CY - flash_half + 4,
         FLASH_CX + flash_half - 4, FLASH_CY + flash_half - 4],
        radius=(flash_half - 4) // 2, fill=(255, 250, 235, 200)
    )
    # Flash ring
    d.rounded_rectangle(
        [FLASH_CX - flash_half, FLASH_CY - flash_half,
         FLASH_CX + flash_half, FLASH_CY + flash_half],
        radius=flash_half // 2, outline=(180, 175, 165, 255), width=2
    )

    # ── Microphone hole ───────────────────────────────────────────────
    d.ellipse(
        [MIC_CX - MIC_RADIUS, MIC_CY - MIC_RADIUS,
         MIC_CX + MIC_RADIUS, MIC_CY + MIC_RADIUS],
        fill=(25, 25, 28, 255)
    )
    # Mic inner ring (subtle)
    d.ellipse(
        [MIC_CX - MIC_RADIUS + 2, MIC_CY - MIC_RADIUS + 2,
         MIC_CX + MIC_RADIUS - 2, MIC_CY + MIC_RADIUS - 2],
        outline=(60, 60, 63, 180), width=1
    )

    # ── Edge rim (raised border above artwork) ───────────────────────
    # Outer rim line
    d.rounded_rectangle(
        [CASE_X, CASE_Y, CASE_X + CASE_W, CASE_Y + CASE_H],
        radius=CORNER_R,
        outline=(160, 158, 155, 240), width=3
    )
    # Inner rim shadow (depth from raised edge to print surface)
    inner_rim = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    ir = ImageDraw.Draw(inner_rim)
    ir.rounded_rectangle(
        [CASE_X + 5, CASE_Y + 5, CASE_X + CASE_W - 5, CASE_Y + CASE_H - 5],
        radius=CORNER_R - 5,
        outline=255, width=4
    )
    inner_rim = inner_rim.filter(ImageFilter.GaussianBlur(2.0))
    rim_shadow = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 60))
    img.paste(rim_shadow, (0, 0), inner_rim)

    # ── Button indicators ─────────────────────────────────────────────
    d.rounded_rectangle(
        [BTN_RIGHT_X - 2, BTN_PWR_Y, BTN_RIGHT_X + 6, BTN_PWR_Y + BTN_H],
        radius=3, fill=(175, 173, 170, 220)
    )
    d.rounded_rectangle(
        [BTN_LEFT_X - 4, BTN_VOL_UP_Y, BTN_LEFT_X + 4, BTN_VOL_UP_Y + BTN_H],
        radius=3, fill=(175, 173, 170, 220)
    )
    d.rounded_rectangle(
        [BTN_LEFT_X - 4, BTN_VOL_DN_Y, BTN_LEFT_X + 4, BTN_VOL_DN_Y + BTN_H],
        radius=3, fill=(175, 173, 170, 220)
    )

    return img


# ═════════════════════════════════════════════════════════════════════════
# HIGHLIGHT — subtle directional lighting
# ═════════════════════════════════════════════════════════════════════════
def generate_highlight():
    """Subtle light gradient from top-left — must not look CGI.

    Only covers the case body area (masked by case silhouette).
    """
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    nx = xx / CANVAS_W
    ny = yy / CANVAS_H
    light = 1.0 - np.sqrt(nx**2 + ny**2) * 0.4
    light = light.clip(0.4, 1.0)

    highlight_alpha = (light * 18).clip(0, 18).astype(np.uint8)
    highlight_px = np.full((CANVAS_H, CANVAS_W, 3), 255, dtype=np.uint8)
    rgba = np.dstack([highlight_px, highlight_alpha])

    # Mask to case body only
    shape_mask = case_body_mask()
    shape_arr = np.array(shape_mask, dtype=np.uint8)
    rgba[..., 3] = (rgba[..., 3].astype(np.float32) * shape_arr / 255).astype(np.uint8)

    img = Image.fromarray(rgba, "RGBA")

    # Subtle specular on camera ring
    spec = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spec)
    ring_outer = LENS_RADIUS + LENS_RING_WIDTH
    sd.arc(
        [LENS_CX - ring_outer, LENS_CY - ring_outer,
         LENS_CX + ring_outer, LENS_CY + ring_outer],
        start=215, end=325, fill=(255, 255, 255, 60), width=3
    )
    img = Image.alpha_composite(img, spec)

    return img


# ═════════════════════════════════════════════════════════════════════════
# SHADOW — outside-only contact shadow (below the case)
# ═════════════════════════════════════════════════════════════════════════
def generate_shadow():
    """Directional contact shadow that sits BENEATH the case.

    The shadow is OUTSIDE-ONLY — it does not overlap the case body itself.
    This ensures compositing the shadow below base is physically correct:
    the shadow darkens the background/surface, not the product.

    Shadow shape:
    - Soft contact shadow at the bottom edge of the case
    - Slight offset to bottom-right (light source from top-left)
    - Softened falloff away from contact point
    """
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    # Build shadow shape: larger/softer rounded rect offset from case
    shadow_offset_x = 6
    shadow_offset_y = 12
    shadow_expand = 14

    shadow_shape = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    sd = ImageDraw.Draw(shadow_shape)
    sd.rounded_rectangle(
        [CASE_X - shadow_expand + shadow_offset_x,
         CASE_Y + shadow_offset_y,
         CASE_X + CASE_W + shadow_expand + shadow_offset_x,
         CASE_Y + CASE_H + shadow_expand + shadow_offset_y],
        radius=CORNER_R + shadow_expand,
        fill=120
    )
    shadow_shape = shadow_shape.filter(ImageFilter.GaussianBlur(18))

    # Punch out the case body interior — shadow is OUTSIDE the case only
    body = case_body_mask()
    # Expand body mask slightly inward to avoid a 1px seam
    body_expanded = body.filter(ImageFilter.GaussianBlur(1.5))
    body_arr = np.array(body_expanded, dtype=np.uint16)
    shadow_arr = np.array(shadow_shape, dtype=np.uint16)

    # Shadow exists where shadow_shape is opaque AND body is transparent
    # = shadow_shape * (255 - body) / 255
    outside_only = (shadow_arr * (255 - body_arr)) // 255
    outside_only = outside_only.clip(0, 255).astype(np.uint8)

    # Create RGBA shadow: black pixels with outside_only as alpha
    shadow_px = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    shadow_rgba = np.dstack([shadow_px, outside_only])
    img = Image.fromarray(shadow_rgba, "RGBA")

    return img


# ═════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import os

    out_dir = os.path.join(
        "assets", "case_templates", "apple", "iphone-17e", "hard", "rear"
    )
    os.makedirs(out_dir, exist_ok=True)

    print("Generating iPhone 17e hard/rear template layers...")
    print("  STATUS: PROTOTYPE / REFERENCE TEMPLATE")
    print("  See file header for geometry provenance classification.")
    print()

    base = generate_base()
    base.save(os.path.join(out_dir, "base.png"))
    print(f"  base.png  {base.size}")

    mask = generate_print_mask()
    mask.save(os.path.join(out_dir, "print_mask.png"))
    print(f"  print_mask.png  {mask.size} (L-mode)")

    overlay = generate_overlay()
    overlay.save(os.path.join(out_dir, "overlay.png"))
    print(f"  overlay.png  {overlay.size}")

    highlight = generate_highlight()
    highlight.save(os.path.join(out_dir, "highlight.png"))
    print(f"  highlight.png  {highlight.size}")

    shadow = generate_shadow()
    shadow.save(os.path.join(out_dir, "shadow.png"))
    print(f"  shadow.png  {shadow.size}")

    print()
    print("Done. All layers saved to", out_dir)
    print()
    print("NOTE: This is a PROTOTYPE template. Camera layout, corner radius,")
    print("case thickness, and print bezel are estimates/assumptions.")
    print("Only body dimensions (146.7 x 71.5 x 7.80 mm) are Apple-verified.")
