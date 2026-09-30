"""
Layered phone case renderer for WallMock 2.0.

Composites template layers (base, artwork, highlight, overlay, shadow)
into a final product image. Completely independent of Flask, HTTP,
storefront, checkout, pricing, and supplier APIs.

Public API:
    render_case(artwork_img, template, *, template_dir, fit_mode,
                zoom, offset_x, offset_y, focal_point) -> Image

Layer order (bottom to top):
    base → fitted+masked artwork → highlight → overlay → shadow
"""

import os
from pathlib import Path
from typing import Optional, Tuple, List

from PIL import Image, ImageChops

from .catalog_models import CaseTemplate, CaseTemplateLayer
from .case_artwork_fitter import fit_artwork


def _load_layer_png(filename: str, template_dir: Path) -> Image.Image:
    """Load a PNG layer from the template directory."""
    path = template_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Template layer not found: {path}"
        )
    return Image.open(str(path)).convert("RGBA")


def _load_mask(filename: str, template_dir: Path) -> Image.Image:
    """Load a mask layer as an L-mode (grayscale) image.

    Masks are typically saved as L-mode PNGs where pixel values
    represent coverage (0=transparent, 255=opaque). Converting to RGBA
    would put these values in the RGB channels with alpha=255, losing
    the mask semantics. We keep the mask in L mode so it can be used
    directly as an alpha channel in compositing.
    """
    path = template_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Template mask not found: {path}"
        )
    img = Image.open(str(path))
    if img.mode == "L":
        return img
    if img.mode == "LA":
        return img.getchannel("A")
    if img.mode == "RGBA":
        return img.getchannel("A")
    return img.convert("L")


def _apply_opacity(img: Image.Image, opacity: float) -> Image.Image:
    """Scale an image's alpha channel by *opacity* (0.0–1.0)."""
    if opacity >= 1.0:
        return img
    alpha = img.getchannel("A")
    alpha = alpha.point(lambda v: int(v * opacity))
    img = img.copy()
    img.putalpha(alpha)
    return img


def _clip_artwork_to_mask(
    artwork: Image.Image,
    mask: Image.Image,
    paste_x: int,
    paste_y: int,
    canvas_w: int,
    canvas_h: int,
) -> Image.Image:
    """Place fitted artwork on a canvas-sized layer and clip it to *mask*.

    The mask is an L-mode image where pixel values represent coverage
    (0=fully excluded, 255=fully included). Both artwork and mask are
    composited onto a full-canvas transparent image so that the mask can
    clip the artwork at the exact pixel level, including camera cutouts
    and edge feathering.
    """
    artwork_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    artwork_layer.paste(artwork, (paste_x, paste_y), artwork)

    art_alpha = artwork_layer.getchannel("A")
    mask_l = mask if mask.mode == "L" else mask.getchannel("A")
    clipped_alpha = ImageChops.multiply(art_alpha, mask_l)
    artwork_layer.putalpha(clipped_alpha)

    return artwork_layer


def render_case(
    artwork_img: Image.Image,
    template: CaseTemplate,
    *,
    template_dir: Optional[str] = None,
    fit_mode: Optional[str] = None,
    zoom: float = 1.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    focal_point: Tuple[float, float] = (0.5, 0.5),
) -> Image.Image:
    """Render a phone case product image from source artwork.

    Parameters
    ----------
    artwork_img : PIL.Image
        Source design artwork (RGB or RGBA).
    template : CaseTemplate
        Loaded template dataclass with layer definitions.
    template_dir : str, optional
        Directory containing the template's PNG layer files.
        If None, uses the current working directory.
    fit_mode : str, optional
        Override the template's default fit mode (cover/contain/tile).
    zoom : float
        Zoom multiplier for artwork (1.0 = default).
    offset_x, offset_y : float
        Normalized offsets [-1, 1] for artwork positioning.
    focal_point : (float, float)
        Normalized focal point [0, 1] for crop positioning.

    Returns
    -------
    PIL.Image (RGBA), dimensions = template.canvas.width × height.
    """
    # Resolve template directory
    tpl_dir = Path(template_dir) if template_dir else Path.cwd()

    canvas_w = template.canvas.width
    canvas_h = template.canvas.height

    # Start with transparent canvas
    result = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # Resolve fit mode
    effective_fit = fit_mode or template.print_region.fit

    # Load print mask once (needed for artwork layer)
    print_mask = None
    if template.print_region.mask:
        print_mask = _load_mask(template.print_region.mask, tpl_dir)

    # Process layers in order
    for layer in template.layers:
        if layer.type == "base":
            base_img = _load_layer_png(layer.file, tpl_dir)
            base_img = _apply_opacity(base_img, layer.opacity)
            result = Image.alpha_composite(result, base_img)

        elif layer.type == "artwork":
            # Fit artwork to print region
            fitted = fit_artwork(
                artwork_img,
                template.print_region.width,
                template.print_region.height,
                mode=effective_fit,
                zoom=zoom,
                offset_x=offset_x,
                offset_y=offset_y,
                focal_point=focal_point,
            )

            if print_mask is not None:
                artwork_layer = _clip_artwork_to_mask(
                    fitted, print_mask,
                    template.print_region.x, template.print_region.y,
                    canvas_w, canvas_h,
                )
            else:
                # No mask: place artwork directly
                artwork_layer = Image.new(
                    "RGBA", (canvas_w, canvas_h), (0, 0, 0, 0)
                )
                artwork_layer.paste(
                    fitted,
                    (template.print_region.x, template.print_region.y),
                    fitted,
                )

            artwork_layer = _apply_opacity(artwork_layer, layer.opacity)
            result = Image.alpha_composite(result, artwork_layer)

        elif layer.type == "highlight":
            if layer.file and (tpl_dir / layer.file).exists():
                hl_img = _load_layer_png(layer.file, tpl_dir)
                hl_img = _apply_opacity(hl_img, layer.opacity)
                result = Image.alpha_composite(result, hl_img)

        elif layer.type == "overlay":
            if layer.file:
                ov_img = _load_layer_png(layer.file, tpl_dir)
                ov_img = _apply_opacity(ov_img, layer.opacity)
                result = Image.alpha_composite(result, ov_img)

        elif layer.type == "shadow":
            if layer.file and (tpl_dir / layer.file).exists():
                sh_img = _load_layer_png(layer.file, tpl_dir)
                sh_img = _apply_opacity(sh_img, layer.opacity)
                result = Image.alpha_composite(result, sh_img)

    return result


def get_available_template_layers(template: CaseTemplate, template_dir: str) -> List[str]:
    """Return list of layer files that exist on disk for *template*."""
    tpl_dir = Path(template_dir)
    found = []
    for layer in template.layers:
        if layer.file:
            if (tpl_dir / layer.file).exists():
                found.append(layer.file)
    return found
