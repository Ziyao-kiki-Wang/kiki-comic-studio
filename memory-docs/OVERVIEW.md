---
layer: framework
update_mode: rewrite
role: "项目概览 —— 是什么、解决什么问题、主流程、技术栈"
read_when: "第一次进入项目，或需要向他人解释项目定位时"
not_for: "当前进展（-> STATUS），模块细节（-> detail_mem/MAP.md）"
---

# AI 漫画工坊（comic-generator / kiki-comic-studio）

## 一句话定位

把一段**文字故事主题**变成一条**可直接发布的科普漫画长图**：AI 写故事、画分镜、加气泡对话，用户微调后导出排版好的 PNG 长图 / 可编辑 PPTX。

## 目标

- 让不会画画的人能产出"固定角色 + 讲故事 + 排版好看"的漫画内容（公众号/小红书科普、产品说明、绘本）
- 角色形象在多格分镜中保持一致（上传参考图或 AI 生成标准照）
- 气泡、旁白、字体、贴纸、长图模板全部可视化微调，不依赖设计工具

## 主要业务流

```text
故事主题 + 角色参考图（可上传/可 AI 生成）
  -> AI 生成故事表（每格：场景/出场人物/台词/画面描述）
  -> 逐格生成分镜图（角色一致性靠参考图）
  -> 画面精修（拖气泡/改台词/AI 改图/手机屏幕特写/单格贴图）
  -> 选长图模板排版（17 种模板 + 艺术字 + 贴纸装饰）
  -> 导出 PNG 长图 / PPTX
```

## 核心服务 / 模块

| 模块 | 角色 | 入口 |
|---|---|---|
| `server/api/` | FastAPI 后端：项目/故事/生图/排版/账户/积分 | `server/api/app.py` |
| `server/core/` | 故事生成、分镜合成、气泡排版、长图渲染、PPTX | `server/core/story.py` `compose.py` `page_layouts.py` |
| `server/services/` | LLM 调用、图像生成、素材/字体管理 | `server/services/llm.py` `image_gen.py` `assets.py` |
| `server/db/` | 账户域存储（MySQL 生产 / SQLite 本地兜底） | `server/db/connection.py` |
| `web/` | React 工作台：故事表/分镜预览/画面精修/排版/贴纸 | `web/src/pages/` `web/src/lib/api.js` |
| `schemas/` | 模板/字体/气泡/贴纸/小标题的配置定义 | `schemas/*.json` |

## 技术栈

- 后端：Python 3.12 + FastAPI + uvicorn + Pillow（气泡/排版合成）
- 前端：React 18 + Vite + Konva（画布拖拽气泡/贴纸）
- 生图/写故事：OpenAI 兼容接口（`OPENAI_BASE_URL`，生产指向 openlux）
- 存储：项目文件走文件系统 `projects/<id>/`；账户/积分走 MySQL（生产）或 SQLite（本地）
- 导出：PNG 长图（1080px 宽）+ PPTX（文字可编辑）
- 部署：nginx 静态托管 `web/dist` + `/api/*` 反代 systemd 服务 `127.0.0.1:8002`

## 运行形态

- **本地开发**：后端 `127.0.0.1:8000` + 前端 Vite `127.0.0.1:5173`，`VITE_API_BASE` 默认 `http://127.0.0.1:8000`
- **生产**：`https://comic.frowang.com`（Cloudflare → 香港服务器 `212.189.107.74`），前端同源请求 `/api` 由 nginx 反代到 `comic-generator.service:8002`

## 相关文档

- 当前状态：`memory-docs/STATUS.md`
- 部署细节：`memory-docs/detail_mem/DECISIONS.md`（部署形态决策）
- 代码导航：`memory-docs/detail_mem/MAP.md`
- 术语：`memory-docs/GLOSSARY.md`
