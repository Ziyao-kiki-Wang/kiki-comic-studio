"""Render an isolated copy of an existing project, without paid generation calls."""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "projects" / "comic_20260907_092215"
QA_ROOT = ROOT / "output" / "qa-projects"
os.environ["COMIC_PROJECTS_DIR"] = str(QA_ROOT)
TARGET = QA_ROOT / "studio_preview"
TARGET.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(SOURCE, TARGET, dirs_exist_ok=True)

from PIL import Image, ImageDraw
from server import store
from server.core import lettering, compose
from server.core.studio import TEMPLATES

pid = "studio_preview"
sb = store.load_storyboard(pid)
sb.update(
    {
        "project_id": pid,
        "characters_confirmed": True,
        "background_mode": "scene",
        "long_layout": {
            "template_id": "cards",
            "gap": 60,
            "gaps": {},
            "footer": "陌生来电先核实，转账汇款多留心。",
        },
    }
)
types = ["burst", "speech", "thought", "ellipse", "whisper", "caption"]
for i, s in enumerate(sb["scenes"]):
    s["heading"] = ["高额回报的诱惑", "第一次转账", "越陷越深", "及时止损"][i]
    s["question"] = [
        "承诺高额回报，可信吗？",
        "收到转账要求，怎么办？",
        "对方继续要钱，怎么办？",
        "发现被骗后，怎么办？",
    ][i]
    meta = store.load_scene_meta(pid, s["scene_id"])
    for j, b in enumerate(meta.get("bubbles", [])):
        b.update(
            {"type": types[(i * 2 + j) % len(types)], "width": 440, "font_size": 34}
        )
        b.pop("geometry", None)
    store.save_scene_meta(pid, s["scene_id"], meta)
store.save_storyboard(pid, sb)
lettering.letter_all(pid, sb)
folder = ROOT / "output" / "studio-validation"
folder.mkdir(parents=True, exist_ok=True)
thumbs = []
for kind, t in TEMPLATES.items():
    image, layout = compose.render_long_image(pid, sb, {"template_id": kind})
    image.save(folder / f"template-{kind}.png")
    preview = image.copy()
    preview.thumbnail((210, 1100))
    thumbs.append((t["name"], preview))
sheet = Image.new("RGB", (5 * 230, ((len(thumbs) + 4) // 5) * 1170), "#e8eaef")
draw = ImageDraw.Draw(sheet)
for i, (name, thumb) in enumerate(thumbs):
    x = (i % 5) * 230 + 10
    y = (i // 5) * 1170 + 10
    draw.text((x, y), name, font=lettering.load_font(21), fill="#222222")
    sheet.paste(thumb, (x, y + 38))
sheet.save(folder / "template-gallery.png")
compose.make_long_image(pid, sb)
print("All templates rendered", flush=True)
print("Validation project:", TARGET, flush=True)
