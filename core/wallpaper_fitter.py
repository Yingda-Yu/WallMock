from PIL import Image, ImageDraw


def fit_wallpaper(wallpaper, screen_width, screen_height, mode="cover", offset_x=0, offset_y=0, scale=1.0):
    wp_w, wp_h = wallpaper.size
    sw, sh = screen_width, screen_height

    if mode == "cover":
        src_ratio = wp_w / wp_h
        dst_ratio = sw / sh

        if src_ratio > dst_ratio:
            new_h = sh * scale
            new_w = new_h * src_ratio
        else:
            new_w = sw * scale
            new_h = new_w / src_ratio

        new_w = int(max(new_w, sw))
        new_h = int(max(new_h, sh))

        resized = wallpaper.resize((new_w, new_h), Image.LANCZOS)

        offset_x_px = int((sw - new_w) / 2 + offset_x)
        offset_y_px = int((sh - new_h) / 2 + offset_y)

        canvas = Image.new("RGBA", (int(sw), int(sh)), (0, 0, 0, 0))
        canvas.paste(resized, (offset_x_px, offset_y_px))
        return canvas

    elif mode == "contain":
        resized = wallpaper.copy()
        resized.thumbnail((sw * scale, sh * scale), Image.LANCZOS)
        canvas = Image.new("RGBA", (int(sw), int(sh)), (0, 0, 0, 0))
        x = int((sw - resized.width) / 2 + offset_x)
        y = int((sh - resized.height) / 2 + offset_y)
        canvas.paste(resized, (x, y))
        return canvas

    elif mode == "stretch":
        return wallpaper.resize((int(sw), int(sh)), Image.LANCZOS).convert("RGBA")

    else:
        return fit_wallpaper(wallpaper, sw, sh, "cover", offset_x, offset_y, scale)


def apply_rounded_corners(img, radius):
    if radius <= 0:
        return img

    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    r = min(radius, w // 2, h // 2)

    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=r, fill=255)

    result = img.copy()
    result.putalpha(mask)
    return result


def create_screen_mask(width, height, radius):
    mask = Image.new("L", (int(width), int(height)), 0)
    draw = ImageDraw.Draw(mask)
    r = min(radius, width // 2, height // 2)
    draw.rounded_rectangle([(0, 0), (width - 1, height - 1)], radius=r, fill=255)
    return mask
