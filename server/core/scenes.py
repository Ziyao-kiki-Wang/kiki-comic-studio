# -*- coding: utf-8 -*-
"""第 3 步：根据剧情与人物参考图生成场景，原图进版本池。"""

from server import store
from server.services import image_gen
from server.core import characters as character_engine
from server.core import story
from server.core.studio import background_mode, screen_enabled
from server.core.style_prompts import SCENE_RENDER_DIRECTION, object_style, negative_style
from server.services.assets import asset_path


def _build_prompt(sb: dict, scene: dict, project_id: str | None = None) -> str:
    chars = [
        c for c in sb["characters"] if c["character_id"] in scene.get("characters", [])
    ]
    replacements = {
        item.get("replace_character_id")
        for item in scene.get("reference_assets", [])
        if item.get("mode") == "replace_character"
    }
    char_hint = "; ".join(
        f"{c['name']}: "
        + (
            "appearance exclusively from the scene-specific reference image; "
            "ignore the global character reference for this scene"
            if c["character_id"] in replacements
            else c.get("english_desc", "Preserve the character reference")
        )
        for c in chars
    )
    prompt = (
        f"{scene['scene_prompt_en']}. "
        f"The scene contains exactly these people: {char_hint or 'NONE; no characters'}. "
        f"They must look EXACTLY like the reference image(s) — same faces, hairstyles and clothes. "
        "Unlisted characters must not appear, including inside screens, photos or reflections. "
    )
    local_refs = scene.get("reference_assets", [])
    if local_refs:
        prompt += (
            "Additional scene-only reference images are attached. Use them only for this scene; "
            "preserve their visible design and do not add them to other scenes. "
        )
        replaced = [
            item.get("replace_character_id")
            for item in local_refs
            if item.get("mode") == "replace_character"
        ]
        if replaced:
            names = [
                next(
                    (c["name"] for c in chars if c["character_id"] == cid), cid
                )
                for cid in replaced
            ]
            prompt += (
                "For this scene, the scene-specific reference image(s) replace "
                f"the matching character reference(s): {', '.join(names)}. "
            )
    fixed_identity = any(
        (c.get("reference_source") == "upload"
         and not (project_id and character_engine.character_stylized(project_id, c)))
        or c["character_id"] in replacements
        for c in chars
    )
    stylized_uploads = [
        c for c in chars
        if project_id and c.get("reference_source") == "upload"
        and character_engine.character_stylized(project_id, c)
    ]
    if stylized_uploads:
        names = ", ".join(c["name"] for c in stylized_uploads)
        prompt += (
            f"These characters were supplied as style-adapted references ({names}): keep their "
            "identity, outfit and proportions, rendered in the same target art style as the environment. "
        )
    if fixed_identity:
        prompt += "Supplied IP characters are immutable designs. Preserve their original visual style, facial features, proportions, signature colors, clothes and accessories. Adapt the environment to these characters, never redesign them to fit another style. "
    if background_mode(sb, scene) == "transparent":
        prompt += "BACKGROUND OVERRIDE: output a PNG with a genuinely transparent alpha background. Render the people, story-relevant objects and furniture, information displays, and purposeful comic reaction symbols as one composed vignette. Keep transparent pixels around them and in the gaps. Do not paint a white, gray, colored, checkerboard or blurred backdrop, or an opaque poster board behind the entire group. Omit rooms, walls, distant scenery and continuous floor. Keep furniture that supports the action, but do not add it just to fill space. Furniture is foreground, not background. Isolated reaction rays, sweat drops, warning icons and motion strokes are allowed on alpha. Preserve clear overlap, readable silhouettes and room for later dialogue. "
    if screen_enabled(scene) and scene.get("screen_mode", "integrated") == "integrated":
        prompt += "COMPOSITION OVERRIDE: follow the prepared scene's camera, object scale and close-up arrangement. A story-critical phone or information display may be as large as the character, placed in the foreground or as a separate illustrative display. Do not shrink it to realistic hand-held size if the composition calls for emphasis. Keep perspective, hand contact and the information hierarchy clear; do not duplicate devices unless the scene needs a comparison. "
        if scene.get("screen_inset"):
            prompt += f"Content to integrate on the physical screen, simplify to key readable information: {scene['screen_inset'].get('screen_prompt_en', '')}. "
    if fixed_identity:
        prompt += f"Environment and objects only: {object_style(sb)}. Environment-only exclusions: {negative_style(sb)}. These style preferences must not restyle reference characters. "
    else:
        prompt += f"{sb['style']['style_prompt']}. {negative_style(sb)}. "
    prompt += SCENE_RENDER_DIRECTION
    prompt += (
        "FRAMING REQUIREMENT: keep each character's entire head, hairstyle, highest hair tip, "
        "topknot, ears and head accessories completely inside the image. "
        "Leave at least 8% of the image height as clear headroom ABOVE the highest hair or accessory, "
        "not merely above the forehead. Leave clear space beside the visible character silhouette. "
        "Default to complete characters with hands, clothing and feet inside the frame; natural occlusion "
        "by a table or another story object is allowed. An explicitly requested waist-up or close-up shot "
        "may omit the lower body, but must still preserve the complete head and hair. "
        "If a large phone or a tall hairstyle makes the composition crowded, pull the camera back or "
        "scale the subject group down; never solve it by cutting off hair or character features at the canvas edge. "
    )
    prompt += "Keep dialogue bubbles and captions out of the illustration; leave natural negative space for editable lettering. Screen content and story-critical signs are allowed."
    if scene.get("screen_enabled") is False:
        prompt += " SCREEN OVERRIDE: this scene does not need phones or screens. Do not introduce phones, tablets, monitors or screen close-ups; disregard earlier screen-specific instructions."
    return prompt


