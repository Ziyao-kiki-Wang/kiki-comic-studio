# 漫画生成 Agent 字体包

为你的漫画气泡 / 标题 / 正文准备的字体文件集合。所有文件按"无衬线优先 + 衬线可选"组织，每个字重单独一个文件，便于 Python (Pillow)、React (Konva)、PptxGenJS 直接引用。

存放路径：`C:\Users\2023\Desktop\comic-fonts\`

---

## 📦 实际交付清单（你可以直接看的）

### 1. `microsoft-yahei/` — 微软雅黑（Windows 自带 ✅ 已复制到本地）

| 文件名 | 包含字重 | 用途 |
|--------|---------|------|
| `msyh.ttc` | index 0: Regular (400), index 1: UI Regular | 微软雅黑 Regular |
| `msyhl.ttc` | index 0: Light (290), index 1: UI Light | 微软雅黑 Light（附加） |
| `msyhbd.ttc` | index 0: Bold (700), index 1: UI Bold | 微软雅黑 Bold |

> 说明：`msyh.ttc` 里**只有 Regular**，`msyhbd.ttc` 里**只有 Bold**（不是某些老资料说的"一个含多种字重"）。
> 也就是说 Windows 11 当前发布版已经把这两个字重拆成独立文件了，所以代码里直接引 `msyh.ttc` 就是 Regular，`msyhbd.ttc` 就是 Bold，不用 `index` 参数。

### 2. `source-han-sans/` — 思源黑体（开源，替代"方正兰亭黑"系列 ✅ 已下载）

| 文件名 | 字重 (usWeightClass) | 你原本要的方正字体 |
|--------|---------------------|--------------------|
| `SourceHanSansSC-ExtraLight.otf` | 100 | 方正兰亭黑-细（最接近）|
| `SourceHanSansSC-Light.otf` | 300 | 方正兰亭黑-纤细 |
| `SourceHanSansSC-Normal.otf` | 350 | （常规补充）|
| `SourceHanSansSC-Regular.otf` | 400 | 方正兰亭黑-常规 |
| `SourceHanSansSC-Medium.otf` | 500 | 方正兰亭黑-中粗 |
| `SourceHanSansSC-Bold.otf` | 700 | 方正兰亭黑-粗黑 |
| `SourceHanSansSC-Heavy.otf` | 900 | 方正兰亭黑-加粗 |

### 3. `source-han-serif/` — 思源宋体（开源，替代"方正大雅宋"系列 ✅ 已下载）

| 文件名 | 字重 (usWeightClass) | 你原本要的方正字体 |
|--------|---------------------|--------------------|
| `SourceHanSerifSC-ExtraLight.otf` | 100 | 方正细雅宋（最细）|
| `SourceHanSerifSC-Light.otf` | 300 | 方正细雅宋 |
| `SourceHanSerifSC-Regular.otf` | 400 | 方正大雅宋 |
| `SourceHanSerifSC-Medium.otf` | 500 | 方正大雅宋（中等）|
| `SourceHanSerifSC-SemiBold.otf` | 600 | 方正中粗雅宋 |
| `SourceHanSerifSC-Bold.otf` | 700 | 方正中粗雅宋（接近）|
| `SourceHanSerifSC-Heavy.otf` | 900 | 方正中粗雅宋-粗 |

---

## 🔍 为什么用"思源字体"替代"方正字体"？

| 项目 | 方正（你原本要的） | 思源（实际给你的） |
|------|-------------------|-------------------|
| 字形气质 | 中文黑体/宋体经典代表 | 中文黑体/宋体开源经典，字形气质一致 |
| 协议 | **商业字体**，商用需付费授权 | **SIL OFL 1.1 开源**，可商用 |
| 字符集 | 简繁日韩越齐全 | 简繁日韩齐全（已选 SC 子集）|
| 体积 | 单字重一般 ~10-15 MB | 单字重 ~15-25 MB |
| 文件格式 | 主要是 TTF | OTF（OpenType，更现代）|

**你的项目已经预留了字体名称位置，建议：**
- 不要去改代码里已经写好的"方正兰亭黑"等名字 — 改成对应的思源 OTF 文件就行
- 思源黑体 → 替代"兰亭黑系列"
- 思源宋体 → 替代"大雅宋系列"

---

## 💻 使用示例

### Python (Pillow) — 你的后端漫画渲染

```python
from PIL import Image, ImageDraw, ImageFont

# 微软雅黑（TTC，文件本身就是 Regular 或 Bold）
font_yahei_regular = ImageFont.truetype("comic-fonts/microsoft-yahei/msyh.ttc", size=24)
font_yahei_bold    = ImageFont.truetype("comic-fonts/microsoft-yahei/msyhbd.ttc", size=24)

# 思源黑体（无衬线，按字重加载）
font_sans_light   = ImageFont.truetype("comic-fonts/source-han-sans/SourceHanSansSC-Light.otf", 24)
font_sans_regular = ImageFont.truetype("comic-fonts/source-han-sans/SourceHanSansSC-Regular.otf", 24)
font_sans_bold    = ImageFont.truetype("comic-fonts/source-han-sans/SourceHanSansSC-Bold.otf", 24)

