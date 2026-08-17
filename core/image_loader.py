from PIL import Image
import os
from pathlib import Path

SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def is_supported_image(filepath):
    ext = Path(filepath).suffix.lower()
    return ext in SUPPORTED_FORMATS


def load_image(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")
    if not is_supported_image(filepath):
        raise ValueError(f"不支持的图片格式: {filepath}")
    try:
        img = Image.open(filepath)
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        elif img.mode == "RGB":
            img = img.convert("RGBA")
        return img
    except Exception as e:
        raise ValueError(f"图片加载失败: {filepath} - {str(e)}")


def get_image_info(filepath):
    img = load_image(filepath)
    return {
        "path": filepath,
        "filename": os.path.basename(filepath),
        "width": img.width,
        "height": img.height,
        "mode": img.mode,
        "ratio": img.width / img.height if img.height > 0 else 0,
    }


def image_to_base64_preview(img, max_size=800, quality=85):
    import io
    import base64

    preview = img.copy()
    if preview.width > max_size or preview.height > max_size:
        preview.thumbnail((max_size, max_size), Image.LANCZOS)
    if preview.mode == "RGBA":
        preview = preview.convert("RGB")
    buf = io.BytesIO()
    preview.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")


def image_to_base64(img, max_size=None, quality=95, format="JPEG"):
    import io
    import base64

    result = img.copy()
    if max_size and (result.width > max_size or result.height > max_size):
        result.thumbnail((max_size, max_size), Image.LANCZOS)
    if result.mode == "RGBA":
        result = result.convert("RGB")
    buf = io.BytesIO()
    fmt = format.upper()
    if fmt == "JPEG":
        result.save(buf, format="JPEG", quality=quality)
        mime = "image/jpeg"
    elif fmt == "PNG":
        result.save(buf, format="PNG")
        mime = "image/png"
    elif fmt == "WEBP":
        result.save(buf, format="WEBP", quality=quality)
        mime = "image/webp"
    else:
        result.save(buf, format="JPEG", quality=quality)
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode("utf-8")


def base64_to_image(base64_str):
    import base64
    import io

    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    img_data = base64.b64decode(base64_str)
    img = Image.open(io.BytesIO(img_data))
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    elif img.mode == "RGB":
        img = img.convert("RGBA")
    return img
