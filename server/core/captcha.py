# -*- coding: utf-8 -*-
"""图形验证码：无状态 HMAC token + PIL 图片（登录/注册/邀请码发放共用）。

token 内只落答案 hash，不依赖 Redis。校验链：格式→验签→时效→答案→一次性 jti；
jti 的「未消费检查+标记消费」在同一把锁内原子完成，并发复用同一 token 只有一个
能通过；输错答案不作废 token，改答案可重试。

密钥：COMIC_CAPTCHA_SECRET 环境变量。未配置直接报错（兜底密钥=放行伪造 token），
服务启动期由 server.api.app 拦截。
"""

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import random
import threading
import time
import uuid
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 去除易混淆的 0/O/1/I
CHAR_SET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
INVITATION_CODE_LENGTH = 6
CAPTCHA_LENGTH = 4
CAPTCHA_TTL_SECONDS = 300
_JTI_RETENTION_SECONDS = 600

_state_lock = threading.Lock()
_used_jtis: dict = {}  # jti -> expire_ts


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    missing = len(data) % 4
    if missing:
        data += "=" * (4 - missing)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def _get_captcha_secret() -> str:
    secret = (os.environ.get("COMIC_CAPTCHA_SECRET") or "").strip()
    if not secret:
        raise RuntimeError(
            "COMIC_CAPTCHA_SECRET 未配置：无法签发/校验验证码 token。"
            "请在 .env 配置（随机强密钥）。"
        )
    return secret


def _hash_answer(answer: str) -> str:
    return hashlib.sha256(
        (_get_captcha_secret() + ":" + answer.strip().upper()).encode("utf-8")
    ).hexdigest()


def _issue_captcha_token(answer: str, now_ts: Optional[int] = None) -> str:
    now = now_ts if now_ts is not None else int(time.time())
    payload = {
        "answer_hash": _hash_answer(answer),
        "exp": now + CAPTCHA_TTL_SECONDS,
        "jti": uuid.uuid4().hex,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    signature = hmac.new(
        _get_captcha_secret().encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
    ).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}"


def _verify_captcha_token(token: str, answer: str, now_ts: Optional[int] = None) -> Tuple[bool, str]:
    """校验链：格式→验签→时效→答案→一次性 jti。返回 (ok, reason)。"""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False, "bad_format"
        payload_b64, sign_b64 = parts
        expected_sig_b64 = _b64url_encode(
            hmac.new(
                _get_captcha_secret().encode("utf-8"),
                payload_b64.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(sign_b64, expected_sig_b64):
            return False, "bad_signature"
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))

        now = now_ts if now_ts is not None else int(time.time())
        if int(payload.get("exp", 0)) < now:
            return False, "expired"
        jti = str(payload.get("jti", ""))
        if not jti:
            return False, "missing_jti"
        if not hmac.compare_digest(str(payload.get("answer_hash", "")), _hash_answer(answer)):
            return False, "wrong_answer"
        with _state_lock:
            stale = [k for k, ts in _used_jtis.items() if ts < now]
            for k in stale:
                _used_jtis.pop(k, None)
            if jti in _used_jtis:
                return False, "replayed"
            _used_jtis[jti] = now + _JTI_RETENTION_SECONDS
        return True, jti
    except RuntimeError:
        raise  # 配置类故障不降级为验证码错误
    except Exception as e:
        return False, f"error:{e}"


# ---------------------------------------------------------------------------
# 验证码图片（PIL）
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",   # Windows: Arial Bold
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


def _load_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _render_captcha_image(text: str) -> bytes:
    """绘制 200x69 PNG：随机着色字符 + 旋转 + 干扰弧线 + 噪点。"""
    from PIL import Image, ImageDraw

    width, height = 200, 69
    image = Image.new("RGB", (width, height), (247, 245, 239))
    draw = ImageDraw.Draw(image)
    font = _load_font(40)

    slot = width // (len(text) + 1)
    for i, ch in enumerate(text):
        angle = random.uniform(-25, 25)
        ch_img = Image.new("RGBA", (60, 70), (0, 0, 0, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        color = tuple(random.randint(28, 108) for _ in range(3))
        ch_draw.text((6, 6), ch, font=font, fill=color + (255,))
        ch_img = ch_img.rotate(angle, expand=True, resample=Image.BICUBIC)
        x = 12 + i * slot + random.randint(-4, 4)
        y = random.randint(2, 10)
        image.paste(ch_img, (x, y), ch_img)

    for _ in range(4):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        arc_color = tuple(random.randint(140, 200) for _ in range(3))
        draw.arc(
            [min(start[0], end[0]), min(start[1], end[1]),
             max(start[0], end[0]) + 60, max(start[1], end[1]) + 60],
            start=random.randint(0, 180), end=random.randint(180, 360),
            fill=arc_color, width=2,
        )

    for _ in range(160):
        xy = (random.randint(0, width - 1), random.randint(0, height - 1))
        gray = random.randint(150, 220)
        draw.point(xy, fill=(gray, gray, gray))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _generate_captcha_text() -> str:
    return "".join(random.choice(CHAR_SET) for _ in range(CAPTCHA_LENGTH))


def _generate_invitation_code() -> str:
    return "".join(random.choice(CHAR_SET) for _ in range(INVITATION_CODE_LENGTH))
