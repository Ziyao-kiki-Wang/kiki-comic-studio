# -*- coding: utf-8 -*-
"""项目文件静态服务：GET /files/{pid}/{path}（防路径穿越，中文文件名安全）。"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from server import store
from server.core import compose

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{pid}/{path:path}")
def get_file(pid: str, path: str, download: bool = False):
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