def foreground_path(project_id, scene_id):
    """Return the model's transparent original, without creating a cutout file."""
    raw = store.active_raw_path(project_id, scene_id)
    if raw is not None:
        try:
            if image_gen.validate_image(raw):
                return raw
        except image_gen.InvalidImageError:
            pass
    return None


def scene_asset(project_id, sb, scene):
    """Use the generated original directly; transparent mode requires its own alpha."""
    raw = store.active_raw_path(project_id, scene["scene_id"])
    if raw is not None and background_mode(sb, scene) == "transparent":
        image_gen.validate_image(raw, require_transparency=True)
    return raw


def _ref_files(project_id: str, sb: dict, scene: dict, refs: dict):
    files = []
    local = scene.get("reference_assets", [])
    replacements = {
        item.get("replace_character_id")
        for item in local
        if item.get("mode") == "replace_character"
    }
    # Put replacement references first so the model sees them before any
    # append-only context; the prompt labels which character they control.
    for item in local:
        if item.get("mode") == "replace_character":
            files.append(asset_path(project_id, item["asset_id"]))
    for cid in scene.get("characters", []):
        if cid not in replacements and cid in refs and refs[cid].exists():
            files.append(refs[cid])
    for item in local:
        if item.get("mode") == "replace_character":
            continue
        # References are scoped to this scene's prompt.  Their registry lookup
        # also prevents a hand-edited storyboard from escaping the project.
        files.append(asset_path(project_id, item["asset_id"]))
    return files


