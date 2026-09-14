# -*- coding: utf-8 -*-
"""第 3 步：参考图场景生成（人物+道具参考图一起传），原图进版本池。"""

from server import store
from server.services import image_gen
from server.core.studio import background_mode, screen_enabled
from server.services.assets import asset_path


def _build_prompt(sb: dict, scene: dict) -> str:
    chars = [
        c for c in sb["characters"] if c["character_id"] in scene.get("characters", [])
    ]
    props = [p for p in sb.get("props", []) if p["prop_id"] in scene.get("props", [])]
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
            else c["english_desc"]
        )
        for c in chars
    )
    prop_hint = "; ".join(f"{p['name']}: {p['english_desc']}" for p in props)
    prompt = (
        f"{scene['scene_prompt_en']}. "
        f"The scene contains exactly these people: {char_hint}. "
        f"They must look EXACTLY like the reference image(s) — same faces, hairstyles and clothes. "
    )
    if prop_hint:
        prompt += f"These props must also match their reference image(s): {prop_hint}. "
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
    if any(c.get("reference_source") == "upload" for c in chars):
        prompt += "Supplied IP characters are immutable designs. Preserve their original visual style, facial features, proportions, signature colors, clothes and accessories. Adapt the environment to these characters, never redesign them to fit another style. "
    if background_mode(sb, scene) == "transparent":
        prompt += "BACKGROUND OVERRIDE: output a PNG with a genuinely transparent alpha background. Render the interacting people AND all supporting furniture and narrative props as one complete scene vignette, with transparent pixels around them and in the gaps between objects. Do not paint a white, gray, colored, checkerboard or blurred backdrop. Omit the surrounding room, walls, distant scenery and continuous floor even if mentioned in the scene description. KEEP tables, chairs, sofas, documents, bags, phones, displays and signs involved in the action. Furniture is foreground, not background. Preserve contact, overlap and spatial relationships as one coherent group, entirely inside the frame. Use expressive poses, varied camera angles and clear silhouettes; leave breathing room for dialogue. "
        if scene.get("retained_props"):
            prompt += f"Essential props to retain: {scene['retained_props']}. "
    if screen_enabled(scene) and scene.get("screen_mode", "integrated") == "integrated":
        prompt += "COMPOSITION OVERRIDE: generate phones and their screen content naturally WITH the scene, with matching perspective, lighting, scale and hand contact. Use an over-the-shoulder view, a person showing a screen to another, or a story-motivated product display. Do not reserve a sidebar, split the composition, or float a giant flat UI card beside a person. This overrides any earlier instruction that the phone back must face the viewer. "
        if scene.get("screen_inset"):
            prompt += f"Content to integrate on the physical screen, simplify to key readable information: {scene['screen_inset'].get('screen_prompt_en', '')}. "
    prompt += f"{sb['style']['style_prompt']}, no {sb['style']['negative_prompt'].replace(', ', ', no ')}. Keep dialogue bubbles and captions out of the illustration; leave natural negative space for editable lettering. Screen content and story-critical signs are allowed."
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
    for pid in scene.get("props", []):
        if pid in refs and refs[pid].exists():
            files.append(refs[pid])
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
    ref_files = _ref_files(project_id, sb, scene, refs)
    prompt = _build_prompt(sb, scene)
    # Bind identities to the actual attachment order, not the order of prose.
    identity_lines = []
    for c in sb["characters"]:
        if c["character_id"] not in scene.get("characters", []):
            continue
        replacement = next((r for r in scene.get("reference_assets", [])
                            if r.get("mode") == "replace_character" and r.get("replace_character_id") == c["character_id"]), None)
        path = asset_path(project_id, replacement["asset_id"]) if replacement else refs.get(c["character_id"])
        if path in ref_files:
            number = ref_files.index(path) + 1 + bool(edit_instruction)
            identity_lines.append(f"Image {number} = {c['character_id']} = {c['name']}; fixed story role: {c.get('role', '')}; identity description: {c.get('description', c.get('english_desc', ''))}.")
    prompt += "\nIDENTITY BINDING (mandatory): " + " ".join(identity_lines)
    prompt += " Never swap the characters' roles or transfer one character's actions to another reference. Interpret the action description using these fixed identities."
    prompt += f"\nStory action: {scene.get('story', '')}. Dialogue speaker identities (for understanding actions only, do not draw dialogue): "
    prompt += "; ".join(f"{d.get('speaker')}: {d.get('text')}" for d in scene.get("dialogues", []))
    if edit_instruction:
        current = store.active_raw_path(project_id, sid)
        if current is None:
            raise ValueError("请先生成这一格，再基于当前图修改")
        ref_files = [current, *ref_files]
        prompt = (
            "Edit the FIRST image, which is the current scene. Other images are identity references. "
            "Preserve composition and details except where the requested changes require adjustment. "
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
            and c["character_id"] in scene.get("characters", [])
            for c in sb["characters"]
        )
        image_gen.edit(
            prompt,
            ref_files,
            out,
            size="1536x1024",
            background="transparent" if transparent else "opaque",
            allow_reference_fallback=not (
                fixed_ip or edit_instruction or scene.get("reference_assets")
            ),
        )
    else:
        image_gen.generate(
            prompt, out, size="1536x1024",
            background="transparent" if transparent else "opaque",
        )
    store.register_version(project_id, sid, version)
    store.clear_scene_stale(project_id, sid)
    scene["reference_stale"] = False
    store.save_storyboard(project_id, sb)
    meta = store.load_scene_meta(project_id, sid) or {}
    meta["status"] = "draft"
    meta["render_stale"] = True
    meta["generation_stale"] = False
    meta.setdefault("generation_history", {})[f"v{version}"] = {
        "prompt": prompt,
        "edit_instruction": edit_instruction or "",
        "background": "transparent" if transparent else "opaque",
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
