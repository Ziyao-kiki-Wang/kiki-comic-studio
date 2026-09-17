---
layer: detail
update_mode: append
role: "决策记录 —— 重要的技术/部署取舍，当前视图 + 理由"
read_when: "要改架构、推翻既有做法、或好奇'为什么这么设计'时"
not_for: "当前进展（-> STATUS），临时探索记录（-> archive/）"
---

# Decisions

> 当前视图只保留仍生效的决策 + 一句话理由。完整演进过程见 `HISTORY.md` 或 archive。

## 部署形态（2026-09-14 定）

| 决策 | 选择 | 理由 / 替代 |
|---|---|---|
| 入口 | `comic.frowang.com` **子域** | 干净独立，不跟主站 cookie/路由挤；替代方案 `frowang.com/comic/` 路径被否 |
| DNS | CNAME → `frowang.com`（Cloudflare Proxied） | 与 api/chat/paper 等现有子域惯例一致；服务器换 IP 只改一处 |
| 证书 | Cloudflare Origin CA 通配符 `*.frowang.com` | 已有证书 2040 年到期，新子域直接复用，不用 certbot 重签 |
| 服务器 | `212.189.107.74`（香港，frowang 生产机） | 复用现有 Python/Node/nginx/MySQL 环境；与 llm-read-paper(8000)、pay-account-service(8001) 共存，comic 用 8002 |
| 反向代理 | nginx `location /api/` → `127.0.0.1:8002`，**不剥前缀** | 前端请求 `/api/auth/captcha` 直接透传，后端路由注册也是 `/api/...` |
| 前端托管 | nginx `root` 指向 `web/dist`（静态） | 前端不走 node 服务，build 即生效 |

## 数据库（2026-09-14 定）

| 决策 | 选择 | 理由 / 替代 |
|---|---|---|
| 生产库 | MySQL `127.0.0.1:3307`，库名 `comic`，独立用户 `comic` | 与主站 `lunwen` **完全隔离**（不共享表/用户），出问题不互相影响 |
| 本地兜底 | 不配 `COMIC_MYSQL_*` → `output/comic.db` SQLite | 本地开发零依赖可跑，`connection.py` 翻译 `%s`→`?` 兼容两种驱动 |
| 表名 | 统一 `comic_` 前缀 | 一眼识别属于漫画工坊，不与主站表混淆 |

## GitHub 访问（2026-09-14 定）

| 决策 | 选择 | 理由 |
|---|---|---|
| 服务器拉代码 | **Deploy Key**（`~/.ssh/comic_deploy_ed25519`，只读） | 不用在服务器放个人 GitHub 密码/PAT；只读权限够用（pull only） |
| 本机双账号 | `github.com`→Rostopher（id_ed25519）、`github-kiki`→Ziyao-kiki-Wang（kiki_ed25519） | SSH config host alias 区分，两个账号共存互不干扰 |
| 署名 | 仓库 local config `user.name=Ziyao-kiki-Wang` + noreply 邮箱 | 历史 Devin 署名已 rewrite（5 个 commit） |

## 前端 API 地址（2026-09-15 修）

| 决策 | 选择 | 理由 |
|---|---|---|
| production | `API_BASE=""`（同源） | 之前写死 `127.0.0.1:8000` 导致手机端请求打到用户自己设备 → 验证码全挂。同源 + nginx 反代后自然走 `comic.frowang.com/api/*` |
| 本地开发 | `VITE_API_BASE` 或默认 `http://127.0.0.1:8000` | 直连后端，CORS 已全开 |
| 超时 | auth 20s / 生图 60s `AbortSignal.timeout` | 大陆→香港链路慢，防无限挂起 |

## 验证码（既有设计）

| 决策 | 选择 | 理由 |
|---|---|---|
| 形态 | 无状态 HMAC token + PIL PNG，TTL 300s | 不依赖 Redis，token 内落答案 hash；一次性 jti 防重放；输错可重试不换新图 |

## 字体 / 素材（既有设计）

| 决策 | 选择 | 理由 |
|---|---|---|
| `fonts/` 365MB 不入 git | gitignore，服务器单独 tar 上传 | 字体二进制太大；`fonts/README.md` 记来源 |
| 贴纸/气泡素材入 git | `web/public/` 73MB 提交 | 前端直接用，体积可控 |

---

## 编辑延迟 / 前端接管合成（2026-09-16 评估，待实施）

| 决策 | 选择 | 理由 / 替代 |
|---|---|---|
| 问题根因 | 每次 `save()` 都 `recompose_scene` → 服务端 Pillow 重画 panel.png 传回 | 延迟不是"传消息"慢，是"服务端栅格化→传图"慢；服务器地理位置只叠加小头 |
| 关键发现 | 前端 `bubbleLayout.js`/`Bubble.jsx`/`EditableText.jsx`/`SceneOverlay`/`LongSceneOverlay` 已完整复刻 `bubbles.py`/`compose.py` 的几何与层级 | Konva 画布**所见即所得**，差距只剩"画布→PNG"这一步导出 |
| 改造方向 | Phase 1：Konva `stage.toDataURL()` 前端出 panel.png，`save()` 不再走 `recompose_scene`；Phase 2：长图排版引擎(`compose.py`+`page_layouts.py`+`headings.py`)前端 Canvas 重写 | Phase 1 改动小收益最大；Phase 2 是大工程可延后。Electron 打包现有 Python 后端被否——等于把服务端 Pillow 背上每个用户电脑 |
| 桌面化建议 | 若做桌面 App 用 **Tauri**（前端已本地化，只打 WebView 壳），不打 Python 运行时 | Electron 打包"重后端"是绕远路；先前端接管合成再谈壳 |

## 已废弃 / 被替代的做法

- ~~`frowang.com/comic/` 路径挂载~~ → 改用 `comic.frowang.com` 子域（更干净）
- ~~前端写死 `http://127.0.0.1:8000`~~ → production 改同源（2026-09-15 修复移动端验证码 bug）
- ~~rembg / BiRefNet 本地抠图~~ → 透明模式改由生图模型直接输出透明 PNG
