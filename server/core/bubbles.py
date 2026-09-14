"""Bubble geometry. Browser geometry is persisted so PNG and PPTX reuse the exact layout."""

import math
from PIL import Image, ImageDraw
from server.core.studio import BUBBLES


def wrap_lines(text, measure, max_width):
    lines, current = [], ""
    closing = set("，。！？；：、）》】…,.!?;:)")
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
        elif current and measure(current + char) > max_width:
            if char in closing and len(current) > 1:
                lines.append(current[:-1])
                current = current[-1] + char
            else:
                lines.append(current)
                current = char
        else:
            current += char
    lines.append(current)
    return lines


def layout_input(b):
    return {
        "revision": 3,
        "text": b.get("text", ""),
        "type": b.get("type", "speech"),
        "width": b.get("width", 420),
        "font_size": b.get("font_size", 36),
        # Keep the browser geometry cache comparable with the server cache.
        # The client uses this field to measure text with an imported font.
        "font_family": b.get("font_id") or b.get("font_family") or "system",
        "x": b.get("x", 0),
        "y": b.get("y", 0),
        "tail_side": b.get("tail_side", "bottom"),
        "tail_position": b.get(
            "tail_position", 0.75 if b.get("tail") == "right" else 0.25
        ),
        "tail_tip": b.get("tail_tip"),
        "body_height": b.get("body_height"),
        "rotation": b.get("rotation", 0),
        "scale_x": b.get("scale_x", 1),
        "scale_y": b.get("scale_y", 1),
        "text_align": b.get("text_align", "left"),
        "text_box": b.get("text_box") or None,
        "flip_x": bool(b.get("flip_x")),
        "flip_y": bool(b.get("flip_y")),
        "tail_local": b.get("tail_local"),
    }


