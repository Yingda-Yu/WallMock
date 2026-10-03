"""
Responsive WebP generation for WallMock catalog builds.

Renders a single master image at full resolution, then derives
multiple responsive WebP variants at different widths using
high-quality Lanczos resampling.

Key properties:
  - High-quality downscaling (LANCZOS)
  - Preserves aspect ratio
  - Never upscales past source resolution
  - WebP quality = 85 (configurable)
  - Deterministic output
"""
import os
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image


def generate_responsive_webp(
    master_image: Image.Image,
    widths: List[int],
    output_dir: str,
    base_filename: str,
    *,
    quality: int = 85,
) -> List[Dict]:
    """Generate responsive WebP variants from a master image.

    Renders one master image, then derives responsive WebP files at
    each requested width. Widths larger than the master image width
    are skipped (no upscaling).

    Parameters
    ----------
    master_image : PIL.Image
        The full-resolution master render (RGBA or RGB).
    widths : List[int]
        List of target widths in pixels. Sorted ascending.
    output_dir : str
        Directory where WebP files will be written.
    base_filename : str
        Base filename without extension. Each variant gets a
        ``-w{width}.webp`` suffix.
    quality : int
        WebP quality (1-100). Default 85.

    Returns
    -------
    List[Dict]
        List of output asset info dicts, each with:
          - path: relative filename (e.g. "rear-w800.webp")
          - width: output width in pixels
          - height: output height in pixels
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    master_w = master_image.width
    master_h = master_image.height

    results = []

    # Sort widths descending so we always downscale from the master
    # (or from the previous step if we wanted — but Lanczos from master
    #  is higher quality than iterative downscaling).
    for width in sorted(set(widths), reverse=True):
        # Don't upscale past source resolution
        if width >= master_w:
            # Use the master at its native resolution
            resized = master_image.copy()
            actual_width = master_w
        else:
            # Calculate proportional height
            ratio = width / master_w
            height = int(round(master_h * ratio))
            if height < 1:
                height = 1

            # High-quality Lanczos downscaling
            resized = master_image.resize(
                (width, height),
                Image.LANCZOS,
            )
            actual_width = width

        actual_height = resized.height

        filename = f"{base_filename}-w{actual_width}.webp"
        filepath = out_dir / filename

        # Save as WebP
        # For images with alpha, WebP supports it natively
        save_kwargs = {"quality": quality, "method": 6}
        if resized.mode == "RGBA":
            # PIL's WebP save handles RGBA correctly
            resized.save(str(filepath), "WEBP", **save_kwargs)
        elif resized.mode == "RGB":
            resized.save(str(filepath), "WEBP", **save_kwargs)
        else:
            # Convert to RGBA first for safety
            resized.convert("RGBA").save(str(filepath), "WEBP", **save_kwargs)

        results.append({
            "path": filename,
            "width": actual_width,
            "height": actual_height,
        })

    # Sort results by width ascending for consistent output
    results.sort(key=lambda r: r["width"])
    return results


def generate_single_webp(
    image: Image.Image,
    output_path: str,
    *,
    quality: int = 85,
) -> Dict:
    """Save a single image as WebP.

    Parameters
    ----------
    image : PIL.Image
        The image to save.
    output_path : str
        Full output file path.
    quality : int
        WebP quality (1-100). Default 85.

    Returns
    -------
    Dict
        Asset info with path, width, height.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs = {"quality": quality, "method": 6}
    if image.mode in ("RGBA", "RGB"):
        image.save(str(out_path), "WEBP", **save_kwargs)
    else:
        image.convert("RGBA").save(str(out_path), "WEBP", **save_kwargs)

    return {
        "path": str(out_path),
        "width": image.width,
        "height": image.height,
    }
