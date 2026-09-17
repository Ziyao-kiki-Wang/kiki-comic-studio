# -*- coding: utf-8 -*-
"""第 1 步：LLM 根据主题与人物形象写故事和画面提示词。"""

import json
from copy import deepcopy

from server import store
from server.config import SCHEMAS_DIR
from server.core.studio import background_mode
from server.core.style_prompts import SCENE_VISUAL_DIRECTION, object_style
from server.services import llm
from server.services.assets import asset_path


def load_style(style_id: str) -> dict:
    """从 schemas/styles.json 里取风格。"""
    menu = json.loads((SCHEMAS_DIR / "styles.json").read_text(encoding="utf-8"))
    for s in menu["styles"]:
        if s["style_id"] == style_id:
            return s
    raise ValueError(
        f"未知风格 {style_id}，可选：{[s['style_id'] for s in menu['styles']]}"
    )


def create_storyboard(
    project_id: str,
    topic: str,
    scene_count: int,
    style_id: str,
    force: bool = False,
    provided_characters: list | None = None,
    background_mode: str = "scene",
) -> dict:
    """生成故事表并落盘。已有 storyboard.json 时默认沿用。"""
    pdir = store.init_dirs(project_id)
    sb_path = pdir / "storyboard.json"
    if sb_path.exists() and not force:
        print("第 1 步：storyboard.json 已存在，直接沿用")
        return store.load_storyboard(project_id)

    style = load_style(style_id)
    print(f"第 1 步：让 LLM 写故事表（{scene_count} 格，风格 {style_id}）……")
    prompt = f"""你是漫画编剧，同时负责每格的画面设计。请根据下面的主题，写一部 {scene_count} 格漫画的故事表。

主题：{topic}

要求：
1. 对话口语化、简短，每格 1-3 句对话，说明文字（caption）一句话。
2. 人物 2 个左右，外貌穿着的英文描述要具体（发型、脸型、年龄、衣服）。
3. 根据每格的场景地点、剧情与动作，自动确定画面需要的物品、家具和漫画辅助符号，直接写进 scene_prompt_en，不需要单独的道具清单或道具编号。反复出现的同一物品保持颜色、形状等设计一致，但可以按叙事重点夸张改变画面中的比例。
4. 手机、桌椅、文件、告示牌和辅助符号随人物一起生成。根据叙事重点主动选择巨型手机、放大的屏幕展示、错落的物品组合或动作对峙；不用等用户另外要求。物品可夸张放大，透视、握持与遮挡要清楚。screen_inset 默认填 null，所需屏幕展示直接画在主图中。关键信息用少量屏幕/告示文字、对话或旁白讲清楚；留出排字位置，不要画台词气泡。
5. 人物默认完整入画，不要用画布边缘截断发髻、头发、发饰、手脚或衣摆；桌椅等的自然遮挡可以保留。明确要求半身或特写时可不显示下半身，但完整头部和最高处的发梢、发饰必须入画，在其上方至少预留画面高度 8% 的空白。高发髻、夸张动作或大手机放不下时，退远镜头或缩小整组主体。把这些取景要求写进每格 scene_prompt_en。
6. 只输出 JSON，不要任何其他文字。JSON 格式如下：

{{
  "title": "漫画标题",
  "characters": [
    {{"character_id": "英文编号", "name": "中文名", "role": "身份",
      "english_desc": "英文外貌穿着描述"}}
  ],
  "scenes": [
    {{"scene_id": "scene_01", "location": "地点",
      "characters": ["出场人物 id"],
      "story": "这一格发生了什么",
      "dialogues": [{{"speaker": "character_id", "text": "台词"}}],
      "caption": "图下方说明文字",
      "scene_prompt_en": "英文画面描述，含必要的屏幕内容，但不画对话与气泡",
      "screen_inset": null}}
  ]
}}"""
    prompt += "\n画面表现要求：\n" + SCENE_VISUAL_DIRECTION
    if background_mode == "transparent":
        prompt += "\n画面直接输出透明背景 PNG：在 scene_prompt_en 中明确要求真实透明背景，保留人物、叙事物品与强化情绪的漫画符号作为完整组合，外围和物品间空隙透明。地点用于决定物品与人物动作，不画外围房间、墙壁、远景与连续地面，不画白色或棋盘格背景。允许人物周围有孤立的警示标记、速度线等表现元素，不要求每格站立全身照。"
    provided = provided_characters or []
    prompt += f"\n环境与道具的参考画风：{object_style({'style': style, 'style_id': style_id})}。"
    if provided:
        original_names = [c["name"] for c in provided if c.get("reference_mode") != "stylized"]
        stylized_names = [c["name"] for c in provided if c.get("reference_mode") == "stylized"]
        prompt += "\n以下固定角色的参考图随消息附上，每张图前标明角色编号和名字。必须保留编号、名字和用户指定的身份，不能从外貌推断善恶或改换故事角色。请观察图片，在 english_desc 中用英文记录可见的发型、服装、颜色、身体比例和画风，不能虚构看不见的细节；外貌以图片为准，description 是用户补充要求。动作和道具持握方式需适合实际形象。不得重新设计角色。只有剧情必需时才补充其他配角。"
        if original_names:
            prompt += f"{'、'.join(original_names)} 使用上传的原始形象，角色自身保持附图的原画风和比例，style 仅用于协调环境与道具。"
        if stylized_names:
            prompt += f"{'、'.join(stylized_names)} 的形象会按目标画风重绘，参考图仅用于确定身份、服装与比例；画面按 style 统一风格。"
        prompt += "\n"
        prompt += json.dumps(provided, ensure_ascii=False)
    prompt += "\n画面中出现的角色必须与该格 characters 完全一致，手机屏幕、照片、倒影里的人物也算出场。不要在 scene_prompt_en 中引入未列出的角色。"
    prompt += '\n每句对话可附 bubble_type，选择 speech/ellipse/burst/thought/whisper；旁白仍放 caption。每格附 question（适合问答模板的问题，20字内）、heading（8字内章节名）。screen_inset 非空时必须是 {"screen_prompt_en":"英文屏幕描述"}。'
    image_refs = [
        (f"角色 {c['character_id']} = {c['name']}；故事身份：{c.get('role', '')}",
         pdir / "characters" / f"{store.valid_id(c['character_id'])}.png")
        for c in provided
    ]
    sb = llm.chat_json(prompt, image_refs=image_refs)
    if not isinstance(sb, dict) or not sb.get("scenes") or not sb.get("characters"):
        raise ValueError("故事生成结果缺少角色或分镜，请重新创建")
    if len(sb["scenes"]) != scene_count:
        raise ValueError(
            f"故事返回 {len(sb['scenes'])} 格，与要求的 {scene_count} 格不符，请重试"
        )
    by_id = {c["character_id"]: c for c in sb["characters"]}
    for c in provided:
        if c["character_id"] not in by_id:
            raise ValueError(f"故事未使用指定角色 {c['name']}，请重新创建")
        by_id[c["character_id"]].update(c)
        if not any(c["character_id"] in s.get("characters", []) for s in sb["scenes"]):
            raise ValueError(f"故事未让指定角色 {c['name']} 出场，请重新创建")
        by_id[c["character_id"]]["english_desc"] = (
            by_id[c["character_id"]].get("english_desc")
            or "Preserve the supplied reference character's exact identity, outfit and visual style."
        )
    for c in sb["characters"]:
        store.valid_id(c["character_id"])
    # New stories describe objects in the action and illustration prompt.
    # Existing projects keep their legacy data when loaded above.
    sb.pop("props", None)
    sb["schema_version"] = 2
    sb["characters_confirmed"] = False
    sb["background_mode"] = background_mode
    sb["long_layout"] = {"template_id": "cards", "gap": 60, "gaps": {}}
    # 补上项目元信息和风格（风格不进 LLM 提示词，画图时才用）
    sb["project_id"] = project_id
    sb["topic"] = topic
    sb["style_id"] = style_id
    sb["style"] = {
        "style_prompt": style["style_prompt"],
        "negative_prompt": style["negative_prompt"],
    }
    for i, scene in enumerate(sb.get("scenes", []), 1):
        scene.pop("props", None)
        scene.pop("retained_props", None)
        scene.setdefault("scene_id", f"scene_{i:02d}")
        store.valid_id(scene["scene_id"])
        if any(cid not in by_id for cid in scene.get("characters", [])):
            raise ValueError("分镜引用了未定义的角色")
        if scene.get("screen_inset") and not isinstance(scene["screen_inset"], dict):
            raise ValueError("屏幕特写描述格式错误，请重新创建")
        scene["screen_mode"] = "integrated"
        scene["order"] = i
        scene["stale"] = False
    store.save_storyboard(project_id, sb)
    # The initial multimodal result is already prepared. User edits change its
    # source and trigger preparation on the next generation, not on each save.
    for scene in sb["scenes"]:
        if all(by_id[cid].get("reference_source") == "upload" for cid in scene.get("characters", [])):
            meta = store.load_scene_meta(project_id, scene["scene_id"]) or {}
            meta["prompt_preparation"] = {"source": _prompt_source(project_id, sb, scene)}
            store.save_scene_meta(project_id, scene["scene_id"], meta)
    print(
        f"  已保存：storyboard.json（标题：{sb.get('title')}，{len(sb.get('scenes', []))} 格）"
    )
    return sb


