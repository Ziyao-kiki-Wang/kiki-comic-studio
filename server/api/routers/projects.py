# -*- coding: utf-8 -*-
"""项目管理：列表 / 创建（后台写故事表）/ 全量详情 / 更新故事表。"""

import json
import urllib.parse
import io
import math
import re
import copy

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from server import store
from server.api import tasks
from server.api.deps import get_owned_project
from server.core.security import verify_token
from server.db import people_repository
from server.config import PROJECTS_DIR
from server.core import story, compose, scenes as scene_engine
from server.core.asset_render import validate_transform
from server.core.studio import (
    CATALOG,
    BUBBLES,
    background_mode,
    screen_enabled,
    long_layout,
    validate_long_layout,
    FONT_IDS,
)
from server.services.uploads import decode_image, save_reference
from server.services import assets

router = APIRouter(prefix="/projects", tags=["projects"])


def _file_url(pid: str, relpath: str) -> str | None:
    """项目内文件存在则返回 /api/files/ URL（逐段 quote，中文名安全）。"""
    if not (PROJECTS_DIR / pid / relpath).is_file():
        return None
    quoted = "/".join(urllib.parse.quote(seg) for seg in relpath.split("/"))
    revision = (PROJECTS_DIR / pid / relpath).stat().st_mtime_ns
    return f"/api/files/{urllib.parse.quote(pid)}/{quoted}?v={revision}"


def _asset_url(pid: str, asset_id: str) -> str | None:
    try:
        record = assets.asset_record(pid, asset_id)
    except (ValueError, FileNotFoundError):
        return None
    return _file_url(pid, record["path"])


def _editable(pid):
    if tasks.active_for_project(pid):
        raise HTTPException(409, "生成任务运行中，请完成后再编辑")


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default="主人公", max_length=150)
    description: str = Field(default="", max_length=1200)
    image_data: str = Field(max_length=11200000)


def _project_status(pid: str, sb: dict) -> tuple[int, str]:
    """项目级审核状态：全部格 approved 才算 approved。返回 (已通过数, 状态)。"""
    scenes = sb.get("scenes", [])
    approved = 0
    for s in scenes:
        meta = store.load_scene_meta(pid, s["scene_id"])
        if meta and meta.get("status") == "approved":
            approved += 1
    status = "approved" if scenes and approved == len(scenes) else "draft"
    return approved, status


def _project_summary(pid: str) -> dict:
    d = PROJECTS_DIR / pid
    item = {
        "project_id": pid,
        "title": None,
        "scene_count": 0,
        "stale_scenes": [],
        "approved_count": 0,
        "status": "draft",
        "long_image_stale": False,
    }
    sb_path = d / "storyboard.json"
    if sb_path.exists():
        try:
            sb = store.load_storyboard(pid)
            item["title"] = sb.get("title")
            item["scene_count"] = len(sb.get("scenes", []))
            item["stale_scenes"] = store.stale_scenes(sb)
            item["approved_count"], item["status"] = _project_status(pid, sb)
            item["long_image_stale"] = compose.long_image_stale(pid, sb)
        except (json.JSONDecodeError, OSError):
            item["title"] = "（storyboard.json 损坏）"
    # 更新时间：storyboard 和长图里较新的那个，兜底用目录 mtime
    mtimes = [
        p.stat().st_mtime for p in (sb_path, d / "output" / "长图.png") if p.exists()
    ]
    item["updated_at"] = max(mtimes) if mtimes else d.stat().st_mtime
    return item


@router.get("")
def list_projects(people_id: int = Depends(verify_token)):
    owned = people_repository.list_project_ids_by_owner(people_id)
    return [_project_summary(pid) for pid in owned]


class CreateProjectIn(BaseModel):
    topic: str = Field(min_length=1, max_length=5000)
    scene_count: int = Field(default=5, ge=1, le=20)
    style_id: str = "commercial_comic"
    background_mode: str = Field(default="scene", pattern="^(scene|transparent)$")
    characters: list[CharacterIn] = Field(default_factory=list, max_length=6)


