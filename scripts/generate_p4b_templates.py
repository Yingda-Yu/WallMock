"""
Generate P4B Wave-1 iPhone 17 and iPhone Air case template layers.

===========================================================================
GEOMETRY PROVENANCE — classification of every dimension
===========================================================================

iPhone 17:
  VERIFIED (Apple official spec — apple.com/iphone-17/specs/):
    - Body height: 149.6 mm
    - Body width:  71.5 mm
    - Body depth:  7.95 mm
    - 48MP Dual Fusion rear camera system (dual lens)
  VISUALLY ESTIMATED (from Apple product imagery):
    - Dual camera diagonally arranged in upper-left
    - Corner radius: ~12.0 mm
    - Button positions (volume up/down, side button)
  ASSUMED (prototype hard-case parameters):
    - Case thickness: 1.5 mm per side
    - Print bezel: ~1.5 mm from case edge
    - Camera cutout clearance: ~1 mm around lens
  SUPPLIER GEOMETRY: none (prototype only)

iPhone Air:
  VERIFIED (Apple official spec — apple.com/iphone-air/specs/):
    - Body height: 156.2 mm
    - Body width:  74.7 mm
    - Body depth:  5.64 mm
    - 48MP Fusion Main rear camera system (single lens)
  VISUALLY ESTIMATED (from Apple product imagery):
    - Single camera in upper-left region
    - Corner radius: ~13.0 mm (slim Air design language)
    - Button positions
  ASSUMED (prototype hard-case parameters):
    - Case thickness: 1.2 mm per side (thinner for Air model)
    - Print bezel: ~1.2 mm from case edge
    - Camera cutout clearance: ~1 mm around lens
  SUPPLIER GEOMETRY: none (prototype only)

Scale: 13 px/mm (consistent with iPhone 17e template)
"""

import math
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ═════════════════════════════════════════════════════════════════════════
# Shared scale
# ═════════════════════════════════════════════════════════════════════════
SCALE = 13  # px per mm
CASE_THICKNESS_MM = 1.5  # mm per side (standard hard case)
AIR_CASE_THICKNESS_MM = 1.2  # mm per side (thinner for Air)
BEZEL_MM = 1.5  # print bezel
AIR_BEZEL_MM = 1.2  # thinner bezel for Air


