"""
Case artwork fitter for WallMock 2.0.

Fits source artwork to a target print region using cover, contain, or tile
modes. Supports zoom, normalized offsets, and focal-point-based cropping.

This module is independent of Flask, HTTP, and the template loader.
It operates purely on PIL Image objects and numeric parameters.

Public API:
    fit_artwork(artwork, target_w, target_h, *, mode, zoom,
                offset_x, offset_y, focal_point) -> Image
"""

from typing import Tuple, Optional

from PIL import Image, ImageFilter

# High-quality resampling filter
RESAMPLE = Image.LANCZOS


def fit_artwork(
    artwork: Image.Image,
    target_w: int,
    target_h: int,
    *,
    mode: str = "cover",
    zoom: float = 1.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    focal_point: Tuple[float, float] = (0.5, 0.5),
) -> Image.Image:
    """Fit *artwork* into a (target_w × target_h) RGBA image.

    Parameters
    ----------
    artwork : PIL.Image
        Source artwork. May be RGB or RGBA.
    target_w, target_h : int
        Output dimensions in pixels.
    mode : str
        'cover'  – fill the region, cropping overflow.
        'contain'– fit entirely, padding with transparency.
        'tile'   – repeat the artwork at its natural size (or zoomed).
    zoom : float
        Multiplier applied to the computed scale (1.0 = no change).
    offset_x, offset_y : float
        Normalized offsets in [-1, 1]. Positive = right/down.
        0.0 = centered (or focal-point-adjusted) position.
    focal_point : (float, float)
        Normalized (x, y) in [0, 1]. Determines which part of the
        source is visible when cropping. (0.5, 0.5) = center.

    Returns
    -------
    PIL.Image (RGBA), dimensions (target_w, target_h).
    """
    if target_w <= 0 or target_h <= 0:
        raise ValueError(f"Invalid target dimensions: {target_w}x{target_h}")

    # Ensure RGBA
    art = artwork.convert("RGBA")
    aw, ah = art.size

    if aw == 0 or ah == 0:
        raise ValueError("Artwork has zero dimension")

    if mode == "cover":
        return _fit_cover(art, aw, ah, target_w, target_h,
                          zoom, offset_x, offset_y, focal_point)
    elif mode == "contain":
        return _fit_contain(art, aw, ah, target_w, target_h,
                            zoom, offset_x, offset_y, focal_point)
    elif mode == "tile":
        return _fit_tile(art, aw, ah, target_w, target_h,
                         zoom, offset_x, offset_y)
    else:
        raise ValueError(f"Unknown fit mode: '{mode}'. Use cover/contain/tile.")


# ---------------------------------------------------------------------------
# cover — fill target, crop overflow
# ---------------------------------------------------------------------------

def _fit_cover(art, aw, ah, tw, th, zoom, ox, oy, fp):
    """Scale to cover target, crop centered on focal point + offsets."""
    scale = max(tw / aw, th / ah) * zoom
    scaled_w = int(round(aw * scale))
    scaled_h = int(round(ah * scale))

    scaled = art.resize((scaled_w, scaled_h), RESAMPLE)

    # Compute crop origin using focal point + offset
    # focal_point determines the center of the visible region
    # offset shifts it further (normalized to target dimensions)
    crop_x = int(scaled_w * fp[0]) - tw // 2
    crop_y = int(scaled_h * fp[1]) - th // 2

    # Apply offsets (in source pixels after scaling)
    crop_x += int(ox * tw)
    crop_y += int(oy * th)

    # Clamp crop origin so we stay within the scaled image
    crop_x = max(0, min(crop_x, scaled_w - tw))
    crop_y = max(0, min(crop_y, scaled_h - th))

    result = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    result.paste(scaled, (-crop_x, -crop_y))
    return result


# ---------------------------------------------------------------------------
# contain — fit entirely, pad with transparency
# ---------------------------------------------------------------------------

def _fit_contain(art, aw, ah, tw, th, zoom, ox, oy, fp):
    """Scale to fit inside target, center using focal point + offsets."""
    scale = min(tw / aw, th / ah) * zoom
    scaled_w = int(round(aw * scale))
    scaled_h = int(round(ah * scale))

    scaled = art.resize((scaled_w, scaled_h), RESAMPLE)

    # Position: focal point maps to target center, then offset
    paste_x = tw // 2 - int(scaled_w * fp[0])
    paste_y = th // 2 - int(scaled_h * fp[1])

    paste_x += int(ox * tw)
    paste_y += int(oy * th)

    # Clamp paste position so artwork stays partially visible
    paste_x = max(-scaled_w + 1, min(paste_x, tw - 1))
    paste_y = max(-scaled_h + 1, min(paste_y, th - 1))

    result = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    result.paste(scaled, (paste_x, paste_y), scaled)  # use alpha mask
    return result


# ---------------------------------------------------------------------------
# tile — repeat artwork to fill target
# ---------------------------------------------------------------------------

def _fit_tile(art, aw, ah, tw, th, zoom, ox, oy):
    """Tile the artwork at natural (or zoomed) size to fill target."""
    tile_w = max(1, int(round(aw * zoom)))
    tile_h = max(1, int(round(ah * zoom)))

    tile = art.resize((tile_w, tile_h), RESAMPLE)

    # Offset shifts the tile grid (normalized to tile dimensions)
    offset_px_x = int(ox * tile_w) % tile_w
    offset_px_y = int(oy * tile_h) % tile_h

    result = Image.new("RGBA", (tw, th), (0, 0, 0, 0))

    # Cover the full target plus one extra tile for offset
    start_x = -offset_px_x
    start_y = -offset_px_y
    for y in range(start_y, th + tile_h, tile_h):
        for x in range(start_x, tw + tile_w, tile_w):
            result.paste(tile, (x, y), tile)

    # Crop to exact target
    return result.crop((0, 0, tw, th))
