# -*- coding: utf-8 -*-
"""FastAPI 依赖：登录态 + 项目归属。

- ``verify_token``：解 JWT → people_id（401）
- ``get_owned_project(pid, people_id)``：项目存在且属于当前用户 → 返回 pid
  （404 不区分「不存在」与「别人的」，避免探测项目编号）

项目归属事实存在 comic_project 表（projects/ 目录是纯文件，无法按人过滤），
由 people_repository 的 create/get/owner_of/list_by_owner 维护。
"""

from fastapi import Depends, HTTPException, Request

from server.core.security import verify_token
from server.db import people_repository


def _people_id_from_request(request: Request) -> int:
    """从 Authorization header 或 ?token= query 解 people_id（401）。

    <img>/<a> 标签带不了 Authorization header，文件下载走 ?token= 兑底。
    """
    auth = request.headers.get("authorization") or ""
    token = auth[7:] if auth.startswith("Bearer ") else request.query_params.get("token", "")
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "缺少 Bearer token"},
        )
    # 复用 verify_token 的验签逻辑（它接收 Authorization header 值）
    return verify_token(authorization=f"Bearer {token}")


def get_owned_project(
    pid: str, people_id: int = Depends(verify_token)
) -> str:
    owner = people_repository.project_owner(pid)
    if owner is None or int(owner) != int(people_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        )
    return pid


def get_task_owner(
    task_id: str, people_id: int = Depends(verify_token)
) -> str:
    """轮询任务状态：task 必须存在、其 project 属于当前用户。"""
    from server.api import tasks

    t = tasks.get_task(task_id)
    if not t:
        raise HTTPException(
            status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "任务不存在"}
        )
    owner = people_repository.project_owner(t.project_id)
    if owner is None or int(owner) != int(people_id):
        raise HTTPException(
            status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "任务不存在"}
        )
    return task_id
