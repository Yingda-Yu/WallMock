"""
Generate iPhone 17e phone-case template layers for WallMock 2.0.

All dimensions derived from Apple's published iPhone 17e specifications:
  - Body: 146.7 x 71.5 x 7.80 mm
  - Single 48MP Fusion camera (simplified cutout geometry)
Source: https://support.apple.com/zh-cn/126470

Scale: 13 px/mm (chosen for good detail at reasonable file size)
Case adds ~1.5mm per side (typical hard-case thickness).

Produces: base.png, print_mask.png, overlay.png, highlight.png, shadow.png
"""

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ─── Canvas ──────────────────────────────────────────────────────────────
CANVAS_W = 1600
CANVAS_H = 2000

# ─── Scale ───────────────────────────────────────────────────────────────
SCALE = 13  # px per mm

# ─── iPhone 17e dimensions (Apple official) ───────────────────────────────
PHONE_H_MM = 146.7
PHONE_W_MM = 71.5

# ─── Case dimensions (phone + case thickness) ────────────────────────────
CASE_THICKNESS_MM = 1.5
CASE_W = 970
CASE_H = 1950

# ─── Case position (centered in canvas) ──────────────────────────────────
CASE_X = (CANVAS_W - CASE_W) // 2   # 315
CASE_Y = (CANVAS_H - CASE_H) // 2   # 25

# ─── Corner radius (~12mm for iPhone body curvature) ──────────────────────
CORNER_R = 150

# ─── Bezel / print margin (1.5mm from case edge — tight for full-bleed) ─
BEZEL = 20  # ~1.5mm * 13

# ─── Print region bounding box ────────────────────────────────────────────
PRINT_X = CASE_X + BEZEL       # 335
PRINT_Y = CASE_Y + BEZEL       # 45
PRINT_W = CASE_W - 2 * BEZEL   # 930
PRINT_H = CASE_H - 2 * BEZEL   # 1910

# ─── Camera module (single camera, top-left) ─────────────────────────────
CAM_MOD_SIZE = 320
CAM_MARGIN = 91                 # ~7mm from case edge
CAM_X = CASE_X + CAM_MARGIN     # 406
CAM_Y = CASE_Y + CAM_MARGIN     # 116

# ─── Camera lens ──────────────────────────────────────────────────────────
LENS_D = 160                     # ~12mm
LENS_X = CAM_X + (CAM_MOD_SIZE - LENS_D) // 2
LENS_Y = CAM_Y + (CAM_MOD_SIZE - LENS_D) // 2

# ─── Camera ring (metallic bezel around lens) ────────────────────────────
RING_D = 190
RING_X = CAM_X + (CAM_MOD_SIZE - RING_D) // 2
RING_Y = CAM_Y + (CAM_MOD_SIZE - RING_D) // 2

# ─── Button positions ─────────────────────────────────────────────────────
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
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([x, y, x + rw, y + rh], radius=radius, fill=255)
    return mask


# ═════════════════════════════════════════════════════════════════════════
# BASE — premium case body with depth and edge elevation
# ═════════════════════════════════════════════════════════════════════════
def generate_base():
    """Case body: clean premium surface with 3D edge depth."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    shape_mask = rounded_rect_mask(
        CANVAS_W, CANVAS_H, CASE_X, CASE_Y, CASE_W, CASE_H, CORNER_R
    )

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

    # Outer edge: dark line for case thickness/depth (stronger)
    edge_line = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    el = ImageDraw.Draw(edge_line)
    el.rounded_rectangle(
        [CASE_X, CASE_Y, CASE_X + CASE_W, CASE_Y + CASE_H],
        radius=CORNER_R,
        outline=(150, 148, 145, 230), width=3
    )
    img = Image.alpha_composite(img, edge_line)

    # Inner edge highlight: bright line just inside rim (raised edge effect, stronger)
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
# PRINT MASK — where artwork is allowed (narrow bezel, camera excluded)
# ═════════════════════════════════════════════════════════════════════════
def generate_print_mask():
    """White where printable, transparent where not."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    # Full printable area (tight bezel)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [PRINT_X, PRINT_Y, PRINT_X + PRINT_W, PRINT_Y + PRINT_H],
        radius=CORNER_R - BEZEL,
        fill=(255, 255, 255, 255)
    )

    # Cut out camera module area with feathered edge
    cam_mask = Image.new("L", (CANVAS_W, CANVAS_H), 255)
    cd = ImageDraw.Draw(cam_mask)
    cam_pad = 8
    cd.rounded_rectangle(
        [CAM_X - cam_pad, CAM_Y - cam_pad,
         CAM_X + CAM_MOD_SIZE + cam_pad, CAM_Y + CAM_MOD_SIZE + cam_pad],
        radius=28, fill=0
    )
    cam_mask = cam_mask.filter(ImageFilter.GaussianBlur(1.5))

    result = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    white = Image.new("RGBA", (CANVAS_W, CANVAS_H), (255, 255, 255, 255))
    result.paste(white, (0, 0), cam_mask)

    return result


