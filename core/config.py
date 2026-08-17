import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_PATH = BASE_DIR / "config" / "settings.json"


def load_settings():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_abs_path(rel_path):
    return str(BASE_DIR / rel_path)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path
