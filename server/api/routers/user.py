# -*- coding: utf-8 -*-
"""用户域接口：详情、邀请码、积分余额、积分流水（均需登录）。

- GET  /api/user/detail          当前用户详情
- GET  /api/user/invitations     我的邀请码列表
- GET  /api/user/points          积分余额
- POST /api/user/points/history  积分流水分页
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.core.security import verify_token
from server.db import people_repository

router = APIRouter(prefix="/api/user", tags=["用户"])


def _fmt_dt(dt) -> Optional[str]:
    """时间列兼容：MySQL 返回 datetime、SQLite 返回字符串，统一输出 'YYYY-MM-DD HH:MM:SS'。"""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt[:19]  # 'YYYY-MM-DD HH:MM:SS' 或 'YYYY-MM-DDTHH:MM:SS' 截齐
    return dt.isoformat(sep=" ")


@router.get("/detail")
def get_user_detail(people_id: int = Depends(verify_token)) -> dict:
    row = people_repository.get_people_detail(people_id)
    if not row:
        raise HTTPException(
            status_code=404, detail={"code": "USER_NOT_FOUND", "message": "用户不存在"}
        )
    return {
        "success": True,
        "data": {
            "peopleId": row.get("peopleId"),
            "peopleName": row.get("peopleName"),
            "peoplePhone": row.get("peoplePhone"),
            "peopleDatetime": _fmt_dt(row.get("peopleDatetime")),
            "points": float(row.get("points") or 0),
            "peopleState": row.get("peopleState"),
        },
    }


@router.get("/invitations")
def get_my_invitations(people_id: int = Depends(verify_token)) -> dict:
    rows = people_repository.list_invitation_codes(people_id)
    items = []
    for row in rows:
        items.append(
            {
                "id": row.get("id"),
                "invitationCode": row.get("invitationCode"),
                "createTime": _fmt_dt(row.get("createTime")),
                "invalid": bool(row.get("invalid")),
            }
        )
    return {"success": True, "data": items}


@router.get("/points")
def get_points(people_id: int = Depends(verify_token)) -> dict:
    balance = people_repository.get_points_balance(people_id)
    return {"success": True, "data": {"points": int(balance)}}


class PointsHistoryRequest(BaseModel):
    pageNumber: int = Field(default=1, ge=1)
    pageSize: int = Field(default=10, ge=1, le=100)


@router.post("/points/history")
def get_points_history(
    req: PointsHistoryRequest, people_id: int = Depends(verify_token)
) -> dict:
    data = people_repository.list_points_history(people_id, req.pageNumber, req.pageSize)
    return {"success": True, "data": data}