def generate_device_template(config):
    """Generate all template layers for a device config.

    Config keys:
        device_id, display_name, spec_url,
        phone_w_mm, phone_h_mm, phone_d_mm,
        corner_r_mm, camera_type ("single" or "dual"),
        case_thickness_mm, bezel_mm,
        canvas_w, canvas_h,
        provenance_text
    """
    device_id = config["device_id"]
    phone_w_mm = config["phone_w_mm"]
    phone_h_mm = config["phone_h_mm"]
    corner_r_mm = config.get("corner_r_mm", 12.0)
    case_thickness_mm = config.get("case_thickness_mm", CASE_THICKNESS_MM)
    bezel_mm = config.get("bezel_mm", BEZEL_MM)
    camera_type = config.get("camera_type", "single")
    canvas_w = config["canvas_w"]
    canvas_h = config["canvas_h"]

    # Derived dimensions
    case_w = int(round((phone_w_mm + 2 * case_thickness_mm) * SCALE))
    case_h = int(round((phone_h_mm + 2 * case_thickness_mm) * SCALE))
    case_x = (canvas_w - case_w) // 2
    case_y = (canvas_h - case_h) // 2
    corner_r = int(round(corner_r_mm * SCALE))

    bezel_px = int(round(bezel_mm * SCALE))
    print_x = case_x + bezel_px
    print_y = case_y + bezel_px
    print_w = case_w - 2 * bezel_px
    print_h = case_h - 2 * bezel_px
    print_corner_r = max(corner_r - bezel_px, 10)

    # Camera layout
    cam_config = _camera_config(camera_type, case_x, case_y, case_w, case_h)

    # Button positions
    btn_h = int(round(4.6 * SCALE))
    btn_right_x = case_x + case_w - 3
    btn_left_x = case_x - 3
    btn_vol_up_y = case_y + int(case_h * 0.26)
    btn_vol_dn_y = case_y + int(case_h * 0.34)
    btn_pwr_y = case_y + int(case_h * 0.30)

    # ── helpers ────────────────────────────────────────────────────────

    def rounded_rect_mask(w, h, x, y, rw, rh, radius):
        mask = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(mask)
        d.rounded_rectangle([x, y, x + rw, y + rh], radius=radius, fill=255)
        return mask

    def case_body_mask():
        return rounded_rect_mask(
            canvas_w, canvas_h, case_x, case_y, case_w, case_h, corner_r
        )

    def camera_exclusion_mask():
        """L-mode mask: 255=printable, 0=excluded (camera area)"""
        mask = Image.new("L", (canvas_w, canvas_h), 255)
        d = ImageDraw.Draw(mask)
        pad = cam_config["exclude_pad"]

        # If a plateau exists, exclude the entire plateau region from print
        # (the raised platform surface is not a good print target)
        if "plateau" in cam_config:
            plat = cam_config["plateau"]
            plat_h = plat["bottom"] - plat["top"]
            plat_r = plat_h // 2
            d.rounded_rectangle(
                [plat["left"], plat["top"], plat["right"], plat["bottom"]],
                radius=plat_r,
                fill=0
            )

        for comp in cam_config["components"]:
            if comp["type"] == "lens":
                r = comp["radius"] + comp.get("ring_width", 0) + pad
                d.ellipse(
                    [comp["cx"] - r, comp["cy"] - r,
                     comp["cx"] + r, comp["cy"] + r],
                    fill=0
                )
            elif comp["type"] == "flash":
                half = comp["size"] // 2 + pad
                d.rounded_rectangle(
                    [comp["cx"] - half, comp["cy"] - half,
                     comp["cx"] + half, comp["cy"] + half],
                    radius=half // 2, fill=0
                )
            elif comp["type"] == "mic":
                r = comp["radius"] + pad
                d.ellipse(
                    [comp["cx"] - r, comp["cy"] - r,
                     comp["cx"] + r, comp["cy"] + r],
                    fill=0
                )
        return mask

    # ── BASE ──────────────────────────────────────────────────────────
    def generate_base():
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shape_mask = case_body_mask()

        base_rgb = np.array([248, 247, 245], dtype=np.float32)
        yy, xx = np.mgrid[0:canvas_h, 0:canvas_w].astype(np.float32)
        cx = case_x + case_w / 2
        cy = case_y + case_h / 2

        x_norm = (xx - cx) / (case_w / 2)
        cyl_darken = 1.0 - (np.abs(x_norm) ** 2) * 0.12

        dy = (yy - cy) / (case_h / 2)
        dist = np.sqrt(x_norm**2 + dy**2).clip(0, 1)
        rad_darken = 1.0 - dist * 0.05

        darken = cyl_darken * rad_darken

        y_frac = (yy - case_y) / case_h
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

        # Outer edge line
        edge_line = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        el = ImageDraw.Draw(edge_line)
        el.rounded_rectangle(
            [case_x, case_y, case_x + case_w, case_y + case_h],
            radius=corner_r,
            outline=(150, 148, 145, 230), width=3
        )
        img = Image.alpha_composite(img, edge_line)

        # Inner edge highlight
        inner_highlight = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        ih = ImageDraw.Draw(inner_highlight)
        ih.rounded_rectangle(
            [case_x + 3, case_y + 3, case_x + case_w - 3, case_y + case_h - 3],
            radius=corner_r - 3,
            outline=(255, 255, 255, 220), width=3
        )
        inner_highlight = inner_highlight.filter(ImageFilter.GaussianBlur(1.0))
        img = Image.alpha_composite(img, inner_highlight)

        # Inner edge shadow
        inner_shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        ish = ImageDraw.Draw(inner_shadow)
        ish.rounded_rectangle(
            [case_x + 7, case_y + 7, case_x + case_w - 7, case_y + case_h - 7],
            radius=corner_r - 7,
            outline=(0, 0, 0, 55), width=3
        )
        inner_shadow = inner_shadow.filter(ImageFilter.GaussianBlur(1.5))
        img = Image.alpha_composite(img, inner_shadow)

        return img

    # ── PRINT MASK ────────────────────────────────────────────────────
    def generate_print_mask():
        print_region = rounded_rect_mask(
            canvas_w, canvas_h,
            print_x, print_y, print_w, print_h, print_corner_r
        )
        body = case_body_mask()
        cam_clear = camera_exclusion_mask()

        pr_arr = np.array(print_region, dtype=np.uint32)
        body_arr = np.array(body, dtype=np.uint32)
        cam_arr = np.array(cam_clear, dtype=np.uint32)
        result_arr = (pr_arr * body_arr * cam_arr) // (255 * 255)
        result_arr = result_arr.clip(0, 255).astype(np.uint8)
        return Image.fromarray(result_arr, "L")

    # ── OVERLAY ───────────────────────────────────────────────────────
    def generate_overlay():
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Plateau (for air_plateau camera type): raised horizontal platform
        if "plateau" in cam_config:
            plat = cam_config["plateau"]
            plat_w = plat["right"] - plat["left"]
            plat_h = plat["bottom"] - plat["top"]
            plat_r = plat_h // 2  # fully rounded pill shape

            # Plateau shadow (subtle depth beneath)
            plat_shadow = Image.new("L", (canvas_w, canvas_h), 0)
            ps = ImageDraw.Draw(plat_shadow)
            ps.rounded_rectangle(
                [plat["left"] + 2, plat["top"] + 4,
                 plat["right"] + 2, plat["bottom"] + 4],
                radius=plat_r,
                fill=70
            )
            plat_shadow = plat_shadow.filter(ImageFilter.GaussianBlur(4))
            plat_shadow_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            plat_shadow_img.paste(
                Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 100)),
                (0, 0), plat_shadow
            )
            img = Image.alpha_composite(img, plat_shadow_img)

            # Plateau body (matte glass / metallic surface)
            plateau_base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            pb = ImageDraw.Draw(plateau_base)
            pb.rounded_rectangle(
                [plat["left"], plat["top"], plat["right"], plat["bottom"]],
                radius=plat_r,
                fill=(165, 163, 160, 255)
            )
            # Subtle top-to-bottom gradient on plateau
            yy, xx = np.mgrid[0:canvas_h, 0:canvas_w].astype(np.float32)
            plat_ymid = (plat["top"] + plat["bottom"]) / 2
            plat_norm = ((yy - plat_ymid) / (plat_h / 2)).clip(-1, 1)
            grad_factor = (1.0 - plat_norm * 0.15).clip(0, 1)
            # Apply gradient to plateau pixels only
            plat_mask = Image.new("L", (canvas_w, canvas_h), 0)
            pm = ImageDraw.Draw(plat_mask)
            pm.rounded_rectangle(
                [plat["left"], plat["top"], plat["right"], plat["bottom"]],
                radius=plat_r,
                fill=255
            )
            plat_mask_arr = np.array(plat_mask, dtype=np.float32) / 255
            plat_arr = np.array(plateau_base, dtype=np.float32)
            for c in range(3):
                plat_arr[..., c] *= grad_factor
            plat_arr = plat_arr.clip(0, 255).astype(np.uint8)
            plateau_base = Image.fromarray(plat_arr, "RGBA")
            # Mask to plateau shape
            plateau_base.putalpha(plat_mask)
            img = Image.alpha_composite(img, plateau_base)

            # Plateau outer rim highlight
            d.rounded_rectangle(
                [plat["left"], plat["top"], plat["right"], plat["bottom"]],
                radius=plat_r,
                outline=(195, 193, 190, 220), width=2
            )
            # Plateau inner shadow (recessed edge feel)
            inner_edge = Image.new("L", (canvas_w, canvas_h), 0)
            ie = ImageDraw.Draw(inner_edge)
            ie.rounded_rectangle(
                [plat["left"] + 4, plat["top"] + 4,
                 plat["right"] - 4, plat["bottom"] - 4],
                radius=plat_r - 4,
                outline=100, width=2
            )
            inner_edge = inner_edge.filter(ImageFilter.GaussianBlur(2.0))
            inner_edge_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            inner_edge_img.putalpha(inner_edge)
            img = Image.alpha_composite(img, inner_edge_img)

        # Camera components
        for comp in cam_config["components"]:
            if comp["type"] == "lens":
                ring_outer = comp["radius"] + comp.get("ring_width", 12)
                # Ring shadow
                ring_shadow = Image.new("L", (canvas_w, canvas_h), 0)
                rs = ImageDraw.Draw(ring_shadow)
                rs.ellipse(
                    [comp["cx"] - ring_outer - 2, comp["cy"] - ring_outer + 3,
                     comp["cx"] + ring_outer + 2, comp["cy"] + ring_outer + 3],
                    fill=80
                )
                ring_shadow = ring_shadow.filter(ImageFilter.GaussianBlur(3))
                ring_shadow_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
                ring_shadow_img.paste(
                    Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 100)),
                    (0, 0), ring_shadow
                )
                img = Image.alpha_composite(img, ring_shadow_img)

                # Metallic ring body
                d.ellipse(
                    [comp["cx"] - ring_outer, comp["cy"] - ring_outer,
                     comp["cx"] + ring_outer, comp["cy"] + ring_outer],
                    fill=(130, 130, 133, 255)
                )

                # Ring highlight (top-left arc)
                d.arc(
                    [comp["cx"] - ring_outer + 2, comp["cy"] - ring_outer + 2,
                     comp["cx"] + ring_outer - 2, comp["cy"] + ring_outer - 2],
                    start=200, end=340, fill=(200, 200, 203, 230), width=4
                )
                # Ring shadow (bottom-right arc)
                d.arc(
                    [comp["cx"] - ring_outer + 2, comp["cy"] - ring_outer + 2,
                     comp["cx"] + ring_outer - 2, comp["cy"] + ring_outer - 2],
                    start=20, end=160, fill=(70, 70, 73, 200), width=3
                )

                # Lens glass
                d.ellipse(
                    [comp["cx"] - comp["radius"], comp["cy"] - comp["radius"],
                     comp["cx"] + comp["radius"], comp["cy"] + comp["radius"]],
                    fill=(15, 15, 18, 255)
                )

                # Lens glass gradient
                yy, xx = np.mgrid[0:canvas_h, 0:canvas_w].astype(np.float32)
                ldx = (xx - comp["cx"]) / comp["radius"]
                ldy = (yy - comp["cy"]) / comp["radius"]
                ldist = np.sqrt(ldx**2 + ldy**2).clip(0, 1)
                r = (15 + 10 * (1 - ldist)).clip(0, 255)
                g = (15 + 5 * (1 - ldist)).clip(0, 255)
                b = (22 + 15 * (1 - ldist)).clip(0, 255)
                lens_px = np.stack([r, g, b], axis=-1).clip(0, 255).astype(np.uint8)

                lens_mask = Image.new("L", (canvas_w, canvas_h), 0)
                lm = ImageDraw.Draw(lens_mask)
                lm.ellipse(
                    [comp["cx"] - comp["radius"] + 3, comp["cy"] - comp["radius"] + 3,
                     comp["cx"] + comp["radius"] - 3, comp["cy"] + comp["radius"] - 3],
                    fill=255
                )
                lens_mask = lens_mask.filter(ImageFilter.GaussianBlur(0.5))
                lens_a = np.array(lens_mask, dtype=np.uint8)
                lens_rgba = np.dstack([lens_px, lens_a])
                lens_grad = Image.fromarray(lens_rgba, "RGBA")
                img = Image.alpha_composite(img, lens_grad)

                # Specular highlight on lens (top-left)
                spec_x = comp["cx"] + int(comp["radius"] * 0.35)
                spec_y = comp["cy"] - int(comp["radius"] * 0.3)
                spec_r = int(comp["radius"] * 0.25)
                for i in range(spec_r, 0, -1):
                    alpha = int(100 * (1 - i / spec_r))
                    d.ellipse(
                        [spec_x - i, spec_y - i, spec_x + i, spec_y + i],
                        fill=(140, 140, 150, alpha)
                    )

            elif comp["type"] == "flash":
                flash_half = comp["size"] // 2
                d.rounded_rectangle(
                    [comp["cx"] - flash_half, comp["cy"] - flash_half,
                     comp["cx"] + flash_half, comp["cy"] + flash_half],
                    radius=flash_half // 2, fill=(235, 230, 210, 255)
                )
                d.rounded_rectangle(
                    [comp["cx"] - flash_half + 4, comp["cy"] - flash_half + 4,
                     comp["cx"] + flash_half - 4, comp["cy"] + flash_half - 4],
                    radius=(flash_half - 4) // 2, fill=(255, 250, 235, 200)
                )
                d.rounded_rectangle(
                    [comp["cx"] - flash_half, comp["cy"] - flash_half,
                     comp["cx"] + flash_half, comp["cy"] + flash_half],
                    radius=flash_half // 2, outline=(180, 175, 165, 255), width=2
                )

            elif comp["type"] == "mic":
                d.ellipse(
                    [comp["cx"] - comp["radius"], comp["cy"] - comp["radius"],
                     comp["cx"] + comp["radius"], comp["cy"] + comp["radius"]],
                    fill=(25, 25, 28, 255)
                )
                d.ellipse(
                    [comp["cx"] - comp["radius"] + 2, comp["cy"] - comp["radius"] + 2,
                     comp["cx"] + comp["radius"] - 2, comp["cy"] + comp["radius"] - 2],
                    outline=(60, 60, 63, 180), width=1
                )

        # Edge rim
        d.rounded_rectangle(
            [case_x, case_y, case_x + case_w, case_y + case_h],
            radius=corner_r,
            outline=(160, 158, 155, 240), width=3
        )

        # Inner rim shadow
        inner_rim = Image.new("L", (canvas_w, canvas_h), 0)
        ir = ImageDraw.Draw(inner_rim)
        ir.rounded_rectangle(
            [case_x + 5, case_y + 5, case_x + case_w - 5, case_y + case_h - 5],
            radius=corner_r - 5,
            outline=255, width=4
        )
        inner_rim = inner_rim.filter(ImageFilter.GaussianBlur(2.0))
        rim_shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 60))
        img.paste(rim_shadow, (0, 0), inner_rim)

        # Buttons
        d.rounded_rectangle(
            [btn_right_x - 2, btn_pwr_y, btn_right_x + 6, btn_pwr_y + btn_h],
            radius=3, fill=(175, 173, 170, 220)
        )
        d.rounded_rectangle(
            [btn_left_x - 4, btn_vol_up_y, btn_left_x + 4, btn_vol_up_y + btn_h],
            radius=3, fill=(175, 173, 170, 220)
        )
        d.rounded_rectangle(
            [btn_left_x - 4, btn_vol_dn_y, btn_left_x + 4, btn_vol_dn_y + btn_h],
            radius=3, fill=(175, 173, 170, 220)
        )

        return img

    # ── HIGHLIGHT ─────────────────────────────────────────────────────
    def generate_highlight():
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        yy, xx = np.mgrid[0:canvas_h, 0:canvas_w].astype(np.float32)
        nx = xx / canvas_w
        ny = yy / canvas_h
        light = 1.0 - np.sqrt(nx**2 + ny**2) * 0.4
        light = light.clip(0.4, 1.0)

        highlight_alpha = (light * 18).clip(0, 18).astype(np.uint8)
        highlight_px = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
        rgba = np.dstack([highlight_px, highlight_alpha])

        shape_mask = case_body_mask()
        shape_arr = np.array(shape_mask, dtype=np.uint8)
        rgba[..., 3] = (rgba[..., 3].astype(np.float32) * shape_arr / 255).astype(np.uint8)

        img = Image.fromarray(rgba, "RGBA")

        # Specular on first lens ring
        for comp in cam_config["components"]:
            if comp["type"] == "lens":
                ring_outer = comp["radius"] + comp.get("ring_width", 12)
                spec = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
                sd = ImageDraw.Draw(spec)
                sd.arc(
                    [comp["cx"] - ring_outer, comp["cy"] - ring_outer,
                     comp["cx"] + ring_outer, comp["cy"] + ring_outer],
                    start=215, end=325, fill=(255, 255, 255, 60), width=3
                )
                img = Image.alpha_composite(img, spec)
                break  # only first lens gets the main highlight

        return img

    # ── SHADOW ────────────────────────────────────────────────────────
    def generate_shadow():
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        shadow_offset_x = 6
        shadow_offset_y = 12
        shadow_expand = 14

        shadow_shape = Image.new("L", (canvas_w, canvas_h), 0)
        sd = ImageDraw.Draw(shadow_shape)
        sd.rounded_rectangle(
            [case_x - shadow_expand + shadow_offset_x,
             case_y + shadow_offset_y,
             case_x + case_w + shadow_expand + shadow_offset_x,
             case_y + case_h + shadow_expand + shadow_offset_y],
            radius=corner_r + shadow_expand,
            fill=120
        )
        shadow_shape = shadow_shape.filter(ImageFilter.GaussianBlur(18))

        body = case_body_mask()
        body_expanded = body.filter(ImageFilter.GaussianBlur(1.5))
        body_arr = np.array(body_expanded, dtype=np.uint16)
        shadow_arr = np.array(shadow_shape, dtype=np.uint16)

        outside_only = (shadow_arr * (255 - body_arr)) // 255
        outside_only = outside_only.clip(0, 255).astype(np.uint8)

        shadow_px = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        shadow_rgba = np.dstack([shadow_px, outside_only])
        img = Image.fromarray(shadow_rgba, "RGBA")

        return img

    return {
        "base": generate_base(),
        "print_mask": generate_print_mask(),
        "overlay": generate_overlay(),
        "highlight": generate_highlight(),
        "shadow": generate_shadow(),
        "print_region": {
            "x": print_x,
            "y": print_y,
            "width": print_w,
            "height": print_h,
        },
        "camera_region": cam_config.get("region"),
    }


