import math

COMMON_RATIOS = [
    {"name": "9:16", "ratio": 9 / 16, "orientation": "portrait", "device": "phone"},
    {"name": "9:19.5", "ratio": 9 / 19.5, "orientation": "portrait", "device": "phone"},
    {"name": "9:20", "ratio": 9 / 20, "orientation": "portrait", "device": "phone"},
    {"name": "9:21", "ratio": 9 / 21, "orientation": "portrait", "device": "phone"},
    {"name": "3:4", "ratio": 3 / 4, "orientation": "portrait", "device": "tablet"},
    {"name": "4:3", "ratio": 4 / 3, "orientation": "landscape", "device": "tablet"},
    {"name": "10:13", "ratio": 10 / 13, "orientation": "portrait", "device": "tablet"},
    {"name": "16:9", "ratio": 16 / 9, "orientation": "landscape", "device": "monitor"},
    {"name": "16:10", "ratio": 16 / 10, "orientation": "landscape", "device": "laptop"},
    {"name": "21:9", "ratio": 21 / 9, "orientation": "landscape", "device": "ultrawide"},
    {"name": "1:1", "ratio": 1.0, "orientation": "square", "device": "other"},
]

TOLERANCE = 0.03


def detect_ratio(width, height):
    if height == 0 or width == 0:
        return {"name": "unknown", "ratio": 0, "orientation": "unknown", "device": "other"}

    w, h = float(width), float(height)
    orientation = "portrait" if h > w else ("landscape" if w > h else "square")

    ratio_value = min(w, h) / max(w, h)

    best_match = None
    best_diff = float("inf")

    for r in COMMON_RATIOS:
        diff = abs(ratio_value - r["ratio"])
        if diff < best_diff:
            best_diff = diff
            best_match = r

    if best_diff <= TOLERANCE:
        return {
            "name": best_match["name"],
            "ratio": round(w / h, 4),
            "orientation": orientation,
            "device": best_match["device"],
            "confidence": round(1 - best_diff / TOLERANCE, 2),
        }
    else:
        return {
            "name": "custom",
            "ratio": round(w / h, 4),
            "orientation": orientation,
            "device": _guess_device(orientation, w / h),
            "confidence": 0.0,
        }


def _guess_device(orientation, aspect):
    if orientation == "portrait":
        if aspect < 0.5:
            return "phone"
        elif aspect < 0.8:
            return "tablet"
        else:
            return "other"
    elif orientation == "landscape":
        if aspect > 2.0:
            return "ultrawide"
        elif aspect > 1.6:
            return "laptop"
        elif aspect > 1.3:
            return "tablet"
        else:
            return "other"
    return "other"


def recommend_templates(images_info):
    if not images_info:
        return ["phone_hero"]

    count = len(images_info)
    portrait_count = sum(1 for img in images_info if img.get("ratio_info", {}).get("orientation") == "portrait")
    landscape_count = sum(1 for img in images_info if img.get("ratio_info", {}).get("orientation") == "landscape")

    if count == 1:
        img = images_info[0]
        orientation = img.get("ratio_info", {}).get("orientation")
        if orientation == "portrait":
            return ["phone_hero", "laptop_phone", "device_trio"]
        elif orientation == "landscape":
            return ["desktop_hero", "laptop_phone", "device_trio"]
        else:
            return ["phone_hero", "desktop_hero"]
    elif count == 2:
        if portrait_count == 2:
            return ["wallpaper_collection", "phone_ratio_compare"]
        elif landscape_count == 2:
            return ["desktop_hero", "device_trio"]
        else:
            return ["laptop_phone", "device_trio"]
    elif 3 <= count <= 5:
        return ["device_trio", "wallpaper_collection"]
    else:
        return ["wallpaper_collection", "device_trio"]
