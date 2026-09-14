# -*- coding: utf-8 -*-
"""第 2 步：人物标准照生成。"""

from pathlib import Path
import shutil

from server import store
from server.services import image_gen


def cutout_character(project_id: str, character_id: str) -> Path:
    """兼容旧动作名：由生图模型直接输出透明参考图，上传原图保持原样。"""
    pdir = store.project_dir(project_id)
    src = pdir / "characters" / f"{character_id}.png"
    if not src.exists():
        raise FileNotFoundError(f"人物标准照不存在：{src.name}")
    dst = pdir / "characters" / f"{character_id}_rgba.png"
    if image_gen.validate_image(src):
        shutil.copyfile(src, dst)
    else:
        image_gen.edit(
            "Return this exact reference character on a genuinely transparent alpha background as PNG. "
            "Preserve the character's identity, pose, outfit, proportions, visual style and all held accessories. "
            "Only remove the environment. Do not paint a white, colored or checkerboard backdrop.",
            [src], dst, size="1024x1536", background="transparent",
            allow_reference_fallback=False,
        )
    print(f"  {character_id} 透明底已生成：{dst.name}")
    return dst


def _neg(sb: dict) -> str:
    return "no " + sb["style"]["negative_prompt"].replace(", ", ", no ")


def generate_references(
    project_id: str, sb: dict, only_character: str | None = None
) -> dict[str, Path]:
    """画人物标准照，返回 {id: 图片路径}。已存在的默认跳过。

    only_character 指定时只重画该人物（即使已存在），并把引用它的场景标 stale。
    """
    pdir = store.project_dir(project_id)
    style = sb["style"]["style_prompt"]
    neg = _neg(sb)
    refs: dict[str, Path] = {}

    print("第 2 步：画人物标准照……")
    for ch in sb.get("characters", []):
        cid = ch["character_id"]
        path = pdir / "characters" / f"{cid}.png"
        refs[cid] = path
        regen = only_character == cid
        if ch.get("reference_source") == "upload":
            if not path.exists():
                raise FileNotFoundError(
                    f"上传的角色参考图丢失：{ch['name']}，请重新上传"
                )
            if regen:
                raise ValueError("上传的 IP 形象不会自动重画，请使用替换参考图")
            print(f"  {cid} 使用上传形象，保留原样")
            continue
        if only_character and not regen:
            continue
        if path.exists() and not regen:
            print(f"  {cid} 已存在，跳过")
            continue
        print(f"  画人物 {ch['name']}（{cid}）……（约 1 分钟）")
        prompt = (
            f"{ch['english_desc']}, full body, front view, standing, "
            "the entire character silhouette must fit inside the canvas, from the highest hair tip, "
            "topknot or head accessory to the soles of both feet. Show complete hair, accessories, "
            "hands, clothing and feet; never crop them at an image edge. "
            "Leave at least 8% of the image height as clear space ABOVE the highest hair or accessory, "
            "plus clear space on both sides and below the feet. Scale the character down to fit if needed. "
            f"isolated on a genuinely transparent alpha background, PNG, no painted backdrop, {style}, {neg}"
        )
        image_gen.generate(prompt, path, size="1024x1536", background="transparent")
        # Keep the existing download URL as a byte-for-byte copy of the model output.
        shutil.copyfile(path, pdir / "characters" / f"{cid}_rgba.png")
        if regen:
            current = store.load_storyboard(project_id)
            current["characters_confirmed"] = False
            store.save_storyboard(project_id, current)
            marked = store.mark_scenes_stale(project_id, cid)
            if marked:
                print(
                    f"  [stale] {cid} 已重画，这些格子引用了它、需要重跑：{', '.join(marked)}"
                )

    return refs
