# -*- coding: utf-8 -*-
"""中转站 chat 封装：调 gpt-5.6-sol 写 JSON，含 JSON 提取容错。"""

import base64
import json
import mimetypes
import re
import time
from pathlib import Path

from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError

from server.config import CHAT_MODEL

_TIMEOUT = 300.0
_client = OpenAI(timeout=_TIMEOUT, max_retries=0)


_supports_reasoning_effort = True


def _request(prompt: str, temperature: float, image_refs: list[tuple[str, Path]] | None = None) -> str:
    global _supports_reasoning_effort
    content = prompt
    if image_refs:
        content = [{"type": "text", "text": prompt}]
        for label, path in image_refs:
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.extend([
                {"type": "text", "text": label},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{encoded}", "detail": "high",
                }},
            ])
    kwargs = dict(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": content}],
        temperature=temperature,
    )
    if _supports_reasoning_effort:
        kwargs["extra_body"] = {"reasoning_effort": "low"}
    try:
        r = _client.chat.completions.create(**kwargs)
    except APIStatusError as exc:
        if _supports_reasoning_effort and exc.status_code == 400 and "reasoning_effort" in str(exc).lower():
            _supports_reasoning_effort = False
            print("故事模型不支持 reasoning_effort，改用默认推理档位。", flush=True)
            kwargs.pop("extra_body", None)
            r = _client.chat.completions.create(**kwargs)
        else:
            raise
    # 计费：把本次 token 用量记进任务线程的计量器（后台任务收尾统一结算）
    try:
        from server.services import billing
        billing.record_llm_usage(getattr(r, "usage", None))
    except Exception:
        pass  # 计量失败不阻断生成
    return r.choices[0].message.content or ""


def chat_json(prompt: str, temperature: float = 0.7, *, image_refs: list[tuple[str, Path]] | None = None) -> dict:
    """让 LLM 输出一个 JSON 对象并解析返回。容忍 ```json 包裹和前后杂文本。"""
    started = time.monotonic()
    print(f"[{time.strftime('%H:%M:%S')}] 正在请求故事模型；读取等待上限 {int(_TIMEOUT)} 秒，失败自动重试 1 次。", flush=True)
    text = ""
    for attempt in range(2):
        try:
            text = _request(prompt, temperature, image_refs)
            break
        except (APIConnectionError, APIStatusError) as exc:
            elapsed = round(time.monotonic() - started)
            if isinstance(exc, APITimeoutError):
                reason = "等待故事模型响应超时"
            elif isinstance(exc, APIConnectionError):
                reason = "故事模型连接失败，代理或中转服务未正常返回结果"
            else:
                reason = f"故事模型服务返回 HTTP {exc.status_code}"
            cause = type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__
            print(f"[{time.strftime('%H:%M:%S')}] 请求失败，耗时 {elapsed} 秒；错误类型：{cause}。", flush=True)
            retryable = isinstance(exc, (APITimeoutError, APIConnectionError))
            if retryable and attempt == 0:
                print(f"[{time.strftime('%H:%M:%S')}] 自动重试第 2 次……", flush=True)
                continue
            raise RuntimeError(f"{reason}（耗时 {elapsed} 秒）。本次已停止，请检查连接后点击重试。") from exc
    print(f"故事模型已返回，耗时 {round(time.monotonic() - started)} 秒，正在解析故事。", flush=True)
    return extract_json(text)


def extract_json(text: str) -> dict:
    """从 LLM 输出里提取第一个 JSON 对象。"""
    # 先尝试直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 去掉 markdown 代码块包裹再找
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise RuntimeError(f"LLM 输出里没有 JSON 对象：{text[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM 输出的 JSON 解析失败：{e}\n原文前 300 字：{text[:300]}"
        ) from e
