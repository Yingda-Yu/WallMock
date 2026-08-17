import os
import sys
import io
import json
import base64
import threading
from pathlib import Path
from flask import Flask, render_template as flask_render_template, request, jsonify, send_from_directory, redirect, url_for
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_settings, save_settings, get_abs_path, BASE_DIR
from core.image_loader import load_image, get_image_info, is_supported_image, image_to_base64_preview
from core.ratio_detector import detect_ratio, recommend_templates
from core.template_engine import list_templates, load_template, render_template
from core.device_renderer import load_device_configs
from core.batch_processor import batch_process, process_product, scan_input_dir
from core.folder_watcher import InputFolderWatcher

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "web" / "templates"),
    static_folder=str(BASE_DIR / "web" / "static"),
)

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

_session_images = {}
_session_lock = threading.Lock()
_watcher = None
_watcher_status = {"running": False, "logs": []}


def _get_session_id():
    return "default"


def _store_image(img, filename=""):
    sid = _get_session_id()
    with _session_lock:
        if sid not in _session_images:
            _session_images[sid] = []
        img_id = f"img_{len(_session_images[sid])}"
        _session_images[sid].append({
            "id": img_id,
            "image": img,
            "filename": filename,
            "width": img.width,
            "height": img.height,
        })
        return img_id


def _get_images(img_ids=None):
    sid = _get_session_id()
    with _session_lock:
        imgs = _session_images.get(sid, [])
        if img_ids:
            return [item["image"] for item in imgs if item["id"] in img_ids]
        return [item["image"] for item in imgs]


def _get_image_list():
    sid = _get_session_id()
    with _session_lock:
        imgs = _session_images.get(sid, [])
        result = []
        for item in imgs:
            ratio_info = detect_ratio(item["width"], item["height"])
            result.append({
                "id": item["id"],
                "filename": item["filename"],
                "width": item["width"],
                "height": item["height"],
                "ratio_info": ratio_info,
                "preview": image_to_base64_preview(item["image"], max_size=200, quality=70),
            })
        return result


@app.route("/")
def index():
    return flask_render_template("index.html")


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


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        try:
            settings = request.json
            save_settings(settings)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    else:
        return jsonify(load_settings())


@app.route("/api/upload", methods=["POST"])
def api_upload():
    files = request.files.getlist("images")
    if not files:
        return jsonify({"error": "没有上传文件"}), 400

    uploaded = []
    errors = []
    for f in files:
        try:
            img = Image.open(f.stream)
            img.load()
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            elif img.mode == "RGB":
                img = img.convert("RGBA")
            img_id = _store_image(img, f.filename)
            uploaded.append(img_id)
        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})

    image_list = _get_image_list()
    return jsonify({
        "success": len(uploaded) > 0,
        "uploaded_count": len(uploaded),
        "errors": errors,
        "images": image_list,
    })


@app.route("/api/images", methods=["GET"])
def api_images():
    images = _get_image_list()
    return jsonify({"images": images})


@app.route("/api/images/clear", methods=["POST"])
def api_clear_images():
    sid = _get_session_id()
    with _session_lock:
        _session_images[sid] = []
    return jsonify({"success": True})


@app.route("/api/images/reorder", methods=["POST"])
def api_reorder_images():
    data = request.json or {}
    order = data.get("order", [])
    sid = _get_session_id()
    with _session_lock:
        imgs = _session_images.get(sid, [])
        img_map = {item["id"]: item for item in imgs}
        new_imgs = [img_map[oid] for oid in order if oid in img_map]
        for oid in img_map:
            if oid not in new_imgs:
                new_imgs.append(img_map[oid])
        _session_images[sid] = new_imgs
    return jsonify({"success": True, "images": _get_image_list()})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.json or {}
    img_ids = data.get("image_ids", [])
    images = _get_images(img_ids) if img_ids else _get_images()

    results = []
    for img in images:
        ratio_info = detect_ratio(img.width, img.height)
        results.append({
            "width": img.width,
            "height": img.height,
            "ratio_info": ratio_info,
        })

    images_info = [{"ratio_info": r["ratio_info"]} for r in results]
    rec_templates = recommend_templates(images_info)

    return jsonify({
        "images": results,
        "recommended_templates": rec_templates,
    })


