---
layer: framework
update_mode: append
role: "项目演进史 —— 关键阶段、转折、重大事件的时间线"
read_when: "想了解项目怎么走到今天，或追溯某个功能是什么时候上的"
not_for: "当前快照（-> STATUS），决策理由（-> detail_mem/DECISIONS.md）"
---

# History

## 2026-09-15 — 修复编辑器点开格子主画布空白

**问题**：点进某格编辑时，右侧主画布只剩棋盘格（透明底），主体、气泡、文字全不渲染；但左侧分镜缩略图正常。

**根因**：`SceneEditor.jsx` 的 `useImage` 给 `new Image()` 设了 `crossOrigin="anonymous"`，把同源 `?token=` 图片请求变成 CORS fetch。当响应缺少可用的 `Access-Control-Allow-Origin` 时 `onload` 不触发 → `bg` 永远 null → 透明模式主体 `{transparent && bg && <KonvaImage/>}` 画不出。缩略图走普通 `<img>`（无 crossOrigin）不受影响，所以能显示。

**修复**：删掉 `useImage` 里的 `img.crossOrigin="anonymous"`。图片是同源 + `?token=` 鉴权，本就不需要 CORS 标记。commit `aae31ac`，服务器 pull + `web/ npm build` 生效（纯静态，无需重启）。

**教训**：
- 前端用 `new Image()`/`useImage` 预加载**同源、已带 query token** 的图片时，**不要加 `crossOrigin="anonymous"`**——它会把请求升级成 CORS fetch，代理链路上 ACAO 缺失时静默加载失败，且这类 bug 只在"canvas 预加载"路径暴露，普通 `<img>` 显示正常，极具迷惑性。
- 同类排查套路：缩略图能显示、主画布空白 → 先怀疑 `useImage`/canvas 预加载路径与 `<img>` 的差异（crossOrigin、referrerpolicy、webp 解码），而不是文件本身。

## 2026-09-15 — 修复移动端验证码加载失败

**问题**：手机用户打开 `comic.frowang.com` 验证码加载失败。

**根因**：前端 `API_BASE` 写死 `http://127.0.0.1:8000`。`127.0.0.1` 在手机端指向用户自己设备，不是服务器 → 请求根本发不出去。桌面端能用是因为开发者本机恰好跑着 8000 后端。

**修复**：
- `web/src/lib/api.js`、`authApi.js`、`studioAssets.js` 三处 `API_BASE` 改为 `PROD` 下 `""`（同源，走 nginx `/api` 反代），本地开发仍可用 `VITE_API_BASE` 覆盖
- 加 `AbortSignal.timeout`：auth 20s、生图 60s，兜底慢网络
- commit `0feb815`，服务器 pull + rebuild + restart 生效

**教训**：production 环境绝对不要写死 `127.0.0.1` 或内网 IP——`127.0.0.1` 在客户端是"用户自己的设备"。

## 2026-09-14 — 生产部署上线

- GitHub 仓库 `Ziyao-kiki-Wang/kiki-comic-studio`，服务器走 deploy key 拉取
- 服务器 `/home/website/comic-generator/`：Python venv + `pip install -r requirements.txt` + `web/ npm build` → `dist/`
- `fonts/` 365MB 不入库，本地 tar 流式传到服务器（微软雅黑 + 思源黑体 + 思源宋体）
- MySQL `comic` 库 + `comic` 用户 + `migrations/001_init_account.sql` 建 6 张表
- systemd `comic-generator.service` → `127.0.0.1:8002`（8000/8001 已被主站占用）
- nginx `comic.frowang.com` server block：443 + 通配证书 + `/api` 反代 8002 + 静态 `dist`
- `scripts/seed_invitation_codes.py` seed 邀请码
- 端到端验证：`/api/auth/captcha` 返回 token + PNG

## 2026-09-14 — 仓库迁移与署名清理

- 本地仓库配双 GitHub 账号：`github.com`→Rostopher、`github-kiki`→Ziyao-kiki-Wang（SSH host alias + 双 key）
- remote 改 `git@github-kiki:Ziyao-kiki-Wang/kiki-comic-studio.git`
- 历史 5 个 Devin 署名 commit 全部 `git rebase --root --exec 'commit --amend --reset-author'` 重写为 Ziyao-kiki-Wang，force push
- README 重写：从开发文档改为面向新人的项目介绍，加工作台+成品长图截图

## 更早 — 项目演进主线

（按 git log 倒序，见 commit message）

- `feat(account)` 账户域：独立注册/登录/积分/邀请码，与主站 lunwen 隔离
- `feat(story)` 故事驱动分镜：角色参考图 + 表现风格，去掉 prop manifest
- `feat(web)` React 工作台 + 内置视觉素材（气泡/贴纸/风格预览）
- `feat(server)` 漫画生成 pipeline + FastAPI 后端
- `chore(core)` 初始化：docs + gitignore + 需求清单
