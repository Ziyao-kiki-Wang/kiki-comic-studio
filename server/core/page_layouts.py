"""Creative page arrangements, keeping full scene panels and editable heading options."""

import math
from PIL import Image, ImageColor, ImageDraw
from server.core.bubbles import wrap_lines
from server.core.headings import render_heading
from server.core.lettering import load_font
from server.core.asset_render import paste_image


def _tint(color, amount=.9):
    return tuple(round(c + (255 - c) * amount) for c in ImageColor.getrgb(color))


def prepare_pages(sources, settings, theme, project_id, width=1080):
    kind = theme["layout"]
    accent = settings.get("accent") or theme["accent"]
    tracking = settings.get("letter_spacing", 0)
    margin, gutter = (52, 24) if kind == "filmstrip" else (48, 28)
    available = width - margin * 2
    columns = 1 if kind == "editorial_mix" else min(3 if kind == "comic_strip" else 2, len(sources))
    body_size = 26 if kind == "comic_strip" else 28 if columns > 1 else 32
    font = load_font(body_size, project_id, settings.get("body_font_id"))
    step = body_size + settings.get("body_line_gap", 14)

    def make_entry(source, tile_width, index, hero=False):
        scene, panel = source["scene"], source["panel"]
        heading_options = {"style": "plain", "font_size": 30, "align": "left", **settings.get("heading", {}),
                           **settings.get("heading_overrides", {}).get(scene["scene_id"], {})}
        text = heading_options.get("text", scene.get("heading") or scene.get("location") or "")
        padding = 24 if kind in ("editorial_mix", "gallery_grid", "sketchbook") else 18
        inner_width = tile_width - padding * 2
        sideways = kind == "editorial_mix"
        text_width = 320 if sideways else inner_width
        badge = render_heading(text, heading_options,
                               load_font(int(heading_options["font_size"]), project_id, settings.get("body_font_id")),
                               text_width, accent, tracking)
        caption = "" if source["meta"].get("caption_layout") else scene.get("caption", "")
        caption_lines = wrap_lines(caption, lambda value: font.getlength(value) + max(0, len(value)-1)*tracking, text_width) if caption else []
        caption_h = math.ceil(len(caption_lines) * step)
        heading_h = badge["height"] + 18 if badge["image"] else 0
        image_width = inner_width - text_width - 32 if sideways else inner_width
        frame_h = round(image_width * (1 if kind == "gallery_grid" else .85 if kind == "comic_strip" else .76 if kind == "filmstrip" else .62 if hero else 1.25))
        factor = min(image_width / panel.width, frame_h / panel.height)
        picture_size = (max(1, round(panel.width*factor)), max(1, round(panel.height*factor)))
        if kind not in ("gallery_grid", "filmstrip", "comic_strip"):
            frame_h = picture_size[1]
        if sideways:
            body_h = max(frame_h, heading_h + caption_h + 36)
            height = body_h + padding * 2
            image_x = padding if index % 2 == 0 else tile_width-padding-image_width
            text_x = tile_width-padding-text_width if index % 2 == 0 else padding
            text_y = padding + max(0, (body_h-heading_h-caption_h)//2)
            frame = (image_x, padding+(body_h-frame_h)//2, image_width, frame_h)
            heading_box = (text_x, text_y, text_width)
            caption_xy = (text_x, text_y+heading_h)
        else:
            top_space = 30 if kind == "sketchbook" else padding
            # Photos first in the scrapbook / gallery; headings above frames elsewhere.
            photo_first = kind in ("sketchbook", "gallery_grid")
            frame = (padding, top_space if photo_first else top_space+heading_h, image_width, frame_h)
            heading_y = top_space+frame_h+18 if photo_first else top_space
            heading_box = (padding, heading_y, text_width)
            cap_y = heading_y+heading_h if photo_first else frame[1]+frame_h+18
            caption_xy = (padding, cap_y)
            height = max(frame[1]+frame_h, heading_y+badge["height"], cap_y+caption_h) + padding
        return {"scene": scene, "panel": panel, "meta": source.get("meta", {}), "width": tile_width, "height": height,
                "frame": frame, "picture_size": picture_size, "heading": badge, "heading_text": text,
                "heading_align": heading_options["align"], "heading_box": heading_box,
                "caption": caption_lines, "caption_xy": caption_xy, "font": font, "step": step, "index": index}

    rows, index = [], 0
    while index < len(sources):
        hero = kind == "magazine_grid" and index == 0
        row_columns = 1 if hero else columns
        batch = sources[index:index+row_columns]
        tile_width = (available - gutter*(row_columns-1)) // row_columns
        row = [make_entry(source, tile_width, index+j, hero) for j, source in enumerate(batch)]
        rows.append(row)
        index += len(batch)
    y, entries = 0, []
    for row_index, row in enumerate(rows):
        row_width = sum(e["width"] for e in row) + gutter*(len(row)-1)
        x = (width-row_width)//2
        for column, e in enumerate(row):
            offset = 24 if kind == "sketchbook" and column % 2 else 0
            e.update({"x": x, "y": y+offset, "row": row_index})
            x += e["width"] + gutter
        row_h = max(e["y"]-y+e["height"] for e in row)
        gap = round(max(settings.get("gaps", {}).get(e["scene"]["scene_id"], settings.get("gap", 60)) for e in row)) if row_index < len(rows)-1 else 0
        for e in row:
            e["gap_after"] = gap
        entries.extend(row)
        y += row_h+gap
    return {"entries": entries, "height": y, "kind": kind, "accent": accent, "tracking": tracking,
            "caption_align": settings.get("caption_align", "center")}


def draw_backdrop(canvas, header_h, theme, accent):
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    kind = theme["layout"]
    if kind == "sketchbook":
        for y in range(12, height, 28):
            for x in range(12, width, 28):
                draw.ellipse((x,y,x+1,y+1), fill="#dbcfb7")
    elif kind == "filmstrip":
        for y in range(20, height-15, 40):
            for x in (14, width-32):
                draw.rounded_rectangle((x,y,x+18,y+23), radius=4, fill="#f0e5ce")
    elif kind == "gallery_grid":
        draw.ellipse((width-280,-160,width+180,260), fill=_tint(accent,.89))
        draw.ellipse((-250,height-350,200,height+80), fill=_tint(accent,.89))
    if kind in ("magazine_grid", "editorial_mix"):
        draw.line((48,header_h-4,width-48,header_h-4), fill=accent, width=3)
        draw.line((48,header_h+4,width-48,header_h+4), fill=_tint(accent,.65), width=1)
    elif kind == "comic_strip":
        draw.line((48,header_h-4,width-48,header_h-4), fill=accent, width=5)
        for x in (48, width-64):
            draw.rectangle((x,header_h-13,x+16,header_h+5), fill=accent)


def paint_pages(canvas, plan, top, write):
    draw = ImageDraw.Draw(canvas)
    accent, kind = plan["accent"], plan["kind"]
    boxes = []
    for e in plan["entries"]:
        x, y, w, h = e["x"], top+e["y"], e["width"], e["height"]
        if kind == "filmstrip":
            draw.rectangle((x,y,x+w-1,y+h-1), fill="#263842", outline="#68757a", width=1)
        elif kind == "comic_strip":
            draw.rectangle((x+4,y+4,x+w-1,y+h-1), fill=_tint(accent,.7))
            draw.rectangle((x,y,x+w-5,y+h-5), fill="white", outline=accent, width=3)
        elif kind == "sketchbook":
            draw.rectangle((x+5,y+7,x+w-1,y+h-1), fill="#ddd1b8")
            draw.rectangle((x,y,x+w-6,y+h-8), fill="#fffdf8")
            points = [(x+3+t,y+4+math.sin(t/19)*1.5) for t in range(0,w-10,5)]
            draw.line(points, fill=accent, width=2)
            draw.line((x+4,y+8,x+3,y+h-12,x+w-11,y+h-11), fill=_tint(accent,.4), width=2)
            cx = x+w//2
            draw.polygon([(cx-48,y+4),(cx+48,y+8),(cx+45,y+23),(cx-50,y+19)],fill="#e4c891")
        elif kind == "gallery_grid":
            draw.rounded_rectangle((x+3,y+6,x+w-1,y+h-1), radius=22, fill=_tint(accent,.83))
            draw.rounded_rectangle((x,y,x+w-4,y+h-6), radius=22, fill="white")
        else:
            draw.rectangle((x,y,x+w-1,y+h-1),fill="#fffdfa" if kind == "editorial_mix" else "white")
            if kind == "magazine_grid":
                draw.line((x,y+h-1,x+w,y+h-1),fill=_tint(accent,.55),width=2)

        fx, fy, fw, fh = e["frame"]
        draw.rectangle((x+fx,y+fy,x+fx+fw-1,y+fy+fh-1), fill=_tint(accent,.93) if kind != "filmstrip" else "#e8ece9")
        image = e["panel"].resize(e["picture_size"],Image.Resampling.LANCZOS)
        picture_x, picture_y = x+fx+(fw-image.width)//2, y+fy+(fh-image.height)//2
        paste_image(canvas,image,(picture_x,picture_y))

        badge = e["heading"]
        hx, hy, hw = e["heading_box"]
        hx += (hw-badge["width"])/2 if e["heading_align"] == "center" else hw-badge["width"] if e["heading_align"] == "right" else 0
        if badge["image"]:
            paste_image(canvas,badge["image"],(round(x+hx),round(y+hy)))
        cap_x, cap_y = e["caption_xy"]
        cap_align = plan.get("caption_align", "center")
        cap_anchor = {"left": "lt", "center": "mt", "right": "rt"}.get(cap_align, "lt")
        cap_w = e["heading_box"][2]
        cap_tx = x + cap_x if cap_align == "left" else (x + cap_x + cap_w if cap_align == "right" else x + cap_x + cap_w / 2)
        for i, line in enumerate(e["caption"]):
            write(draw,(cap_tx,y+cap_y+i*e["step"]),line,font=e["font"],fill="#edf0ed" if kind == "filmstrip" else "#424a49",anchor=cap_anchor)
        if kind == "editorial_mix" and badge["image"]:
            draw.line((x+e["heading_box"][0],y+hy-16,x+e["heading_box"][0]+48,y+hy-16),fill=accent,width=3)
        boxes.append({"scene_id":e["scene"]["scene_id"], "x":x,"y":y,"width":w,"height":h,
                      "row":e["row"],"gap_after":e["gap_after"],
                      "picture":{"x":picture_x,"y":picture_y,"width":image.width,"height":image.height,
                                 "panel_w":e["panel"].width,"panel_h":e["panel"].height,
                                 "caption_layout":bool(e.get("meta",{}).get("caption_layout")),
                                 "transparent":e.get("meta",{}).get("background_mode") == "transparent"},
                      "caption":{"lines":e["caption"],"x":x+cap_x,"y":y+cap_y,"height":math.ceil(len(e["caption"])*e["step"])},
                      "heading":{**{k:v for k,v in badge.items() if k != "image"}, "text":e["heading_text"],
                                 "align":e["heading_align"],"x":round(x+hx),"y":round(y+hy)}})
    return boxes
