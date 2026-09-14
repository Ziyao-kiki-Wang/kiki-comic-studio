# -*- coding: utf-8 -*-
"""
小样测试 01：人物一致性
-----------------------
验证整个项目最关键的问题：
    同一个角色，画 3 张不同场景的图，长得像不像同一个人？

流程：
    第 1 步：根据人物表（schemas/character.example.json）画一张"小林标准照"
    第 2 步：拿标准照当参考图，画"小林在银行大厅"
    第 3 步：拿标准照当参考图，画"小林在街上"
    第 4 步：把 3 张图拼成一张对比图，肉眼判断像不像

运行方法（在 spike 目录下）：
    pip install -r requirements.txt
    把 .env.example 改名成 .env，填入你的 OpenAI API Key
    python 01_character_consistency.py
"""

import base64
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

SPIKE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SPIKE_DIR.parent
OUT_DIR = SPIKE_DIR / "output"
OUT_DIR.mkdir(exist_ok=True)

# 从 .env 文件读取 OPENAI_API_KEY（脚本不会把 Key 打印或传出去）
load_dotenv(SPIKE_DIR / ".env")
client = OpenAI()

MODEL = "gpt-image-2"   # 中转站里的画图模型名；以后想换型号改这一行就行

# 画风咒语：以后改成从 schemas/styles.json 里读，现在先用默认的商业漫画风
STYLE = "clean Chinese commercial comic style, soft clean lines, flat shading, bright warm colors, simple shapes"
NEG = "no text, no words, no letters, no speech bubble, no watermark"


def build_character_desc() -> str:
    """从人物表里拼出一段英文外貌描述——这就是"三张表驱动画图"的第一次实践。"""
    char = json.loads((ROOT_DIR / "schemas" / "character.example.json").read_text(encoding="utf-8"))
    a = char["appearance"]
    c = char["clothing"]
    i = char["identity"]
    parts = [
        f"{i['age']}-year-old {i['gender']}, {i['occupation']}",
        a["hair"], a["face"], a["body"],
        f"wearing {c['top']} with {c['outerwear']}, {c['bottom']}",
        ", ".join(c["accessories"]),
    ]
    return ", ".join(parts)


def save_result(result, path: Path):
    """保存图片：兼容两种返回格式（base64 或图片 URL）"""
    d = result.data[0]
    if getattr(d, "b64_json", None):
        path.write_bytes(base64.b64decode(d.b64_json))
    elif getattr(d, "url", None):
        import urllib.request
        urllib.request.urlretrieve(d.url, path)
    else:
        raise RuntimeError("API 返回里既没有 b64_json 也没有 url，请把这条错误发给我")
    print(f"  已保存：{path.name}")


def step1_standard_sheet(desc: str) -> Path:
    """第 1 步：画标准照（正面全身、纯色背景，方便后面当参考图）"""
    ref_path = OUT_DIR / "1_standard_sheet.png"
    if ref_path.exists():
        print("第 1 步：标准照已存在，跳过（想重画就删掉 output 里的图）")
        return ref_path

    print("第 1 步：画小林标准照……（约 1 分钟）")
    prompt = f"{desc}, full body, front view, standing, plain light gray background, {STYLE}, {NEG}"
    r = client.images.generate(model=MODEL, prompt=prompt, size="1024x1536")
    save_result(r, ref_path)
    return ref_path


def step23_scenes(ref_path: Path, desc: str):
    """第 2、3 步：把标准照作为参考图发给 API，画两个不同场景"""
    scenes = [
        ("2_bank_lobby.png", "in a bright tidy bank lobby, reaching out one hand to signal 'please stop', calm professional smile"),
        ("3_street.png", "walking on a city street, holding a folder, gentle smile"),
    ]
    for filename, scene_desc in scenes:
        out_path = OUT_DIR / filename
        if out_path.exists():
            print(f"  {filename} 已存在，跳过")
            continue
        print(f"画图中：{filename}……（约 1 分钟）")
        prompt = (
            f"The exact same woman from the reference image: {desc}. "
            f"Now she is {scene_desc}. "
            f"Keep her face, hairstyle and uniform EXACTLY the same as the reference. "
            f"{STYLE}, {NEG}"
        )
        with open(ref_path, "rb") as f:
            r = client.images.edit(model=MODEL, image=[f], prompt=prompt, size="1536x1024")
        save_result(r, out_path)


def step4_contact_sheet():
    """第 4 步：三张图并排拼成一张对比图"""
    files = ["1_standard_sheet.png", "2_bank_lobby.png", "3_street.png"]
    images = [Image.open(OUT_DIR / f) for f in files]
    h = 800
    resized = [im.resize((int(im.width * h / im.height), h)) for im in images]
    gap = 20
    total_w = sum(im.width for im in resized) + gap * (len(resized) + 1)
    sheet = Image.new("RGB", (total_w, h + gap * 2), "white")
    x = gap
    for im in resized:
        sheet.paste(im, (x, gap))
        x += im.width + gap
    sheet_path = OUT_DIR / "对比图.png"
    sheet.save(sheet_path)
    print(f"\n对比图已生成：{sheet_path}")
    print("从左到右：标准照 → 银行大厅 → 街上。看看是不是同一个人！")


if __name__ == "__main__":
    desc = build_character_desc()
    print(f"人物描述（来自人物表）：{desc}\n")
    ref = step1_standard_sheet(desc)
    step23_scenes(ref, desc)
    step4_contact_sheet()
