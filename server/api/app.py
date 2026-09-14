# -*- coding: utf-8 -*-
"""FastAPI 入口。

启动：python -m server.api.app（端口 8000）

说明：
- 所有 handler 用 def 不用 async def —— 第 1 期引擎全是阻塞调用，
  def handler 会进 FastAPI 线程池，不会冻结 event loop。
- 生成类动作一律走 tasks.submit 后台线程，接口立即返回 task_id，
  前端拿 GET /api/tasks/{task_id} 轮询。
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from server.services.bubble_assets import ASSET_DIR, VARIANTS, filename
from server.core.studio import BUBBLES

from server.api import tasks
from server.api.routers import assets, files, generate, projects, styles
from server.api.routers import tasks as tasks_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI 漫画长图生产工具 API", version="0.2.0")
    @app.get("/api/bubble-catalog")
    def bubble_catalog():
        return {kind: [v for v in VARIANTS if filename(kind, v) is None or (ASSET_DIR / filename(kind, v)).is_file()] for kind in BUBBLES}
    app.mount("/api/bubble-assets", StaticFiles(directory=ASSET_DIR, check_dir=False), name="bubble-assets")

    @app.exception_handler(ValueError)
    def invalid_value(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    def missing_file(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 前端 Vite 开发服务器跨域，先全开
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    tasks.load_tasks()  # 孤儿任务恢复：上次卡在 running 的标 failed
    app.include_router(projects.router, prefix="/api")
    app.include_router(generate.router, prefix="/api")
    app.include_router(tasks_router.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(assets.router, prefix="/api")
    app.include_router(styles.router, prefix="/api")
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