# ═════════════════════════════════════════════════════════════════════════
# OVERLAY — camera module with depth, rings, rim, buttons
# ═════════════════════════════════════════════════════════════════════════
def generate_overlay():
    """Camera module, rings, edge rim, buttons — above artwork."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    # ── Camera module drop shadow (depth under the bump) ──────────────
    mod_shadow = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ms = ImageDraw.Draw(mod_shadow)
    ms.rounded_rectangle(
        [CAM_X + 4, CAM_Y + 4,
         CAM_X + CAM_MOD_SIZE + 4, CAM_Y + CAM_MOD_SIZE + 4],
        radius=26, fill=(0, 0, 0, 55)
    )
    mod_shadow = mod_shadow.filter(ImageFilter.GaussianBlur(4))
    img = Image.alpha_composite(img, mod_shadow)

    # ── Camera module body (dark metallic) ───────────────────────────
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [CAM_X, CAM_Y, CAM_X + CAM_MOD_SIZE, CAM_Y + CAM_MOD_SIZE],
        radius=25, fill=(48, 48, 51, 255)
    )

    # Module metallic gradient (lighter top-left, darker bottom-right)
    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    mod_cx = CAM_X + CAM_MOD_SIZE / 2
    mod_cy = CAM_Y + CAM_MOD_SIZE / 2
    mdx = (xx - mod_cx) / (CAM_MOD_SIZE / 2)
    mdy = (yy - mod_cy) / (CAM_MOD_SIZE / 2)
    mdist = np.sqrt(mdx**2 + mdy**2).clip(0, 1)
    sheen = 1.0 - mdist * 0.35
    r = (85 * sheen).clip(0, 255)
    g = (85 * sheen).clip(0, 255)
    b = (88 * sheen).clip(0, 255)
    grad_px = np.stack([r, g, b], axis=-1).clip(0, 255).astype(np.uint8)

    mod_mask = rounded_rect_mask(
        CANVAS_W, CANVAS_H, CAM_X, CAM_Y, CAM_MOD_SIZE, CAM_MOD_SIZE, 25
    )
    grad_a = np.array(mod_mask, dtype=np.uint8)
    grad_rgba = np.dstack([grad_px, grad_a])
    mod_grad = Image.fromarray(grad_rgba, "RGBA")
    img = Image.alpha_composite(img, mod_grad)

    # Module inner bevel (bright top-left edge, dark bottom-right)
    d2 = ImageDraw.Draw(img)
    d2.rounded_rectangle(
        [CAM_X + 2, CAM_Y + 2, CAM_X + CAM_MOD_SIZE - 2, CAM_Y + CAM_MOD_SIZE - 2],
        radius=23, outline=(110, 110, 112, 120), width=2
    )

    # ── Camera ring (metallic bezel) ─────────────────────────────────
    d3 = ImageDraw.Draw(img)
    # Outer ring shadow
    d3.ellipse(
        [RING_X - 5, RING_Y - 5, RING_X + RING_D + 5, RING_Y + RING_D + 5],
        fill=(30, 30, 33, 255)
    )
    # Metallic ring
    d3.ellipse(
        [RING_X, RING_Y, RING_X + RING_D, RING_Y + RING_D],
        fill=(125, 125, 128, 255)
    )
    # Ring highlight (top-left arc — light source)
    d3.arc(
        [RING_X + 2, RING_Y + 2, RING_X + RING_D - 2, RING_Y + RING_D - 2],
        start=200, end=340, fill=(195, 195, 198, 220), width=5
    )
    # Ring shadow (bottom-right arc)
    d3.arc(
        [RING_X + 2, RING_Y + 2, RING_X + RING_D - 2, RING_Y + RING_D - 2],
        start=20, end=160, fill=(65, 65, 68, 200), width=4
    )

    # ── Lens (dark glass) ────────────────────────────────────────────
    d4 = ImageDraw.Draw(img)
    # Lens housing (slight ring inside the metallic ring)
    d4.ellipse(
        [LENS_X - 6, LENS_Y - 6, LENS_X + LENS_D + 6, LENS_Y + LENS_D + 6],
        fill=(20, 20, 22, 255)
    )
    # Lens glass (dark with subtle gradient)
    lens_grad = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    lcx = LENS_X + LENS_D / 2
    lcy = LENS_Y + LENS_D / 2
    ldx = (xx - lcx) / (LENS_D / 2)
    ldy = (yy - lcy) / (LENS_D / 2)
    ldist = np.sqrt(ldx**2 + ldy**2).clip(0, 1)
    r = (18 + 8 * (1 - ldist)).clip(0, 255)
    g = (18 + 4 * (1 - ldist)).clip(0, 255)
    b = (25 + 12 * (1 - ldist)).clip(0, 255)
    lens_px = np.stack([r, g, b], axis=-1).clip(0, 255).astype(np.uint8)

    lens_mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    lm = ImageDraw.Draw(lens_mask)
    lm.ellipse(
        [LENS_X, LENS_Y, LENS_X + LENS_D, LENS_Y + LENS_D],
        fill=255
    )
    lens_mask = lens_mask.filter(ImageFilter.GaussianBlur(0.5))
    lens_a = np.array(lens_mask, dtype=np.uint8)
    lens_rgba = np.dstack([lens_px, lens_a])
    lens_grad = Image.fromarray(lens_rgba, "RGBA")
    img = Image.alpha_composite(img, lens_grad)

    # Specular highlight on lens (top-left)
    d5 = ImageDraw.Draw(img)
    spec_x = LENS_X + int(LENS_D * 0.32)
    spec_y = LENS_Y + int(LENS_D * 0.25)
    spec_r = int(LENS_D * 0.14)
    spec_grad = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    for i in range(spec_r, 0, -1):
        alpha = int(90 * (1 - i / spec_r))
        d5.ellipse(
            [spec_x - i, spec_y - i, spec_x + i, spec_y + i],
            fill=(120, 120, 130, alpha)
        )

    # ── Camera module grounding shadow on case body (depth under bump) ──
    cam_ground = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    cg = ImageDraw.Draw(cam_ground)
    cg.rounded_rectangle(
        [CAM_X - 4, CAM_Y - 4,
         CAM_X + CAM_MOD_SIZE + 8, CAM_Y + CAM_MOD_SIZE + 8],
        radius=28, fill=60
    )
    cam_ground = cam_ground.filter(ImageFilter.GaussianBlur(5))
    cam_ground_img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    cam_ground_img.paste(
        Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 70)),
        (0, 0), cam_ground
    )
    img = Image.alpha_composite(img, cam_ground_img)

    # ── Edge rim (raised border above artwork, stronger) ───────────────
    d6 = ImageDraw.Draw(img)
    # Outer rim line (clear edge definition)
    d6.rounded_rectangle(
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

    # ── Button indicators ────────────────────────────────────────────
    d7 = ImageDraw.Draw(img)
    d7.rounded_rectangle(
        [BTN_RIGHT_X - 2, BTN_PWR_Y, BTN_RIGHT_X + 6, BTN_PWR_Y + BTN_H],
        radius=3, fill=(175, 173, 170, 220)
    )
    d7.rounded_rectangle(
        [BTN_LEFT_X - 4, BTN_VOL_UP_Y, BTN_LEFT_X + 4, BTN_VOL_UP_Y + BTN_H],
        radius=3, fill=(175, 173, 170, 220)
    )
    d7.rounded_rectangle(
        [BTN_LEFT_X - 4, BTN_VOL_DN_Y, BTN_LEFT_X + 4, BTN_VOL_DN_Y + BTN_H],
        radius=3, fill=(175, 173, 170, 220)
    )

    return img


# ═════════════════════════════════════════════════════════════════════════
# HIGHLIGHT — subtle directional lighting
# ═════════════════════════════════════════════════════════════════════════
def generate_highlight():
    """Subtle light gradient from top-left — must not look CGI."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    nx = xx / CANVAS_W
    ny = yy / CANVAS_H
    light = 1.0 - np.sqrt(nx**2 + ny**2) * 0.4
    light = light.clip(0.4, 1.0)

    highlight_alpha = (light * 18).clip(0, 18).astype(np.uint8)
    highlight_px = np.full((CANVAS_H, CANVAS_W, 3), 255, dtype=np.uint8)
    rgba = np.dstack([highlight_px, highlight_alpha])

    shape_mask = rounded_rect_mask(
        CANVAS_W, CANVAS_H, CASE_X, CASE_Y, CASE_W, CASE_H, CORNER_R
    )
    shape_arr = np.array(shape_mask, dtype=np.uint8)
    rgba[..., 3] = (rgba[..., 3].astype(np.float32) * shape_arr / 255).astype(np.uint8)

    img = Image.fromarray(rgba, "RGBA")

    # Subtle specular on camera ring
    spec = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spec)
    sd.arc(
        [RING_X, RING_Y, RING_X + RING_D, RING_Y + RING_D],
        start=215, end=325, fill=(255, 255, 255, 60), width=4
    )
    img = Image.alpha_composite(img, spec)

    return img


