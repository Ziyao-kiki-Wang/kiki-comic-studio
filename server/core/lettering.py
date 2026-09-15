"""Render a scene as separate picture and caption assets, preserving alpha and browser geometry."""

from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat
from server import store
from server.config import PANEL_W
from server.core import bubbles, scenes
from server.core.asset_render import render_asset
from server.core.studio import BUBBLES, background_mode, screen_enabled
from server.services.assets import font_path

# Project-bundled CJK font is the reliable cross-platform fallback: the
# fonts/ tree is deployed alongside the code, so any text without an explicit
# font_id still renders Chinese correctly on both Windows and the Linux host.
_FALLBACK_FONT = (
    Path(__file__).resolve().parents[2]
    / "fonts"
    / "source-han-sans"
    / "SourceHanSansSC-Regular.otf"
)

FONT_CANDIDATES = [
    str(_FALLBACK_FONT),
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size, project_id=None, font_id=None):
    if project_id and font_id:
        custom = font_path(project_id, font_id)
        if custom:
            return ImageFont.truetype(custom, int(size))
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, int(size))
    return ImageFont.load_default(size=int(size))


def wrap_text(draw, text, font, max_width):
    return bubbles.wrap_lines(text, lambda t: draw.textlength(t, font=font), max_width)


def text_lines(text, font, width):
    return bubbles.wrap_lines(text, lambda t: font.getlength(t), width)


