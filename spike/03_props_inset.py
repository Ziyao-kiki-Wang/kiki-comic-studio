# -*- coding: utf-8 -*-
"""
小样测试 03：道具一致性 + 手机屏幕特写框
----------------------------------------
在 02 的基础上新增两个能力：
1. 道具（手机等）也有"标准照"，画场景时和人物标准照一起当参考图 → 道具不走样
2. 展示手机屏幕时，人物正常拿手机（背面朝观众），
   屏幕内容由 AI 单独生成，作为"特写框"贴在画面角落

产物都在 output_demo/ 里（和 02 的 output/ 互不干扰），跑过的步骤自动跳过。

用法（在 spike 目录下）：
    .venv/Scripts/python.exe 03_props_inset.py [图片张数]
"""

import base64
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

SPIKE_DIR = Path(__file__).resolve().parent
OUT_DIR = SPIKE_DIR / "output_demo"
CHAR_DIR = OUT_DIR / "characters"
PROP_DIR = OUT_DIR / "props"
SCREEN_DIR = OUT_DIR / "screens"
for d in (CHAR_DIR, PROP_DIR, SCREEN_DIR):
    d.mkdir(parents=True, exist_ok=True)

load_dotenv(SPIKE_DIR / ".env")
client = OpenAI()

CHAT_MODEL = "gpt-5.6-sol"
IMAGE_MODEL = "gpt-image-2"

STYLE = "clean Chinese commercial comic style, soft clean lines, flat shading, bright warm colors, simple shapes"
NEG = "no text, no words, no letters, no speech bubble, no watermark"

TOPIC = (
    "一位中老年客户轻信陌生链接，下载了不明来源的APP，"
    "结果银行卡里的钱被骗子盗刷走了。通过这个故事提醒大家："
    "不要下载不明APP，涉及银行卡操作先向银行核实。"
)

PANEL_W = 1080
INSET_W = 320          # 特写框宽度
INSET_H = 480          # 特写框高度
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def save_result(result, path: Path):
    d = result.data[0]
    if getattr(d, "b64_json", None):
        path.write_bytes(base64.b64decode(d.b64_json))
    elif getattr(d, "url", None):
        import urllib.request
        urllib.request.urlretrieve(d.url, path)
    else:
        raise RuntimeError("API 返回里既没有 b64_json 也没有 url")


# ---------- 第 1 步：LLM 写故事表（含道具清单 + 特写框设计） ----------

def step1_storyboard(scene_count: int) -> dict:
    sb_path = OUT_DIR / "storyboard.json"
    if sb_path.exists():
        print("第 1 步：storyboard.json 已存在，直接沿用")
        return json.loads(sb_path.read_text(encoding="utf-8"))

    print(f"第 1 步：让 {CHAT_MODEL} 写故事表（{scene_count} 张图，含道具和特写框）……")
    prompt = f"""你是一个漫画编剧。请根据下面的主题，写一部 {scene_count} 格漫画的故事表。

主题：{TOPIC}

要求：
1. 对话口语化、简短，每格 1-3 句对话，说明文字（caption）一句话。
2. 人物 2 个左右，外貌穿着的英文描述要具体（发型、脸型、年龄、衣服）。
3. 故事里反复出现的重要道具（如手机、银行卡、宣传单）列入 props，附英文外观描述。
4. 如果某一格需要展示手机屏幕内容：不要让人物反拿手机！在 scene_prompt_en 里写
   "holds the phone naturally, the back of the phone facing the viewer, looking down at it,
   the phone screen is NOT visible"，并给这一格加 screen_inset，
   在 screen_prompt_en 里详细描述手机屏幕上显示的界面，包括界面上要出现的中文文字内容。
   不需要展示屏幕的格子，screen_inset 填 null。
5. 只输出 JSON，不要任何其他文字。JSON 格式如下：

{{
  "title": "漫画标题",
  "characters": [
    {{"character_id": "英文编号", "name": "中文名", "role": "身份",
      "english_desc": "英文外貌穿着描述"}}
  ],
  "props": [
    {{"prop_id": "英文编号", "name": "中文名", "english_desc": "英文外观描述"}}
  ],
  "scenes": [
    {{"scene_id": "scene_01", "location": "地点",
      "characters": ["出场人物 id"],
      "props": ["出场道具 id"],
      "story": "这一格发生了什么",
      "dialogues": [{{"speaker": "character_id", "text": "台词"}}],
      "caption": "图下方说明文字",
      "scene_prompt_en": "英文画面描述，不含任何文字元素",
      "screen_inset": null}}
  ]
}}"""
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    text = r.choices[0].message.content
    sb = json.loads(re.search(r"\{.*\}", text, re.DOTALL).group(0))
    sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已保存：storyboard.json（标题：{sb.get('title')}）")
    return sb


