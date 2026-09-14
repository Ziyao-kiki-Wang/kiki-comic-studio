# -*- coding: utf-8 -*-
"""第 1 步：LLM 写故事表（gpt-5.6-sol，含 props 和 screen_inset 字段）。"""

import json

from server import store
from server.config import SCHEMAS_DIR
from server.services import llm


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
    prompt = f"""你是一个漫画编剧。请根据下面的主题，写一部 {scene_count} 格漫画的故事表。

主题：{topic}

要求：
1. 对话口语化、简短，每格 1-3 句对话，说明文字（caption）一句话。
2. 人物 2 个左右，外貌穿着的英文描述要具体（发型、脸型、年龄、衣服）。
3. 故事里反复出现的重要道具（如手机、银行卡、宣传单）列入 props，附英文外观描述。
4. 手机、桌椅、文件等应由模型随人物一起生成，融入自然动作、透视、接触和遮挡。需要看到屏幕时使用越肩视角、向他人展示手机或有情节依据的展示物，不要默认在旁边贴一个巨大屏幕卡片。screen_inset 默认填 null，关键信息用简短屏幕文字、对话或旁白讲清楚。每格用不同姿态和景别，让人物表情生动；留出少量自然空白供后期气泡排字，不要画气泡。
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
      "scene_prompt_en": "英文画面描述，含必要的屏幕内容，但不画对话与气泡",
      "screen_inset": null}}
  ]
}}"""
    if background_mode == "transparent":
        prompt += "\n画面直接输出透明背景 PNG：在 scene_prompt_en 中明确要求真实透明背景，保留人物与参与动作的桌椅、沙发、手机、文件和展示牌作为完整组合，外围和物品间空隙透明。地点仅用于决定道具与人物动作，不画外围房间、墙壁、远景与连续地面，不画白色或棋盘格背景。不是只留下人物，也不要求每格站立全身照。"
    provided = provided_characters or []
    if provided:
        prompt += "\n以下是用户提供的固定角色（附图将直接用于绘制）。必须保留编号、名字、身份，并让主人公出场。不得重新设计其外貌或服装；english_desc 只描述身份动作，注明严格以参考图为准。可以补充其他配角。\n"
        prompt += json.dumps(provided, ensure_ascii=False)
    prompt += '\n每句对话可附 bubble_type，选择 speech/ellipse/burst/thought/whisper；旁白仍放 caption。每格附 question（适合问答模板的问题，20字内）、heading（8字内章节名）。screen_inset 非空时必须是 {"screen_prompt_en":"英文屏幕描述"}。'
    sb = llm.chat_json(prompt)
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
            c.get("description")
            or "Preserve the supplied reference character's exact identity, outfit and visual style."
        )
    for c in sb["characters"]:
        store.valid_id(c["character_id"])
    for p in sb.get("props", []):
        store.valid_id(p["prop_id"])
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
    print(
        f"  已保存：storyboard.json（标题：{sb.get('title')}，{len(sb.get('scenes', []))} 格）"
    )
    return sb
