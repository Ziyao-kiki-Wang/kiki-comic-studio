# -*- coding: utf-8 -*-
"""认证路由：图形验证码 + 登录 + 注册。

- GET  /api/auth/captcha    图形验证码（HMAC token + base64 PNG，无状态）
- POST /api/auth/login      密码登录 → 扁平 {token, name, peopleId}
- POST /api/auth/register   注册（邀请码制）→ {success: true, value: "操作成功"}

响应契约（前端按此提取）：
- 业务失败：HTTP 200 + {"value": "中文错误消息"}
- 登录成功：扁平 {token, name, peopleId, status}
- 验证码一次性消费（验过即作废，不论后续密码对错）

Phase 1 不含 TOTP/找回密码/信任设备——内测期从简，后续按需平移。
"""

import base64
import logging
import re
from typing import Optional

from fastapi import APIRouter, Request

from server.core.captcha import (
    CAPTCHA_TTL_SECONDS,
    _generate_captcha_text,
    _issue_captcha_token,
    _render_captcha_image,
    _verify_captcha_token,
)
from server.core.security import issue_token
from server.db import people_repository
from server.db.people_repository import sha256_hex

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 8-18 位，必含大小写字母+数字，特殊符号可选
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])"
    r"[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;':\",./<>?]{8,18}$"
)
PASSWORD_RULE_MSG = "密码：8-18位，必须包含大小写字母、数字或特殊符号"
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


def _fail(message: str) -> dict:
    """业务失败响应：HTTP 200 + {value: msg}。"""
    return {"value": message}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_captcha(captcha_token: str, captcha_input: str) -> Optional[str]:
    """验证码校验：返回 None=通过（通过即消费 jti），否则为中文错误文案。"""
    if not captcha_token or not captcha_input:
        return "请输入验证码"
    ok, result = _verify_captcha_token(captcha_token, captcha_input)
    if ok:
        return None
    return "验证码已过期，请重新获取" if result in ("expired", "replayed") else "验证码错误！"


@router.get("/captcha", summary="获取图形验证码")
def get_auth_captcha() -> dict:
    text = _generate_captcha_text()
    token = _issue_captcha_token(text)
    image_b64 = base64.b64encode(_render_captcha_image(text)).decode("utf-8")
    return {
        "success": True,
        "data": {
            "captcha_token": token,
            "image_base64": image_b64,
            "expires_in": CAPTCHA_TTL_SECONDS,
        },
    }


@router.post("/login", summary="用户登录")
def login(payload: dict, request: Request) -> dict:
    people_phone = str(payload.get("peoplePhone") or "").strip()
    people_password = str(payload.get("peoplePassword") or "")
    captcha_token = str(payload.get("captcha_token") or "").strip()
    captcha_input = str(payload.get("captcha_input") or "").strip()

    captcha_err = _check_captcha(captcha_token, captcha_input)
    if captcha_err:
        return _fail(captcha_err)

    ip = _client_ip(request)

    if people_repository.is_login_locked(people_phone):
        return _fail("异常登陆账号锁定60分钟")

    frozen = people_repository.find_frozen_by_phone(people_phone)
    if frozen:
        msg = frozen.get("people_reason") or f"账号已冻结至{frozen.get('frozen_datetime')}"
        return _fail(msg)

    people = people_repository.find_by_phone(people_phone)
    if not people:
        people_repository.record_login_error(people_phone, ip)
        return _fail("没有此用户，请先注册用户！")

    if (people.get("people_password") or "") != sha256_hex(people_password):
        people_repository.record_login_error(people_phone, ip)
        return _fail("用户名或密码不正确！")

    token = issue_token(people.get("people_id"), people.get("people_name") or "")
    return {
        "token": token,
        "name": people.get("people_name"),
        "peopleId": people.get("people_id"),
        "status": people.get("people_status"),
    }


@router.post("/register", summary="用户注册（邀请码制）")
def register(payload: dict, request: Request) -> dict:
    people_name = str(payload.get("peopleName") or "").strip()
    people_phone = str(payload.get("peoplePhone") or "").strip()
    people_password = str(payload.get("peoplePassword") or "")
    invitation_code = str(payload.get("invitationCode") or "").strip()
    captcha_token = str(payload.get("captcha_token") or "").strip()
    captcha_input = str(payload.get("captcha_input") or "").strip()

    captcha_err = _check_captcha(captcha_token, captcha_input)
    if captcha_err:
        return _fail(captcha_err)

    if not people_name:
        return _fail("姓名不能为空！")
    if not people_phone:
        return _fail("手机号不能为空！")
    if not PHONE_PATTERN.match(people_phone):
        return _fail("手机号格式不正确")
    if not invitation_code:
        return _fail("邀请码不能为空！")
    if not PASSWORD_PATTERN.match(people_password):
        return _fail(PASSWORD_RULE_MSG)

    ok, err = people_repository.register_user(
        name=people_name,
        phone=people_phone,
        password_sha=sha256_hex(people_password),
        invitation_code=invitation_code,
        ip=_client_ip(request),
    )
    if not ok:
        return _fail(err)
    return {"success": True, "value": "操作成功"}
