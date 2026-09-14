# -*- coding: utf-8 -*-
"""
小样测试 04：风格对比
--------------------
用同一个故事的同一格（output_demo/storyboard.json 的 scene_01），
把 schemas/styles.json 里的每种风格各画一遍：人物标准照 + 场景图，
最后拼成一张带中文标签的对比图，方便挑选风格。

产物在 output_styles/ 里，跑过的风格自动跳过。
用法（在 spike 目录下）：.venv/Scripts/python.exe 04_style_showcase.py
"""

import base64
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

SPIKE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SPIKE_DIR.parent
OUT_DIR = SPIKE_DIR / "output_styles"
OUT_DIR.mkdir(exist_ok=True)

load_dotenv(SPIKE_DIR / ".env")
client = OpenAI()
IMAGE_MODEL = "gpt-image-2"

# 顺手带上 scene_04 问题的修正：屏幕内容只画界面、不要外壳（本次风格测试不用屏幕，但留个记录）
sb = json.loads((SPIKE_DIR / "output_demo" / "storyboard.json").read_text(encoding="utf-8"))
scene = sb["scenes"][0]                      # 第 1 格：在家点链接
character = sb["characters"][0]              # 周先生
styles = json.loads((ROOT_DIR / "schemas" / "styles.json").read_text(encoding="utf-8"))["styles"]

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"


def save_result(result, path: Path):
    d = result.data[0]
    if getattr(d, "b64_json", None):
        path.write_bytes(base64.b64decode(d.b64_json))
    elif getattr(d, "url", None):
        import urllib.request
        urllib.request.urlretrieve(d.url, path)
    else:
        raise RuntimeError("API 返回里既没有 b64_json 也没有 url")


def main():
    cell_w, cell_h, label_h, gap = 520, 347, 56, 30
    cells = []

    for st in styles:
        sid = st["style_id"]
        style_dir = OUT_DIR / sid
        style_dir.mkdir(exist_ok=True)
        char_path = style_dir / "char.png"
        scene_path = style_dir / "scene.png"

        if not char_path.exists():
            print(f"[{sid}] 画人物标准照……（约 1 分钟）")
            prompt = (f"{character['english_desc']}, full body, front view, standing, "
                      f"plain light gray background, {st['style_prompt']}, {st['negative_prompt']}")
            save_result(client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1536"), char_path)

        if not scene_path.exists():
            print(f"[{sid}] 画场景……（约 1 分钟）")
            prompt = (f"{scene['scene_prompt_en']}. "
                      f"The person must look EXACTLY like the reference image — same identity, "
                      f"re-interpreted in this art style: {st['style_prompt']}. "
                      f"{st['negative_prompt']}")
            try:
                with open(char_path, "rb") as f:
                    save_result(client.images.edit(model=IMAGE_MODEL, image=[f], prompt=prompt, size="1536x1024"), scene_path)
            except Exception as e:
                # 个别风格可能被安全系统误拦，降级为不带参考图直接画（风格对比不严格依赖人物一致）
                print(f"[{sid}] 参考图模式被拦（{type(e).__name__}），改为直接画……")
                fallback = (f"{scene['scene_prompt_en']}. {character['english_desc']}. "
                            f"{st['style_prompt']}. {st['negative_prompt']}")
                save_result(client.images.generate(model=IMAGE_MODEL, prompt=fallback, size="1536x1024"), scene_path)

        img = Image.open(scene_path).convert("RGB").resize((cell_w, cell_h))
        cells.append((st["name"], img))
        print(f"[{sid}] 完成")

    cols = 2
    rows = (len(cells) + cols - 1) // cols
    sheet_w = cols * cell_w + (cols + 1) * gap
    sheet_h = rows * (cell_h + label_h) + (rows + 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#f2f4f8")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT_PATH, 34)

    for i, (name, img) in enumerate(cells):
        col, row = i % cols, i // cols
        x = gap + col * (cell_w + gap)
        y = gap + row * (cell_h + label_h + gap)
        draw.rectangle([x, y, x + cell_w, y + label_h], fill="#1a3a6b")
        tw = draw.textlength(name, font=font)
        draw.text((x + (cell_w - tw) / 2, y + 8), name, font=font, fill="white")
        sheet.paste(img, (x, y + label_h))

    out_path = OUT_DIR / "风格对比.png"
    sheet.save(out_path)
    print(f"\n完成！对比图：{out_path}")


if __name__ == "__main__":
    main()
