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
import os
import logging
import time
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from server.services.bubble_assets import ASSET_DIR, VARIANTS, filename
from server.core.studio import BUBBLES
from server.config import ROOT_DIR

from server.api import tasks
from server.api.routers import assets, auth, files, generate, projects, styles, user
from server.api.routers import tasks as tasks_router

# ---------- 请求日志 ----------
# 所有 /api/* 请求写一行到 output/logs/api.log；handler 抛异常时附完整 traceback。
# 后台任务内部 print 仍走 tasks._LogWriter（进 task.logs），不打到这个文件。
LOG_DIR = ROOT_DIR / "output" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_api_logger = logging.getLogger("comic.api")
_api_logger.setLevel(logging.INFO)
if not _api_logger.handlers:  # uvicorn --reload 会重复 import，避免重复 handler
    _fh = logging.FileHandler(LOG_DIR / "api.log", encoding="utf-8")
    _fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    _api_logger.addHandler(_fh)
    _api_logger.propagate = False  # 不冒泡给 uvicorn，避免一条日志写两遍


def create_app() -> FastAPI:
    app = FastAPI(title="AI 漫画长图生产工具 API", version="0.2.0")

    @app.middleware("http")
    async def request_log_middleware(request: Request, call_next):
        start = time.perf_counter()
        # 只记 API；静态文件/长图下载量太大，且 files.py 已有自己的归属校验
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        try:
            response = await call_next(request)
        except Exception:
            # 未捕获异常 = 未来的 500；把 traceback 记到 api.log
            _api_logger.error(
                "%s %s -> 500\n%s",
                request.method,
                request.url.path,
                traceback.format_exc(),
            )
            raise
        elapsed = (time.perf_counter() - start) * 1000
        if response.status_code >= 400:
            _api_logger.warning(
                "%s %s -> %s (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
            )
        else:
            _api_logger.info(
                "%s %s -> %s (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
            )
        return response

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

    # 账户域启动自检：密钥缺失时注册/登录/验证码全失守，启动即失败好过带病运行。
    # 本地纯创作（不走 /api/auth/*）不受影响——这里只拦 auth 服务启动项。
    for var in ("COMIC_JWT_KEY_HEX", "COMIC_CAPTCHA_SECRET"):
        if not (os.environ.get(var) or "").strip():
            raise RuntimeError(
                f"{var} 未配置，服务拒绝启动。请在 .env 配置（见 .env.example）。"
            )

    app.include_router(auth.router)
    app.include_router(user.router)
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
