# -*- coding: utf-8 -*-
"""
小样测试 02：完整流程（主题 → 故事表 → 人物 → 场景 → 气泡文字 → 长图）

用法（在 spike 目录下）：
    .venv/Scripts/python.exe 02_full_pipeline.py [图片张数]
    例如：.venv/Scripts/python.exe 02_full_pipeline.py 4

每一步的产物都缓存在 output/ 里，跑过的步骤自动跳过、不重复扣费：
    storyboard.json   故事表（可以手工改，改完删掉后续产物重跑即可）
    characters/*.png  人物标准照
    scene_XX_raw.png  原始场景图（AI 画的，不带字）
    scene_XX.png      加了气泡和说明文字的场景图
    长图.png           最终成品
"""

import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

SPIKE_DIR = Path(__file__).resolve().parent
OUT_DIR = SPIKE_DIR / "output"
CHAR_DIR = OUT_DIR / "characters"
CHAR_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(SPIKE_DIR / ".env")
client = OpenAI()

CHAT_MODEL = "gpt-5.6-sol"    # 写故事表用的模型（便宜的那个）
IMAGE_MODEL = "gpt-image-2"   # 画图模型

STYLE = "clean Chinese commercial comic style, soft clean lines, flat shading, bright warm colors, simple shapes"
NEG = "no text, no words, no letters, no speech bubble, no watermark"

# 本次主题：客户下载不明 APP，银行卡被盗刷
TOPIC = (
    "一位中老年客户轻信陌生链接，下载了不明来源的APP，"
    "结果银行卡里的钱被骗子盗刷走了。通过这个故事提醒大家："
    "不要下载不明APP，涉及银行卡操作先向银行核实。"
)

PANEL_W = 1080          # 公众号长图标准宽度
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",    # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",  # 黑体
    "C:/Windows/Fonts/simsun.ttc",  # 宋体
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ---------- 第 1 步：LLM 写故事表 ----------

def step1_storyboard(scene_count: int) -> dict:
    sb_path = OUT_DIR / "storyboard.json"
    if sb_path.exists():
        print("第 1 步：storyboard.json 已存在，直接沿用（可手工修改后删掉场景图重跑）")
        return json.loads(sb_path.read_text(encoding="utf-8"))

    print(f"第 1 步：让 {CHAT_MODEL} 写故事表（{scene_count} 张图）……")
    prompt = f"""你是一个漫画编剧。请根据下面的主题，写一部 {scene_count} 格漫画的故事表。

主题：{TOPIC}

要求：
1. 对话口语化、简短，每格 1-3 句对话，说明文字（caption）一句话。
2. 人物 2 个左右，人物外貌穿着的英文描述要具体（发型、脸型、年龄、衣服），方便画图。
3. 只输出 JSON，不要任何其他文字。JSON 格式如下：

{{
  "title": "漫画标题",
  "characters": [
    {{"character_id": "英文编号如 customer_01", "name": "中文名", "role": "身份",
      "english_desc": "英文外貌穿着描述"}}
  ],
  "scenes": [
    {{"scene_id": "scene_01", "location": "地点",
      "characters": ["出场人物的 character_id"],
      "story": "这一格发生了什么",
      "dialogues": [{{"speaker": "character_id", "text": "台词"}}],
      "caption": "图下方的说明文字",
      "scene_prompt_en": "英文画面描述：场景、人物动作、表情，不要包含任何文字元素"}}
  ]
}}"""
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    text = r.choices[0].message.content
    # 容错：从返回里提取 JSON（有的模型会在外面包一层废话）
    match = re.search(r"\{.*\}", text, re.DOTALL)
    sb = json.loads(match.group(0))
    sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已保存：storyboard.json（标题：{sb.get('title')}）")
    return sb


# ---------- 第 2 步：画人物标准照 ----------

def step2_characters(sb: dict) -> dict:
    print("第 2 步：画人物标准照……")
    ref_paths = {}
    for ch in sb["characters"]:
        path = CHAR_DIR / f"{ch['character_id']}.png"
        ref_paths[ch["character_id"]] = path
        if path.exists():
            print(f"  {ch['character_id']} 已存在，跳过")
            continue
        print(f"  画 {ch['name']}（{ch['character_id']}）……（约 1 分钟）")
        prompt = f"{ch['english_desc']}, full body, front view, standing, plain light gray background, {STYLE}, {NEG}"
        r = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1536")
        save_result(r, path)
    return ref_paths


# ---------- 第 3 步：拿标准照当参考，画每格场景 ----------

