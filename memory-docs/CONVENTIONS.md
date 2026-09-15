---
layer: framework
update_mode: patch
role: "硬规则与工作约定 —— 部署、代码、数据、安全上必须遵守的约束"
read_when: "做任何修改/部署前，按任务定位相关规则"
not_for: "临时进展（-> STATUS），历史原因（-> HISTORY）"
---

# Conventions

## 部署（最重要，容易踩坑）

| 规则 | 说明 |
|---|---|
| **服务器目录** | `/home/website/comic-generator/`，`git pull` 生效 |
| **服务重启** | 改了 `server/` 必须 `systemctl restart comic-generator`；改了 `web/` 必须 `npm run build` 重建 `dist/` |
| **只读 deploy key** | 服务器用 `~/.ssh/comic_deploy_ed25519` 只读拉 GitHub，**不要在服务器上改代码再 commit** |
| **端口** | 8000=llm-read-paper、8001=pay-account-service 已占用；**comic 固定 8002** |
| **gitignore 资产** | `fonts/`(365MB)、`projects/`、`.env` 不入库，服务器上是部署时单独放的，pull 不动它们 |
| **nginx** | 单文件 `/etc/nginx/conf.d/frowang.conf`，改前备份；`nginx -t && systemctl reload nginx` |
| **证书** | Cloudflare Origin CA 通配符 `*.frowang.com`（2040 年到期），新子域直接复用，不用重签 |
| **回滚** | `git reset --hard <sha>` 高风险，需明确授权；优先 `git revert` |

## 环境变量 / 密钥

| 变量 | 用途 | 位置 |
|---|---|---|
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | 生图/写故事的 LLM 服务 | 本地 `spike/.env` 兜底加载；生产在服务器 `.env` |
| `COMIC_JWT_KEY_HEX` | 登录 token 验签（必填，缺失拒绝启动） | `.env` |
| `COMIC_CAPTCHA_SECRET` | 图形验证码签名（必填） | `.env` |
| `COMIC_MYSQL_*` | 生产数据库；不配则本地落 `output/comic.db` SQLite | `.env` |
| `COMIC_PROJECTS_DIR` | 覆盖 `projects/` 路径（测试/隔离用） | 可选 |

`.env` 永远不 commit；服务器 `.env` 在 `/home/website/comic-generator/.env`（chmod 600）。

## 数据库

- 生产 MySQL `127.0.0.1:3307`，库名 `comic`，用户 `comic`（只能访问 `comic.*`，与主站 `lunwen` 完全隔离）
- 表名统一 `comic_` 前缀：`comic_people / comic_points / comic_project / comic_invitation_code / comic_login_errorlog / comic_app_config`
- 建表：`migrations/001_init_account.sql`，幂等 `CREATE TABLE IF NOT EXISTS`
- 代码里 SQL 写 `%s` 占位；`connection.py` 的 `_strip_mysql_syntax` 负责 SQLite/MySQL 双语兼容

## 前端 API 约定（踩过的坑）

- **production 必须同源**：`API_BASE` 在 `import.meta.env.PROD` 时是 `""`，请求走 `comic.frowang.com/api/*` → nginx 反代。**绝对不要写死 IP:端口**（2026-09-15 因此导致移动端验证码全挂）
- `VITE_API_BASE` 仅用于本地开发覆盖
- 三个文件共用同一约定：`web/src/lib/api.js` `authApi.js` `studioAssets.js`——改一处必须改全部

## 代码风格

- 后端：Python，类型注解，FastAPI router 按域拆（`routers/`）；core 不依赖 api 层
- 前端：React 函数组件 + hooks；画布交互用 Konva；API 集中在 `lib/api.js` `lib/authApi.js`
- 提交：Conventional Commits（`feat|fix|docs|chore(server|web|account|story)`）

## 数据 / 文件

- 项目数据：`projects/<project_id>/`，`storyboard.json` 为故事主数据，`scenes/<scene_id>.json` 为分镜编辑态，`output/长图.png` 为成品
- 字体：`fonts/` 共享字体（17 款），项目可上传覆盖；路径相对仓库根
- 素材：`web/public/bubble-assets/`、`sticker-assets/` 在 git 里；`fonts/` 在 gitignore
- 大文件：单张角色图 ≤8MB，字体 ≤32MB，nginx `client_max_body_size 40m`

## 测试 / 验证

- 后端行为测试不调付费生图接口（`pytest tests/test_studio.py -q`）
- `scripts/validate_studio.py` 生成全部模板预览到 `output/qa-projects/`
- 服务器验证：`curl http://127.0.0.1:8002/openapi.json` 数路由；`/api/auth/captcha` 应返回 `{success:true}`
