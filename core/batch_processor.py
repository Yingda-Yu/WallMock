import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from PIL import Image

from .image_loader import load_image, is_supported_image
from .ratio_detector import detect_ratio, recommend_templates
from .template_engine import render_template

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"

_logger = None


def get_logger():
    global _logger
    if _logger is None:
        LOGS_DIR.mkdir(exist_ok=True)
        log_file = LOGS_DIR / f"batch_{datetime.now().strftime('%Y%m%d')}.log"
        _logger = logging.getLogger("wallmock_batch")
        _logger.setLevel(logging.INFO)
        if not _logger.handlers:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            fh.setFormatter(fmt)
            _logger.addHandler(fh)
    return _logger


def load_processed_record(output_dir):
    record_file = Path(output_dir) / ".wallmock_processed.json"
    if record_file.exists():
        try:
            with open(record_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_processed_record(output_dir, record):
    record_file = Path(output_dir) / ".wallmock_processed.json"
    try:
        with open(record_file, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except Exception as e:
        get_logger().warning(f"保存处理记录失败: {e}")


def get_file_hash(filepath):
    try:
        stat = os.stat(filepath)
        return f"{stat.st_size}_{int(stat.st_mtime)}"
    except Exception:
        return ""


def wait_for_file_stable(filepath, checks=3, interval=1.0):
    last_size = -1
    stable_count = 0
    while stable_count < checks:
        try:
            current_size = os.path.getsize(filepath)
        except Exception:
            time.sleep(interval)
            continue
        if current_size == last_size and current_size > 0:
            stable_count += 1
        else:
            stable_count = 0
            last_size = current_size
        time.sleep(interval)
    return True


def scan_input_dir(input_dir):
    results = []
    input_path = Path(input_dir)
    if not input_path.exists():
        return results

    for item in sorted(input_path.iterdir()):
        if item.name.startswith(".") or item.name.startswith("~$"):
            continue
        if item.is_dir():
            images = []
            for f in sorted(item.iterdir()):
                if is_supported_image(f) and not f.name.startswith("."):
                    images.append(str(f))
            if images:
                results.append({
                    "type": "product",
                    "name": item.name,
                    "path": str(item),
                    "images": images,
                })
        elif item.is_file() and is_supported_image(item):
            results.append({
                "type": "single",
                "name": item.stem,
                "path": str(item),
                "images": [str(item)],
            })
    return results


def generate_unique_filename(output_dir, base_name, ext):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    candidate = output_path / f"{base_name}{ext}"
    counter = 1
    while candidate.exists():
        candidate = output_path / f"{base_name}_{counter:02d}{ext}"
        counter += 1
    return str(candidate)


def save_output_image(img, output_path, format="JPEG", quality=95, min_size_kb=0):
    fmt = format.upper()
    ext_map = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
    ext = ext_map.get(fmt, ".jpg")

    save_img = img
    if fmt == "JPEG" and save_img.mode == "RGBA":
        background = Image.new("RGB", save_img.size, (255, 255, 255))
        background.paste(save_img, mask=save_img.split()[3])
        save_img = background
    elif fmt == "JPEG" and save_img.mode != "RGB":
        save_img = save_img.convert("RGB")

    output_path = str(output_path)
    if not output_path.lower().endswith(ext):
        output_path = str(Path(output_path).with_suffix(ext))

    current_quality = quality
    save_img.save(output_path, format=fmt, quality=current_quality)

    if min_size_kb > 0:
        file_size_kb = os.path.getsize(output_path) / 1024
        attempts = 0
        while file_size_kb < min_size_kb and attempts < 5:
            current_quality = min(100, current_quality + 10)
            save_img.save(output_path, format=fmt, quality=current_quality)
            file_size_kb = os.path.getsize(output_path) / 1024
            attempts += 1

    return output_path


def process_product(product_info, output_root, options=None):
    if options is None:
        options = {}

    logger = get_logger()
    product_name = product_info["name"]
    image_paths = product_info["images"]

    output_dir = Path(output_root) / product_name
    output_dir.mkdir(parents=True, exist_ok=True)

    record = load_processed_record(output_dir)

    images = []
    valid_paths = []
    for img_path in image_paths:
        try:
            wait_for_file_stable(img_path)
            img = load_image(img_path)
            images.append(img)
            valid_paths.append(img_path)
        except Exception as e:
            logger.error(f"跳过损坏图片: {img_path} - {e}")

    if not images:
        logger.warning(f"商品 {product_name} 没有有效图片，跳过")
        return {"success": False, "product": product_name, "error": "no valid images"}

    template_ids = options.get("templates", None)
    if not template_ids:
        images_info = []
        for img in images:
            ratio_info = detect_ratio(img.width, img.height)
            images_info.append({"ratio_info": ratio_info})
        template_ids = recommend_templates(images_info)

    generated = []
    for tpl_id in template_ids:
        try:
            result = render_template(tpl_id, images, options)
            base_name = f"{product_name}_{tpl_id}"
            fmt = options.get("output_format", "JPEG")
            ext_map = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
            ext = ext_map.get(fmt.upper(), ".jpg")
            out_path = generate_unique_filename(str(output_dir), base_name, ext)
            quality = options.get("output_quality", 95)
            min_size = options.get("min_file_size_kb", 0)
            out_path = save_output_image(result, out_path, fmt, quality, min_size)
            generated.append(out_path)
            logger.info(f"生成成功: {out_path}")
        except Exception as e:
            logger.error(f"模板 {tpl_id} 生成失败: {product_name} - {e}")

    for p in valid_paths:
        file_id = os.path.basename(p)
        record[file_id] = {
            "hash": get_file_hash(p),
            "processed_at": datetime.now().isoformat(),
        }
    save_processed_record(output_dir, record)

    return {
        "success": True,
        "product": product_name,
        "generated_count": len(generated),
        "output_files": generated,
    }


def batch_process(input_dir, output_dir, options=None):
    logger = get_logger()
    logger.info(f"开始批量处理: {input_dir} -> {output_dir}")

    products = scan_input_dir(input_dir)
    logger.info(f"发现 {len(products)} 个商品/图片")

    results = []
    for product in products:
        try:
            result = process_product(product, output_dir, options)
            results.append(result)
        except Exception as e:
            logger.error(f"处理商品失败: {product.get('name')} - {e}")
            results.append({"success": False, "product": product.get("name"), "error": str(e)})

    success_count = sum(1 for r in results if r.get("success"))
    logger.info(f"批量处理完成: 成功 {success_count}/{len(results)}")

    return results
