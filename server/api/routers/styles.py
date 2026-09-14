# -*- coding: utf-8 -*-
"""风格菜单：GET /styles（前端下拉框数据源）。"""

import json

from fastapi import APIRouter

from server.config import SCHEMAS_DIR
from server.core.studio import CATALOG
from server.services.assets import font_catalog

router = APIRouter(prefix="/styles", tags=["styles"])


@router.get("")
def list_styles():
    menu = json.loads((SCHEMAS_DIR / "styles.json").read_text(encoding="utf-8"))
    return {"styles": menu["styles"], "fonts": font_catalog(), **CATALOG}