# ---------- 第 2 步：画人物标准照 + 道具标准照 ----------

def step2_reference_sheets(sb: dict):
    print("第 2 步：画人物/道具标准照……")
    refs = {}
    for ch in sb["characters"]:
        path = CHAR_DIR / f"{ch['character_id']}.png"
        refs[ch["character_id"]] = path
        if path.exists():
            print(f"  {ch['character_id']} 已存在，跳过")
            continue
        print(f"  画人物 {ch['name']}……（约 1 分钟）")
        prompt = f"{ch['english_desc']}, full body, front view, standing, plain light gray background, {STYLE}, {NEG}"
        save_result(client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1536"), path)
    for prop in sb.get("props", []):
        path = PROP_DIR / f"{prop['prop_id']}.png"
        refs[prop["prop_id"]] = path
        if path.exists():
            print(f"  {prop['prop_id']} 已存在，跳过")
            continue
        print(f"  画道具 {prop['name']}……（约 1 分钟）")
        prompt = f"{prop['english_desc']}, single object, centered, plain light gray background, product shot, {STYLE}, {NEG}"
        save_result(client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1024"), path)
    return refs


# ---------- 第 3 步：画场景（人物+道具标准照一起当参考） ----------

def step3_scenes(sb: dict, refs: dict):
    print("第 3 步：画场景图……")
    for scene in sb["scenes"]:
        raw_path = OUT_DIR / f"{scene['scene_id']}_raw.png"
        if raw_path.exists():
            print(f"  {scene['scene_id']} 已存在，跳过")
            continue
        chars = [c for c in sb["characters"] if c["character_id"] in scene["characters"]]
        props = [p for p in sb.get("props", []) if p["prop_id"] in scene.get("props", [])]
        char_hint = "; ".join(f"{c['name']}: {c['english_desc']}" for c in chars)
        prop_hint = "; ".join(f"{p['name']}: {p['english_desc']}" for p in props)
        prompt = (
            f"{scene['scene_prompt_en']}. "
            f"The scene contains exactly these people: {char_hint}. "
            f"They must look EXACTLY like the reference image(s) — same faces, hairstyles and clothes. "
        )
        if prop_hint:
            prompt += f"These props must also match their reference image(s): {prop_hint}. "
        prompt += f"{STYLE}, {NEG}"
        ref_files = [refs[c["character_id"]] for c in chars] + [refs[p["prop_id"]] for p in props]
        handles = [open(p, "rb") for p in ref_files]
        print(f"  画 {scene['scene_id']}（{scene['location']}，{len(handles)} 张参考图）……（约 1 分钟）")
        try:
            save_result(client.images.edit(model=IMAGE_MODEL, image=handles, prompt=prompt, size="1536x1024"), raw_path)
        finally:
            for f in handles:
                f.close()


# ---------- 第 4 步：AI 单独生成手机屏幕内容（特写框素材） ----------

def step4_screen_assets(sb: dict):
    print("第 4 步：生成手机屏幕特写素材……")
    for scene in sb["scenes"]:
        inset = scene.get("screen_inset")
        if not inset:
            continue
        path = SCREEN_DIR / f"{scene['scene_id']}_screen.png"
        if path.exists():
            print(f"  {scene['scene_id']} 屏幕素材已存在，跳过")
            continue
        print(f"  生成 {scene['scene_id']} 的手机屏幕……（约 1 分钟）")
        prompt = (
            f"A smartphone screen, full-screen mobile app interface, flat modern UI design. "
            f"On the screen: {inset['screen_prompt_en']}. "
            f"Chinese text on the screen must be rendered accurately and clearly."
        )
        save_result(client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1536"), path)


# ---------- 第 5 步：合成（场景 + 特写框 + 气泡 + 说明文字） ----------

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


def draw_bubble(draw, text, slot_x, slot_y, font):
    """画气泡，返回气泡高度（方便下一个气泡往下排）"""
    max_w = 420
    pad = 22
    line_h = font.size + 14
    lines = wrap_text(draw, text, font, max_w - pad * 2)
    box_h = pad * 2 + line_h * len(lines) - 14
    x1, y1, x2, y2 = slot_x, slot_y, slot_x + max_w, slot_y + box_h
    draw.rounded_rectangle([x1, y1, x2, y2], radius=24, fill="white", outline="#333333", width=4)
    draw.polygon([(x1 + 70, y2 - 2), (x1 + 130, y2 - 2), (x1 + 70, y2 + 46)],
                 fill="white", outline="#333333")
    for i, line in enumerate(lines):
        draw.text((x1 + pad, y1 + pad + i * line_h), line, font=font, fill="#222222")
    return box_h


def paste_inset(canvas: Image.Image, screen_path: Path, x: int, y: int):
    """把手机屏幕素材以圆角带边框的特写框贴到画面上"""
    screen = Image.open(screen_path).convert("RGB").resize((INSET_W, INSET_H))
    mask = Image.new("L", (INSET_W, INSET_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, INSET_W, INSET_H], radius=30, fill=255)
    canvas.paste(screen, (x, y), mask)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([x, y, x + INSET_W, y + INSET_H], radius=30, outline="#1a1a1a", width=8)


def step5_composite(sb: dict):
    print("第 5 步：合成场景（特写框 + 气泡 + 说明文字）……")
    bubble_font = load_font(36)
    caption_font = load_font(34)

    for scene in sb["scenes"]:
        out_path = OUT_DIR / f"{scene['scene_id']}.png"
        if out_path.exists():
            print(f"  {scene['scene_id']} 已合成，跳过")
            continue
        raw = Image.open(OUT_DIR / f"{scene['scene_id']}_raw.png").convert("RGB")
        panel = raw.resize((PANEL_W, int(raw.height * PANEL_W / raw.width)))
        canvas = Image.new("RGB", (PANEL_W, panel.height + 100), "#ffffff")
        canvas.paste(panel, (0, 0))

        has_inset = bool(scene.get("screen_inset"))
        if has_inset:
            paste_inset(canvas, SCREEN_DIR / f"{scene['scene_id']}_screen.png",
                        PANEL_W - INSET_W - 50, 50)

        draw = ImageDraw.Draw(canvas)
        if has_inset:
            # 有特写框时气泡全部在左侧依次往下排，避开右边的特写框
            y = 40
            for dlg in scene["dialogues"][:3]:
                y += draw_bubble(draw, dlg["text"], 50, y, bubble_font) + 36
        else:
            slots = [(50, 40), (PANEL_W - 470, 40), (50, 280)]
            for i, dlg in enumerate(scene["dialogues"][:3]):
                draw_bubble(draw, dlg["text"], *slots[i], font=bubble_font)

        cap = scene["caption"]
        cap_w = draw.textlength(cap, font=caption_font)
        draw.text(((PANEL_W - cap_w) / 2, panel.height + 28), cap, font=caption_font, fill="#444444")
        canvas.save(out_path)
        print(f"  已保存：{out_path.name}")


# ---------- 第 6 步：拼长图 ----------

def step6_long_image(sb: dict):
    print("第 6 步：拼长图……")
    panels = [Image.open(OUT_DIR / f"{s['scene_id']}.png") for s in sb["scenes"]]
    gap, header_h = 50, 220
    total_h = header_h + sum(p.height for p in panels) + gap * (len(panels) + 1)
    long_img = Image.new("RGB", (PANEL_W, total_h), "#f2f4f8")
    draw = ImageDraw.Draw(long_img)
    draw.rectangle([0, 0, PANEL_W, header_h], fill="#1a3a6b")
    title_font = load_font(64)
    title = sb.get("title", "漫画")
    tw = draw.textlength(title, font=title_font)
    draw.text(((PANEL_W - tw) / 2, (header_h - title_font.size) / 2 - 10), title, font=title_font, fill="white")
    y = header_h + gap
    for p in panels:
        long_img.paste(p, (0, y))
        y += p.height + gap
    out_path = OUT_DIR / "长图.png"
    long_img.save(out_path)
    print(f"\n完成！最终成品：{out_path}（{PANEL_W}×{total_h}）")


if __name__ == "__main__":
    scene_count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"主题：{TOPIC}\n张数：{scene_count}\n")
    sb = step1_storyboard(scene_count)
    refs = step2_reference_sheets(sb)
    step3_scenes(sb, refs)
    step4_screen_assets(sb)
    step5_composite(sb)
    step6_long_image(sb)