# 思源宋体（衬线，按字重加载）
font_serif_light   = ImageFont.truetype("comic-fonts/source-han-serif/SourceHanSerifSC-Light.otf", 24)
font_serif_regular = ImageFont.truetype("comic-fonts/source-han-serif/SourceHanSerifSC-Regular.otf", 24)
font_serif_semibold= ImageFont.truetype("comic-fonts/source-han-serif/SourceHanSerifSC-SemiBold.otf", 24)
```

### React + Konva — 你的前端漫画编辑/预览

Konva 通过 `fontFamily` 引用字体，需要先用 `@font-face` 声明或把字体放到 public/fonts：

```js
// 方式 A：用 @fontsource npm 包（推荐，已把 OTF 转成 WOFF2 内置）
// npm i @fontsource/noto-sans-sc @fontsource/noto-serif-sc
import '@fontsource/noto-sans-sc/400.css';  // Regular
import '@fontsource/noto-sans-sc/700.css';  // Bold
import '@fontsource/noto-serif-sc/400.css';
// Noto Sans CJK / Noto Serif CJK 与 Source Han Sans / Source Han Serif 同一字体家族，
// 是 Google 在 GitHub 上提供的 webfont 重新打包版，名称改成了 Noto。

// 方式 B：用本地的 OTF 直接放到 public/fonts，再用 @font-face 声明
new Konva.Text({
  text: '你这个想法很有意思！',
  fontFamily: '"Source Han Sans SC", "Microsoft YaHei", sans-serif',
  fontStyle: 'bold',  // Konva 自动匹配 -Bold.otf
  fontSize: 24,
  fill: '#000',
});
```

> Konva 的 `fontStyle` 支持 `normal | bold | italic | bold italic`，跟你的字体文件名后缀（`Regular/Bold`）对应。

### PptxGenJS — 导出 PPTX

```js
import Pptxgen from "pptxgenjs";
const pptx = new Pptxgen();

// 定义字体别名（PPT 不嵌入字体，依赖打开 PPT 的电脑装了对应字体）
pptx.defineFont({ alias: "TitleYahei",   face: "微软雅黑" });
pptx.defineFont({ alias: "BodyHanSans",  face: "Source Han Sans SC" });
pptx.defineFont({ alias: "BodyHanSerif", face: "Source Han Serif SC" });

pptx.addText("漫画标题", {
  fontFace: "TitleYahei", fontSize: 32, bold: true,
});
pptx.addText("正文/对白", {
  fontFace: "BodyHanSans", fontSize: 18,
});
```

> **关键点**：PptxGenJS 不嵌入字体文件，所以请你和最终打开 PPTX 的电脑**都先安装这些 OTF/TTC**。

---

## 📥 字体来源与版本

| 字体 | 版本 | 下载源 |
|------|------|--------|
| 微软雅黑 | Windows 11 22H2 / 23H2 系统自带 | `C:\Windows\Fonts\` |
| 思源黑体 (Source Han Sans) | 2.005R（2025-06） | https://github.com/adobe-fonts/source-han-sans/releases/tag/2.005R |
| 思源宋体 (Source Han Serif) | 2.003R | https://github.com/adobe-fonts/source-han-serif/releases/tag/2.003R |

通过 **gh-proxy.com** 镜像下载（原始 GitHub 域名在当前网络下握手失败，镜像可达）。

---

## 📜 版权与合规

| 字体 | 协议 | 商用 |
|------|------|------|
| 微软雅黑 | Windows EULA | 视授权情况（一般办公场景随 Windows 即可） |
| 思源黑体 | SIL OFL 1.1 | ✅ 免费商用 |
| 思源宋体 | SIL OFL 1.1 | ✅ 免费商用 |

SIL OFL 1.1 简要：
- ✅ 可商用
- ✅ 可修改
- ⚠️ 修改后再分发不能沿用原名
- ⚠️ 必须随附协议文本（思源字体的 GitHub release 里有 `LICENSE.txt`）

---

## 🔧 安装到 Windows 系统（可选）

如果希望 Word / Photoshop / 浏览器等系统级可用：

1. 打开 `comic-fonts` 目录
2. 全选所有 `*.otf` 文件 → 右键 → "为所有用户安装" 或 "安装"
3. 等待字体管理器加载完成
4. 在 Word 里能看到 "Source Han Sans SC" 和 "Source Han Serif SC" 的多个字重

---

## 📂 最终目录结构

```
C:\Users\2023\Desktop\comic-fonts\
├── README.md                              ← 你正在看的文件
│
├── microsoft-yahei/
│   ├── msyh.ttc                           (Regular + UI Regular)
│   ├── msyhbd.ttc                         (Bold + UI Bold)
│   └── msyhl.ttc                          (Light + UI Light)
│
├── source-han-sans/                       (7 个字重 OTF)
│   ├── SourceHanSansSC-ExtraLight.otf
│   ├── SourceHanSansSC-Light.otf
│   ├── SourceHanSansSC-Normal.otf
│   ├── SourceHanSansSC-Regular.otf
│   ├── SourceHanSansSC-Medium.otf
│   ├── SourceHanSansSC-Bold.otf
│   └── SourceHanSansSC-Heavy.otf
│
└── source-han-serif/                      (7 个字重 OTF)
    ├── SourceHanSerifSC-ExtraLight.otf
    ├── SourceHanSerifSC-Light.otf
    ├── SourceHanSerifSC-Regular.otf
    ├── SourceHanSerifSC-Medium.otf
    ├── SourceHanSerifSC-SemiBold.otf
    ├── SourceHanSerifSC-Bold.otf
    └── SourceHanSerifSC-Heavy.otf
```

---

_由 WorkBuddy 整理于 2026-09-09_
