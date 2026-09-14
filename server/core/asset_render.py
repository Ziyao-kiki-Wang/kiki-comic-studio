"""Safe rendering of user supplied raster layers."""

from __future__ import annotations

import math

from PIL import Image

from server.services.assets import asset_path


def paste_image(canvas, image, position):
    """Composite once, preserving source alpha on transparent pages."""
    if canvas.mode == "RGBA":
        canvas.alpha_composite(image.convert("RGBA"), dest=position)
    else:
        canvas.paste(image, position, image)


def validate_transform(item: dict, *, label: str = "图层") -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"{label} 必须是对象")
    for key in ("x", "y"):
        value = item.get(key, 0)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or abs(value) > 40000
        ):
            raise ValueError(f"{label}.{key} 坐标无效")
    for key in ("width", "height"):
        value = item.get(key)
        if value is not None and (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 1 <= value <= 1800
        ):
            raise ValueError(f"{label}.{key} 需在 1–1800 像素之间")
    rotation = item.get("rotation", 0)
    if (
        not isinstance(rotation, (int, float))
        or isinstance(rotation, bool)
        or not math.isfinite(rotation)
        or abs(rotation) > 360
    ):
        raise ValueError(f"{label}.rotation 需在 -360–360 度之间")
    opacity = item.get("opacity", 1)
    if (
        not isinstance(opacity, (int, float))
        or isinstance(opacity, bool)
        or not math.isfinite(opacity)
        or not 0 <= opacity <= 1
    ):
        raise ValueError(f"{label}.opacity 需在 0–1 之间")
    for key in ("flip_x", "flip_y"):
        if key in item and not isinstance(item[key], bool):
            raise ValueError(f"{label}.{key} 必须是布尔值")
    z = item.get("z_index", 0)
    if (
        not isinstance(z, (int, float))
        or isinstance(z, bool)
        or not math.isfinite(z)
        or abs(z) > 10000
    ):
        raise ValueError(f"{label}.z_index 无效")
    return item


def render_asset(canvas: Image.Image, project_id: str, item: dict) -> Image.Image:
    """Composite an asset at a top-left position, keeping alpha and transforms.

    ``x``/``y`` describe the transformed image's top-left corner.  Drawing on
    a full-size transparent layer makes negative or partially outside positions
    clip naturally and avoids crashes while users drag an item at the edge.
    """
    validate_transform(item)
    path = asset_path(project_id, item["asset_id"])
    with Image.open(path) as source:
        sprite = source.convert("RGBA")
    requested_width = item.get("width")
    requested_height = item.get("height")
    if requested_width is None and requested_height is None:
        scale = min(1, 1800 / max(sprite.width, sprite.height))
        width = max(1, round(sprite.width * scale))
        height = max(1, round(sprite.height * scale))
    elif requested_width is None:
        height = int(requested_height)
        width = max(1, round(sprite.width * height / sprite.height))
    elif requested_height is None:
        width = int(requested_width)
        height = max(1, round(sprite.height * width / sprite.width))
    else:
        width = int(requested_width)
        height = int(requested_height)
    original_size = (width, height)
    sprite = sprite.resize((width, height), Image.Resampling.LANCZOS)
    if item.get("flip_x"):
        sprite = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if item.get("flip_y"):
        sprite = sprite.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    rotation = float(item.get("rotation", 0))
    if rotation:
        # Browser/Konva angles increase clockwise; Pillow increases
        # counter-clockwise.  Keep x/y anchored to the unrotated top-left and
        # rotate around that image's center.
        sprite = sprite.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
    opacity = float(item.get("opacity", 1))
    if opacity < 1:
        alpha = sprite.getchannel("A").point(lambda value: round(value * opacity))
        sprite.putalpha(alpha)

    x = round(item.get("x", 0) + (original_size[0] - sprite.width) / 2)
    y = round(item.get("y", 0) + (original_size[1] - sprite.height) / 2)
    if canvas.mode == "RGBA":
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.paste(sprite, (x, y))
        canvas.alpha_composite(layer)
    else:
        canvas.paste(
            sprite,
            (x, y),
            sprite,
        )
    return canvas
