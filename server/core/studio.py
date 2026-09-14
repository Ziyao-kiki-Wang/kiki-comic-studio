"""Studio catalogs and validated presentation options, shared by API and renderers."""

import json
import re
import math
from server.config import SCHEMAS_DIR
from server import store
from server.core.asset_render import validate_transform

CATALOG = json.loads((SCHEMAS_DIR / "studio.json").read_text(encoding="utf-8"))
BUBBLES = {b["id"]: b for b in CATALOG["bubbles"]}
TEMPLATES = {t["id"]: t for t in CATALOG["templates"]}
FONT_CATALOG = json.loads((SCHEMAS_DIR / "fonts.json").read_text(encoding="utf-8"))
FONT_IDS = {item["id"] for item in FONT_CATALOG.get("fonts", [])}
HEADING_STYLES = {item["id"]: item for item in json.loads((SCHEMAS_DIR / "heading_styles.json").read_text(encoding="utf-8"))["styles"]}


def background_mode(sb, scene=None):
    return (scene or {}).get("background_mode") or sb.get("background_mode", "scene")


def screen_enabled(scene):
    """Explicit opt-in, with content-based defaults for older storyboards."""
    if isinstance(scene.get("screen_enabled"), bool):
        return scene["screen_enabled"]
    return bool(scene.get("screen_inset") or scene.get("screen_mode") == "inset" or re.search(
        r"\b(phone|smartphone|tablet|laptop|screen|monitor)\b|手机|屏幕|平板|电脑",
        f"{scene.get('scene_prompt_en', '')} {scene.get('story', '')}", re.IGNORECASE,
    ))


def long_layout(sb):
    value = sb.get("long_layout") or {}
    merged = {
        "template_id": "cards",
        "gap": 60,
        "gaps": {},
        "title": "",
        "subtitle": "",
        "footer": "",
        "footer_blocks": [],
        "accent": "",
        "background_color": "",
        "background_opacity": 1,
        "title_top": 48,
        "title_bottom": 32,
        "margin_top_cm": 0,
        "margin_bottom_cm": 0,
        "print_width_cm": 20,
        "title_line_gap": 18,
        "letter_spacing": 0,
        "body_line_gap": 14,
        "title_style": "plain",
        "title_art_style": "plain",
        "font_size": 58,
        "align": "center",
        "title_font_id": None,
        "body_font_id": None,
        "title_image_asset": None,
        "stickers": [],
        "heading": {"style": "plain", "font_size": 30, "align": "left"},
        "heading_overrides": {},
        **value,
    }
    if "title_style" not in value and "title_art_style" in value:
        merged["title_style"] = value["title_art_style"]
    if "title_art_style" not in value:
        merged["title_art_style"] = merged["title_style"]
    return merged


