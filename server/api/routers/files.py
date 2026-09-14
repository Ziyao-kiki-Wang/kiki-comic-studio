# -*- coding: utf-8 -*-
"""项目文件静态服务：GET /files/{pid}/{path}（防路径穿越 + 项目归属校验）。

<img>/<a> 标签带不了 Authorization header，所以接受 ?token= query 参数
（deps._people_id_from_request 同时认 header 和 query）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from server import store
from server.api.deps import _people_id_from_request
from server.core import compose
from server.db import people_repository

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{pid}/{path:path}")
def get_file(pid: str, path: str, request: Request, download: bool = False):
    # 项目归属：当前用户必须是 owner，否则 404（不区分不存在/别人的）
    people_id = _people_id_from_request(request)
    owner = people_repository.project_owner(pid)
    if owner is None or int(owner) != int(people_id):
        raise HTTPException(404, f"项目不存在：{pid}")
    try:
        base = store.project_dir(pid).resolve()
    except FileNotFoundError:
        raise HTTPException(404, f"项目不存在：{pid}")
    target = (base / path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(404, f"文件不存在：{path}")
    if download and target == (base / "output" / "长图.png").resolve():
        try:
            if compose.long_image_stale(pid):
                raise HTTPException(409, "长图已过期，请重新合成后再下载；旧图仍可预览")
        except FileNotFoundError:
            raise HTTPException(409, "长图已过期，请重新合成后再下载；旧图仍可预览")
    return FileResponse(
        target,
        filename=target.name if download else None,
        headers={"Cache-Control": "no-cache"},
    )
