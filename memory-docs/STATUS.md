---
layer: framework
update_mode: rewrite
role: "当前快照 —— 项目级焦点、近期里程碑、阻塞"
read_when: "每次进入项目或需要知道'现在做到哪了'时"
not_for: "完整历史（-> HISTORY），模块级细节（-> detail_mem/PROGRESS.md）"
---

# Project Status

> 更新时间：2026-09-15

## Current Focus

- **已上线**：`https://comic.frowang.com` 生产部署完成（2026-09-14），前后端 + MySQL + nginx 全链路通
- 当前阶段：**内测可用**，接受真实用户反馈；主线是迭代分镜质量与排版细节
- **2026-09-16 识别的主痛点**：分镜编辑依赖服务端 Pillow 重画，延迟明显；已评估出"前端接管合成"路径（Phase 1 小改动，见 DECISIONS.md）

## Done（最近 3-5 条）

- [x] 生产部署上线 (`2026-09-14`) — comic.frowang.com 可访问，nginx + systemd + MySQL + 通配证书
- [x] 修复编辑器点开格子主画布空白 (`2026-09-15`) — `useImage` 的 `crossOrigin="anonymous"` 把同源 `?token=` 图片升级成 CORS fetch，ACAO 缺失时 onload 不触发、透明主体画不出；去掉该属性即恢复
- [x] 修复移动端验证码加载失败 (`2026-09-15`) — API_BASE 写死 127.0.0.1:8000 导致手机端请求打到用户自己设备；改为 production 同源 + fetch 超时
- [x] Git 历史署名重写 (`2026-09-14`) — 5 个 Devin 署名 commit 全部 rewrite 为 Ziyao-kiki-Wang，贡献者列表干净
- [x] 仓库迁移到 GitHub (`2026-09-14`) — `Ziyao-kiki-Wang/kiki-comic-studio`，服务器走 deploy key 拉取
- [x] README 重写 (`2026-09-14`) — 面向新人的项目介绍 + 工作台/成品长图截图

## In Progress

- 无跨模块工作流阻塞；各模块状态见 `detail_mem/PROGRESS.md`

## Backlog

- P0：观察真实用户注册/生成链路是否有新问题（尤其移动端）
- P0：**分镜编辑前端接管合成**（Phase 1：Konva `toDataURL` 出 panel.png，`save` 不走 `recompose_scene`）— 解决编辑延迟，方案见 DECISIONS.md 2026-09-16
- P1：`fonts/` 365MB 未入库，服务器靠 tar 上传；考虑字体 CDN 化或精简字重
- P1：账户域与主站 lunwen 完全隔离，若需单点登录（SSO）需额外设计
- P2：`tasks._tasks` / `store._locks` 进程内字典，横向扩容前需要外部化（Redis/DB）
- P2：`output/comic.db` SQLite 仅本地用，生产必须配 `COMIC_MYSQL_*`
- P2：长图排版引擎前端化（Phase 2，`compose.py` Canvas 重写），若做桌面 App 用 Tauri 不打 Python

## 当前必须遵守的约束（快照）

- 服务器只读 deploy key 拉代码；**不直接改服务器文件**，一切走 git push + pull
- `fonts/*`、`projects/*`、`.env` 均 gitignore——服务器上的这些文件是部署时单独放的，pull 不会覆盖
- 服务器 8000/8001 已被主站占用，comic 固定用 **8002**
- 前端 production 必须走同源 API（`/api/*`），不写死 IP/端口

## 相关文档

- 模块实现清单：`memory-docs/detail_mem/PROGRESS.md`
- 部署形态决策：`memory-docs/detail_mem/DECISIONS.md`
- 项目演变：`memory-docs/HISTORY.md`