@app.route("/api/preview", methods=["POST"])
def api_preview():
    data = request.json or {}
    template_id = data.get("template_id", "single_phone")
    img_ids = data.get("image_ids", [])
    options = data.get("options", {})

    images = _get_images(img_ids) if img_ids else _get_images()
    if not images:
        return jsonify({"error": "没有可用图片"}), 400

    try:
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
    template_id = data.get("template_id", "single_phone")
    img_ids = data.get("image_ids", [])
    options = data.get("options", {})
    product_name = data.get("product_name", "wallpaper")
    output_format = options.get("output_format", "JPEG")
    output_quality = options.get("output_quality", 95)
    min_size_kb = options.get("min_file_size_kb", 0)

    images = _get_images(img_ids) if img_ids else _get_images()
    if not images:
        return jsonify({"error": "没有可用图片"}), 400

    try:
        result = render_template(template_id, images, options)

        output_dir = BASE_DIR / "output"
        output_dir.mkdir(exist_ok=True)

        ext_map = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
        ext = ext_map.get(output_format.upper(), ".jpg")

        base_name = f"{product_name}_{template_id}"
        counter = 1
        out_path = output_dir / f"{base_name}{ext}"
        while out_path.exists():
            out_path = output_dir / f"{base_name}_{counter:02d}{ext}"
            counter += 1

        from core.batch_processor import save_output_image
        final_path = save_output_image(result, str(out_path), output_format, output_quality, min_size_kb)

        file_size_kb = os.path.getsize(final_path) / 1024

        return jsonify({
            "success": True,
            "output_path": final_path,
            "file_size_kb": round(file_size_kb, 1),
            "size": {"width": result.width, "height": result.height},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/batch/scan", methods=["GET"])
def api_batch_scan():
    settings = load_settings()
    input_dir = BASE_DIR / settings["paths"]["input_dir"]
    products = scan_input_dir(str(input_dir))
    return jsonify({"products": products, "input_dir": str(input_dir)})


@app.route("/api/batch/run", methods=["POST"])
def api_batch_run():
    data = request.json or {}
    settings = load_settings()
    input_dir = BASE_DIR / settings["paths"]["input_dir"]
    output_dir = BASE_DIR / settings["paths"]["output_dir"]
    options = data.get("options", {})

    try:
        results = batch_process(str(input_dir), str(output_dir), options)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/watcher/status", methods=["GET"])
def api_watcher_status():
    global _watcher
    return jsonify({
        "running": _watcher is not None and _watcher.is_running(),
        "logs": _watcher_status["logs"][-50:],
    })


@app.route("/api/watcher/start", methods=["POST"])
def api_watcher_start():
    global _watcher
    if _watcher and _watcher.is_running():
        return jsonify({"success": True, "message": "已在运行"})

    settings = load_settings()
    input_dir = BASE_DIR / settings["paths"]["input_dir"]
    output_dir = BASE_DIR / settings["paths"]["output_dir"]

    def on_progress(event, name, data=None):
        _watcher_status["logs"].append({
            "time": str(os.times()),
            "event": event,
            "name": name,
            "data": data,
        })
        if len(_watcher_status["logs"]) > 200:
            _watcher_status["logs"] = _watcher_status["logs"][-100:]

    _watcher = InputFolderWatcher(
        str(input_dir),
        str(output_dir),
        options={},
        on_progress=on_progress,
    )
    _watcher.start()
    return jsonify({"success": True})


@app.route("/api/watcher/stop", methods=["POST"])
def api_watcher_stop():
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None
    return jsonify({"success": True})


@app.route("/api/output/open", methods=["POST"])
def api_open_output():
    settings = load_settings()
    output_dir = BASE_DIR / settings["paths"]["output_dir"]
    output_dir.mkdir(exist_ok=True)
    try:
        import subprocess
        if sys.platform == "win32":
            os.startfile(str(output_dir))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(output_dir)])
        else:
            subprocess.Popen(["xdg-open", str(output_dir)])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/input/open", methods=["POST"])
def api_open_input():
    settings = load_settings()
    input_dir = BASE_DIR / settings["paths"]["input_dir"]
    input_dir.mkdir(exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(input_dir))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def create_app():
    return app


if __name__ == "__main__":
    settings = load_settings()
    port = settings["app"].get("port", 5876)
    app.run(host="127.0.0.1", port=port, debug=False)