def _camera_config(camera_type, case_x, case_y, case_w, case_h):
    """Return camera component layout for the given camera type.

    Camera types:
    - single: iPhone 17e style, single lens + flash + mic
    - dual_vertical: iPhone 17 style, vertically stacked dual camera
      (main on top, ultrawide below), flash+mic to the right
    - air_plateau: iPhone Air style, single lens + flash on a
      horizontally extended raised plateau (side-to-side)
    """

    if camera_type == "dual_vertical":
        # iPhone 17: vertically stacked dual camera
        # 48MP Dual Fusion — main (top) + ultrawide (bottom)
        # Both lenses in a vertical column, flash + mic to the right
        main_lens_radius = 60      # ~4.6mm main lens
        uw_lens_radius = 50        # ~3.8mm ultrawide
        ring_width = 12
        lens_spacing = 130         # vertical distance between lens centers

        # Lens column: centered vertically in upper camera region
        lens_cx = case_x + int(case_w * 0.22)
        top_lens_cy = case_y + int(case_h * 0.11)
        bottom_lens_cy = top_lens_cy + lens_spacing

        # Flash: to the right of the lens column, aligned with top lens
        flash_cx = lens_cx + 130
        flash_cy = top_lens_cy + 5
        flash_size = 42

        # Mic: below flash, roughly between the two lenses vertically
        mic_cx = flash_cx + 5
        mic_cy = bottom_lens_cy - 10
        mic_radius = 11

        return {
            "exclude_pad": 18,
            # Camera region bbox for geometry-aware crops
            "region": {
                "x": lens_cx - main_lens_radius - ring_width - 20,
                "y": top_lens_cy - main_lens_radius - ring_width - 20,
                "w": (flash_cx + flash_size // 2 + 20) - (lens_cx - main_lens_radius - ring_width - 20),
                "h": (bottom_lens_cy + uw_lens_radius + ring_width + 20) - (top_lens_cy - main_lens_radius - ring_width - 20),
            },
            "components": [
                {
                    "type": "lens",
                    "cx": lens_cx,
                    "cy": top_lens_cy,
                    "radius": main_lens_radius,
                    "ring_width": ring_width,
                },
                {
                    "type": "lens",
                    "cx": lens_cx,
                    "cy": bottom_lens_cy,
                    "radius": uw_lens_radius,
                    "ring_width": ring_width,
                },
                {
                    "type": "flash",
                    "cx": flash_cx,
                    "cy": flash_cy,
                    "size": flash_size,
                },
                {
                    "type": "mic",
                    "cx": mic_cx,
                    "cy": mic_cy,
                    "radius": mic_radius,
                },
            ],
        }

    elif camera_type == "air_plateau":
        # iPhone Air: single lens + flash + mic on a full-width raised plateau
        # The plateau extends essentially edge-to-edge across the top of the rear
        # — matching Apple's iPhone Air design language.
        lens_radius = 65      # ~5.0mm main lens
        ring_width = 12
        plateau_v_pad = 22    # vertical padding (top/bottom of plateau)

        # Plateau spans nearly the full case width, edge-to-edge
        # Small inset from case sides for visual naturalness
        plateau_side_inset = 6
        plateau_left = case_x + plateau_side_inset
        plateau_right = case_x + case_w - plateau_side_inset

        # Plateau vertical position: across the top portion of the phone
        plateau_top = case_y + int(case_h * 0.06)
        plateau_bottom = case_y + int(case_h * 0.19)

        # Lens position: left side within the plateau
        lens_cx = case_x + int(case_w * 0.22)
        lens_cy = (plateau_top + plateau_bottom) // 2

        # Flash: right-center within the plateau
        flash_cx = case_x + int(case_w * 0.62)
        flash_cy = lens_cy - 4
        flash_size = 44

        # Mic: far right within the plateau
        mic_cx = case_x + int(case_w * 0.82)
        mic_cy = lens_cy + 2
        mic_radius = 11

        return {
            "exclude_pad": 18,
            "region": {
                "x": plateau_left - 5,
                "y": plateau_top - 5,
                "w": (plateau_right - plateau_left) + 10,
                "h": (plateau_bottom - plateau_top) + 10,
            },
            "plateau": {
                "left": plateau_left,
                "right": plateau_right,
                "top": plateau_top,
                "bottom": plateau_bottom,
            },
            "components": [
                {
                    "type": "lens",
                    "cx": lens_cx,
                    "cy": lens_cy,
                    "radius": lens_radius,
                    "ring_width": ring_width,
                },
                {
                    "type": "flash",
                    "cx": flash_cx,
                    "cy": flash_cy,
                    "size": flash_size,
                },
                {
                    "type": "mic",
                    "cx": mic_cx,
                    "cy": mic_cy,
                    "radius": mic_radius,
                },
            ],
        }

    else:
        # Default: single camera (iPhone 17e style)
        lens_radius = 70
        ring_width = 12

        lens_cx = case_x + int(case_w * 0.22)
        lens_cy = case_y + int(case_h * 0.13)

        flash_cx = lens_cx + 140
        flash_cy = lens_cy - 20
        flash_size = 48

        mic_cx = flash_cx
        mic_cy = lens_cy + 55
        mic_radius = 12

        return {
            "exclude_pad": 18,
            "region": {
                "x": lens_cx - lens_radius - ring_width - 20,
                "y": lens_cy - lens_radius - ring_width - 20,
                "w": (flash_cx + flash_size // 2 + 20) - (lens_cx - lens_radius - ring_width - 20),
                "h": (mic_cy + mic_radius + 20) - (lens_cy - lens_radius - ring_width - 20),
            },
            "components": [
                {
                    "type": "lens",
                    "cx": lens_cx,
                    "cy": lens_cy,
                    "radius": lens_radius,
                    "ring_width": ring_width,
                },
                {
                    "type": "flash",
                    "cx": flash_cx,
                    "cy": flash_cy,
                    "size": flash_size,
                },
                {
                    "type": "mic",
                    "cx": mic_cx,
                    "cy": mic_cy,
                    "radius": mic_radius,
                },
            ],
        }


def write_template_json(out_dir, config):
    """Write the template.json metadata file."""
    import json

    template = {
        "schema_version": 1,
        "id": f"{config['device_id']}__hard__rear",
        "device_id": config["device_id"],
        "case_type": "hard",
        "view": "rear",
        "status": "prototype",
        "provenance": config["provenance"],
        "canvas": {
            "width": config["canvas_w"],
            "height": config["canvas_h"],
        },
        "print_region": {
            "mode": "mask",
            "x": config["_print_x"],
            "y": config["_print_y"],
            "width": config["_print_w"],
            "height": config["_print_h"],
            "fit": "cover",
            "mask": "print_mask.png",
        },
        "layers": [
            {"type": "shadow", "file": "shadow.png"},
            {"type": "base", "file": "base.png"},
            {"type": "artwork", "blend": "normal"},
            {"type": "highlight", "file": "highlight.png", "opacity": 1.0},
            {"type": "overlay", "file": "overlay.png"},
        ],
    }

    # Camera region (geometry-aware crops, review-time metadata only)
    if config.get("_camera_region"):
        template["camera_region"] = config["_camera_region"]

    # Write with stable sorted keys for deterministic output
    with open(os.path.join(out_dir, "template.json"), "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


# ═════════════════════════════════════════════════════════════════════════
# Device configurations
# ═════════════════════════════════════════════════════════════════════════

IPHONE_17_CONFIG = {
    "device_id": "iphone-17",
    "display_name": "iPhone 17",
    "spec_url": "https://www.apple.com/iphone-17/specs/",
    "phone_w_mm": 71.5,
    "phone_h_mm": 149.6,
    "phone_d_mm": 7.95,
    "corner_r_mm": 12.0,
    "camera_type": "dual_vertical",
    "case_thickness_mm": 1.5,
    "bezel_mm": 1.5,
    "canvas_w": 1600,
    "canvas_h": 2050,
    "provenance": {
        "verified_device_dimensions": "149.6 x 71.5 x 7.95 mm (Apple official spec — apple.com/iphone-17/specs/)",
        "estimated_device_anchors": "48MP Dual Fusion — vertically stacked dual camera (main top, ultrawide bottom), flash + mic to right, corner radius, button positions (visually estimated from Apple product imagery)",
        "assumed_case_parameters": "1.5mm case thickness, 1.5mm print bezel (prototype hard-case assumptions)",
        "supplier_geometry": "none — not a production SKU template",
    },
}

IPHONE_AIR_CONFIG = {
    "device_id": "iphone-air",
    "display_name": "iPhone Air",
    "spec_url": "https://www.apple.com/iphone-air/specs/",
    "phone_w_mm": 74.7,
    "phone_h_mm": 156.2,
    "phone_d_mm": 5.64,
    "corner_r_mm": 13.0,
    "camera_type": "air_plateau",
    "case_thickness_mm": 1.2,
    "bezel_mm": 1.2,
    "canvas_w": 1650,
    "canvas_h": 2150,
    "provenance": {
        "verified_device_dimensions": "156.2 x 74.7 x 5.64 mm (Apple official spec — apple.com/iphone-air/specs/)",
        "estimated_device_anchors": "single main lens + flash + mic on full-width raised plateau (edge-to-edge across top rear), corner radius, button positions (visually estimated from Apple product imagery)",
        "assumed_case_parameters": "1.2mm case thickness, 1.2mm print bezel (slim prototype case assumptions for Air)",
        "supplier_geometry": "none — not a production SKU template",
    },
}


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_root)

    devices = [IPHONE_17_CONFIG, IPHONE_AIR_CONFIG]

    for config in devices:
        device_id = config["device_id"]
        print(f"Generating {config['display_name']} hard/rear template layers...")
        print(f"  STATUS: PROTOTYPE / REFERENCE TEMPLATE")
        print(f"  Body: {config['phone_h_mm']} x {config['phone_w_mm']} x {config['phone_d_mm']} mm (Apple verified)")
        print(f"  Camera: {config['camera_type']}")
        print(f"  Canvas: {config['canvas_w']}x{config['canvas_h']}")
        print()

        layers = generate_device_template(config)

        # Store print region back in config for template.json
        config["_print_x"] = layers["print_region"]["x"]
        config["_print_y"] = layers["print_region"]["y"]
        config["_print_w"] = layers["print_region"]["width"]
        config["_print_h"] = layers["print_region"]["height"]

        # Store camera region for geometry-aware crops
        config["_camera_region"] = layers["camera_region"]

        out_dir = os.path.join(
            "assets", "case_templates", "apple", device_id, "hard", "rear"
        )
        os.makedirs(out_dir, exist_ok=True)

        layers["base"].save(os.path.join(out_dir, "base.png"))
        print(f"  base.png  {layers['base'].size}")

        layers["print_mask"].save(os.path.join(out_dir, "print_mask.png"))
        print(f"  print_mask.png  {layers['print_mask'].size} (L-mode)")

        layers["overlay"].save(os.path.join(out_dir, "overlay.png"))
        print(f"  overlay.png  {layers['overlay'].size}")

        layers["highlight"].save(os.path.join(out_dir, "highlight.png"))
        print(f"  highlight.png  {layers['highlight'].size}")

        layers["shadow"].save(os.path.join(out_dir, "shadow.png"))
        print(f"  shadow.png  {layers['shadow'].size}")

        write_template_json(out_dir, config)
        print(f"  template.json  (id={config['device_id']}__hard__rear)")

        print()
        print("NOTE: This is a PROTOTYPE template.")
        print(f"Only body dimensions are Apple-verified.")
        print()

    print(f"Done. Generated {len(devices)} template(s).")


if __name__ == "__main__":
    main()