def scene_reference_images(project_id: str, sb: dict, scene: dict) -> list:
    """Only identities and explicit local references inform the story model."""
    images = []
    local = scene.get("reference_assets", [])
    for character in sb["characters"]:
        cid = character["character_id"]
        if cid not in scene.get("characters", []):
            continue
        replacement = next((r for r in local if r.get("mode") == "replace_character"
                            and r.get("replace_character_id") == cid), None)
        path = (asset_path(project_id, replacement["asset_id"]) if replacement else
                store.project_dir(project_id) / "characters" / f"{store.valid_id(cid)}.png")
        if not path.exists():
            raise FileNotFoundError(f"角色参考图不存在：{character['name']}，请先生成或上传形象")
        images.append((f"角色 {cid} = {character['name']}；故事身份：{character.get('role', '')}", path))
    for ref in local:
        if ref.get("mode") != "replace_character":
            images.append(("本格补充参考，只参考物品或构图，不据此添加出场角色", asset_path(project_id, ref["asset_id"])))
    return images


def _prompt_source(project_id: str, sb: dict, scene: dict) -> dict:
    """Cache the editable visual inputs so lettering changes need no LLM call."""
    images = scene_reference_images(project_id, sb, scene)
    return deepcopy({
        "visual_direction": SCENE_VISUAL_DIRECTION,
        "scene": {key: scene.get(key) for key in (
            "scene_id", "story", "scene_prompt_en", "location", "characters",
            "screen_mode", "screen_enabled", "screen_inset", "reference_assets",
        )},
        "characters": [c for c in sb["characters"] if c["character_id"] in scene.get("characters", [])],
        "background": background_mode(sb, scene),
        "style": sb["style"],
        "images": [{"label": label, "path": str(path), "mtime_ns": path.stat().st_mtime_ns,
                    "size": path.stat().st_size} for label, path in images],
    })


