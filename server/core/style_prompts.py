"""Shared scene presentation and rendering styles; character identities stay fixed."""

# The actual direction is part of the preparation input, so older restrained
# prompts are refreshed when a scene is next generated, without redrawing caches.
SCENE_VISUAL_DIRECTION = """默认采用表现力强的广告科普漫画构图，夸张、有戏、精致，缩成手机上的小图也能立刻看懂。
1. 每格先选一个视觉中心：关键物品/关键信息，或人物的关键动作。用主次大小、前后层次和斜向布局突出它，避免人物均匀站一排、平视证件照或每格坐着看小手机。必要时将手机、告示牌、礼物堆等夸张放大到接近人物大小；不受现实尺寸限制，但手、肢体数量和接触关系必须合理。
2. 把情绪写成可画的眉眼、嘴形和身体动作：惊讶时瞪眼张嘴并后仰，受骗时急得跺脚或抓头，警觉时猛地伸手阻止，识破后果断行动，推荐时热情探身。按当前剧情选择，不要每格都惊恐，也不要只写“表情生动”。夸张表演不能改变角色的固定形象和故事身份。
3. 选 1–3 组与本格相关的辅助元素，例如通知弹窗、礼品货堆、风险告示、放大镜、锁形图标或对错标记，增加信息和层次；可加入少量无文字的惊讶线、速度线、汗滴、怒气或闪光。符号是漫画表现，不是新增剧情事件；没有意义的家具和装饰不凑数。
4. 根据故事安排不同构图：巨物特写、人物与物品错落组合、双方动作对峙、围绕告示牌讲解、果断行动等。相邻格改变主体方向、大小关系和动作，不要把所有格都做成巨型手机。结尾也要有明确而有力的动作。只借鉴这些表现方式，不能引入别的角色、服装或外貌。
5. 保持场景、人物名单、事件和用户指定文字/金额/数字。只改变画面表现，不为了丰富画面虚构收益率、损失金额、权威结论或新的事件；无依据时用通用图标和已有短语。屏幕或告示牌只突出少量剧情关键信息，不密铺小字。台词气泡、旁白、章节标题仍留给后期排版，不直接画进图里。
6. 主体组合要醒目，充分利用画面中部；在完整头发和发饰上方保留至少 8% 的空间，并留侧边排字位置，不能因完整入画就缩成远处小人。透明模式下，人物、物品和漫画符号直接组成透明素材，空隙保持透明，不加整块海报底板、假白底或棋盘格。
7. scene_prompt_en 具体写清本格的视觉中心、相对大小、姿态表情、物品/符号位置和关键文字，约 120–220 个英文词；不要堆砌“好看、高质量”等空泛词。用户明确指定克制、真实比例或其他构图时遵循用户要求。按图修改时，只在修改范围内加强表现，保留未要求改变的内容。"""

SCENE_RENDER_DIRECTION = (
    "VISUAL PRESENTATION: use the prepared scene's expressive educational-advertising comic composition. "
    "Give the story one unmistakable visual focal point, strong scale hierarchy, layered depth, lively diagonals "
    "and bold readable acting. Enlarge a story-critical object when it helps communicate the scene; "
    "literal real-world object scale is not required. Keep character anatomy, limb counts and contact coherent. "
    "Use the specified supporting objects and a few purposeful comic accents such as reaction rays, sweat drops, "
    "motion strokes or warning symbols. These accents are allowed illustration content, not dialogue balloons. "
    "They must remain isolated on alpha in transparent mode. Keep the subject group prominent within the safe "
    "frame, never tiny figures floating in excessive empty space. Preserve each reference character's identity "
    "and art style. Do not invent extra cast, events, amounts, percentages or claims for decoration. "
    "Follow explicit user composition and restraint requests over this default; when editing, preserve "
    "the composition and expression outside the requested changes. "
)

def object_style(sb: dict) -> str:
    if sb.get("style_id") == "chibi":
        return "comic object illustration, simple bright colors, thick clean outlines, rounded object shapes"
    character_terms = {"cute round characters", "big expressive eyes", "super deformed cute characters", "big head small body"}
    return ", ".join(part.strip() for part in sb["style"]["style_prompt"].split(",")
                     if part.strip().lower() not in character_terms)


def negative_style(sb: dict) -> str:
    # Lettering is composed later; screen text and signs are part of the image.
    omitted = {"text", "words", "letters", "speech bubble"}
    return ", ".join("no " + part.strip() for part in sb["style"]["negative_prompt"].split(",")
                     if part.strip() and part.strip().lower() not in omitted)
