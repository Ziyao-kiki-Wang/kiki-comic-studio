---
layer: framework
update_mode: patch
role: "项目术语表 —— 业务/技术名词的统一定义"
read_when: "遇到项目特有名词不确定含义时"
not_for: "代码实现细节（-> MAP.md / 源码）"
---

# Glossary

## 业务概念

| 术语 | 含义 |
|---|---|
| **分镜** | 漫画的一格。一个项目含若干分镜，每格有场景、出场人物、台词、画面描述 |
| **故事表** | `storyboard.json`，记录项目的故事结构：分镜列表 + 每格剧情/台词/旁白 |
| **长图** | 最终导出的成品，1080px 宽的竖向 PNG，按选中的排版模板把分镜串成一条 |
| **工作台** | 前端主界面，四步流程：分镜制作 → 画面精修 → 作品排版 → 贴纸装饰 |
| **画面精修** | 单格编辑：拖气泡、改台词、AI 改图、手机屏幕特写、单格贴图、多选组合 |
| **排版模板** | 长图样式，17 种（清爽科普/手账/国风长卷/电影胶片等），定义在 `schemas/` |
| **透明主体** | 生图模式：直接输出透明背景 PNG，人物+道具作为整体，外围透明 |
| **本格专属参考** | 给某一格单独上传角色参考图，只影响这一格的生图 |
| **单格贴图** | 往某一格上叠加 PNG/JPEG/WebP，可拖动/缩放/旋转/调透明度 |
| **手机屏幕特写** | 分镜里有手机时，单独生成屏幕内容特写图叠加在分镜上 |
| **邀请码** | 注册必填，`comic_invitation_code` 表，由 `scripts/seed_invitation_codes.py` 生成 |
| **积分** | 账户余额，`comic_people.points`，生图扣积分 |

## 技术名词

| 术语 | 含义 |
|---|---|
| `comic_` 前缀 | MySQL 表名前缀，与主站 `lunwen` 库完全隔离 |
| `projects/<id>/` | 项目数据目录，含 storyboard、scenes、素材、成品 |
| `schemas/` | 模板/字体/气泡/贴纸的 JSON 配置定义，不是代码 |
| `detail_mem/` | memory-docs 详细层：MAP（代码导航）/PROGRESS（模块状态）/DECISIONS（决策） |
| deploy key | GitHub 只读部署密钥，服务器用它 `git pull`，不能 push |
| 同源 API | 前端 production 模式下 `API_BASE=""`，请求走当前域名 `/api/*` 由 nginx 反代 |
