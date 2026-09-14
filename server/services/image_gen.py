# -*- coding: utf-8 -*-
"""gpt-image-2 封装：generate / edit（多参考图）+ 审核误拦降级 + b64/url 兼容。"""

import base64
import binascii
import http.client
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from openai import BadRequestError, OpenAI
from PIL import Image

from server.config import IMAGE_MODEL

_client = OpenAI()


class ModerationBlocked(Exception):
    """提示词被中转站安全系统拦截（400）。"""


class InvalidImageError(RuntimeError):
    """生成结果或已有缓存不是完整、可解码的图片。"""


class MissingTransparencyError(InvalidImageError):
    """请求透明背景，但图片未包含透明背景和可见主体。"""


def validate_image(path: Path, *, require_transparency: bool = False) -> bool:
    """检查文件结构和实际像素；Image.open 本身不会完整解码。"""
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            alpha = image.convert("RGBA").getchannel("A").getextrema()
    except (FileNotFoundError, PermissionError):
        raise
    except (OSError, ValueError, SyntaxError) as exc:
        raise InvalidImageError(
            f"图片 {path.name} 损坏或不完整，请重新生成对应素材。"
        ) from exc
    transparent = alpha[0] == 0 and alpha[1] > 0
    if require_transparency and not transparent:
        raise MissingTransparencyError(
            f"图片 {path.name} 没有透明背景或可见主体，请在故事设置下方点击“生成漫画”或重跑对应分镜，生成透明 PNG。"
        )
    return transparent


def _save_result(result, path: Path, *, require_transparency: bool = False):
    """先校验临时文件，再原子替换；不完整的下载不会成为正式缓存。"""
    if not result.data:
        raise InvalidImageError(f"API 没有返回图片：{path.name}，请重试生成。")
    d = result.data[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        if getattr(d, "b64_json", None):
            try:
                content = base64.b64decode(d.b64_json, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise InvalidImageError("API 返回的图片 Base64 数据无效") from exc
            temp.write_bytes(content)
            transparent = validate_image(temp)
        elif getattr(d, "url", None):
            # Only download the same generated image again; do not repeat a paid
            # generation request just because its download was interrupted.
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(d.url, timeout=60) as response:
                        content = response.read()
                    temp.write_bytes(content)
                    transparent = validate_image(temp)
                    break
                except (
                    urllib.error.URLError,
                    http.client.HTTPException,
                    TimeoutError,
                    InvalidImageError,
                ) as exc:
                    if attempt == 2:
                        raise InvalidImageError(
                            "同一图片下载 3 次仍失败或数据不完整"
                        ) from exc
                    print(f"  [重试] {path.name} 下载失败或不完整，重新下载（{attempt + 2}/3）……")
        else:
            raise InvalidImageError("API 返回里既没有 b64_json 也没有 url")
        if require_transparency and not transparent:
            raise MissingTransparencyError(
                f"未保存 {path.name}：生图接口没有返回包含透明背景和可见主体的 PNG。"
                "请确认当前图片服务支持透明输出后重试；已有图片已保留。"
            )
        temp.replace(path)
    except MissingTransparencyError:
        raise
    except InvalidImageError as exc:
        raise InvalidImageError(
            f"未保存 {path.name}：API 返回的图片无效或下载不完整。"
            "已有文件保持原样，请重试生成对应素材。"
        ) from exc
    finally:
        temp.unlink(missing_ok=True)


def _is_moderation(err: Exception) -> bool:
    """识别审核拦截：英文 moderation_blocked 或中文"防护限制/违反"提示。"""
    if not isinstance(err, BadRequestError):
        return False
    msg = str(err).lower()
    return "moderation" in msg or "防护限制" in msg or "违反" in msg


def generate(
    prompt: str, path: Path, size: str = "1024x1024", *, background: str = "auto", request_timeout: float | None = None
):
    """文生图。被审核拦截时抛 ModerationBlocked，由调用方决定怎么降级。"""
    try:
        client = _client.with_options(timeout=request_timeout, max_retries=0) if request_timeout else _client
        result = client.images.generate(
            model=IMAGE_MODEL, prompt=prompt, size=size,
            background=background, output_format="png",
        )
    except BadRequestError as e:
        if _is_moderation(e):
            raise ModerationBlocked(str(e)) from e
        raise
    _save_result(result, path, require_transparency=background == "transparent")


def edit(
    prompt: str,
    ref_paths: list[Path],
    path: Path,
    size: str = "1536x1024",
    allow_reference_fallback: bool = True,
    *,
    background: str = "auto",
    request_timeout: float | None = None,
):
    """参考图生图（一次可传多张参考图）。

    降级策略：带参考图被审核拦（400）时，去掉参考图直接 generate 重试一次。
    """
    handles = [open(p, "rb") for p in ref_paths]
    try:
        client = _client.with_options(timeout=request_timeout, max_retries=0) if request_timeout else _client
        result = client.images.edit(
            model=IMAGE_MODEL, image=handles, prompt=prompt, size=size,
            background=background, output_format="png",
        )
        _save_result(result, path, require_transparency=background == "transparent")
    except BadRequestError as e:
        if not _is_moderation(e):
            raise
        if not allow_reference_fallback:
            raise ModerationBlocked(
                "固定 IP 参考图请求被拦截，已停止，未尝试去掉参考图重画。请调整场景描述后重试。"
            ) from e
        print(f"  [降级] 带参考图被审核拦截，去掉参考图重试……")
        generate(prompt, path, size=size, background=background, request_timeout=request_timeout)
    finally:
        for f in handles:
            f.close()
