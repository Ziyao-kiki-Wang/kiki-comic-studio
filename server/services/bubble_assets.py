"""Shared, bundled bubble artwork. No project-specific copies or external URLs."""
from server.config import ROOT_DIR
from server.core.studio import BUBBLES

ASSET_DIR = ROOT_DIR / "web" / "public" / "bubble-assets"
VARIANTS = ("transparent", "white", "3d")

def filename(kind, variant="white"):
    if kind not in BUBBLES:
        return None
    spec = BUBBLES.get(kind, {})
    prefix = spec.get("asset_prefix")
    if not prefix and variant == "3d":
        prefix = "original_" + kind
    return f"{prefix}-{variant}.png" if prefix and variant in VARIANTS else None

def asset_path(kind, variant="white"):
    name = filename(kind, variant)
    if not name:
        return None
    path = ASSET_DIR / name
    if not path.is_file():
        raise ValueError("这款气泡素材尚未制作完成，请选择其他版本")
    return path
