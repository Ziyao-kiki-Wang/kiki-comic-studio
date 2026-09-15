---
layer: detail
update_mode: patch
role: "代码导航 —— 概念/功能到 1-2 个权威入口文件"
read_when: "要改某个功能，先找入口文件时"
not_for: "全量 API/组件清单（留给代码），当前状态（-> PROGRESS.md）"
---

# Code Map

> 只记"概念 → 入口文件"，不堆全量清单。改功能前先在这找入口。

## 后端（server/）

| 功能 | 入口文件 | 说明 |
|---|---|---|
| FastAPI app 挂载/启动 | `server/api/app.py` | 路由注册、CORS、StaticFiles、启动校验（JWT/captcha key 缺失拒绝启动） |
| 项目 CRUD | `server/api/routers/projects.py` | 项目列表、创建、故事表读写 |
| 分镜生图 | `server/api/routers/generate.py` → `server/core/scenes.py` | 逐格生图、重跑、改图 |
| 故事生成 | `server/core/story.py` | 主题+角色 → 故事表（分镜列表+台词） |
| 气泡/文字排版合成 | `server/core/compose.py` `lettering.py` `bubbles.py` | Pillow 把气泡/旁白/字体合到分镜上 |
| 长图排版渲染 | `server/core/page_layouts.py` | 17 种模板 → 最终 PNG |
| PPTX 导出 | `server/core/page_layouts.py`（或独立模块） | 文字可编辑的 PPTX |
| LLM 调用 | `server/services/llm.py` | OpenAI 兼容接口，故事/描述生成 |
| 图像生成 | `server/services/image_gen.py` | 分镜/角色/透明主体生图 |
| 素材/字体/贴纸管理 | `server/services/assets.py` `bubble_assets.py` | 上传、共享字体、贴纸读取 |
| 账户域（注册/登录/积分/邀请码） | `server/api/routers/auth.py` `user.py` | 验证码、JWT、积分扣减 |
| 验证码 | `server/core/captcha.py` | HMAC token + PIL 图片，TTL 300s，无状态 |
| 数据库连接 | `server/db/connection.py` | MySQL/SQLite 双语，`%s`→`?` 翻译 |
| 数据仓库 | `server/db/people_repository.py` | people/points/invitation 的 SQL |
| 计费 | `server/services/billing.py` | 积分扣减逻辑 |

## 前端（web/src/）

| 功能 | 入口文件 | 说明 |
|---|---|---|
| 四步导航/工作台壳 | `web/src/pages/WorkspaceShell.jsx` | 分镜制作→画面精修→作品排版→贴纸装饰 |
| 故事表 + 分镜预览 | `web/src/pages/ProjectWorkbench.jsx` | 写故事、生成、逐格缩略图 |
| 单格画面精修 | `web/src/pages/SceneEditor.jsx` `SceneImageTools.jsx` | 气泡拖拽(Konva)、AI 改图、特写、贴图 |
| 长图排版 | `web/src/pages/LongImageDesigner.jsx` | 模板选择、标题/副标题、间距、预览 |
| 贴纸装饰 | `web/src/pages/DecorationEditor.jsx` | 155 张贴纸、拖放、层级 |
| 登录/注册/个人中心 | `web/src/pages/auth/Login.jsx` `Register.jsx` `Profile.jsx` | |
| 通用 API 封装 | `web/src/lib/api.js` | 项目/分镜/生图请求，带 401 跳登录 |
| 账户 API 封装 | `web/src/lib/authApi.js` | 登录/注册/验证码/积分 |
| 素材/图片 URL | `web/src/lib/studioAssets.js` | 图片地址拼接、字体加载 |

## 配置与数据

| 内容 | 位置 |
|---|---|
| 模板/字体/气泡/贴纸定义 | `schemas/*.json` |
| 共享字体（17 款） | `fonts/`（gitignore，服务器单独放） |
| 前端静态素材（气泡/贴纸/风格预览） | `web/public/`（在 git 里） |
| 建表 SQL | `migrations/001_init_account.sql` |
| 环境变量样例 | `.env.example` |
| 部署 skill | `~/.agents/skills/frowang-deploy/SKILL.md` |