@router.post("", status_code=201)
def create_project(body: CreateProjectIn, people_id: int = Depends(verify_token)):
    try:
        story.load_style(body.style_id)  # 提前校验风格存在
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        uploaded = [(c, decode_image(c.image_data)) for c in body.characters]
    except ValueError as e:
        raise HTTPException(422, str(e))
    pid = store.new_project_id()
    store.init_dirs(pid)
    # 归属先落库：后续任何 pid 路由都要走 get_owned_project 校验
    people_repository.create_project_ownership(pid, people_id, title=body.topic[:255])
    provided = []
    for i, (c, png) in enumerate(uploaded, 1):
        cid = f"user_{i:02d}"
        save_reference(pid, cid, png)
        provided.append(
            {
                "character_id": cid,
                "name": c.name,
                "role": c.role,
                "description": c.description,
                "reference_source": "upload",
            }
        )
    t = tasks.submit(
        "create_project",
        pid,
        {
            "topic": body.topic,
            "scene_count": body.scene_count,
            "style_id": body.style_id,
        },
        lambda: story.create_storyboard(
            pid,
            body.topic,
            body.scene_count,
            body.style_id,
            force=True,
            provided_characters=provided,
            background_mode=body.background_mode,
        ),
        people_id=people_id,
    )
    return {"project_id": pid, "task_id": t.task_id}


@router.get("/{pid}")
def project_detail(pid: str = Depends(get_owned_project)):
    try:
        store.project_dir(pid)
    except FileNotFoundError:
        raise HTTPException(404, f"项目不存在：{pid}")
    try:
        sb = store.load_storyboard(pid)
    except FileNotFoundError:
        raise HTTPException(
            409, "故事表还没生成好（创建任务可能仍在跑），请轮询任务状态"
        )

    scenes = []
    for s in sb.get("scenes", []):
        s["screen_enabled"] = screen_enabled(s)
        sid = s["scene_id"]
        meta = store.load_scene_meta(pid, sid)
        fg = scene_engine.foreground_path(pid, sid)
        foreground_url = _file_url(pid, fg.relative_to(store.project_dir(pid)).as_posix()) if fg else None
        scenes.append(
            {
                "scene_id": sid,
                "generation_prompt": scene_engine._build_prompt(sb, s),
                "last_generation": (meta or {})
                .get("generation_history", {})
                .get(
                    ((meta or {}).get("active_version") or "")
                    .rsplit("_", 1)[-1]
                    .removesuffix(".png")
                ),
                "layout": meta,
                "status": (meta or {}).get("status", "draft"),
                "composite_url": _file_url(pid, f"output/{sid}.png"),
                "raw_url": _file_url(pid, meta["active_version"])
                if meta and meta.get("active_version")
                else None,
                "screen_url": _file_url(pid, f"screens/{sid}_screen.png"),
                "foreground_url": foreground_url,
                "background_mode": background_mode(sb, s),
                "panel_url": _file_url(pid, f"output/{sid}_panel.png"),
                "render_stale": (meta or {}).get("render_stale", False),
                "reference_stale": s.get("reference_stale", False),
                "reference_assets": [
                    {
                        **item,
                        "url": _asset_url(pid, item.get("asset_id", "")),
                    }
                    for item in s.get("reference_assets", [])
                ],
            }
        )
    return {
        "storyboard": sb,
        "scenes": scenes,
        "character_urls": {
            c["character_id"]: _file_url(pid, f"characters/{c['character_id']}.png")
            for c in sb.get("characters", [])
        },
        "character_rgba_urls": {
            c["character_id"]: _file_url(
                pid, f"characters/{c['character_id']}_rgba.png"
            )
            for c in sb.get("characters", [])
        },
        "prop_urls": {
            p["prop_id"]: _file_url(pid, f"props/{p['prop_id']}.png")
            for p in sb.get("props", [])
        },
        "long_image_url": _file_url(pid, "output/长图.png"),
        "long_image_stale": compose.long_image_stale(pid, sb),
        "long_layout": long_layout(sb),
        "assets": [
            {**record, "url": _asset_url(pid, record["asset_id"])}
            for record in assets.project_assets(pid)
        ],
        "fonts": assets.project_fonts(pid),
        "active_task": tasks.active_for_project(pid).to_dict()
        if tasks.active_for_project(pid)
        else None,
        **_project_summary(pid),
    }


