# -*- coding: utf-8 -*-
"""鉴权：PyJWT HS512 签发/验签。

独立站自有 key：COMIC_JWT_KEY_HEX 环境变量（64 字节随机串 hex，
openssl rand -hex 64 生成），与主站 pay-account-service 的 key 完全独立——
两套服务互不认对方 token。无默认值：缺失时服务启动期由 server.api.app 拦截。
"""

import time

import jwt
from fastapi import Header, HTTPException

JWT_ALG = "HS512"
JWT_ISS = "comic-generator"
JWT_TTL_SECONDS = 7 * 24 * 3600  # 7 天，与前端 Cookie 有效期对齐


def _jwt_key() -> bytes:
    import os

    key_hex = (os.environ.get("COMIC_JWT_KEY_HEX") or "").strip()
    if not key_hex:
        raise RuntimeError(
            "COMIC_JWT_KEY_HEX 未配置：无法签发/校验 token。"
            "请在 .env 配置（openssl rand -hex 64 生成）。"
        )
    return bytes.fromhex(key_hex)


def issue_token(people_id, username: str) -> str:
    """签发用户 JWT。payload：sub=用户名, user=people_id, rol=角色。"""
    now = int(time.time())
    claims = {
        "sub": username,
        "iss": JWT_ISS,
        "appKey": "comic",
        "user": str(people_id),
        "rol": ["ROLE_USER"],
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(claims, _jwt_key(), algorithm=JWT_ALG, headers={})


def verify_token(authorization: str | None = Header(default=None)) -> int:
    """验签并返回 people_id。失败抛 401。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "缺少 Bearer token"},
        )
    token = authorization[7:]
    try:
        payload = jwt.decode(
            token, _jwt_key(), algorithms=[JWT_ALG], issuer=JWT_ISS
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail={"code": "TOKEN_EXPIRED", "message": "token 已过期"}
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": f"token 无效: {e}"},
        )

    user_id = payload.get("user") or payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "token 缺少 user/sub"},
        )
    return int(user_id)
