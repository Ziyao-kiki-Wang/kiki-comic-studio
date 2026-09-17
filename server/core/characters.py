# -*- coding: utf-8 -*-
"""第 2 步：人物标准照生成。"""

from pathlib import Path
import filecmp
import shutil

from server import store
from server.services import image_gen
from server.services.image_gen import MissingTransparencyError


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
        try:
            image_gen.edit(
                "Return this exact reference character on a genuinely transparent alpha background as PNG. "
                "Preserve the character's identity, pose, outfit, proportions, visual style and all held accessories. "
                "Only remove the environment. Do not paint a white, colored or checkerboard backdrop.",
                [src], dst, size="1024x1536", background="transparent",
                allow_reference_fallback=False,
            )
        except MissingTransparencyError as exc:
            # 模型返回非透明图；接受不透明结果（原图已备份在 {cid}.png），
            # 让任务继续走而不是整个生成断在这一步
            print(f"  [警告] {character_id} 透明化失败，已保留不透明版本：{exc}")
            shutil.copyfile(src, dst)
    print(f"  {character_id} 透明底已生成：{dst.name}")
    return dst


def stylize_character(project_id: str, sb: dict, character_id: str) -> Path:
    """把用户上传的人物图重绘成项目画风，结果作为该人物的生效参考图。

    原图固定在 {cid}_original.png；风格化结果写回 {cid}.png，并另存
    {cid}_styled.png 供切换模式时恢复，避免重复调用生图。
    """
    pdir = store.project_dir(project_id)
    folder = pdir / "characters"
    original = folder / f"{character_id}_original.png"
    if not original.exists():
        # 旧项目没有原图备份时，当前 {cid}.png 就是上传图
        src = folder / f"{character_id}.png"
        if src.exists():
            shutil.copyfile(src, original)
    if not original.exists():
        raise FileNotFoundError(f"找不到 {character_id} 的上传原图，请重新上传")
    out = folder / f"{character_id}.png"
    styled = folder / f"{character_id}_styled.png"
    style = sb["style"]["style_prompt"]
    neg = _neg(sb)
    prompt = (
        "Redraw the attached reference character as a clean character sheet in the target art style. "
        "Preserve the character's identity: same face, hairstyle, age, body proportions, signature colors, "
        "outfit and held accessories. Keep the same pose and facing direction where possible. "
        "Isolated on a genuinely transparent alpha background, PNG, no painted backdrop. "
        f"Target art style: {style}. {neg}"
    )
    try:
        image_gen.edit(
            prompt, [original], styled, size="1024x1536", background="transparent",
            allow_reference_fallback=False, request_timeout=240,
        )
    except MissingTransparencyError as exc:
        print(f"  [警告] {character_id} 风格化未返回透明背景，已接受不透明结果：{exc}")
        image_gen.edit(
            prompt, [original], styled, size="1024x1536", background="opaque",
            allow_reference_fallback=False, request_timeout=240,
        )
    shutil.copyfile(styled, out)
    (folder / f"{character_id}_rgba.png").unlink(missing_ok=True)
    print(f"  {character_id} 已按画风重绘：{out.name}")
    return out


def character_stylized(project_id: str, character: dict) -> bool:
    """该上传人物当前是否处于风格化模式（{cid}.png 是风格化产物）。"""
    return character_reference_mode(project_id, character) == "stylized"


def character_reference_mode(project_id: str, character: dict) -> str:
    """上传人物的参考模式：original / stylized。

    以 storyboard 的 reference_mode 字段为准；字段缺失时按是否存在
    风格化产物 {cid}_styled.png 推断，兼容未升级的旧数据。
    """
    if character.get("reference_source") != "upload":
        return "generated"
    mode = character.get("reference_mode")
    if mode in ("original", "stylized"):
        return mode
    folder = store.project_dir(project_id) / "characters"
    if (folder / f"{character['character_id']}_styled.png").exists():
        return "stylized"
    return "original"


def ensure_uploaded_reference(project_id: str, sb: dict, character: dict) -> None:
    """风格化模式下补齐或修复 {cid}.png（如缺失则用已存风格化图或重新风格化）。"""
    if not character_stylized(project_id, character):
        return
    cid = character["character_id"]
    folder = store.project_dir(project_id) / "characters"
    path = folder / f"{cid}.png"
    styled = folder / f"{cid}_styled.png"
    original = folder / f"{cid}_original.png"
    if styled.exists():
        if not _same_file(path, styled):
            shutil.copyfile(styled, path)
            print(f"  {cid} 已从缓存恢复风格化形象")
        return
    if not path.exists() or (original.exists() and _same_file(path, original)):
        print(f"  {cid} 的风格化形象缺失，重新按画风绘制……")
        stylize_character(project_id, sb, cid)


def _neg(sb: dict) -> str:
    return "no " + sb["style"]["negative_prompt"].replace(", ", ", no ")


def _same_file(a: Path, b: Path) -> bool:
    """两个文件都存在且内容一致。"""
    try:
        return a.exists() and b.exists() and filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


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
            if regen:
                raise ValueError("上传的 IP 形象不会自动重画，请使用替换参考图")
            if character_stylized(project_id, ch):
                styled = pdir / "characters" / f"{cid}_styled.png"
                original = pdir / "characters" / f"{cid}_original.png"
                # 风格化模式下 {cid}.png 应该是风格化产物：
                # - 已有风格化缓存但 {cid}.png 被覆盖成原图/丢失 → 恢复
                # - 无缓存且 {cid}.png 仍是原图 → 现场风格化
                if styled.exists():
                    if not path.exists() or not _same_file(path, styled):
                        shutil.copyfile(styled, path)
                        print(f"  {cid} 已恢复为风格化形象")
                    else:
                        print(f"  {cid} 使用风格化形象")
                    continue
                if original.exists() and _same_file(path, original):
                    print(f"  按画风绘制人物 {ch['name']}（{cid}）……（约 1 分钟）")
                    stylize_character(project_id, sb, cid)
                    continue
                if not path.exists():
                    raise FileNotFoundError(
                        f"上传的角色参考图丢失：{ch['name']}，请重新上传"
                    )
                print(f"  {cid} 使用风格化形象")
                continue
            if not path.exists():
                raise FileNotFoundError(
                    f"上传的角色参考图丢失：{ch['name']}，请重新上传"
                )
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
        try:
            image_gen.generate(prompt, path, size="1024x1536", background="transparent")
        except MissingTransparencyError as exc:
            print(f"  [警告] {cid} 生成未返回透明背景，已接受不透明结果：{exc}")
            image_gen.generate(prompt, path, size="1024x1536", background="opaque")
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
