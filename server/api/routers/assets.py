"""Project image/font uploads and scene-local reference collections."""

from __future__ import annotations

import urllib.parse
import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from server import store
from server.api import tasks
from server.api.deps import get_owned_project
from server.core.security import verify_token
from server.services import assets
from server.services import image_gen

router = APIRouter(prefix="/projects", tags=["assets"])


def _editable(project_id: str):
    if tasks.active_for_project(project_id):
        raise HTTPException(409, "生成任务运行中，请完成后再编辑")


def _asset_url(project_id: str, record: dict) -> str:
    quoted_pid = urllib.parse.quote(project_id)
    quoted = "/".join(urllib.parse.quote(part) for part in record["path"].split("/"))
    revision = (store.project_dir(project_id) / record["path"]).stat().st_mtime_ns
    return f"/api/files/{quoted_pid}/{quoted}?v={revision}"


def _asset_payload(project_id: str, record: dict) -> dict:
    return {
        **record,
        "name": record.get("filename", ""),
        "url": _asset_url(project_id, record),
    }


class AssetUploadIn(BaseModel):
    # The frontend already has a readImage helper, so JSON base64 avoids a
    # second multipart upload path and is shared by stickers and references.
    name: str = Field(default="image.png", max_length=160)
    image_data: str = Field(max_length=12_000_000)
    kind: str = Field(default="sticker", max_length=40)
    scene_id: str | None = None


class FontUploadIn(BaseModel):
    name: str = Field(default="font.ttf", max_length=160)
    font_data: str | None = Field(default=None, max_length=45_000_000)
    image_data: str | None = Field(default=None, max_length=45_000_000)


class AssetGenerateIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=2)
    size: str = Field(default="1536x1024", pattern="^(1024x1024|1536x1024|1024x1536)$")
    background: str = Field(default="auto", pattern="^(auto|transparent)$")


@router.post("/{pid}/assets/generate", status_code=202)
def generate_asset(
    body: AssetGenerateIn,
    pid: str = Depends(get_owned_project),
    people_id: int = Depends(verify_token),
):
    _editable(pid)
    store.project_dir(pid)
    if not body.prompt.strip():
        raise HTTPException(422, "请填写图片生成要求")
    # 余额闸门：AI 素材生成也消耗生图额度
    from server.services import billing
    if not billing.check_balance(people_id, min_points=1.0):
        raise HTTPException(
            402, {"code": "INSUFFICIENT_POINTS", "message": "积分不足，请联系管理员充值"}
        )
    try:
        references = [assets.asset_path(pid, asset_id) for asset_id in body.reference_asset_ids]
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, "参考图片不存在，请重新上传") from exc
    def run():
        print(f"开始生成结尾图片（{len(references)} 张参考图）……")
        prompt = body.prompt.strip()
        if references:
            prompt = "Use the attached reference images in their supplied order (image 1, image 2). Preserve the identity and recognizable appearance of referenced characters as requested.\n" + prompt
        if body.background == "transparent":
            prompt += "\nReturn a PNG with true alpha transparency outside the subjects; do not paint a checkerboard background."
        temporary = store.project_dir(pid) / "output" / f"generated-{uuid.uuid4().hex}.png"
        try:
            if references:
                image_gen.edit(prompt, references, temporary, size=body.size,
                               allow_reference_fallback=False, background=body.background, request_timeout=240)
            else:
                image_gen.generate(prompt, temporary, size=body.size, background=body.background, request_timeout=240)
            print("图片已生成，正在保存素材……")
            record = assets.create_asset(pid, "data:image/png;base64," + base64.b64encode(temporary.read_bytes()).decode(),
                                         kind="image", filename="AI生成结尾图片.png",
                                         metadata={"prompt":body.prompt, "reference_asset_ids":body.reference_asset_ids})
            print("图片已保存，可以插入结尾。")
            return {"asset": _asset_payload(pid, record)}
        finally:
            temporary.unlink(missing_ok=True)
    task = tasks.submit("generate_asset", pid, body.model_dump(), run, people_id=people_id)
    return {"task_id": task.task_id}


class SceneReferenceIn(BaseModel):
    asset_id: str
    mode: str = Field(default="append", pattern="^(append|replace_character)$")
    replace_character_id: str | None = None


class SceneReferencesIn(BaseModel):
    references: list[SceneReferenceIn] = Field(default_factory=list, max_length=20)


def _scene(project_id: str, scene_id: str) -> tuple[dict, dict]:
    store.valid_id(scene_id)
    sb = store.load_storyboard(project_id)
    scene = next((item for item in sb.get("scenes", []) if item.get("scene_id") == scene_id), None)
    if scene is None:
        raise HTTPException(404, f"故事表里没有 {scene_id}")
    return sb, scene


def _asset_usage(project_id: str, asset_id: str) -> list[str]:
    """Find layout references before allowing a destructive library delete."""
    sb = store.load_storyboard(project_id)
    usage = []
    layout = sb.get("long_layout") or {}
    if layout.get("title_image_asset") == asset_id:
        usage.append("long_layout.title_image_asset")
    if any(item.get("asset_id") == asset_id for item in layout.get("stickers", [])):
        usage.append("long_layout.stickers")
    if any(item.get("asset_id") == asset_id for item in layout.get("footer_blocks", [])):
        usage.append("long_layout.footer_blocks")
    for scene in sb.get("scenes", []):
        sid = scene.get("scene_id")
        if any(item.get("asset_id") == asset_id for item in scene.get("reference_assets", [])):
            usage.append(f"{sid}.reference_assets")
        meta = store.load_scene_meta(project_id, sid) or {}
        if any(item.get("asset_id") == asset_id for item in meta.get("overlays", [])):
            usage.append(f"{sid}.overlays")
    return usage


