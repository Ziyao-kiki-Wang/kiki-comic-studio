# -*- coding: utf-8 -*-
"""生成动作：POST /projects/{pid}/generate 单入口分发，全部走后台任务。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server import cli, store
from server.api import tasks
from server.api.deps import get_owned_project
from server.core.security import verify_token
from server.core import characters, compose, lettering, screens

router = APIRouter(tags=["generate"])

ACTIONS = (
    "run_all",
    "rerun_scene",
    "edit_scene",
    "rollback_scene",
    "regen_character",
    "recompose",
    "recompose_scene",
    "cutout_character",
    "prepare_characters",
    "compose_long",
    "screen_scene",
)


class GenerateIn(BaseModel):
    action: str
    scene_id: str | None = None
    version: int | None = None
    character_id: str | None = None
    instruction: str | None = Field(default=None, max_length=4000)


def _recompose(pid: str):
    """只重新合成 + 拼长图，不调任何画图 API（改了台词/caption 后用）。"""
    sb = store.load_storyboard(pid)
    print("重新合成全部格子（不重画原图）……")
    for scene in sb["scenes"]:
        lettering.letter_scene(pid, sb, scene, force=True)
    compose.make_long_image(pid, sb)


def _build_fn(pid: str, body: GenerateIn):
    sb = store.load_storyboard(pid)
    scene_ids = [s["scene_id"] for s in sb.get("scenes", [])]

    if body.action == "recompose_scene":
        if body.scene_id not in scene_ids:
            raise HTTPException(404, "请指定存在的分镜")
        if store.active_raw_path(pid, body.scene_id) is None:
            raise HTTPException(409, "这一格还没有原图，请先生成画面")
        def recompose_scene():
            current = store.load_storyboard(pid)
            scene = next(s for s in current["scenes"] if s["scene_id"] == body.scene_id)
            lettering.letter_scene(pid, current, scene, force=True)
            ready = all((store.project_dir(pid) / "output" / f"{s['scene_id']}_panel.png").exists()
                        and not (store.load_scene_meta(pid, s["scene_id"]) or {}).get("render_stale") for s in current["scenes"])
            if ready:
                compose.make_long_image(pid, current)
            else:
                print("当前分镜已保存；其余分镜完成后再合成长图。")
        return recompose_scene

    if body.action == "run_all":
        if not sb.get("characters_confirmed", True):
            raise HTTPException(409, "请先确认角色形象，再开始场景生成")
        return lambda: cli.run_pipeline(pid)

    if body.action == "prepare_characters":
        # generate_references 返回 {cid: Path}；dict 会进 t.result 被 json 落盘，
        # 所以把 Path 转成项目相对路径字符串，避免 PosixPath 序列化炸 _save_locked
        def prep():
            refs = characters.generate_references(pid, sb)
            return {"references": {cid: str(p) for cid, p in refs.items()}}
        return prep

    if body.action == "compose_long":
        return lambda: compose.make_long_image(pid, sb)

    if body.action in ("rerun_scene", "edit_scene"):
        if not body.scene_id:
            raise HTTPException(422, "rerun_scene 需要 scene_id")
        if body.scene_id not in scene_ids:
            raise HTTPException(404, f"故事表里没有 {body.scene_id}")
        if body.action == "edit_scene":
            if not body.instruction or not body.instruction.strip():
                raise HTTPException(422, "请填写图片修改要求")
            if store.active_raw_path(pid, body.scene_id) is None:
                raise HTTPException(409, "请先生成这一格，再基于当前图修改")
        return lambda: cli.rerun_scene(
            pid,
            body.scene_id,
            body.instruction.strip() if body.action == "edit_scene" else None,
        )

    if body.action == "screen_scene":
        if not body.scene_id or body.scene_id not in scene_ids:
            raise HTTPException(404, "请指定存在的分镜")
        if not body.instruction or not body.instruction.strip():
            raise HTTPException(422, "请描述屏幕上要显示的内容")
        if store.active_raw_path(pid, body.scene_id) is None:
            raise HTTPException(409, "请先生成这一格画面，再添加屏幕特写")

        def screen_scene():
            current = store.load_storyboard(pid)
            target = next(
                s for s in current["scenes"] if s["scene_id"] == body.scene_id
            )
            target["screen_enabled"] = True
            target["screen_mode"] = "inset"
            target["screen_inset"] = {
                "screen_prompt_en": body.instruction.strip()
            }
            store.save_storyboard(pid, current)
            meta = store.load_scene_meta(pid, body.scene_id) or {
                "scene_id": body.scene_id
            }
            meta["screen_content_stale"] = True
            meta["screen_inset_hidden"] = False
            meta.setdefault(
                "screen_inset",
                {"x": 710, "y": 50, "width": 320, "height": 480},
            )
            meta["render_stale"] = True
            store.save_scene_meta(pid, body.scene_id, meta)
            sb2 = store.load_storyboard(pid)
            screens.generate_screens(pid, sb2, only_scene=body.scene_id)
            scene = next(
                s for s in sb2["scenes"] if s["scene_id"] == body.scene_id
            )
            lettering.letter_scene(pid, sb2, scene, force=True)
            compose.make_long_image(pid, sb2)

        return screen_scene

    if body.action == "rollback_scene":
        if not body.scene_id or body.version is None:
            raise HTTPException(422, "rollback_scene 需要 scene_id 和 version")
        if body.scene_id not in scene_ids:
            raise HTTPException(404, f"故事表里没有 {body.scene_id}")
        if body.version not in store.scene_versions(pid, body.scene_id):
            raise HTTPException(
                404,
                f"{body.scene_id} 没有 v{body.version}"
                f"（现有版本：{store.scene_versions(pid, body.scene_id)}）",
            )
        return lambda: cli.rollback_scene(pid, body.scene_id, body.version)

    if body.action == "regen_character":
        if not body.character_id:
            raise HTTPException(422, "regen_character 需要 character_id")
        if body.character_id not in [
            c["character_id"] for c in sb.get("characters", [])
        ]:
            raise HTTPException(404, f"故事表里没有人物 {body.character_id}")
        return lambda: characters.generate_references(
            pid, sb, only_character=body.character_id
        )

    if body.action == "recompose":
        return lambda: _recompose(pid)

    if body.action == "cutout_character":
        if not body.character_id:
            raise HTTPException(422, "cutout_character 需要 character_id")
        if body.character_id not in [
            c["character_id"] for c in sb.get("characters", [])
        ]:
            raise HTTPException(404, f"故事表里没有人物 {body.character_id}")
        return lambda: characters.cutout_character(pid, body.character_id)

    raise HTTPException(422, f"未知 action：{body.action}，可选：{list(ACTIONS)}")


@router.post("/projects/{pid}/generate", status_code=202)
def generate(
    body: GenerateIn,
    pid: str = Depends(get_owned_project),
    people_id: int = Depends(verify_token),
):
    if tasks.active_for_project(pid):
        raise HTTPException(409, "本项目已有生成任务，请等待完成")
    try:
        store.project_dir(pid)
    except FileNotFoundError:
        raise HTTPException(404, f"项目不存在：{pid}")
    try:
        fn = _build_fn(pid, body)
    except FileNotFoundError:
        raise HTTPException(
            409, "故事表还没生成好（创建任务可能仍在跑），请轮询任务状态"
        )
    # 余额闸门：内测期赠分制，0 余额拦生成（消耗在生成成功后按量结算）
    from server.services import billing
    if not billing.check_balance(people_id, min_points=1.0):
        raise HTTPException(
            402, {"code": "INSUFFICIENT_POINTS", "message": "积分不足，请联系管理员充值"}
        )
    t = tasks.submit(
        "generate", pid, body.model_dump(exclude_none=True), fn, people_id=people_id
    )
    return {"task_id": t.task_id, "action": body.action}