# ═════════════════════════════════════════════════════════════════════════
# SHADOW — directional contact shadow
# ═════════════════════════════════════════════════════════════════════════
def generate_shadow():
    """Directional contact shadow grounding the product."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

    # Main body shadow — offset to bottom-right (light from top-left)
    shadow_offset_x = 8
    shadow_offset_y = 14
    shadow_expand = 16
    shadow_mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    sd = ImageDraw.Draw(shadow_mask)
    sd.rounded_rectangle(
        [CASE_X - shadow_expand + shadow_offset_x,
         CASE_Y + shadow_offset_y,
         CASE_X + CASE_W + shadow_expand + shadow_offset_x,
         CASE_Y + CASE_H + shadow_expand + shadow_offset_y],
        radius=CORNER_R + shadow_expand,
        fill=110
    )
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(20))

    shadow_px = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    shadow_a = np.array(shadow_mask, dtype=np.uint8)
    rgba = np.dstack([shadow_px, shadow_a])
    img = Image.fromarray(rgba, "RGBA")

    # Camera module shadow (small offset shadow under the bump)
    cam_shadow = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    cs = ImageDraw.Draw(cam_shadow)
    cs.rounded_rectangle(
        [CAM_X + 5, CAM_Y + 5,
         CAM_X + CAM_MOD_SIZE + 5, CAM_Y + CAM_MOD_SIZE + 5],
        radius=25, fill=50
    )
    cam_shadow = cam_shadow.filter(ImageFilter.GaussianBlur(3))
    cam_shadow_img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    cam_shadow_img.paste(
        Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 80)),
        (0, 0), cam_shadow
    )
    img = Image.alpha_composite(img, cam_shadow_img)

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

    base = generate_base()
    base.save(os.path.join(out_dir, "base.png"))
    print(f"  base.png  {base.size}")

    mask = generate_print_mask()
    mask.save(os.path.join(out_dir, "print_mask.png"))
    print(f"  print_mask.png  {mask.size}")

    overlay = generate_overlay()
    overlay.save(os.path.join(out_dir, "overlay.png"))
    print(f"  overlay.png  {overlay.size}")

    highlight = generate_highlight()
    highlight.save(os.path.join(out_dir, "highlight.png"))
    print(f"  highlight.png  {highlight.size}")

    shadow = generate_shadow()
    shadow.save(os.path.join(out_dir, "shadow.png"))
    print(f"  shadow.png  {shadow.size}")

    print("Done. All layers saved to", out_dir)