@router.get("/{pid}/assets")
def list_assets(pid: str = Depends(get_owned_project), kind: str | None = None):
    store.project_dir(pid)
    try:
        records = assets.project_assets(pid, kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "assets": [_asset_payload(pid, record) for record in records],
        "fonts": assets.project_fonts(pid),
    }


@router.post("/{pid}/assets", status_code=201)
def upload_asset(body: AssetUploadIn, pid: str = Depends(get_owned_project)):
    _editable(pid)
    store.project_dir(pid)
    if body.scene_id is not None:
        _scene(pid, body.scene_id)
    try:
        record = assets.create_asset(
            pid,
            body.image_data,
            kind=body.kind,
            filename=body.name,
            scene_id=body.scene_id,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc
    payload = _asset_payload(pid, record)
    # Keep both shapes while the editor migrates: new clients can use
    # ``asset`` while simple upload forms can read asset_id/url directly.
    return {"asset": payload, **payload}


@router.delete("/{pid}/assets/{asset_id}")
def remove_asset(asset_id: str, pid: str = Depends(get_owned_project)):
    _editable(pid)
    store.project_dir(pid)
    usage = _asset_usage(pid, asset_id)
    if usage:
        raise HTTPException(409, "素材仍被布局引用，不能删除：" + ", ".join(usage))
    try:
        assets.delete_asset(pid, asset_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True, "asset_id": asset_id}


@router.get("/{pid}/fonts")
def list_fonts(pid: str = Depends(get_owned_project)):
    store.project_dir(pid)
    return {"fonts": assets.project_fonts(pid)}


@router.post("/{pid}/fonts/{font_id}", status_code=201)
def upload_font(font_id: str, body: FontUploadIn, pid: str = Depends(get_owned_project)):
    _editable(pid)
    store.project_dir(pid)
    data = body.font_data or body.image_data
    if not data:
        raise HTTPException(422, "请上传字体文件")
    try:
        record = assets.save_font(pid, font_id, data, body.name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"font": {**next(item for item in assets.project_fonts(pid) if item["id"] == font_id), "installed": record}}


@router.get("/{pid}/fonts/{font_id}/file")
def get_font_file(font_id: str, pid: str = Depends(get_owned_project)):
    store.project_dir(pid)
    try:
        path = assets.font_path(pid, font_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if path is None:
        raise HTTPException(404, "字体尚未导入")
    media_type = {".ttf": "font/ttf", ".otf": "font/otf", ".ttc": "font/collection"}[path.suffix.lower()]
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-cache"})


@router.get("/{pid}/scenes/{scene_id}/references")
def list_scene_references(scene_id: str, pid: str = Depends(get_owned_project)):
    _, scene = _scene(pid, scene_id)
    result = []
    for item in scene.get("reference_assets", []):
        try:
            record = assets.asset_record(pid, item["asset_id"])
        except (ValueError, FileNotFoundError):
            continue
        result.append({**item, "asset": _asset_payload(pid, record)})
    return {"scene_id": scene_id, "references": result}


@router.put("/{pid}/scenes/{scene_id}/references")
def update_scene_references(scene_id: str, body: SceneReferencesIn, pid: str = Depends(get_owned_project)):
    _editable(pid)
    sb, scene = _scene(pid, scene_id)
    character_ids = set(scene.get("characters", []))
    seen = set()
    saved = []
    for i, item in enumerate(body.references):
        try:
            record = assets.asset_record(pid, item.asset_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(422, f"references[{i}] 的素材不存在") from exc
        if item.asset_id in seen:
            raise HTTPException(422, "场景参考图不能重复")
        seen.add(item.asset_id)
        if item.mode == "replace_character":
            if item.replace_character_id not in character_ids:
                raise HTTPException(422, "replace_character_id 必须是本格出场角色")
        if record.get("kind") not in {"scene_reference", "image", "sticker"}:
            raise HTTPException(422, "该素材类型不能作为场景参考图")
        saved.append(
            {
                "asset_id": item.asset_id,
                "mode": item.mode,
                **({"replace_character_id": item.replace_character_id} if item.mode == "replace_character" else {}),
            }
        )
    scene["reference_assets"] = saved
    # This changes the next generation inputs.  The already-rendered panel is
    # still valid and remains editable, so it must not be marked render_stale.
    scene["reference_stale"] = True
    meta = store.load_scene_meta(pid, scene_id) or {"scene_id": scene_id}
    meta["status"] = "draft"
    store.save_storyboard(pid, sb)
    store.save_scene_meta(pid, scene_id, meta)
    return list_scene_references(scene_id, pid)


@router.post("/{pid}/scenes/{scene_id}/references", status_code=201)
def upload_scene_reference(scene_id: str, body: AssetUploadIn, pid: str = Depends(get_owned_project)):
    """Convenience endpoint: upload and append one scene-local reference."""
    _editable(pid)
    _scene(pid, scene_id)
    record = upload_asset(
        body.model_copy(update={"kind": "scene_reference", "scene_id": scene_id}),
        pid=pid,
    )["asset"]
    current = list_scene_references(scene_id, pid=pid)["references"]
    refs = [
        {
            "asset_id": item["asset_id"],
            "mode": item.get("mode", "append"),
            **({"replace_character_id": item["replace_character_id"]} if item.get("replace_character_id") else {}),
        }
        for item in current
    ]
    refs.append({"asset_id": record["asset_id"], "mode": "append"})
    return update_scene_references(scene_id, SceneReferencesIn(references=refs), pid=pid)