def step3_scenes(sb: dict, ref_paths: dict):
    print("第 3 步：画场景图……")
    for scene in sb["scenes"]:
        raw_path = OUT_DIR / f"{scene['scene_id']}_raw.png"
        if raw_path.exists():
            print(f"  {scene['scene_id']} 已存在，跳过")
            continue
        chars_in_scene = [c for c in sb["characters"] if c["character_id"] in scene["characters"]]
        char_hint = "; ".join(f"{c['name']}: {c['english_desc']}" for c in chars_in_scene)
        prompt = (
            f"{scene['scene_prompt_en']}. "
            f"The scene contains exactly these people: {char_hint}. "
            f"They must look EXACTLY like the reference image(s) — same faces, hairstyles and clothes. "
            f"{STYLE}, {NEG}"
        )
        refs = [open(ref_paths[c["character_id"]], "rb") for c in chars_in_scene]
        print(f"  画 {scene['scene_id']}（{scene['location']}）……（约 1 分钟）")
        try:
            r = client.images.edit(model=IMAGE_MODEL, image=refs, prompt=prompt, size="1536x1024")
            save_result(r, raw_path)
        finally:
            for f in refs:
                f.close()


# ---------- 第 4 步：加气泡和说明文字（程序画，不是 AI 画） ----------

def wrap_text(draw, text, font, max_width):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def draw_bubble(draw, text, slot_x, slot_y, side, font):
    """画一个气泡：圆角白底框 + 指向说话人的小尾巴 + 自动换行的文字"""
    max_w = 420
    pad = 22
    line_h = font.size + 14
    lines = wrap_text(draw, text, font, max_w - pad * 2)
    box_h = pad * 2 + line_h * len(lines) - 14
    x1, y1, x2, y2 = slot_x, slot_y, slot_x + max_w, slot_y + box_h
    draw.rounded_rectangle([x1, y1, x2, y2], radius=24, fill="white", outline="#333333", width=4)
    tail_x = x1 + 70 if side == "left" else x2 - 100
    draw.polygon([(tail_x, y2 - 2), (tail_x + 60, y2 - 2), (tail_x + (0 if side == "left" else 60), y2 + 46)],
                 fill="white", outline="#333333")
    for i, line in enumerate(lines):
        draw.text((x1 + pad, y1 + pad + i * line_h), line, font=font, fill="#222222")


def step4_lettering(sb: dict):
    print("第 4 步：加气泡和说明文字……")
    bubble_font = load_font(36)
    caption_font = load_font(34)
    slots = [(50, 40, "left"), (PANEL_W - 470, 40, "right"), (50, 280, "left")]

    for scene in sb["scenes"]:
        out_path = OUT_DIR / f"{scene['scene_id']}.png"
        if out_path.exists():
            print(f"  {scene['scene_id']} 已排版，跳过")
            continue
        raw = Image.open(OUT_DIR / f"{scene['scene_id']}_raw.png").convert("RGB")
        panel = raw.resize((PANEL_W, int(raw.height * PANEL_W / raw.width)))
        # 画面下方加一条说明文字区域
        canvas = Image.new("RGB", (PANEL_W, panel.height + 100), "#ffffff")
        canvas.paste(panel, (0, 0))
        draw = ImageDraw.Draw(canvas)
        for i, dlg in enumerate(scene["dialogues"][:3]):
            draw_bubble(draw, dlg["text"], *slots[i], font=bubble_font)
        cap = scene["caption"]
        cap_w = draw.textlength(cap, font=caption_font)
        draw.text(((PANEL_W - cap_w) / 2, panel.height + 28), cap, font=caption_font, fill="#444444")
        canvas.save(out_path)
        print(f"  已保存：{out_path.name}")


# ---------- 第 5 步：拼长图 ----------

def step5_long_image(sb: dict):
    print("第 5 步：拼长图……")
    panels = [Image.open(OUT_DIR / f"{s['scene_id']}.png") for s in sb["scenes"]]
    gap, header_h = 50, 220
    total_h = header_h + sum(p.height for p in panels) + gap * (len(panels) + 1)
    long_img = Image.new("RGB", (PANEL_W, total_h), "#f2f4f8")
    draw = ImageDraw.Draw(long_img)
    # 标题头
    draw.rectangle([0, 0, PANEL_W, header_h], fill="#1a3a6b")
    title_font = load_font(64)
    title = sb.get("title", "漫画")
    tw = draw.textlength(title, font=title_font)
    draw.text(((PANEL_W - tw) / 2, (header_h - title_font.size) / 2 - 10), title, font=title_font, fill="white")
    # 依次贴每一格
    y = header_h + gap
    for p in panels:
        long_img.paste(p, (0, y))
        y += p.height + gap
    out_path = OUT_DIR / "长图.png"
    long_img.save(out_path)
    print(f"\n完成！最终成品：{out_path}（{PANEL_W}×{total_h}）")


# ---------- 工具 ----------

def save_result(result, path: Path):
    d = result.data[0]
    if getattr(d, "b64_json", None):
        import base64
        path.write_bytes(base64.b64decode(d.b64_json))
    elif getattr(d, "url", None):
        import urllib.request
        urllib.request.urlretrieve(d.url, path)
    else:
        raise RuntimeError("API 返回里既没有 b64_json 也没有 url，请把这条错误发给我")


if __name__ == "__main__":
    scene_count = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f"主题：{TOPIC}\n张数：{scene_count}\n")
    sb = step1_storyboard(scene_count)
    refs = step2_characters(sb)
    step3_scenes(sb, refs)
    step4_lettering(sb)
    step5_long_image(sb)