def _validate_storyboard(sb: dict):
    """基本结构校验：防止把残缺 JSON 落盘后引擎崩在奇怪的地方。"""
    if not isinstance(sb, dict):
        raise HTTPException(422, "storyboard 必须是 JSON 对象")
    if not isinstance(sb.get("scenes"), list) or not sb["scenes"]:
        raise HTTPException(422, "缺少 scenes 列表（或为空）")
    seen = set()
    for i, s in enumerate(sb["scenes"]):
        if not isinstance(s, dict) or not isinstance(s.get("scene_id"), str):
            raise HTTPException(422, f"scenes[{i}] 缺少 scene_id")
        if s["scene_id"] in seen:
            raise HTTPException(422, f"scene_id 重复：{s['scene_id']}")
        seen.add(s["scene_id"])
        store.valid_id(s["scene_id"])
        for font_key in ("bubble_font_id", "caption_font_id"):
            if s.get(font_key) is not None and s.get(font_key) not in FONT_IDS:
                raise HTTPException(422, f"{font_key} 字体槽位无效")
        if s.get("screen_mode", "integrated") not in ("integrated", "inset"):
            raise HTTPException(422, "未知手机构图模式")
        if "screen_enabled" in s and not isinstance(s["screen_enabled"], bool):
            raise HTTPException(422, "手机与屏幕开关必须为布尔值")
        inset = s.get("screen_inset")
        if inset is not None and (not isinstance(inset, dict) or not isinstance(inset.get("screen_prompt_en", ""), str)):
            raise HTTPException(422, "屏幕描述格式无效")
        if isinstance(inset, dict) and len(inset.get("screen_prompt_en", "")) > 2000:
            raise HTTPException(422, "屏幕描述最多 2000 字")
        if not isinstance(s.get("scene_prompt_en"), str) or not s["scene_prompt_en"].strip():
            raise HTTPException(422, f"第 {i + 1} 格：画面描述不能为空")
        if not isinstance(s.get("characters"), list) or any(
            not isinstance(cid, str) for cid in s.get("characters", [])
        ):
            raise HTTPException(422, f"第 {i + 1} 格：出场人物格式无效")
        if not isinstance(s.get("props", []), list) or any(
            not isinstance(p, str) for p in s.get("props", [])
        ):
            raise HTTPException(422, f"第 {i + 1} 格：出场道具格式无效")
        if screen_enabled(s) and s.get("screen_mode") == "inset" and not (inset or {}).get("screen_prompt_en", "").strip():
            raise HTTPException(422, f"第 {i + 1} 格：请填写屏幕特写要显示的内容")
        if s.get("background_mode") not in (None, "scene", "transparent"):
            raise HTTPException(422, "未知背景模式")
        if len(s.get("dialogues", [])) > 20:
            raise HTTPException(422, "每格最多 20 条对话")
        references = s.get("reference_assets", [])
        if not isinstance(references, list) or len(references) > 20:
            raise HTTPException(422, "每格最多 20 张专属参考图")
        for j, ref in enumerate(references):
            if not isinstance(ref, dict) or not isinstance(ref.get("asset_id"), str):
                raise HTTPException(422, f"scenes[{i}].reference_assets[{j}] 缺少 asset_id")
            store.valid_id(ref["asset_id"])
            if ref.get("mode", "append") not in ("append", "replace_character"):
                raise HTTPException(422, "场景参考图模式无效")
            if ref.get("mode", "append") == "replace_character" and ref.get(
                "replace_character_id"
            ) not in set(s.get("characters", [])):
                raise HTTPException(422, "替换参考图必须对应本格出场角色")
        for j, d in enumerate(s.get("dialogues", [])):
            if not isinstance(d, dict) or not isinstance(d.get("text"), str):
                raise HTTPException(422, f"scenes[{i}].dialogues[{j}] 缺少 text")
            if len(d["text"]) > 500:
                raise HTTPException(422, "每条台词最多 500 字")
    for i, c in enumerate(sb.get("characters", [])):
        if not isinstance(c, dict) or not isinstance(c.get("character_id"), str):
            raise HTTPException(422, f"characters[{i}] 缺少 character_id")
        store.valid_id(c["character_id"])
    if sb.get("background_mode", "scene") not in ("scene", "transparent"):
        raise HTTPException(422, "未知背景模式")
    validate_long_layout(sb.get("long_layout") or {}, seen)


