import os
import sys
import base64
import io
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from flask import Flask, request, jsonify
from PIL import Image

from core.config import load_settings
from core.image_loader import image_to_base64_preview, image_to_base64, base64_to_image
from core.ratio_detector import detect_ratio, recommend_templates
from core.template_engine import list_templates, load_template, render_template, get_canvas_presets
from core.device_renderer import load_device_configs

app = Flask(__name__)


def _decode_images(image_data_list):
    images = []
    for img_data in image_data_list:
        img = base64_to_image(img_data.get("base64", ""))
        images.append(img)
    return images


@app.route("/api/templates", methods=["GET"])
def api_templates():
    templates = list_templates()
    return jsonify({"templates": templates})


@app.route("/api/templates/<template_id>", methods=["GET"])
def api_template_detail(template_id):
    try:
        tpl = load_template(template_id)
        return jsonify(tpl)
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/devices", methods=["GET"])
def api_devices():
    configs = load_device_configs()
    return jsonify({"devices": configs})


@app.route("/api/canvas-presets", methods=["GET"])
def api_canvas_presets():
    return jsonify({"presets": get_canvas_presets()})


@app.route("/api/settings", methods=["GET"])
def api_settings():
    return jsonify(load_settings())


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.json or {}
    image_data_list = data.get("images", [])

    results = []
    for img_data in image_data_list:
        try:
            img = base64_to_image(img_data.get("base64", ""))
            ratio_info = detect_ratio(img.width, img.height)
            results.append({
                "filename": img_data.get("filename", ""),
                "width": img.width,
                "height": img.height,
                "ratio_info": ratio_info,
            })
        except Exception as e:
            results.append({"error": str(e)})

    images_info = [{"ratio_info": r["ratio_info"]} for r in results if "ratio_info" in r]
    rec_templates = recommend_templates(images_info)

    return jsonify({
        "images": results,
        "recommended_templates": rec_templates,
    })


@app.route("/api/preview", methods=["POST"])
def api_preview():
    data = request.json or {}
    template_id = data.get("template_id", "phone_hero")
    image_data_list = data.get("images", [])
    options = data.get("options", {})

    if not image_data_list:
        return jsonify({"error": "没有可用图片"}), 400

    try:
        images = _decode_images(image_data_list)
        result = render_template(template_id, images, options)
        preview_data = image_to_base64_preview(result, max_size=1000, quality=85)
        return jsonify({
            "success": True,
            "preview": preview_data,
            "size": {"width": result.width, "height": result.height},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json or {}
    template_id = data.get("template_id", "phone_hero")
    image_data_list = data.get("images", [])
    options = data.get("options", {})
    product_name = data.get("product_name", "wallpaper")
    output_format = options.get("output_format", "JPEG")
    output_quality = options.get("output_quality", 95)

    if not image_data_list:
        return jsonify({"error": "没有可用图片"}), 400

    try:
        images = _decode_images(image_data_list)
        result = render_template(template_id, images, options)

        result_data = image_to_base64(
            result, max_size=None, quality=output_quality, format=output_format
        )

        base64_payload = result_data.split(",", 1)[1] if "," in result_data else result_data
        file_size_kb = len(base64_payload) * 3 / 4 / 1024

        ext_map = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
        ext = ext_map.get(output_format.upper(), "jpg")
        filename = f"{product_name}_{template_id}.{ext}"

        return jsonify({
            "success": True,
            "image": result_data,
            "filename": filename,
            "file_size_kb": round(file_size_kb, 1),
            "size": {"width": result.width, "height": result.height},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
