# -*- coding: utf-8 -*-
"""任务状态轮询：GET /tasks/{task_id}。"""

from fastapi import APIRouter, HTTPException

from server.api import tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}")
def get_task(task_id: str):
    t = tasks.get_task(task_id)
    if not t:
        raise HTTPException(404, f"任务不存在：{task_id}")
    return t.to_dict()
