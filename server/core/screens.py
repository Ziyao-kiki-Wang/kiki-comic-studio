# -*- coding: utf-8 -*-
"""第 4 步：手机屏幕特写素材生成。

注意：提示词必须写明"只画屏幕内容，不要手机外壳"，
否则 AI 会把手机边框画进去，贴进特写框后出现"框套框"。
"""

from server import store
from server.services import image_gen
from server.core.studio import screen_enabled


def generate_screens(project_id: str, sb: dict, only_scene: str | None = None):
    print("第 4 步：生成手机屏幕特写素材……")
    pdir = store.project_dir(project_id)
    for scene in sb["scenes"]:
        inset = scene.get("screen_inset")
        if not screen_enabled(scene) or not inset or scene.get("screen_mode", "integrated") != "inset":
            continue
        sid = scene["scene_id"]
        path = pdir / "screens" / f"{sid}_screen.png"
        meta = store.load_scene_meta(project_id, sid) or {}
        if path.exists() and only_scene != sid and not meta.get("screen_content_stale"):
            print(f"  {sid} 屏幕素材已存在，跳过")
            continue
        print(f"  生成 {sid} 的手机屏幕……（约 1 分钟）")
        prompt = (
            f"A smartphone screen, full-screen mobile app interface, flat modern UI design. "
            f"Screen content only, full-bleed UI, no phone frame or bezel. "
            f"On the screen: {inset['screen_prompt_en']}. "
            f"Chinese text on the screen must be rendered accurately and clearly."
        )
        try:
            image_gen.generate(prompt, path, size="1024x1536")
        except image_gen.ModerationBlocked as e:
            # 详细描述（如涉及扣款/卡号的诈骗界面）容易误触 fraud 防护，
            # 降级为泛化描述重试一次；再失败就把原始错误抛清楚
            print(f"  [降级] 屏幕素材提示词被审核拦截，改用泛化描述重试……")
            fallback = (
                "A smartphone screen, full-screen mobile app interface, flat modern UI design. "
                "Screen content only, full-bleed UI, no phone frame or bezel. "
                "On the screen: a generic app page with a red warning banner at the top, "
                "several notification cards with large clear Chinese text, and simple form fields. "
                "Educational anti-fraud illustration, no logos, no personal data."
            )
            try:
                image_gen.generate(fallback, path, size="1024x1536")
            except image_gen.ModerationBlocked:
                raise RuntimeError(
                    f"{sid} 屏幕素材两次被审核拦截。原始错误：{e}\n"
                    f"请手动修改 storyboard.json 里该格的 screen_prompt_en 后重跑。"
                ) from e
        meta["screen_content_stale"] = False
        meta["render_stale"] = True
        store.save_scene_meta(project_id, sid, meta)
