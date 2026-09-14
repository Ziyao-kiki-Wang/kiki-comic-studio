"""Article and creative page layouts built from separate panel and caption assets."""

import hashlib
import json
import math

from PIL import Image, ImageColor, ImageDraw
from server import store
from server.config import PANEL_W
from server.core.asset_render import render_asset, paste_image
from server.core.lettering import load_font
from server.core.bubbles import wrap_lines
from server.core.headings import render_heading
from server.core.page_layouts import prepare_pages, draw_backdrop, paint_pages
from server.core.studio import TEMPLATES, long_layout
from server.services.assets import asset_path, font_record


def long_image_signature(project_id, sb, settings=None):
    """Return a stable signature for the inputs used by the saved long image."""
    settings = dict(settings or long_layout(sb))
    settings.pop("thumbnail", None)
    panels = {}
    pdir = store.project_dir(project_id)
    for scene in sb.get("scenes", []):
        sid = scene["scene_id"]
        meta = store.load_scene_meta(project_id, sid) or {}
        panel = pdir / "output" / f"{sid}_panel.png"
        if not panel.exists():
            panel = pdir / "output" / f"{sid}.png"
        panels[sid] = {
            "path": str(panel.relative_to(pdir)).replace("\\", "/"),
            "mtime_ns": panel.stat().st_mtime_ns if panel.exists() else None,
            "size": panel.stat().st_size if panel.exists() else None,
            "render_stale": bool(meta.get("render_stale")),
        }
    # Panel mtimes cover image/overlay edits.  Text used by the long-layout
    # renderer is tracked separately because chapter headings and captions can
    # change without re-rendering a scene panel.
    content = [
        {
            "scene_id": scene.get("scene_id"),
            "heading": scene.get("heading"),
            "question": scene.get("question"),
            "location": scene.get("location"),
            "caption": scene.get("caption", ""),
        }
        for scene in sb.get("scenes", [])
    ]
    payload = {
        "settings": settings,
        "title": settings.get("title") or sb.get("title") or "",
        "scenes": content,
        "panels": panels,
        "fonts": {
            fid: font_record(project_id, fid)
            for fid in {settings.get("title_font_id"), settings.get("body_font_id")}
            if fid
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(), **payload}


def long_image_stale(project_id, sb=None):
    """Whether the existing long image no longer matches current editor state."""
    pdir = store.project_dir(project_id)
    output = pdir / "output" / "长图.png"
    if not output.exists():
        return False
    try:
        sb = sb or store.load_storyboard(project_id)
        manifest_path = pdir / "output" / "long_layout.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        current = long_image_signature(project_id, sb)
        return (
            manifest.get("signature") != current["sha256"]
            or any(item.get("render_stale") for item in current["panels"].values())
        )
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return True


def render_long_image(project_id, sb, options=None):
    settings = {**long_layout(sb), **(options or {})}
    if options and "title_style" not in options and "title_art_style" in options:
        settings["title_style"] = options["title_art_style"]
    kind = settings["template_id"]
    theme = TEMPLATES[kind]
    creative = bool(theme.get("layout"))
    accent = settings.get("accent") or theme["accent"]
    bg = settings.get("background_color") or theme["background"]
    opacity = settings["background_opacity"]
    canvas_mode = "RGB" if opacity == 1 else "RGBA"
    canvas_fill = bg if opacity == 1 else (*ImageColor.getrgb(bg), round(255 * opacity))
    pixels_per_cm = PANEL_W / settings["print_width_cm"]
    margin_top = round(settings["margin_top_cm"] * pixels_per_cm)
    margin_bottom = round(settings["margin_bottom_cm"] * pixels_per_cm)
    dpi = pixels_per_cm * 2.54
    pdir = store.project_dir(project_id)
    # A blank title stays blank; template names such as “漫画故事” must never
    # be silently inserted into the exported long image.
    title = settings.get("title") or sb.get("title") or ""
    subtitle = settings.get("subtitle") or ""
    footer = settings.get("footer") or ""
    title_font_size = int(settings.get("font_size", settings.get("title_font_size", 58)))
    title_font = load_font(title_font_size, project_id, settings.get("title_font_id"))
    body_font = load_font(32, project_id, settings.get("body_font_id"))
    tracking = settings["letter_spacing"]
    title_style = settings.get("title_style", settings.get("title_art_style", "plain"))
    title_align = settings.get("align", "center")
    title_x = (
        80
        if title_align == "left"
        else PANEL_W - 80
        if title_align == "right"
        else PANEL_W / 2
    )
    title_anchor = "lt" if title_align == "left" else "rt" if title_align == "right" else "mt"
    title_image = None
    title_image_asset = settings.get("title_image_asset")
    if title_image_asset:
        with Image.open(asset_path(project_id, title_image_asset)) as source:
            title_image = source.convert("RGBA")
        max_width = 900
        if title_image.width > max_width:
            title_image = title_image.resize(
                (
                    max_width,
                    max(1, round(title_image.height * max_width / title_image.width)),
                ),
                Image.Resampling.LANCZOS,
            )

    def measure(text, font):
        return font.getlength(text) + max(0, len(text) - 1) * tracking

    def lines(text, font, width):
        return wrap_lines(text, lambda t: measure(t, font), width)

    def write(draw, xy, text, font, fill, anchor="lt"):
        if not tracking:
            draw.text(xy, text, font=font, fill=fill, anchor=anchor)
            return
        x, y = xy
        if anchor == "mt":
            x -= measure(text, font) / 2
        elif anchor == "rt":
            x -= measure(text, font)
        baseline = y - font.getbbox(text or "国", anchor="ls")[1]
        for index, ch in enumerate(text):
            draw.text(
                (x + font.getlength(text[:index]) + index * tracking, baseline),
                ch,
                font=font,
                fill=fill,
                anchor="ls",
            )

    title_step = title_font_size + settings["title_line_gap"]
    body_step = 32 + settings["body_line_gap"]
    title_lines = [] if title_image else lines(title, title_font, 900)
    sub_lines = lines(subtitle, body_font, 900) if subtitle else []
    title_block_h = title_image.height if title_image else title_step * len(title_lines)
    header_h = round(
        settings["title_top"]
        + title_block_h
        + body_step * len(sub_lines)
        + (8 if sub_lines else 0)
        + settings["title_bottom"]
    )
    entries = []
    for i, scene in enumerate(sb.get("scenes", [])):
        sid = scene["scene_id"]
        meta = store.load_scene_meta(project_id, sid) or {}
        if meta.get("render_stale"):
            raise ValueError(f"{sid} 的文字或背景已修改，请先重新合成后再排版长图")
        path = pdir / "output" / f"{sid}_panel.png"
        if path.exists():
            with Image.open(path) as im:
                panel = im.convert("RGBA")
        else:
            legacy = pdir / "output" / f"{sid}.png"
            if not legacy.exists():
                raise ValueError(f"{sid} 尚未生成，请先完成各格再导出长图")
            with Image.open(legacy) as im:
                cap_h = meta.get("caption", {}).get("height", 100)
                panel = im.convert("RGBA").crop(
                    (0, 0, im.width, max(1, im.height - cap_h))
                )
        if creative:
            entries.append({"scene": scene, "panel": panel, "meta": meta})
            continue
        x = (
            132
            if kind == "timeline"
            else 105
            if kind == "notebook"
            else 0
            if kind == "poster"
            else 72
            if kind == "scroll"
            else 48
        )
        width = PANEL_W - x - (48 if kind in ("timeline", "notebook") else x)
        pad = 20 if kind in ("cards", "frames", "stickers", "notice") else 0
        picture_h = round(panel.height * (width - 2 * pad) / panel.width)
        heading = (
            (
                scene.get("question")
                or scene.get("heading")
                or scene.get("location")
                or ""
            )
            if kind == "qa"
            else (scene.get("heading") or scene.get("location") or "")
        )
        heading_options = {
            "style": "plain", "font_size": 30, "align": "left",
            **settings.get("heading", {}),
            **settings.get("heading_overrides", {}).get(sid, {}),
        }
        heading = heading_options.get("text", heading)
        heading_render = render_heading(
            heading, heading_options,
            load_font(int(heading_options["font_size"]), project_id, settings.get("body_font_id")),
            width - 44, accent, tracking,
        )
        heading_h = heading_render["height"] + 36 if heading_render["image"] else 0
        cap_lines = lines(
            ("A  " if kind == "qa" else "") + scene.get("caption", ""),
            body_font,
            width - 48,
        )
        if meta.get("caption_layout"):
            cap_lines = []
        cap_h = max(76, 38 + body_step * len(cap_lines)) if cap_lines else 0
        block_h = (
            heading_h + picture_h + cap_h + pad + (24 if kind == "stickers" else 0)
        )
        entries.append(
            {
                "scene": scene,
                "panel": panel,
                "x": x,
                "width": width,
                "pad": pad,
                "picture_h": picture_h,
                "height": block_h,
                "heading": heading_render,
                "heading_text": heading,
                "heading_align": heading_options["align"],
                "heading_h": heading_h,
                "caption": cap_lines,
                "meta": meta,
            }
        )
    if not entries:
        raise ValueError("没有可导出的分镜")
    page_plan = prepare_pages(entries, settings, theme, project_id, PANEL_W) if creative else None
    gaps = [
        round(
            settings.get("gaps", {}).get(
                e["scene"]["scene_id"], settings.get("gap", 60)
            )
        )
        for e in entries[:-1]
    ]
    foot_lines = lines(footer, body_font, 900) if footer else []
    footer_entries = []
    for block in settings.get("footer_blocks", []):
        if block["type"] == "image":
            with Image.open(asset_path(project_id, block["asset_id"])) as source:
                picture = source.convert("RGBA")
            factor = min(block.get("width", 800) / picture.width, 1600 / picture.height)
            picture = picture.resize((max(1, round(picture.width * factor)), max(1, round(picture.height * factor))), Image.Resampling.LANCZOS)
            footer_entries.append({"block": block, "picture": picture, "height": picture.height})
        elif block.get("text", "").strip():
            font = load_font(block.get("font_size", 32), project_id, settings.get("body_font_id"))
            wrapped = lines(block["text"], font, 900)
            step = block.get("font_size", 32) + settings["body_line_gap"]
            footer_entries.append({"block": block, "font": font, "lines": wrapped, "step": step, "height": len(wrapped) * step})
    for entry in footer_entries:
        block = entry["block"]
        entry["gap_before"] = round(block["gap_before_cm"] * pixels_per_cm) if "gap_before_cm" in block else 24
    total = round(
        header_h
        + 40
        + (page_plan["height"] if creative else sum(e["height"] for e in entries) + sum(gaps))
        + 70
        + len(foot_lines) * body_step
        + sum(entry["height"] + entry["gap_before"] for entry in footer_entries)
    )
    if total + margin_top + margin_bottom > 40000:
        raise ValueError("长图过长，请减少格数、文字或间距（最多 40000 像素）")
    canvas = Image.new(canvas_mode, (PANEL_W, total), canvas_fill)
    draw = ImageDraw.Draw(canvas)
    if creative:
        draw_backdrop(canvas, header_h, theme, accent)
    if kind == "notebook":
        for y in range(0, total, 48):
            draw.line((30, y, 1050, y), fill="#dbe3eb", width=2)
        draw.line((80, 0, 80, total), fill=accent, width=2)
    if kind == "scroll":
        for x in (25, 36, PANEL_W - 25, PANEL_W - 36):
            draw.line((x, 20, x, total - 20), fill=accent, width=2)
    filled = kind in ("cards", "poster", "notice") or bool(theme.get("header_fill"))
    if filled:
        draw.rectangle((0, 0, PANEL_W, header_h), fill=theme.get("header_fill") or accent)
    elif kind == "frames":
        draw.rectangle((48, 25, 1032, header_h - 10), outline=accent, width=6)
    elif kind == "stickers":
        draw.rounded_rectangle((80, 22, 1000, header_h - 8), radius=16, fill="white")
        draw.rectangle((450, 12, 630, 42), fill="#dec49b")
    elif kind in ("magazine", "timeline", "qa", "scroll"):
        draw.line((72, header_h - 15, 1008, header_h - 15), fill=accent, width=3)
    color = "white" if filled else accent
    y = settings["title_top"]
    if title_image:
        image_x = (
            80
            if title_align == "left"
            else PANEL_W - 80 - title_image.width
            if title_align == "right"
            else (PANEL_W - title_image.width) // 2
        )
        paste_image(canvas, title_image, (round(image_x), round(y)))
        y += title_image.height
    else:
        for line in title_lines:
            if title_style == "outline" and not tracking:
                draw.text(
                    (title_x, y),
                    line,
                    font=title_font,
                    fill=color,
                    anchor=title_anchor,
                    stroke_width=3,
                    stroke_fill=accent if filled else "#ffffff",
                )
            elif title_style == "shadow":
                write(
                    draw,
                    (title_x + (5 if title_align != "right" else -5), y + 6),
                    line,
                    font=title_font,
                    fill="#b8b8b8",
                    anchor=title_anchor,
                )
                write(draw, (title_x, y), line, font=title_font, fill=color, anchor=title_anchor)
            elif title_style == "raised":
                write(
                    draw,
                    (title_x + (3 if title_align != "right" else -3), y + 4),
                    line,
                    font=title_font,
                    fill="#8d8d8d",
                    anchor=title_anchor,
                )
                write(
                    draw,
                    (title_x + (-2 if title_align != "right" else 2), y - 2),
                    line,
                    font=title_font,
                    fill="#ffffff" if filled else "#f4f4f4",
                    anchor=title_anchor,
                )
                write(draw, (title_x, y), line, font=title_font, fill=color, anchor=title_anchor)
            else:
                write(draw, (title_x, y), line, font=title_font, fill=color, anchor=title_anchor)
            y += title_step
    for line in sub_lines:
        write(draw, (title_x, y + 8), line, font=body_font, fill=color, anchor=title_anchor)
        y += body_step
    y = header_h + 40
    boxes = []
    if creative:
        boxes = paint_pages(canvas, page_plan, y, write)
        y += page_plan["height"]
    for i, e in enumerate([] if creative else entries):
        x, w, pad, h = e["x"], e["width"], e["pad"], e["height"]
        sid = e["scene"]["scene_id"]
        boxes.append(
            {
                "scene_id": sid,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "gap_after": gaps[i] if i < len(gaps) else 0,
            }
        )
        if kind in ("cards", "stickers", "notice", "timeline"):
            draw.rounded_rectangle(
                (x, y, x + w - 1, y + h - 1),
                radius=22 if kind == "cards" else 8,
                fill="white",
                outline="#dedede",
                width=2,
            )
        if kind == "frames":
            draw.rectangle(
                (x, y, x + w - 1, y + h - 1), fill="white", outline=accent, width=6
            )
        if kind == "notice":
            draw.rectangle((x, y, x + 8, y + h - 1), fill=accent)
        if kind == "timeline":
            cy = y + 32
            end = (
                y + h + (gaps[i] if i < len(gaps) else 0) + 32
                if i < len(entries) - 1
                else cy
            )
            draw.line((78, cy, 78, end), fill=accent, width=5)
            draw.ellipse((66, cy - 12, 90, cy + 12), fill=accent)
            draw.ellipse((73, cy - 5, 83, cy + 5), fill="white")
        if kind == "stickers":
            draw.rectangle((x + 50, y + 6, x + 210, y + 26), fill="#dec49b")
        heading_y = y + 18 + (18 if kind == "stickers" else 0)
        badge = e["heading"]
        heading_x = (
            x + (w - badge["width"]) / 2 if e["heading_align"] == "center"
            else x + w - 22 - badge["width"] if e["heading_align"] == "right"
            else x + 22
        )
        if badge["image"]:
            paste_image(canvas, badge["image"], (round(heading_x), round(heading_y)))
        boxes[-1]["heading"] = {
            **{key: value for key, value in badge.items() if key != "image"},
            "text": e["heading_text"], "align": e["heading_align"],
            "x": round(heading_x), "y": round(heading_y),
        }
        py = y + e["heading_h"] + (18 if kind == "stickers" else 0)
        image = e["panel"].resize(
            (w - 2 * pad, e["picture_h"]), Image.Resampling.LANCZOS
        )
        pic_x, pic_y = round(x + pad), round(py)
        paste_image(canvas, image, (pic_x, pic_y))
        # Record the picture box so the long-image preview can overlay a
        # per-scene editor at the exact same position for direct dragging.
        boxes[-1]["picture"] = {
            "x": pic_x, "y": pic_y, "width": image.width, "height": image.height,
            "panel_w": e["panel"].width, "panel_h": e["panel"].height,
            "caption_layout": bool(e["meta"].get("caption_layout")),
            "transparent": e["meta"].get("background_mode") == "transparent",
        }
        cap_y = py + e["picture_h"] + 20
        if kind == "notice" and e["caption"]:
            draw.line((x + 20, cap_y - 8, x + w - 20, cap_y - 8), fill=accent, width=3)
        if kind == "qa" and e["caption"]:
            draw.rectangle((x, cap_y - 2, x + 5, y + h - 8), fill=accent)
        if kind == "poster" and e["caption"]:
            draw.rectangle((x, py + e["picture_h"], x + w, y + h), fill="#ffffff")
        cap_align = settings.get("caption_align", "center")
        cap_anchor = {"left": "lt", "center": "mt", "right": "rt"}.get(cap_align, "lt")
        cap_tx = x + 24 if cap_align == "left" else (x + w - 24 if cap_align == "right" else x + w / 2)
        cap_tx = round(cap_tx)
        for line in e["caption"]:
            write(
                draw, (cap_tx, cap_y), line, font=body_font, fill="#30333a", anchor=cap_anchor
            )
            cap_y += body_step
        if e["caption"]:
            boxes[-1]["caption_box"] = {
                "x": x + 24, "y": py + e["picture_h"] + 20,
                "width": w - 48, "height": math.ceil(len(e["caption"]) * body_step),
            }
        y += h + (gaps[i] if i < len(gaps) else 0)
    draw.line((72, y + 28, 1008, y + 28), fill=accent, width=2)
    for i, line in enumerate(foot_lines):
        write(
            draw,
            (PANEL_W / 2, y + 48 + i * body_step),
            line,
            font=body_font,
            fill=accent,
            anchor="mt",
        )
    foot_y = round(y + 48 + len(foot_lines) * body_step)
    footer_boxes = []
    for entry in footer_entries:
        foot_y += entry["gap_before"]
        align = entry["block"].get("align", "center")
        if "picture" in entry:
            picture = entry["picture"]
            x = 60 if align == "left" else PANEL_W - 60 - picture.width if align == "right" else (PANEL_W - picture.width) // 2
            paste_image(canvas, picture, (round(x), round(foot_y)))
        else:
            x = 90 if align == "left" else PANEL_W - 90 if align == "right" else PANEL_W / 2
            anchor = "lt" if align == "left" else "rt" if align == "right" else "mt"
            for i, line in enumerate(entry["lines"]):
                write(draw, (x, foot_y + i * entry["step"]), line, font=entry["font"], fill=accent, anchor=anchor)
        footer_boxes.append({**entry["block"], "y": foot_y, "height": entry["height"], "gap_before_px": entry["gap_before"]})
        foot_y += entry["height"]
    # Outer margins surround the entire template. They do not stretch or crop it.
    # Stickers retain page coordinates, matching the final decoration editor.
    content_height = total
    if margin_top or margin_bottom:
        padded = Image.new(canvas_mode, (PANEL_W, total + margin_top + margin_bottom), canvas_fill)
        padded.paste(canvas, (0, margin_top))
        canvas = padded
        for box in boxes:
            box["y"] += margin_top
            for key in ("heading", "picture", "caption"):
                if key in box:
                    box[key]["y"] += margin_top
        for box in footer_boxes:
            box["y"] += margin_top
    total = canvas.height
    if kind == "scroll":
        # Continue the side borders through both outer margins to the page edges.
        border_draw = ImageDraw.Draw(canvas)
        for x in (25, 36, PANEL_W - 25, PANEL_W - 36):
            border_draw.line((x, 0, x, margin_top + 20), fill=accent, width=2)
            border_draw.line((x, content_height + margin_top - 20, x, total - 1), fill=accent, width=2)
    stickers = sorted(settings.get("stickers", []), key=lambda item: item.get("z_index", 0))
    for sticker in stickers:
        render_asset(canvas, project_id, sticker)
    return canvas, {
        "width": PANEL_W,
        "height": total,
        "template_id": kind,
        "background_color": bg,
        "background_opacity": opacity,
        "scenes": boxes,
        "title_top": settings["title_top"],
        "header_height": header_h + margin_top,
        "print_width_cm": settings["print_width_cm"],
        "dpi": dpi,
        "page_margins": {
            "top_cm": settings["margin_top_cm"], "bottom_cm": settings["margin_bottom_cm"],
            "top_px": margin_top, "bottom_px": margin_bottom, "content_height": content_height,
        },
        "title_style": title_style,
        "title_art_style": title_style,
        "font_size": title_font_size,
        "align": title_align,
        "title_font_id": settings.get("title_font_id"),
        "title_image_asset": title_image_asset,
        "stickers": stickers,
        "footer_blocks": footer_boxes,
    }


def make_long_image(project_id, sb):
    canvas, layout = render_long_image(project_id, sb)
    out = store.project_dir(project_id) / "output" / "长图.png"
    canvas.save(out, dpi=(layout["dpi"], layout["dpi"]))
    signature = long_image_signature(project_id, sb)
    store._write_json(
        out.with_name("long_layout.json"),
        {
            **layout,
            "signature": signature["sha256"],
            "render_settings": signature["settings"],
            "scene_panels": signature["panels"],
        },
    )
    print(f"完成！长图 {layout['template_id']}，{canvas.width}×{canvas.height}")
    return out
