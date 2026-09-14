# -*- coding: utf-8 -*-
"""中转站 chat 封装：调 gpt-5.6-sol 写 JSON，含 JSON 提取容错。"""

import json
import re
import time

from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError

from server.config import CHAT_MODEL

_client = OpenAI(timeout=180.0, max_retries=0)


def chat_json(prompt: str, temperature: float = 0.7) -> dict:
    """让 LLM 输出一个 JSON 对象并解析返回。容忍 ```json 包裹和前后杂文本。"""
    started = time.monotonic()
    print(f"[{time.strftime('%H:%M:%S')}] 正在请求故事模型；读取等待上限 180 秒，不自动重试。", flush=True)
    try:
        r = _client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
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
        raise RuntimeError(f"{reason}（耗时 {elapsed} 秒）。本次已停止，请检查连接后点击重试。") from exc
    print(f"故事模型已返回，耗时 {round(time.monotonic() - started)} 秒，正在解析故事。", flush=True)
    text = r.choices[0].message.content or ""
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