def prepare_scene_prompt(project_id: str, sb: dict, scene: dict, edit_instruction: str | None = None) -> dict:
    """Return a prepared copy; the caller saves it only after image generation succeeds."""
    meta = store.load_scene_meta(project_id, scene["scene_id"]) or {}
    source = _prompt_source(project_id, sb, scene)
    previous_source = meta.get("prompt_preparation", {}).get("source", {})
    if not edit_instruction and previous_source == source:
        return dict(scene)
    print(f"  正在看角色参考图，整理 {scene['scene_id']} 的画面提示词……", flush=True)
    images = scene_reference_images(project_id, sb, scene)
    if edit_instruction:
        current = store.active_raw_path(project_id, scene["scene_id"])
        if current is None:
            raise ValueError("请先生成这一格，再基于当前图修改")
        images = [("当前待修改画面；其中人物可能画错，身份以随后标注的角色参考图为准", current), *images]
    # Do not expose cache paths or transport metadata to the model.
    context = {k: v for k, v in source.items() if k != "images"}
    context["dialogues"] = scene.get("dialogues", [])
    context["story_context"] = [{"scene_id": s["scene_id"], "story": s.get("story", "")}
                                for s in sb["scenes"]]
    index = next(i for i, s in enumerate(sb["scenes"]) if s["scene_id"] == scene["scene_id"])
    context["neighbor_compositions"] = [
        {"scene_id": s["scene_id"], "scene_prompt_en": s.get("scene_prompt_en", "")}
        for s in sb["scenes"][max(0, index - 1):index + 2] if s["scene_id"] != scene["scene_id"]
    ]
    # A direction update must not undo a user's successful image edit just
    # because its original story text still describes the pre-edit picture.
    if ({k: v for k, v in previous_source.items() if k != "visual_direction"}
            == {k: v for k, v in source.items() if k != "visual_direction"}):
        active = store.active_raw_path(project_id, scene["scene_id"])
        if active:
            history = meta.get("generation_history", {}).get(active.stem.rsplit("_", 1)[-1], {})
            context["confirmed_edit_instruction"] = history.get("edit_instruction", "")
    context["edit_instruction"] = edit_instruction or ""
    prompt = """你是漫画分镜编辑，同时负责画面设计。请看附带的角色参考图，把这一格的当前要求整理为一份完整、一致、有表现力的英文画面提示词。
只处理当前分镜，不重新创作故事，不修改用户的剧情、台词、身份或其他分镜。
规则：
1. 当前 characters 是允许出场的完整名单。严格匹配每张角色图的身份和外观，角色名必须同时标注 character_id；不根据物品参考或画风虚构人物。未勾选角色不能出现在现场、屏幕、照片或倒影中。台词可以来自画外，不代表说话者必须出现在图中。
2. 用户当前 story、人物勾选和明确的镜头要求优先于旧 scene_prompt_en。旧英文只保留仍适用的细节，删除冲突的动作、人物和镜头，不能把两套描述拼起来。若 story 为空，则以当前英文描述为动作依据。
3. edit_instruction 非空时，它是最新修改要求，优先于原动作和构图。根据要求可从当前 characters 中移除人物，但不能新增编号。保留未要求改变的细节。为空时 characters 原样返回。若有 confirmed_edit_instruction，它是用户已经采用的改图要求，优先于旧 story 和旧英文，但低于最新 edit_instruction；保留其已确定的构图、物品、表情和文字，不要退回改图前的版本。
4. 按 visual_direction 设计视觉中心、夸张表情、动作与物品的主次大小。不必拘泥于旧英文的“小手机、自然比例、平视、只留家具、禁止独立放大展示”等保守写法；这些默认限制可改写，明确的用户要求仍优先。screen_enabled=false 时不画屏幕设备。背景按 background 执行：transparent 时保留人物、叙事物品和漫画表现符号，外围与空隙透明。
5. 参考图决定角色的脸、发型、衣服、颜色和比例。reference_mode=original 的上传角色保持附图的原画风，style 仅用于协调环境与道具；reference_mode=stylized 的上传角色会被预先按 style 重绘，参考图只决定身份与造型，画面整体按 style 统一风格。允许剧情需要的简短屏幕文字、标语，禁止绘制台词气泡和旁白。排除其他角色时要写清是额外人物，不能用 no faces、no hands 等描述误删已选角色的必要特征。
6. 直接根据当前 location、story 和动作自动安排叙事物品、辅助符号及其位置，无需用户勾选道具。旧英文里与当前剧情冲突的物品应删除，仍适用的外观细节可保留；不必照搬旧图的桌椅。neighbor_compositions 只用于避免相邻格构图重复，不能把其他格的角色、事件或无关物品搬到本格。
7. 人物默认完整入画，禁止画布边缘截断人物轮廓；允许桌椅等物品自然遮挡。明确要求半身或特写时可省略下半身，但完整头部、发型、发髻及发饰必须保留。在最高发梢或发饰上方至少预留画面高度 8% 的空白，不能只按额头计算；手和可见衣摆也不要被边缘意外裁断。画面拥挤时退远镜头或缩小整组主体，不能为突出手机而裁掉人物头发。整理时修正旧描述或当前图中不完整的取景。
只输出 JSON：{"scene_prompt_en":"整理后的完整英文画面描述，不含互相冲突的旧要求", "characters":["实际出场角色 id"]}。
分镜输入 JSON：
""" + json.dumps(context, ensure_ascii=False)
    result = llm.chat_json(prompt, temperature=0.2, image_refs=images)
    if not isinstance(result, dict):
        raise ValueError("分镜整理没有返回有效对象，请重试；原画面已保留")
    prepared_prompt = result.get("scene_prompt_en")
    cast = result.get("characters")
    allowed = scene.get("characters", [])
    if (not isinstance(prepared_prompt, str) or not prepared_prompt.strip() or len(prepared_prompt) > 8000
            or not isinstance(cast, list) or any(not isinstance(cid, str) or cid not in allowed for cid in cast)
            or len(cast) != len(set(cast)) or (not edit_instruction and set(cast) != set(allowed))):
        raise ValueError("分镜整理改变了指定角色或缺少画面描述，请重试；原画面已保留")
    prepared = dict(scene)
    prepared["scene_prompt_en"] = prepared_prompt.strip()
    prepared["characters"] = [cid for cid in allowed if cid in cast]
    prepared["reference_assets"] = [r for r in scene.get("reference_assets", [])
                                    if r.get("mode") != "replace_character" or r.get("replace_character_id") in cast]
    return prepared