def geometry(b, font):
    inp = layout_input(b)
    saved = b.get("geometry")
    if saved and saved.get("input") == inp:
        return saved
    w, fs, kind = inp["width"], inp["font_size"], inp["type"]
    pad = (
        w * 0.24
        if kind in ("ellipse", "burst", "thought", "cloud", "shout", "handdrawn")
        else 22
    )
    text_width = (b.get("text_box") or {}).get("width", w - 2 * pad)
    lines = wrap_lines(inp["text"], lambda t: font.getlength(t), text_width)
    line_h = fs + 14
    py = (
        fs * 1.1
        if kind in ("ellipse", "burst", "thought", "cloud", "shout", "handdrawn")
        else 22
    )
    h = inp["body_height"] or max(80, 2 * py + len(lines) * line_h)
    text_box = {"x": b["x"] + pad, "y": b["y"] + py, "width": text_width,
                "rotation": 0, **(b.get("text_box") or {}), "height": len(lines) * line_h}
    points = []
    if kind in ("thought", "cloud"):
        for lobe in range(10):
            a = -math.pi / 2 + lobe * math.tau / 10
            z = a + math.tau / 10
            start = [math.cos(a) * w * 0.40, math.sin(a) * h * 0.36]
            end = [math.cos(z) * w * 0.40, math.sin(z) * h * 0.36]
            dx, dy = (end[0] - start[0]) / 2, (end[1] - start[1]) / 2
            for step in range(16):
                t = step * math.pi / 16
                points.append(
                    [
                        (start[0] + end[0]) / 2
                        - dx * math.cos(t)
                        + dy * math.sin(t) * 0.85,
                        (start[1] + end[1]) / 2
                        - dy * math.cos(t)
                        - dx * math.sin(t) * 0.85,
                    ]
                )
        left, top = min(p[0] for p in points), min(p[1] for p in points)
        span_x = max(p[0] for p in points) - left
        span_y = max(p[1] for p in points) - top
        points = [
            [(px - left) * w / span_x, (py - top) * h / span_y] for px, py in points
        ]
    elif kind in ("ellipse", "burst", "shout", "handdrawn"):
        count = 32 if kind in ("burst", "shout") else 128
        for i in range(count):
            a = -math.pi / 2 + i * 2 * math.pi / count
            if kind in ("burst", "shout"):
                outer = [1, 0.81, 0.96, 0.86, 1, 0.84, 0.93, 0.79][(i // 2) % 8]
                k = outer if i % 2 == 0 else (0.64 if kind == "shout" else 0.72)
            elif kind in ("thought", "cloud"):
                k = 0.90 + 0.10 * math.cos(9 * a)
            elif kind == "handdrawn":
                k = 0.97 + 0.02 * math.sin(3 * a) + 0.01 * math.cos(7 * a)
            else:
                k = 1
            points.append(
                [w / 2 + math.cos(a) * w / 2 * k, h / 2 + math.sin(a) * h / 2 * k]
            )
    else:
        radius = 4 if kind == "caption" else min(w, h) * 0.32 if kind == "soft" else 24
        for cx, cy, begin in [
            (w - radius, radius, -90),
            (w - radius, h - radius, 0),
            (radius, h - radius, 90),
            (radius, radius, 180),
        ]:
            for i in range(9):
                a = math.radians(begin + i * 90 / 8)
                points.append([cx + radius * math.cos(a), cy + radius * math.sin(a)])
        # Add straight-edge samples for a movable tail root.
        dense = []
        for i, a in enumerate(points):
            z = points[(i + 1) % len(points)]
            n = max(1, math.ceil(math.dist(a, z) / 14))
            dense.extend(
                [
                    [a[0] + (z[0] - a[0]) * j / n, a[1] + (z[1] - a[1]) * j / n]
                    for j in range(n)
                ]
            )
        points = dense
    pos, side = inp["tail_position"], inp["tail_side"]
    wanted = (
        [w * pos, h]
        if side == "bottom"
        else [w * pos, 0]
        if side == "top"
        else [0, h * pos]
        if side == "left"
        else [w, h * pos]
    )
    index = min(range(len(points)), key=lambda i: math.dist(points[i], wanted))
    anchor = points[index]
    default_tip = [anchor[0] + (-35 if pos < 0.5 else 35), anchor[1] + 65]
    if side == "top":
        default_tip = [anchor[0], -65]
    if side == "left":
        default_tip = [-65, anchor[1] + 35]
    if side == "right":
        default_tip = [w + 65, anchor[1] + 35]
    tip = b.get("tail_local") or (
        untransform_point([inp["tail_tip"]["x"], inp["tail_tip"]["y"]], b)
        if inp["tail_tip"]
        else default_tip
    )
    circles = []
    if BUBBLES.get(kind, BUBBLES["speech"])["tail"]:
        if kind == "thought":
            circles = [
                {
                    "x": anchor[0] + (tip[0] - anchor[0]) * p,
                    "y": anchor[1] + (tip[1] - anchor[1]) * p,
                    "r": r,
                }
                for p, r in [(0.25, 12), (0.55, 8), (0.85, 4)]
            ]
        else:
            n = len(points)
            points = [points[(index + 2 + j) % n] for j in range(n - 3)] + [tip]
    return {
        "input": inp,
        "points": points,
        "circles": circles,
        "height": h,
        "anchor": anchor,
        "tip": tip,
        "line_height": line_h,
        "text_box": text_box,
        "lines": [
            {"text": t, "width": font.getlength(t), "x": aligned_x(text_width, font.getlength(t), inp["text_align"]), "y": fs + i * line_h}
            for i, t in enumerate(lines)
        ],
    }


def paint(canvas, b, font, include_text=True):
    g = geometry(b, font)
    from server.services.bubble_assets import asset_path
    sprite_path = asset_path(b.get("type", "speech"), b.get("bubble_variant", "white"))
    if sprite_path:
        with Image.open(sprite_path) as original:
            sprite = original.convert("RGBA")
        if b.get("flip_x"):
            sprite = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if b.get("flip_y"):
            sprite = sprite.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        angle = math.radians(b.get("rotation", 0))
        sx = sprite.width / (b["width"] * b.get("scale_x", 1))
        sy = sprite.height / (g["height"] * b.get("scale_y", 1))
        co, si = math.cos(angle), math.sin(angle)
        matrix = (sx*co, sx*si, -sx*(co*b["x"]+si*b["y"]), -sy*si, sy*co, sy*(si*b["x"]-co*b["y"]))
        canvas.alpha_composite(sprite.transform(canvas.size, Image.Transform.AFFINE, matrix, Image.Resampling.BICUBIC))
        if include_text:
            paint_text(canvas, g["text_box"], g["lines"], font, b.get("text_color", "#222222"))
        return g
    scale = 2
    layer = Image.new("RGBA", (canvas.width * scale, canvas.height * scale))
    polygons = [g["points"]] + [
        [[c["x"] + c["r"] * math.cos(i * math.tau / 64), c["y"] + c["r"] * math.sin(i * math.tau / 64)] for i in range(64)]
        for c in g["circles"]
    ]
    for polygon in polygons:
        scaled = {"points": [[v * scale for v in transform_point(p, b)] for p in polygon], "circles": [], "lines": []}
        _paint(layer, {**b, "x": 0, "y": 0, "stroke_width": b.get("stroke_width", 3) * scale}, font, scaled, scale)
    canvas.alpha_composite(layer.resize(canvas.size, Image.Resampling.LANCZOS))
    if include_text:
        paint_text(canvas, g["text_box"], g["lines"], font, b.get("text_color", "#222222"))
    return g


def aligned_x(width, text_width, align):
    return width - text_width if align == "right" else (width - text_width) / 2 if align == "center" else 0


def transform_point(point, b):
    angle = math.radians(b.get("rotation", 0))
    x = b["width"] - point[0] if b.get("flip_x") else point[0]
    y = (b.get("body_height") or b.get("height")) - point[1] if b.get("flip_y") else point[1]
    x, y = x * b.get("scale_x", 1), y * b.get("scale_y", 1)
    return [b["x"] + x * math.cos(angle) - y * math.sin(angle), b["y"] + x * math.sin(angle) + y * math.cos(angle)]


def untransform_point(point, b):
    angle = math.radians(b.get("rotation", 0))
    x, y = point[0] - b["x"], point[1] - b["y"]
    local = [(x * math.cos(angle) + y * math.sin(angle)) / b.get("scale_x", 1), (-x * math.sin(angle) + y * math.cos(angle)) / b.get("scale_y", 1)]
    if b.get("flip_x"):
        local[0] = b["width"] - local[0]
    if b.get("flip_y"):
        local[1] = (b.get("body_height") or b.get("height")) - local[1]
    return local


def caption_geometry(text, saved, panel_height, font):
    box = {"x": 32, "y": panel_height + 22, "width": 1016, "font_size": 34, "align": "center", "rotation": 0, **(saved or {})}
    line_h = box["font_size"] + 14
    texts = wrap_lines(text, font.getlength, box["width"])
    runs = [{"text": t, "width": font.getlength(t), "x": aligned_x(box["width"], font.getlength(t), box["align"]), "y": box["font_size"] + i * line_h} for i, t in enumerate(texts)]
    return {**box, "lines": runs, "height": max(line_h, len(runs) * line_h)}


def paint_text(canvas, box, runs, font, color):
    # Render into a local tile before transforming, so rotated text is not
    # clipped at its original (unrotated) position on the output canvas.
    scale, pad = 2, 8
    width = max([box["width"], *[run["x"] + font.getlength(run["text"]) for run in runs]])
    tile = Image.new("RGBA", (math.ceil(width * scale) + pad * 2, math.ceil((box["height"] + font.size) * scale) + pad * 2))
    draw = ImageDraw.Draw(tile)
    large_font = font.font_variant(size=round(font.size * scale))
    for run in runs:
        draw.text((pad + run["x"] * scale, pad + run["y"] * scale), run["text"], font=large_font, fill=color, anchor="ls")
    angle = math.radians(box.get("rotation", 0))
    c, s = math.cos(angle), math.sin(angle)
    x, y = box["x"] * scale, box["y"] * scale
    layer = tile.transform((canvas.width * scale, canvas.height * scale), Image.Transform.AFFINE,
                           (c, s, pad - c*x - s*y, -s, c, pad + s*x - c*y), Image.Resampling.BICUBIC)
    canvas.alpha_composite(layer.resize(canvas.size, Image.Resampling.LANCZOS))


def box_bottom(box):
    return max(transform_point(p, box)[1] for p in [(0,0), (box["width"],0), (0,box["height"]), (box["width"],box["height"])])


def _paint(canvas, b, font, g, scale=1):
    x, y = b["x"], b["y"]
    points = [(x + px, y + py) for px, py in g["points"]]
    draw = ImageDraw.Draw(canvas)
    fill, stroke = b.get("fill", "#ffffff"), b.get("stroke", "#333333")
    if b.get("bubble_variant") == "transparent":
        fill = None
    sw = round(b.get("stroke_width", 3))
    draw.polygon(points, fill=fill)
    if b.get("type") == "whisper" and sw:
        closed = points + [points[0]]
        for a, z in zip(closed, closed[1:]):
            distance = math.dist(a, z)
            for n in range(0, math.ceil(distance), 16 * scale):
                p = n / max(distance, 1)
                q = min(n + 9 * scale, distance) / max(distance, 1)
                draw.line(
                    [
                        (a[0] + (z[0] - a[0]) * p, a[1] + (z[1] - a[1]) * p),
                        (a[0] + (z[0] - a[0]) * q, a[1] + (z[1] - a[1]) * q),
                    ],
                    fill=stroke,
                    width=sw,
                )
    elif sw:
        draw.line(points + [points[0]], fill=stroke, width=sw, joint="curve")
    for c in g["circles"]:
        cx, cy, r = x + c["x"], y + c["y"], c["r"]
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=fill,
            outline=stroke if sw else None,
            width=max(1, sw),
        )
    for run in g["lines"]:
        draw.text(
            (x + run["x"], y + run["y"]),
            run["text"],
            font=font,
            fill=b.get("text_color", "#222222"),
            anchor="ls",
        )
    return g
