# -*- coding: utf-8 -*-
"""项目持久化：projects/{id}/ 目录读写 + 线程锁 + 场景版本池。

目录结构：
    projects/{project_id}/
        storyboard.json           故事表（含 style/characters/props/scenes，场景上有 stale 标记）
        characters/{cid}.png      人物标准照
        props/{pid}.png           道具标准照
        assets/{asset_id}.png     编辑器上传的图片素材
        assets.json               素材注册表（asset_id → 安全相对路径）
        fonts/{font_id}.ttf       项目字体槽位
        versions/{sid}_v{n}.png   场景原图版本池（重跑不覆盖）
        scenes/{sid}.json         排版表 + active_version + versions 列表
        screens/{sid}_screen.png  手机屏幕特写素材
        output/{sid}.png          合成后的单格
        output/长图.png            最终成品
"""

import json
import re
import threading
import time
import uuid
from pathlib import Path

from server.config import PROJECTS_DIR

# 每个项目一把锁，防止并发读写 JSON 互相踩
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(project_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(project_id, threading.Lock())


def new_project_id() -> str:
    return time.strftime("comic_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]


def valid_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("编号只能包含字母、数字、下划线和连字符")
    return value


def project_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / valid_id(project_id)
    if not d.is_dir():
        raise FileNotFoundError(f"项目不存在：{project_id}（{d}）")
    return d


def init_dirs(project_id: str) -> Path:
    d = PROJECTS_DIR / valid_id(project_id)
    for sub in (
        "characters",
        "props",
        "assets",
        "fonts",
        "versions",
        "scenes",
        "screens",
        "foreground",
        "output",
    ):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def list_projects() -> list[str]:
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())


# ---------- JSON 读写 ----------


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def load_assets(project_id: str) -> dict:
    """Read the project asset registry; old projects start with an empty one."""
    path = project_dir(project_id) / "assets.json"
    if not path.exists():
        return {"assets": {}}
    value = _read_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("assets", {}), dict):
        raise ValueError("assets.json 格式无效")
    return value


def save_assets(project_id: str, assets: dict):
    if not isinstance(assets, dict) or not isinstance(assets.get("assets", {}), dict):
        raise ValueError("素材注册表格式无效")
    with _lock(project_id):
        _write_json(project_dir(project_id) / "assets.json", assets)


def load_storyboard(project_id: str) -> dict:
    with _lock(project_id):
        return _read_json(project_dir(project_id) / "storyboard.json")


def save_storyboard(project_id: str, sb: dict):
    with _lock(project_id):
        _write_json(project_dir(project_id) / "storyboard.json", sb)


def load_scene_meta(project_id: str, scene_id: str) -> dict | None:
    valid_id(scene_id)
    path = project_dir(project_id) / "scenes" / f"{scene_id}.json"
    if not path.exists():
        return None
    with _lock(project_id):
        return _read_json(path)


def save_scene_meta(project_id: str, scene_id: str, meta: dict):
    valid_id(scene_id)
    with _lock(project_id):
        _write_json(project_dir(project_id) / "scenes" / f"{scene_id}.json", meta)


# ---------- 场景原图版本池 ----------


def _version_of(path: Path) -> int:
    m = re.search(r"_v(\d+)\.png$", path.name)
    return int(m.group(1)) if m else 0


def scene_versions(project_id: str, scene_id: str) -> list[int]:
    """该格已有的版本号列表（升序）。"""
    valid_id(scene_id)
    vdir = project_dir(project_id) / "versions"
    return sorted(_version_of(p) for p in vdir.glob(f"{scene_id}_v*.png"))


def version_path(project_id: str, scene_id: str, version: int) -> Path:
    valid_id(scene_id)
    return project_dir(project_id) / "versions" / f"{scene_id}_v{version}.png"


def active_raw_path(project_id: str, scene_id: str) -> Path | None:
    """当前生效的场景原图路径；没有版本时返回 None。"""
    meta = load_scene_meta(project_id, scene_id)
    if meta and meta.get("active_version"):
        base = project_dir(project_id).resolve()
        p = (base / meta["active_version"]).resolve()
        if not p.is_relative_to(base):
            raise ValueError("素材路径必须在当前项目中")
        if p.exists():
            return p
    versions = scene_versions(project_id, scene_id)
    return version_path(project_id, scene_id, versions[-1]) if versions else None


def register_version(project_id: str, scene_id: str, version: int):
    """把新版本写进排版表的版本列表，并把 active_version 指向它。"""
    meta = load_scene_meta(project_id, scene_id) or {"scene_id": scene_id}
    rel = f"versions/{scene_id}_v{version}.png"
    versions = meta.setdefault("versions", [])
    if rel not in versions:
        versions.append(rel)
    meta["active_version"] = rel
    save_scene_meta(project_id, scene_id, meta)


def rollback(project_id: str, scene_id: str, version: int) -> Path:
    """把 active_version 回滚到指定版本，返回原图路径。"""
    p = version_path(project_id, scene_id, version)
    if not p.exists():
        raise FileNotFoundError(
            f"{scene_id} 没有 v{version}（现有版本：{scene_versions(project_id, scene_id)}）"
        )
    meta = load_scene_meta(project_id, scene_id) or {"scene_id": scene_id}
    meta["active_version"] = f"versions/{scene_id}_v{version}.png"
    save_scene_meta(project_id, scene_id, meta)
    return p


# ---------- stale 传播 ----------


def mark_scenes_stale(project_id: str, character_id: str) -> list[str]:
    """人物标准照重画后，所有引用该人物的场景标 stale。返回被标记的 scene_id 列表。"""
    sb = load_storyboard(project_id)
    marked = []
    for scene in sb.get("scenes", []):
        if character_id in scene.get("characters", []):
            scene["stale"] = True
            marked.append(scene["scene_id"])
            # 同步标到排版表上
            meta = load_scene_meta(project_id, scene["scene_id"])
            if meta:
                meta["stale"] = True
                meta["status"] = "draft"
                save_scene_meta(project_id, scene["scene_id"], meta)
    if marked:
        save_storyboard(project_id, sb)
    return marked


def clear_scene_stale(project_id: str, scene_id: str):
    sb = load_storyboard(project_id)
    changed = False
    for scene in sb.get("scenes", []):
        if scene["scene_id"] == scene_id and scene.get("stale"):
            scene["stale"] = False
            changed = True
    if changed:
        save_storyboard(project_id, sb)
    meta = load_scene_meta(project_id, scene_id)
    if meta and meta.get("stale"):
        meta["stale"] = False
        save_scene_meta(project_id, scene_id, meta)


def stale_scenes(sb: dict) -> list[str]:
    return [s["scene_id"] for s in sb.get("scenes", []) if s.get("stale")]
