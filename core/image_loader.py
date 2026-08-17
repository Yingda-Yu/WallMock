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
