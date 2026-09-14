# -*- coding: utf-8 -*-
"""全局配置：环境加载、模型名、公共常量。"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

# 加载顺序：项目根 .env → spike/.env（后者不覆盖已存在的变量）
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / "spike" / ".env")

if not os.environ.get("OPENAI_API_KEY"):
    raise RuntimeError(
        "缺少 OPENAI_API_KEY：请在项目根 .env 或 spike/.env 里配置中转站密钥"
    )

CHAT_MODEL = "gpt-5.6-sol"
IMAGE_MODEL = "gpt-image-2"

PROJECTS_DIR = Path(
    os.environ.get("COMIC_PROJECTS_DIR", str(ROOT_DIR / "projects"))
).resolve()
SCHEMAS_DIR = ROOT_DIR / "schemas"

PANEL_W = 1080  # 公众号长图标准宽度