def _validate_layout_assets(pid: str, sb: dict):
    layout = sb.get("long_layout") or {}
    ids = []
    if layout.get("title_image_asset"):
        ids.append((layout["title_image_asset"], "标题图片"))
    ids.extend((item.get("asset_id"), "结尾图片")
               for item in layout.get("footer_blocks", []) if item.get("type") == "image")
    ids.extend(
        (item.get("asset_id"), f"stickers[{i}]")
        for i, item in enumerate(layout.get("stickers", []))
    )
    for scene in sb.get("scenes", []):
        ids.extend(
            (item.get("asset_id"), f"{scene.get('scene_id')}.reference_assets[{i}]")
            for i, item in enumerate(scene.get("reference_assets", []))
        )
    for asset_id, label in ids:
        try:
            store.valid_id(asset_id)
            assets.asset_record(pid, asset_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(422, f"{label}素材不存在") from exc


@router.put("/{pid}/storyboard")
def update_storyboard(sb: dict = Body(...), pid: str = Depends(get_owned_project)):
    _editable(pid)
    try:
        store.project_dir(pid)
    except FileNotFoundError:
        raise HTTPException(404, f"项目不存在：{pid}")
    _validate_storyboard(sb)
    _validate_layout_assets(pid, sb)
    old = store.load_storyboard(pid)
    sb["project_id"] = pid
    sb["characters_confirmed"] = old.get("characters_confirmed", True)
    protected = {c["character_id"]: c for c in old.get("characters", [])}
    if {c["character_id"] for c in sb.get("characters", [])} != set(protected):
        raise HTTPException(422, "此处只能编辑已有角色，请使用上传入口替换形象")
    for c in sb.get("characters", []):
        c["reference_source"] = protected[c["character_id"]].get(
            "reference_source", "generated"
        )
    changed_characters = {c["character_id"] for c in sb.get("characters", [])
                          if any(c.get(k) != protected[c["character_id"]].get(k)
                                 for k in ("name", "role", "description", "english_desc"))}
    for s in sb["scenes"]:
        previous = next(
            (item for item in old["scenes"] if item["scene_id"] == s["scene_id"]), None
        )
        screen_changed = previous is None or (
            screen_enabled(s) != screen_enabled(previous)
            or (screen_enabled(s) and any(s.get(k) != previous.get(k) for k in ("screen_mode", "screen_inset")))
        )
        story_changed = previous is None or any(
            s.get(k) != previous.get(k)
            for k in ("story", "scene_prompt_en", "characters", "location")
        )
        generation_changed = (previous is None or screen_changed or story_changed
                              or background_mode(sb, s) != background_mode(old, previous)
                              or bool(changed_characters.intersection(s.get("characters", [])))
                              or sb.get("style") != old.get("style"))
        visual_changed = generation_changed or (
            previous is None
            or any(
                s.get(k) != previous.get(k)
                for k in ("dialogues", "caption")
            )
        )
        if visual_changed:
            meta = store.load_scene_meta(pid, s["scene_id"]) or {
                "scene_id": s["scene_id"]
            }
            meta["status"] = "draft"
            meta["render_stale"] = True
            if generation_changed:
                meta["generation_stale"] = True
            if screen_changed:
                meta["screen_content_stale"] = True
                meta["screen_inset_hidden"] = not (screen_enabled(s) and s.get("screen_mode") == "inset")
                if meta["screen_inset_hidden"]:
                    meta.pop("screen_inset", None)
            store.save_scene_meta(pid, s["scene_id"], meta)
    store.save_storyboard(pid, sb)
    return {"ok": True, "scene_count": len(sb["scenes"])}


class LayoutIn(BaseModel):
    """编辑器回写的排版表：气泡数组 + 特写框位置。

    screen_inset 显式传 null 表示删除特写框；字段不出现则保持原值。
    """

    bubbles: list[dict] | None = Field(default=None, max_length=20)
    screen_inset: dict | None = None
    overlays: list[dict] | None = Field(default=None, max_length=50)
    caption: str | None = Field(default=None, max_length=1000)
    caption_layout: dict | None = None
    subject_layout: dict | None = None
    layer_order: list[str] | None = Field(default=None, max_length=150)
    element_groups: list[list[str]] | None = Field(default=None, max_length=20)


def _validate_text_box(box, label, caption=False):
    if not isinstance(box, dict):
        raise HTTPException(422, f"{label} 需要位置与尺寸")
    for key, lo, hi in [("x", -2000, 3000), ("y", -2000, 5000), ("width", 80, 1040), ("rotation", -360, 360)]:
        value = box.get(key, 0 if key == "rotation" else None)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise HTTPException(422, f"{label} 的 {key} 超出范围")
    if caption:
        size = box.get("font_size", 34)
        if not isinstance(size, (int, float)) or not math.isfinite(size) or not 18 <= size <= 72:
            raise HTTPException(422, "旁白字号需在 18–72 之间")
        if box.get("align", "center") not in ("left", "center", "right"):
            raise HTTPException(422, "旁白对齐方式无效")
        if box.get("font_id") is not None and box["font_id"] not in FONT_IDS:
            raise HTTPException(422, "旁白字体无效")


def _validate_bubble(b: dict, i: int):
    if isinstance(b, dict):
        if b.get("bubble_variant", "white") not in ("transparent", "white", "3d"):
            raise HTTPException(422, "气泡版本无效")
        for key in ("flip_x", "flip_y"):
            if key in b and not isinstance(b[key], bool):
                raise HTTPException(422, "翻转选项必须为布尔值")
        if b.get("tail_local") is not None and (not isinstance(b["tail_local"], list) or len(b["tail_local"]) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 10000 for v in b["tail_local"])):
            raise HTTPException(422, "固定尾巴坐标无效")
        from server.services.bubble_assets import asset_path
        try:
            asset_path(b.get("type", "speech"), b.get("bubble_variant", "white"))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    if b.get("text_align", "left") not in ("left", "center", "right"):
        raise HTTPException(422, "文字对齐方式无效")
    if b.get("text_box") is not None:
        _validate_text_box(b["text_box"], "对话文字框")
    for key, lo, hi, default in [("rotation", -360, 360, 0), ("scale_x", 0.1, 4, 1), ("scale_y", 0.1, 4, 1), ("body_height", 40, 5000, 80)]:
        value = b.get(key, default)
        if value is None and key == "body_height":
            value = default
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise HTTPException(422, f"气泡 {key} 超出范围")
    for k in ("x", "y", "width", "font_size"):
        if not isinstance(b.get(k), (int, float)) or not math.isfinite(b[k]):
            raise HTTPException(422, f"bubbles[{i}] 缺少数值字段 {k}")
    if not isinstance(b.get("text"), str):
        raise HTTPException(422, f"bubbles[{i}] 缺少 text")
    if (
        not 160 <= b["width"] <= 1000
        or not 18 <= b["font_size"] <= 72
        or len(b["text"]) > 500
    ):
        raise HTTPException(422, "气泡宽度、字号或台词长度超出范围")
    if b.get("type", "speech") not in BUBBLES or b.get("tail_side", "bottom") not in (
        "top",
        "bottom",
        "left",
        "right",
    ):
        raise HTTPException(422, "气泡样式或尾巴方向无效")
    if b.get("font_id") is not None and b.get("font_id") not in FONT_IDS:
        raise HTTPException(422, "气泡字体槽位无效")
    if b.get("font_family") is not None and b.get("font_family") not in (
        "system",
        *FONT_IDS,
    ):
        raise HTTPException(422, "气泡字体槽位无效")
    for key in ("fill", "stroke", "text_color"):
        if key in b and (
            not isinstance(b[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", b[key])
        ):
            raise HTTPException(422, "气泡颜色必须是六位十六进制颜色")
    sw = b.get("stroke_width", 3)
    if not isinstance(sw, (int, float)) or not math.isfinite(sw) or not 0 <= sw <= 12:
        raise HTTPException(422, "气泡边框粗细需在 0–12 之间")
    pos = b.get("tail_position", 0.25)
    if not isinstance(pos, (int, float)) or not 0.1 <= pos <= 0.9:
        raise HTTPException(422, "尾巴位置需在 10%–90% 之间")
    tip = b.get("tail_tip")
    if tip is not None and (
        not isinstance(tip, dict)
        or any(not isinstance(tip.get(k), (int, float)) for k in ("x", "y"))
    ):
        raise HTTPException(422, "尾巴尖端需包含 x、y 坐标")

    def bounded(v):
        if isinstance(v, (float, int)) and (not math.isfinite(v) or abs(v) > 10000):
            raise HTTPException(422, "气泡坐标超出范围")
        if isinstance(v, dict):
            for value in v.values():
                bounded(value)
        elif isinstance(v, list):
            if len(v) > 512:
                raise HTTPException(422, "气泡几何数据过大")
            for value in v:
                bounded(value)

    bounded(b)
    g = b.get("geometry")
    if g and (
        not isinstance(g, dict)
        or not isinstance(g.get("points"), list)
        or not isinstance(g.get("lines"), list)
    ):
        raise HTTPException(422, "气泡排版数据不完整")
    if g:
        if isinstance(g.get("input"), dict) and g["input"].get("revision") == 3:
            _validate_text_box(g.get("text_box"), "文字排版")
            height = g["text_box"].get("height")
            if not isinstance(height, (int, float)) or not 1 <= height <= 10000:
                raise HTTPException(422, "文字排版高度超出范围")

        def point(value):
            return (
                isinstance(value, list)
                and len(value) == 2
                and all(isinstance(v, (int, float)) for v in value)
            )

        if (
            len(g["points"]) < 3
            or not all(point(p) for p in g["points"])
            or not point(g.get("anchor"))
            or not point(g.get("tip"))
            or not isinstance(g.get("input"), dict)
            or not isinstance(g.get("height"), (int, float))
            or not isinstance(g.get("line_height"), (int, float))
            or not isinstance(g.get("circles"), list)
            or any(
                not isinstance(c, dict)
                or any(not isinstance(c.get(k), (int, float)) for k in ("x", "y", "r"))
                for c in g.get("circles", [])
            )
            or any(
                not isinstance(line, dict)
                or not isinstance(line.get("text"), str)
                or any(not isinstance(line.get(k), (int, float)) for k in ("x", "y"))
                for line in g["lines"]
            )
        ):
            raise HTTPException(422, "气泡排版数据不完整")


def _validate_overlay(project_id: str, overlay: dict, i: int):
    if not isinstance(overlay, dict) or not isinstance(overlay.get("asset_id"), str):
        raise HTTPException(422, f"overlays[{i}] 缺少 asset_id")
    try:
        store.valid_id(overlay["asset_id"])
        assets.asset_record(project_id, overlay["asset_id"])
        validate_transform(overlay, label=f"overlays[{i}]")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/{pid}/scenes/{scene_id}/layout")
def update_layout(scene_id: str, body: LayoutIn, pid: str = Depends(get_owned_project)):
    """保存排版表（合并进现有 scene meta，不覆盖 versions/active_version 等）。"""
    _editable(pid)
    try:
        sb = store.load_storyboard(pid)
    except FileNotFoundError:
        raise HTTPException(404, f"项目或故事表不存在：{pid}")
    if scene_id not in [s["scene_id"] for s in sb.get("scenes", [])]:
        raise HTTPException(404, f"故事表里没有 {scene_id}")

    meta = store.load_scene_meta(pid, scene_id) or {"scene_id": scene_id}
    if "subject_layout" in body.model_fields_set:
        if body.subject_layout is not None:
            for key, low, high in [("x", -2000, 3000), ("y", -2000, 5000), ("width", 50, 3000), ("height", 50, 3000)]:
                value = body.subject_layout.get(key)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                    raise HTTPException(422, f"主体图片的 {key} 超出范围")
            meta["subject_layout"] = body.subject_layout
        else:
            meta.pop("subject_layout", None)
    if body.layer_order is not None:
        if len(set(body.layer_order)) != len(body.layer_order):
            raise HTTPException(422, "图层顺序不能重复")
        meta["layer_order"] = body.layer_order
    if "caption_layout" in body.model_fields_set:
        if body.caption_layout is not None:
            _validate_text_box(body.caption_layout, "旁白", caption=True)
            meta["caption_layout"] = body.caption_layout
        else:
            meta.pop("caption_layout", None)
    if body.bubbles is not None:
        scene = next(s for s in sb["scenes"] if s["scene_id"] == scene_id)
        previous = {d.get("bubble_id", f"b{i + 1:02d}"): d
                    for i, d in enumerate(scene.get("dialogues", []))}
        dialogues, seen = [], set()
        for i, b in enumerate(body.bubbles):
            _validate_bubble(b, i)
            bid = b.get("bubble_id", f"b{i + 1:02d}")
            if not isinstance(bid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", bid) or bid in seen:
                raise HTTPException(422, "文字和气泡的编号必须有效且不能重复")
            for key in ("bubble_visible", "text_visible"):
                if key in b and not isinstance(b[key], bool):
                    raise HTTPException(422, "文字和气泡的显示状态必须为布尔值")
            seen.add(bid)
            b["bubble_id"] = bid
            old = previous.get(bid, {})
            dialogues.append({**old, "bubble_id": bid, "text": b["text"],
                              "speaker": old.get("speaker", b.get("speaker")),
                              "bubble_type": b.get("type", "speech")})
        scene["dialogues"] = dialogues
        meta["bubbles"] = body.bubbles
    members = {key for b in meta.get("bubbles", []) for key, visible in
               [(b["bubble_id"], b.get("bubble_visible", True)),
                ("text:" + b["bubble_id"], b.get("text_visible", True))] if visible}
    if body.element_groups is not None:
        seen = set()
        for group in body.element_groups:
            if not 2 <= len(group) <= 40 or any(key not in members or key in seen for key in group) or len(set(group)) != len(group):
                raise HTTPException(422, "组合需要至少两个不同的文字或气泡，每个元素只能属于一个组合")
            seen.update(group)
        meta["element_groups"] = body.element_groups
    else:
        meta["element_groups"] = [remaining for group in meta.get("element_groups", [])
                                  if len(remaining := [key for key in group if key in members]) >= 2]
    if body.overlays is not None:
        for i, overlay in enumerate(body.overlays):
            _validate_overlay(pid, overlay, i)
        meta["overlays"] = body.overlays
    if "screen_inset" in body.model_fields_set:
        if body.screen_inset is None:
            meta.pop("screen_inset", None)
            meta["screen_inset_hidden"] = True
        else:
            for k in ("x", "y", "width", "height"):
                if (
                    not isinstance(body.screen_inset.get(k), (int, float))
                    or not math.isfinite(body.screen_inset[k])
                    or abs(body.screen_inset[k]) > 10000
                ):
                    raise HTTPException(422, f"screen_inset 缺少数值字段 {k}")
            meta["screen_inset"] = body.screen_inset
            meta["screen_inset_hidden"] = False
            for k in ("width", "height"):
                if not 80 <= body.screen_inset[k] <= 1800:
                    raise HTTPException(422, "特写框尺寸需在 80–1800 像素之间")
    if body.caption is not None:
        next(s for s in sb["scenes"] if s["scene_id"] == scene_id)["caption"] = (
            body.caption
        )
    meta["status"] = "draft"
    meta["render_stale"] = True
    store.save_storyboard(pid, sb)
    store.save_scene_meta(pid, scene_id, meta)
    return {"ok": True, "scene_id": scene_id}


class StatusIn(BaseModel):
    status: str = Field(pattern="^(draft|approved)$")


@router.put("/{pid}/scenes/{scene_id}/status")
def update_scene_status(scene_id: str, body: StatusIn, pid: str = Depends(get_owned_project)):
    """审核状态流：draft → approved（也可取消回 draft）。"""
    _editable(pid)
    try:
        sb = store.load_storyboard(pid)
    except FileNotFoundError:
        raise HTTPException(404, f"项目或故事表不存在：{pid}")
    if scene_id not in [s["scene_id"] for s in sb.get("scenes", [])]:
        raise HTTPException(404, f"故事表里没有 {scene_id}")
    meta = store.load_scene_meta(pid, scene_id) or {"scene_id": scene_id}
    meta["status"] = body.status
    store.save_scene_meta(pid, scene_id, meta)
    approved_count, project_status = _project_status(pid, sb)
    return {
        "ok": True,
        "scene_id": scene_id,
        "status": body.status,
        "approved_count": approved_count,
        "project_status": project_status,
    }


@router.put("/{pid}/characters/{cid}/reference")
def replace_reference(cid: str, body: CharacterIn, pid: str = Depends(get_owned_project)):
    _editable(pid)
    sb = store.load_storyboard(pid)
    ch = next((c for c in sb["characters"] if c["character_id"] == cid), None)
    if ch is None:
        raise HTTPException(404, "角色不存在")
    png = decode_image(body.image_data)
    save_reference(pid, cid, png)
    ch.update(
        {
            "name": body.name,
            "role": body.role,
            "description": body.description,
            "english_desc": body.description
            or "Keep the supplied reference character unchanged.",
            "reference_source": "upload",
        }
    )
    sb["characters_confirmed"] = False
    store.save_storyboard(pid, sb)
    store.mark_scenes_stale(pid, cid)
    return {"ok": True}


@router.post("/{pid}/characters/confirm")
def confirm_characters(pid: str = Depends(get_owned_project)):
    _editable(pid)
    sb = store.load_storyboard(pid)
    if any(
        not (
            store.project_dir(pid) / "characters" / f"{c['character_id']}.png"
        ).exists()
        for c in sb["characters"]
    ):
        raise HTTPException(409, "请先生成或上传全部角色参考图")
    sb["characters_confirmed"] = True
    store.save_storyboard(pid, sb)
    return {"ok": True}


@router.post("/{pid}/long-preview")
def preview_long_image(options: dict = Body(...), pid: str = Depends(get_owned_project)):
    sb = store.load_storyboard(pid)
    validate_long_layout(options, {s["scene_id"] for s in sb["scenes"]})
    _validate_layout_assets(pid, {"long_layout": options})
    picture, layout = compose.render_long_image(pid, sb, options)
    picture.thumbnail((180, 4000) if options.get("thumbnail") else (540, 20000))
    out = io.BytesIO()
    picture.save(out, format="PNG")
    # Expose the per-scene boxes so the workbench can overlay a live editor
    # on the exact panel positions for direct dragging in the preview.
    boxes_json = json.dumps({
        "scenes": layout.get("scenes", []),
        "width": layout.get("width"),
        "height": layout.get("height"),
    }, ensure_ascii=False)
    return Response(
        out.getvalue(), media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Long-Layout": urllib.parse.quote(boxes_json, safe=""),
            "Access-Control-Expose-Headers": "X-Long-Layout",
        },
    )