def choose_position(panel, width, height, placed, order):
    small = panel.convert("L").resize(
        (max(1, panel.width // 8), max(1, panel.height // 8))
    )
    edges = small.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(2))
    best, score = (30, 30), float("inf")
    for y in [
        30,
        max(30, (panel.height - height) // 2),
        max(30, panel.height - height - 70),
    ]:
        for x in [
            30,
            max(30, (panel.width - width) // 2),
            max(30, panel.width - width - 30),
        ]:
            box = (x, y, x + width, y + height + 45)
            overlap = any(
                not (
                    box[2] + 12 < a[0]
                    or a[2] + 12 < box[0]
                    or box[3] + 12 < a[1]
                    or a[3] + 12 < box[1]
                )
                for a in placed
            )
            region = edges.crop(
                (
                    int(x / 8),
                    int(y / 8),
                    max(int(x / 8) + 1, int((x + width) / 8)),
                    max(int(y / 8) + 1, int((y + height) / 8)),
                )
            )
            energy = (
                ImageStat.Stat(region).mean[0]
                + abs((y + height / 2) / panel.height - order) * 60
                + (10000 if overlap else 0)
            )
            if energy < score:
                best, score = (x, y), energy
    return best


def paste_inset(canvas, screen_path, x, y, w=320, h=480):
    with Image.open(screen_path) as source:
        screen = source.convert("RGBA").resize(
            (int(w), int(h)), Image.Resampling.LANCZOS
        )
    mask = Image.new("L", screen.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=30, fill=255)
    screen.putalpha(mask)
    canvas.alpha_composite(screen, (int(x), int(y)))
    ImageDraw.Draw(canvas).rounded_rectangle(
        (x, y, x + w - 1, y + h - 1), radius=30, outline="#1a1a1a", width=8
    )


def letter_scene(project_id, sb, scene, force=False):
    sid = scene["scene_id"]
    pdir = store.project_dir(project_id)
    out = pdir / "output" / f"{sid}.png"
    panel_out = pdir / "output" / f"{sid}_panel.png"
    meta = store.load_scene_meta(project_id, sid) or {"scene_id": sid}
    if (
        out.exists()
        and panel_out.exists()
        and not force
        and not meta.get("render_stale")
    ):
        print(f"  {sid} 已合成，跳过")
        return out
    source = scenes.scene_asset(project_id, sb, scene)
    if source is None:
        print(f"  {sid} 还没有场景原图，跳过合成")
        return None
    with Image.open(source) as im:
        panel = im.convert("RGBA").resize(
            (PANEL_W, round(im.height * PANEL_W / im.width)), Image.Resampling.LANCZOS
        )
    saved = {b["bubble_id"]: b for b in meta.get("bubbles", []) if b.get("bubble_id")}
    placed = []
    overlays = list(meta.get("overlays", []))
    # Reserve sticker space while choosing bubble positions. The actual
    # compositing happens after bubbles below so user supplied stickers stay
    # on top in both the editor and the exported image.
    for overlay in sorted(overlays, key=lambda item: item.get("z_index", 0)):
        placed.append(
            (
                overlay.get("x", 0),
                overlay.get("y", 0),
                overlay.get("x", 0) + overlay.get("width", 0),
                overlay.get("y", 0) + overlay.get("height", 0),
            )
        )
    inset = meta.get("screen_inset")
    screen_path = pdir / "screens" / f"{sid}_screen.png"
    if (
        scene.get("screen_inset")
        and screen_enabled(scene)
        and (scene.get("screen_mode") == "inset" or inset)
        and not meta.get("screen_inset_hidden")
        and screen_path.exists()
    ):
        inset = inset or {"x": PANEL_W - 370, "y": 50, "width": 320, "height": 480}
        paste_inset(
            panel, screen_path, inset["x"], inset["y"], inset["width"], inset["height"]
        )
        meta["screen_inset"] = {**inset, "asset": f"screens/{sid}_screen.png"}
        placed.append(
            (
                inset["x"],
                inset["y"],
                inset["x"] + inset["width"],
                inset["y"] + inset["height"],
            )
        )
    else:
        meta.pop("screen_inset", None)
    rendered = []
    dialogues = scene.get("dialogues", [])
    for i, dlg in enumerate(dialogues):
        bid = dlg.get("bubble_id", f"b{i + 1:02d}")
        old = saved.get(bid)
        kind = dlg.get("bubble_type", "speech")
        if kind not in BUBBLES:
            kind = "speech"
        b = {
            "bubble_id": bid,
            "type": kind,
            "speaker": dlg.get("speaker"),
            "x": 30,
            "y": 30,
            "width": 420,
            "font_size": 36,
            **(old or {}),
            "text": dlg["text"],
        }
        selected_font_id = (
            b.get("font_id")
            or b.get("font_family")
            or scene.get("bubble_font_id")
        )
        if selected_font_id == "system":
            selected_font_id = None
        if selected_font_id:
            b["font_id"] = selected_font_id
        font = load_font(
            b["font_size"],
            project_id,
            selected_font_id,
        )
        if not old:
            g = bubbles.geometry(b, font)
            b["x"], b["y"] = choose_position(
                panel, b["width"], g["height"], placed, i / max(1, len(dialogues) - 1)
            )
        g = bubbles.paint(panel, b, font, include_text=False) if b.get("bubble_visible", True) else bubbles.geometry(b, font)
        b.update({"height": g["height"], "geometry": g})
        rendered.append(b)
        placed.append((b["x"], b["y"], b["x"] + b["width"], b["y"] + g["height"] + 50))
    for b in rendered:
        if not b.get("text_visible", True):
            continue
        font = load_font(b["font_size"], project_id, b.get("font_id"))
        bubbles.paint_text(panel, b["geometry"]["text_box"], b["geometry"]["lines"], font, b.get("text_color", "#222222"))
    for overlay in sorted(overlays, key=lambda item: item.get("z_index", 0)):
        render_asset(panel, project_id, overlay)
    pdir.joinpath("output").mkdir(exist_ok=True)
    panel.save(panel_out)
    cap = scene.get("caption", "")
    caption_layout = meta.get("caption_layout")
    font = load_font((caption_layout or {}).get("font_size", 34), project_id, (caption_layout or {}).get("font_id") or scene.get("caption_font_id"))
    cap_box = bubbles.caption_geometry(cap, caption_layout, panel.height, font)
    cap_h = max(0, math.ceil(bubbles.box_bottom(cap_box) + 22 - panel.height)) if caption_layout else max(100, 32 + cap_box["height"])
    transparent = background_mode(sb, scene) == "transparent"
    canvas = Image.new(
        "RGBA",
        (PANEL_W, panel.height + cap_h),
        (0, 0, 0, 0) if transparent else "white",
    )
    canvas.alpha_composite(panel)
    bubbles.paint_text(canvas, cap_box, cap_box["lines"], font, "#343434")
    if transparent or meta.get("layer_order"):
        # Recompose independent objects in the same bottom-to-top order as the editor.
        canvas = Image.new("RGBA", canvas.size, (0, 0, 0, 0) if transparent else "white")
        subject_box = (meta.get("subject_layout") if transparent else None) or {"x": 0, "y": 0, "width": PANEL_W, "height": panel.height}
        def draw_subject():
            with Image.open(source) as original:
                foreground = original.convert("RGBA").resize(
                    (round(subject_box["width"]), round(subject_box["height"])), Image.Resampling.LANCZOS)
            canvas.alpha_composite(foreground, (round(subject_box["x"]), round(subject_box["y"])))
        layers = {"subject": draw_subject}
        if meta.get("screen_inset"):
            layers["inset"] = lambda: paste_inset(canvas, screen_path, inset["x"], inset["y"], inset["width"], inset["height"])
        for b in rendered:
            if b.get("bubble_visible", True):
                layers[b["bubble_id"]] = lambda b=b: bubbles.paint(canvas, b, load_font(b["font_size"], project_id, b.get("font_id")), include_text=False)
        for b in rendered:
            if b.get("text_visible", True):
                layers["text:" + b["bubble_id"]] = lambda b=b: bubbles.paint_text(canvas, b["geometry"]["text_box"], b["geometry"]["lines"], load_font(b["font_size"], project_id, b.get("font_id")), b.get("text_color", "#222222"))
        for overlay in sorted(overlays, key=lambda item: item.get("z_index", 0)):
            key = "overlay:" + (overlay.get("overlay_id") or overlay.get("id") or overlay["asset_id"])
            layers[key] = lambda overlay=overlay: render_asset(canvas, project_id, overlay)
        layers["caption"] = lambda: bubbles.paint_text(canvas, cap_box, cap_box["lines"], font, "#343434")
        order = [key for key in meta.get("layer_order", []) if key in layers]
        order += [key for key in layers if key not in order]
        if not transparent:
            order = ["subject"] + [key for key in order if key != "subject"]
        for key in order:
            layers[key]()
        canvas.crop((0, 0, PANEL_W, panel.height)).save(panel_out)
    if caption_layout:
        # A freely placed caption travels with the picture in every long-image
        # template; the template must not repeat it in a second caption block.
        canvas.save(panel_out)
    canvas.save(out)
    meta.update(
        {
            "canvas": {
                "width": PANEL_W,
                "height": canvas.height,
                "panel_height": panel.height,
            },
            "bubbles": rendered,
            "overlays": overlays,
            "caption": {"text": cap, "font_size": cap_box["font_size"], "height": cap_h},
            "composite": f"output/{sid}.png",
            "panel": f"output/{sid}_panel.png",
            "background_mode": background_mode(sb, scene),
            "status": meta.get("status", "draft"),
            "render_stale": False,
        }
    )
    store.save_scene_meta(project_id, sid, meta)
    print(f"  已合成：{sid}（{'透明主体' if transparent else '完整场景'}）")
    return out


def letter_all(project_id, sb, only_scene=None):
    for scene in sb["scenes"]:
        letter_scene(project_id, sb, scene, force=only_scene == scene["scene_id"])
