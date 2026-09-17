---
layer: detail
update_mode: patch
role: "模块实现状态 —— 每个模块做到哪了、已知缺口、下一步"
read_when: "要改某模块，先确认它的完成度和遗留问题"
not_for: "项目级焦点（-> STATUS.md），决策理由（-> DECISIONS.md）"
---

# Module Progress

## 后端 server/

| 模块 | 状态 | 缺口 / 下一步 |
|---|---|---|
| 故事生成 `core/story.py` | ✅ 可用 | 角色外貌由参考图决定，故事身份由用户设定；剧情/人物改动触发受影响分镜重画 |
| 分镜生图 `core/scenes.py` | ✅ 可用 | 支持完整场景/透明主体两种模式；透明模式直接输出 PNG |
| 气泡/文字合成 `compose.py` `lettering.py` `bubbles.py` | ✅ 可用 | 10 种可视外形 + 14 款参考图样式 + 6 套配色；气泡轮廓与文字独立对象 |
| 长图排版 `page_layouts.py` | ✅ 可用 | 17 种模板 + 艺术字标题 + 小标题样式 + 结尾图文块 + 上下留白（厘米换算） |
| PPTX 导出 | ✅ 可用 | 文字可编辑、气泡轮廓 SVG；打开机器需装对应字体 |
| LLM/生图服务 `services/llm.py` `image_gen.py` | ✅ 可用 | 走 `OPENAI_BASE_URL` 兼容接口；生图支持 `background=transparent` |
| 账户域 `routers/auth.py` `user.py` + `db/` | ✅ 可用 | 注册/登录/JWT/积分/邀请码/验证码全通；手机号唯一 |
| 验证码 `core/captcha.py` | ✅ 可用 | 无状态 HMAC token，TTL 300s，一次性 jti 防重放 |
| 计费 `services/billing.py` | ✅ 可用 | 生图扣积分，注册/邀请送积分（`comic_app_config` 可调） |
| 部署/启动 `scripts/start-studio.ps1` | ✅ 可用 | 本地一键起前后端；生产走 systemd |

## 前端 web/

| 模块 | 状态 | 缺口 / 下一步 |
|---|---|---|
| 工作台导航 `WorkspaceShell.jsx` | ✅ 可用 | 四步固定入口，窄屏抽屉式 |
| 故事表+分镜预览 `ProjectWorkbench.jsx` | ✅ 可用 | 生成前保存、失败可重试、标记通过 |
| 画面精修 `SceneEditor.jsx` | ✅ 可用 | 气泡拖拽/多选组合/AI 改图/手机特写/单格贴图 |
| 长图排版 `LongImageDesigner.jsx` | ✅ 可用 | 模板预览、间距/留白/艺术字/结尾块 |
| 贴纸装饰 `DecorationEditor.jsx` | ✅ 可用 | 155 张内置贴纸 + 用户上传 |
| 账户页 `auth/*.jsx` | ✅ 可用 | 验证码加载/登录/注册/积分流水 |
| API 层 `lib/api.js` `authApi.js` `studioAssets.js` | ✅ 刚修 | **production 同源**（2026-09-15 修），本地开发 `VITE_API_BASE` 覆盖 |

## 部署 / 运维

| 项 | 状态 | 说明 |
|---|---|---|
| GitHub 仓库 | ✅ | `Ziyao-kiki-Wang/kiki-comic-studio`，服务器 deploy key 只读拉取 |
| systemd 服务 | ✅ | `comic-generator.service` → `127.0.0.1:8002`，Restart=always |
| nginx | ✅ | `comic.frowang.com` server block，`/api` 反代 8002，`client_max_body_size 40m` |
| MySQL | ✅ | `comic` 库 6 表，`comic` 用户只授权 `comic.*` |
| 证书 | ✅ | Cloudflare Origin CA 通配符，2040 年到期 |
| fonts | ✅ 已上传 | 365MB tar 流式传输；**未入 git**，服务器上是独立副本 |
| 邀请码 | ✅ 已 seed | `scripts/seed_invitation_codes.py` 已跑 |

## 已知技术债 / 风险

| 项 | 风险 | 处理时机 |
|---|---|---|
| 分镜编辑依赖服务端 recompose | `save()` 触发 Pillow 重画 panel.png 传回，延迟明显；前端 Konva 已能所见即所得 | **下一步 Phase 1**：`stage.toDataURL()` 前端出图，`save` 不再走 `recompose_scene`（见 DECISIONS.md 2026-09-16） |
| `tasks._tasks` / `store._locks` 进程内字典 | 重启丢失任务状态；横向扩容不行 | 需要多实例时外置 Redis/DB |
| `output/comic.db` SQLite | 生产若忘配 `COMIC_MYSQL_*` 会落本地文件 | 已文档化，生产必须配 MySQL |
| fonts 365MB 未入库 | 新环境部署要单独传 | 考虑字体 CDN 化或精简字重 |
| 账户体系独立 | 与主站 lunwen 用户不通 | 若需 SSO 再设计 token 共享 |
| 长图排版引擎在服务端 | `compose.py` 17 套模板 Pillow 渲染，改排版选项要等服务端重渲 | Phase 2：前端 Canvas 重写（大工程，可延后；先靠 Phase 1 的分镜本地合成减少触发） |
