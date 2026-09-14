# -*- coding: utf-8 -*-
"""命令行入口。

用法：
    python -m server.cli new --topic "..." --scenes 5 --style commercial_comic
    python -m server.cli run --project <id>                        # 全流程（有缓存自动跳过）
    python -m server.cli run --project <id> --rerun scene_03       # 单格重跑（生成新版本）
    python -m server.cli run --project <id> --rollback scene_03 1  # 回滚到 v1
    python -m server.cli run --project <id> --regen-character customer_01
    python -m server.cli list
"""

import argparse
import sys

from server import store
from server.core import characters, compose, lettering, scenes, screens, story


def cmd_new(args):
    pid = store.new_project_id()
    store.init_dirs(pid)
    sb = story.create_storyboard(pid, args.topic, args.scenes, args.style, force=True)
    print(f"\n项目已创建：{pid}")
    print(f"目录：projects/{pid}/")
    print(f"下一步：python -m server.cli run --project {pid}")
    return pid


def _reload_sb(project_id: str) -> dict:
    return store.load_storyboard(project_id)


def run_pipeline(project_id: str):
    """全流程：人物 → 场景 → 屏幕素材 → 合成 → 拼长图（每步有缓存自动跳过）。"""
    sb = _reload_sb(project_id)
    stale = store.stale_scenes(sb)
    if stale:
        print(f"[提醒] 这些格子引用的角色重画过，建议重跑：{', '.join(stale)}")
        print(f"       （不会自动重画；用 --rerun <scene_id> 单独重跑）")
    refs = characters.generate_references(project_id, sb)
    scenes.generate_scenes(project_id, _reload_sb(project_id), refs)
    screens.generate_screens(project_id, _reload_sb(project_id))
    lettering.letter_all(project_id, _reload_sb(project_id))
    compose.make_long_image(project_id, _reload_sb(project_id))


def rerun_scene(project_id: str, scene_id: str, edit_instruction: str | None = None):
    """单格重跑：场景原图生成新版本（旧版保留），重新合成、重拼长图。"""
    sb = _reload_sb(project_id)
    scene = next((s for s in sb["scenes"] if s["scene_id"] == scene_id), None)
    if not scene:
        raise ValueError(f"故事表里没有 {scene_id}")
    refs = characters.generate_references(project_id, sb)  # 有缓存，基本全跳过
    ver = scenes.generate_scene(
        project_id, sb, scene, refs, force=True, edit_instruction=edit_instruction
    )
    print(f"  {scene_id} 新版本 {ver} 已设为 active")
    screens.generate_screens(project_id, sb)  # 屏幕素材有缓存，会自动跳过
    lettering.letter_scene(project_id, sb, scene, force=True)
    compose.make_long_image(project_id, sb)


def rollback_scene(project_id: str, scene_id: str, version: int):
    """回滚 active 版本，重新合成、重拼长图。"""
    p = store.rollback(project_id, scene_id, version)
    print(f"  {scene_id} 已回滚到 v{version}（{p.name}）")
    sb = _reload_sb(project_id)
    scene = next(s for s in sb["scenes"] if s["scene_id"] == scene_id)
    lettering.letter_scene(project_id, sb, scene, force=True)
    compose.make_long_image(project_id, sb)


def cmd_run(args):
    pid = args.project
    store.project_dir(pid)  # 校验项目存在
    if args.regen_character:
        sb = _reload_sb(pid)
        characters.generate_references(pid, sb, only_character=args.regen_character)
        print("人物已重画。继续走正常流程（引用它的格子已标 stale，不会自动重画）。")
    if args.rollback:
        scene_id, version = args.rollback
        rollback_scene(pid, scene_id, int(version))
        return
    if args.rerun:
        rerun_scene(pid, args.rerun)
        return
    run_pipeline(pid)


def cmd_list(_args):
    pids = store.list_projects()
    if not pids:
        print("还没有项目。用 new 创建一个。")
        return
    for pid in pids:
        try:
            sb = store.load_storyboard(pid)
            stale = store.stale_scenes(sb)
            tag = f"（{len(sb.get('scenes', []))} 格，标题：{sb.get('title')}）"
            if stale:
                tag += f" [stale: {', '.join(stale)}]"
        except FileNotFoundError:
            tag = "（无 storyboard.json）"
        print(f"  {pid} {tag}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="server.cli", description="AI 漫画长图生产工具（第 1 期：后端核心引擎）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="创建项目并让 LLM 写故事表")
    p_new.add_argument("--topic", required=True, help="漫画主题")
    p_new.add_argument("--scenes", type=int, default=5, help="格数（默认 5）")
    p_new.add_argument(
        "--style", default="commercial_comic", help="风格 id（见 schemas/styles.json）"
    )
    p_new.set_defaults(func=cmd_new)

    p_run = sub.add_parser("run", help="执行全流程 / 单格重跑 / 回滚 / 重画人物")
    p_run.add_argument("--project", required=True, help="项目 id")
    p_run.add_argument("--rerun", metavar="SCENE_ID", help="重跑某一格（生成新版本）")
    p_run.add_argument(
        "--rollback",
        nargs=2,
        metavar=("SCENE_ID", "VERSION"),
        help="回滚某格到指定版本",
    )
    p_run.add_argument(
        "--regen-character", metavar="CHARACTER_ID", help="重画人物标准照并传播 stale"
    )
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="列出所有项目")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as e:
        print(f"\n[错误] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