def validate_long_layout(value, scene_ids):
    if (
        not isinstance(value, dict)
        or value.get("template_id", "cards") not in TEMPLATES
    ):
        raise ValueError("请选择有效的长图模板")
    if not isinstance(value.get("gaps", {}), dict):
        raise ValueError("单独间距必须以分镜编号为键")
    for gap in [value.get("gap", 60), *value.get("gaps", {}).values()]:
        if not isinstance(gap, (int, float)) or not 0 <= gap <= 400:
            raise ValueError("格间距需在 0–400 像素之间")
    if any(k not in scene_ids for k in value.get("gaps", {})):
        raise ValueError("单独间距引用了不存在的格子")
    for key, label, default, minimum, maximum in (
        ("margin_top_cm", "顶部外侧留白", 0, 0, 20),
        ("margin_bottom_cm", "底部外侧留白", 0, 0, 20),
        ("print_width_cm", "成品宽度", 20, 5, 100),
    ):
        number = value.get(key, default)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValueError(f"{label}需在 {minimum}–{maximum} 厘米之间")
    overrides = value.get("heading_overrides", {})
    if not isinstance(overrides, dict) or any(sid not in scene_ids for sid in overrides):
        raise ValueError("小标题设置引用了不存在的分镜")
    for heading in [value.get("heading", {}), *overrides.values()]:
        if not isinstance(heading, dict) or heading.get("style", "plain") not in HEADING_STYLES:
            raise ValueError("请选择有效的小标题样式")
        size = heading.get("font_size", 30)
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not 18 <= size <= 72:
            raise ValueError("小标题字号需在 18–72 之间")
        if heading.get("align", "left") not in {"left", "center", "right"}:
            raise ValueError("小标题对齐方式无效")
        for key in ("fill", "text_color"):
            if heading.get(key) is not None and (not isinstance(heading[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", heading[key])):
                raise ValueError("小标题颜色必须是六位十六进制颜色")
        if "text" in heading and (not isinstance(heading["text"], str) or len(heading["text"]) > 300):
            raise ValueError("小标题文字最多 300 字")
    if not isinstance(value.get("accent", ""), str) or (
        value.get("accent") and not re.fullmatch(r"#[0-9a-fA-F]{6}", value["accent"])
    ):
        raise ValueError("主题色必须是六位十六进制颜色")
    color = value.get("background_color", "")
    if not isinstance(color, str) or (color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
        raise ValueError("背景底色必须是六位十六进制颜色")
    opacity = value.get("background_opacity", 1)
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not math.isfinite(opacity) or not 0 <= opacity <= 1:
        raise ValueError("背景不透明度需在 0–1 之间")
    for key, limit in {
        "title_top": 400,
        "title_bottom": 300,
        "title_line_gap": 100,
        "letter_spacing": 20,
        "body_line_gap": 80,
    }.items():
        v = value.get(key, 0)
        if (
            not isinstance(v, (int, float))
            or isinstance(v, bool)
            or not math.isfinite(v)
            or not 0 <= v <= limit
        ):
            raise ValueError(f"{key} 需在 0–{limit} 像素之间")
    for key in ("title", "subtitle", "footer"):
        if not isinstance(value.get(key, ""), str) or len(value.get(key, "")) > 300:
            raise ValueError("标题、副标题和结尾文字最多 300 字")
    blocks = value.get("footer_blocks", [])
    if not isinstance(blocks, list) or len(blocks) > 12:
        raise ValueError("结尾最多添加 12 个文字或图片内容块")
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in {"text", "image"}:
            raise ValueError("结尾内容必须是文字或图片")
        if block.get("align", "center") not in {"left", "center", "right"}:
            raise ValueError("结尾内容对齐方式无效")
        if "gap_before_cm" in block:
            gap = block["gap_before_cm"]
            if isinstance(gap, bool) or not isinstance(gap, (int, float)) or not math.isfinite(gap) or not 0 <= gap <= 20:
                raise ValueError("结尾内容上方间距需在 0–20 厘米之间")
        if block["type"] == "text":
            if not isinstance(block.get("text", ""), str) or len(block.get("text", "")) > 1000:
                raise ValueError("每个结尾文字框最多 1000 字")
            size = block.get("font_size", 32)
            if isinstance(size, bool) or not isinstance(size, (int, float)) or not 18 <= size <= 72:
                raise ValueError("结尾文字字号需在 18–72 之间")
        else:
            store.valid_id(block.get("asset_id"))
            width = block.get("width", 800)
            if isinstance(width, bool) or not isinstance(width, (int, float)) or not 160 <= width <= 960:
                raise ValueError("结尾图片宽度需在 160–960 像素之间")
    title_style = value.get("title_style") or value.get("title_art_style", "plain")
    if title_style not in {"plain", "outline", "shadow", "raised"}:
        raise ValueError("标题艺术字样式无效")
    if value.get("align", "center") not in {"left", "center", "right"}:
        raise ValueError("标题对齐方式无效")
    font_size = value.get("font_size", 58)
    if (
        not isinstance(font_size, (int, float))
        or isinstance(font_size, bool)
        or not math.isfinite(font_size)
        or not 12 <= font_size <= 120
    ):
        raise ValueError("标题字号需在 12–120 之间")
    for key in ("title_font_id", "body_font_id"):
        font_id = value.get(key)
        if font_id is not None and font_id not in FONT_IDS:
            raise ValueError(f"{key} 不是有效的字体槽位")
    for key in ("title_image_asset",):
        asset_id = value.get(key)
        if asset_id is not None:
            if not isinstance(asset_id, str):
                raise ValueError(f"{key} 必须是 asset_id")
            store.valid_id(asset_id)
    stickers = value.get("stickers", [])
    if not isinstance(stickers, list) or len(stickers) > 50:
        raise ValueError("长图最多添加 50 个贴纸")
    for i, sticker in enumerate(stickers):
        if not isinstance(sticker, dict) or not isinstance(sticker.get("asset_id"), str):
            raise ValueError(f"stickers[{i}] 缺少 asset_id")
        store.valid_id(sticker["asset_id"])
        try:
            validate_transform(sticker, label=f"stickers[{i}]")
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