def generate_scene(
    project_id: str,
    sb: dict,
    scene: dict,
    refs: dict,
    force: bool = False,
    edit_instruction: str | None = None,
) -> str:
    """画一格场景原图，存入版本池并设为 active。返回版本号字符串如 'v1'。"""
    sid = scene["scene_id"]
    existing = store.scene_versions(project_id, sid)
    transparent = background_mode(sb, scene) == "transparent"
    if existing and not force and not (store.load_scene_meta(project_id, sid) or {}).get("generation_stale"):
        current = store.active_raw_path(project_id, sid)
        try:
            image_gen.validate_image(current, require_transparency=transparent)
        except image_gen.MissingTransparencyError:
            print(f"  {sid} 已有图片不含透明背景，由模型生成透明新版本……")
        except image_gen.InvalidImageError:
            print(f"  [修复] {sid} 原图损坏或不完整，保留旧文件并生成新版本……")
        else:
            version_tag = current.stem.rsplit("_", 1)[-1]
            print(f"  {sid} 已有 {version_tag}，跳过")
            return version_tag

    version = (existing[-1] + 1) if existing else 1
    out = store.version_path(project_id, sid, version)
    prepared = story.prepare_scene_prompt(project_id, sb, scene, edit_instruction)
    ref_files = _ref_files(project_id, sb, prepared, refs)
    prompt = _build_prompt(sb, prepared, project_id)
    # Bind identities to the actual attachment order, not the order of prose.
    identity_lines = []
    for c in sb["characters"]:
        if c["character_id"] not in prepared.get("characters", []):
            continue
        replacement = next((r for r in prepared.get("reference_assets", [])
                            if r.get("mode") == "replace_character" and r.get("replace_character_id") == c["character_id"]), None)
        path = asset_path(project_id, replacement["asset_id"]) if replacement else refs.get(c["character_id"])
        if path in ref_files:
            number = ref_files.index(path) + 1 + bool(edit_instruction)
            description = c.get('english_desc') or c.get('description') or 'Use this character reference exclusively'
            if replacement:
                description = 'Use this replacement image exclusively; ignore the global appearance description'
            identity_lines.append(f"Image {number} = {c['character_id']} = {c['name']}; fixed story role: {c.get('role', '')}; identity description: {description}.")
    prompt += "\nIDENTITY BINDING (mandatory): " + " ".join(identity_lines)
    prompt += " Never swap the characters' roles or transfer one character's actions to another reference. Interpret the action description using these fixed identities."
    for ref in prepared.get("reference_assets", []):
        if ref.get("mode") != "replace_character":
            number = ref_files.index(asset_path(project_id, ref["asset_id"])) + 1 + bool(edit_instruction)
            prompt += f"\nImage {number} = scene context only; never a source of character identity or additional cast."
    if edit_instruction:
        current = store.active_raw_path(project_id, sid)
        if current is None:
            raise ValueError("请先生成这一格，再基于当前图修改")
        ref_files = [current, *ref_files]
        prompt = (
            "Edit the FIRST image, which is the current scene. Other images have explicitly labeled roles. "
            "Preserve composition and details except where the prepared scene or requested changes require adjustment. "
            "If the current scene has incorrect characters, restore them from the labeled character references. "
            + prompt
            + "\nUSER EDIT (takes priority over the original scene description): "
            + edit_instruction
        )
    print(
        f"  画 {sid}（{scene.get('location', '')}，v{version}，{len(ref_files)} 张参考图）……（约 1 分钟）"
    )
    if ref_files:
        fixed_ip = any(
            c.get("reference_source") == "upload"
            and not character_engine.character_stylized(project_id, c)
            and c["character_id"] in prepared.get("characters", [])
            for c in sb["characters"]
        )
        image_gen.edit(
            prompt,
            ref_files,
            out,
            size="1536x1024",
            background="transparent" if transparent else "opaque",
            allow_reference_fallback=not (
                fixed_ip or edit_instruction or prepared.get("reference_assets")
            ),
        )
    else:
        image_gen.generate(
            prompt, out, size="1536x1024",
            background="transparent" if transparent else "opaque",
        )
    store.register_version(project_id, sid, version)
    store.clear_scene_stale(project_id, sid)
    scene.update(prepared)
    scene["stale"] = False
    scene["reference_stale"] = False
    next(s for s in sb["scenes"] if s["scene_id"] == sid).update(scene)
    store.save_storyboard(project_id, sb)
    meta = store.load_scene_meta(project_id, sid) or {}
    meta["status"] = "draft"
    meta["render_stale"] = True
    meta["generation_stale"] = False
    meta["prompt_preparation"] = {"source": story._prompt_source(project_id, sb, scene)}
    meta.setdefault("generation_history", {})[f"v{version}"] = {
        "prompt": prompt,
        "edit_instruction": edit_instruction or "",
        "background": "transparent" if transparent else "opaque",
        "scene_prompt_en": scene["scene_prompt_en"],
        "references": [str(path.relative_to(store.project_dir(project_id))) for path in ref_files],
    }
    if not screen_enabled(scene) or scene.get("screen_mode", "integrated") == "integrated":
        meta.pop("screen_inset", None)
        meta["screen_inset_hidden"] = True
    else:
        meta["screen_inset_hidden"] = False
    store.save_scene_meta(project_id, sid, meta)
    # 原图变了，旧的合成产物作废
    composite = store.project_dir(project_id) / "output" / f"{sid}.png"
    if composite.exists():
        composite.unlink()
    return f"v{version}"


def generate_scenes(
    project_id: str, sb: dict, refs: dict, only_scene: str | None = None
):
    """画全部场景（或 force 重画指定一格）。"""
    print("第 3 步：画场景图……")
    for scene in sb["scenes"]:
        generate_scene(
            project_id, sb, scene, refs, force=(only_scene == scene["scene_id"])
        )
