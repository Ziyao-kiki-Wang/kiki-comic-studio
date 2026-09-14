# -*- coding: utf-8 -*-
"""任务状态轮询：GET /tasks/{task_id}（需登录且任务所属项目归当前用户）。"""

from fastapi import APIRouter, Depends, HTTPException

from server.api import tasks
from server.api.deps import get_task_owner

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}")
def get_task(task_id: str = Depends(get_task_owner)):
    t = tasks.get_task(task_id)
    if not t:
        raise HTTPException(404, f"任务不存在：{task_id}")
    return t.to_dict()
