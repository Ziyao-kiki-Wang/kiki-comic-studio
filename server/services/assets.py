"""Project owned assets and fonts.

The editor intentionally addresses every uploaded file by an opaque, validated
``asset_id``.  The JSON registry is the source of truth for metadata while the
actual bytes live below the project directory.  Renderers use this module too,
so an asset can never turn into an arbitrary filesystem path through layout
JSON.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
import time
import uuid
from pathlib import Path

from PIL import Image, ImageOps, ImageFont, UnidentifiedImageError

from server import store

MAX_ASSET_UPLOAD = 8 * 1024 * 1024
MAX_FONT_UPLOAD = 32 * 1024 * 1024
MAX_PIXELS = 20_000_000
ASSET_KINDS = {"sticker", "scene_reference", "title_image", "image"}
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
FONT_LIBRARY_DIR = Path(__file__).resolve().parents[2] / "fonts"
_ASSET_DATA_RE = re.compile(
    r"^data:image/(?:png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)
_FONT_DATA_RE = re.compile(
    r"^data:(?:font/(?:ttf|otf|collection|x-font-ttf|x-font-opentype)|"
    r"application/(?:x-font-ttf|x-font-opentype|font-sfnt));base64,"
    r"([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)


def _catalog() -> dict[str, dict]:
    import json

    # ``store.PROJECTS_DIR`` is monkeypatched in tests; locate the repository
    # schema from this module instead of relying on that temporary directory.
    path = Path(__file__).resolve().parents[2] / "schemas" / "fonts.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in value.get("fonts", [])}


def font_catalog() -> list[dict]:
    return list(_catalog().values())


def _asset_id(value: str) -> str:
    try:
        return store.valid_id(value)
    except ValueError as exc:
        raise ValueError("asset_id 只能包含字母、数字、下划线和连字符") from exc


def _asset_registry(project_id: str) -> dict:
    return store.load_assets(project_id)


def _safe_record_path(project_id: str, record: dict) -> Path:
    asset_id = _asset_id(record.get("asset_id", ""))
    if record.get("asset_id") != asset_id:
        raise ValueError("素材 asset_id 无效")
    rel = record.get("path")
    if not isinstance(rel, str) or not rel:
        raise ValueError("素材路径无效")
    base = store.project_dir(project_id).resolve()
    target = (base / rel).resolve()
    if (
        not target.is_relative_to(base)
        or target.parent != base / "assets"
        or target.name != f"{asset_id}{target.suffix}"
    ):
        raise ValueError("素材路径必须位于当前项目且与 asset_id 匹配")
    return target


def asset_record(project_id: str, asset_id: str) -> dict:
    asset_id = _asset_id(asset_id)
    record = _asset_registry(project_id).get("assets", {}).get(asset_id)
    if not isinstance(record, dict):
        raise FileNotFoundError(f"素材不存在：{asset_id}")
    path = _safe_record_path(project_id, record)
    if not path.is_file():
        raise FileNotFoundError(f"素材文件不存在：{asset_id}")
    return record


def asset_path(project_id: str, asset_id: str) -> Path:
    record = asset_record(project_id, asset_id)
    return _safe_record_path(project_id, record)


def _decode_data(data: str, pattern: re.Pattern[str], limit: int) -> bytes:
    if not isinstance(data, str) or len(data) > limit * 4 // 3 + 200:
        raise ValueError("上传文件过大")
    match = pattern.fullmatch(data)
    if not match:
        raise ValueError("请上传支持的 base64 文件")
    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("base64 文件损坏") from exc
    if len(raw) > limit:
        raise ValueError("上传文件过大")
    return raw


def decode_asset(data: str) -> tuple[bytes, dict]:
    """Decode a raster upload to a normalized RGBA PNG and return dimensions."""
    raw = _decode_data(data, _ASSET_DATA_RE, MAX_ASSET_UPLOAD)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("请上传 PNG、JPEG 或 WebP 图片")
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("图片尺寸过大")
            image.load()
            normalized = ImageOps.exif_transpose(image).convert("RGBA")
            output = io.BytesIO()
            normalized.save(output, format="PNG", optimize=True)
            return output.getvalue(), {
                "width": normalized.width,
                "height": normalized.height,
                "mime_type": "image/png",
            }
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("图片文件损坏或无法读取") from exc


def _filename(filename: str, default: str = "image.png") -> str:
    if not isinstance(filename, str) or not filename.strip():
        return default
    name = Path(filename).name.strip()
    if not name or name in {".", ".."} or len(name) > 160:
        return default
    return name


def create_asset(
    project_id: str,
    data: str,
    *,
    kind: str = "sticker",
    filename: str = "image.png",
    scene_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    if kind not in ASSET_KINDS:
        raise ValueError(f"未知素材类型：{kind}")
    if scene_id is not None:
        store.valid_id(scene_id)
    content, image_meta = decode_asset(data)
    asset_id = "asset_" + uuid.uuid4().hex[:18]
    rel = f"assets/{asset_id}.png"
    path = store.project_dir(project_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    record = {
        "asset_id": asset_id,
        "kind": kind,
        "filename": _filename(filename),
        "path": rel,
        "scene_id": scene_id,
        "created_at": time.time(),
        **image_meta,
    }
    if metadata:
        record["metadata"] = dict(metadata)
    registry = _asset_registry(project_id)
    registry.setdefault("assets", {})[asset_id] = record
    store.save_assets(project_id, registry)
    return record


def delete_asset(project_id: str, asset_id: str):
    """Delete an owned asset after resolving it through the registry."""
    record = asset_record(project_id, asset_id)
    path = _safe_record_path(project_id, record)
    registry = _asset_registry(project_id)
    registry.setdefault("assets", {}).pop(record["asset_id"], None)
    store.save_assets(project_id, registry)
    path.unlink(missing_ok=True)


def project_assets(project_id: str, kind: str | None = None) -> list[dict]:
    records = list(_asset_registry(project_id).get("assets", {}).values())
    if kind:
        if kind not in ASSET_KINDS:
            raise ValueError(f"未知素材类型：{kind}")
        records = [r for r in records if r.get("kind") == kind]
    return sorted(records, key=lambda item: item.get("created_at", 0))


def decode_font(data: str, filename: str) -> tuple[bytes, str]:
    filename = _filename(filename, "font.ttf")
    ext = Path(filename).suffix.lower()
    if ext not in FONT_EXTENSIONS:
        raise ValueError("字体文件必须是 TTF、OTF 或 TTC")
    raw = _decode_data(data, _FONT_DATA_RE, MAX_FONT_UPLOAD)
    if len(raw) < 12:
        raise ValueError("字体文件过小或已损坏")
    # TrueType/OpenType/TrueType collection signatures.  A few valid fonts
    # use a nonstandard signature, so PIL remains the final compatibility check.
    if raw[:4] not in {b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true"}:
        raise ValueError("字体文件格式无效")
    try:
        ImageFont.truetype(io.BytesIO(raw), 16)
    except (OSError, ValueError) as exc:
        raise ValueError("字体文件无法被 Pillow 读取") from exc
    return raw, ext


def save_font(project_id: str, font_id: str, data: str, filename: str) -> dict:
    catalog = _catalog()
    if font_id not in catalog:
        raise ValueError("未知字体槽位")
    raw, ext = decode_font(data, filename)
    folder = store.project_dir(project_id) / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    # One active file per slot keeps loading deterministic.  The old file is
    # replaced atomically only after the upload passed validation.
    target = folder / f"{font_id}{ext}"
    for candidate in folder.glob(f"{font_id}.*"):
        if candidate != target:
            candidate.unlink(missing_ok=True)
    temp = target.with_name(target.name + f".{uuid.uuid4().hex}.tmp")
    temp.write_bytes(raw)
    temp.replace(target)
    # Font metrics are part of cached bubble geometry.  Mark only consumers of
    # this slot stale and clear their geometry so the next render measures with
    # the new file; unrelated scenes remain ready for export.
    try:
        storyboard = store.load_storyboard(project_id)
    except FileNotFoundError:
        storyboard = None
    if storyboard is not None:
        changed = False
        for scene in storyboard.get("scenes", []):
            scene_uses = {
                scene.get("bubble_font_id"),
                scene.get("caption_font_id"),
            }
            meta = store.load_scene_meta(project_id, scene.get("scene_id")) or {}
            scene_uses.add((meta.get("caption_layout") or {}).get("font_id"))
            bubbles = meta.get("bubbles", [])
            for bubble in bubbles:
                if bubble.get("font_id") or bubble.get("font_family"):
                    scene_uses.add(bubble.get("font_id") or bubble.get("font_family"))
            if font_id not in scene_uses:
                continue
            for bubble in bubbles:
                if (bubble.get("font_id") or bubble.get("font_family")) == font_id:
                    bubble.pop("geometry", None)
            meta["render_stale"] = True
            meta["status"] = "draft"
            store.save_scene_meta(project_id, scene["scene_id"], meta)
            scene["font_stale"] = True
            changed = True
        layout = storyboard.get("long_layout") or {}
        if font_id in {layout.get("title_font_id"), layout.get("body_font_id")}:
            storyboard["long_layout_stale"] = True
            changed = True
        if changed:
            store.save_storyboard(project_id, storyboard)
    return {
        "font_id": font_id,
        "filename": _filename(filename),
        "path": f"fonts/{target.name}",
        "size": len(raw),
        "updated_at": time.time(),
        "source": "project",
        "url": f"/api/projects/{project_id}/fonts/{font_id}/file?v={target.stat().st_mtime_ns}",
    }


def font_record(project_id: str, font_id: str) -> dict | None:
    catalog = _catalog()
    if font_id not in catalog:
        raise ValueError("未知字体槽位")
    folder = store.project_dir(project_id) / "fonts"
    for ext in FONT_EXTENSIONS:
        path = folder / f"{font_id}{ext}"
        if path.is_file():
            return {
                "font_id": font_id,
                "filename": path.name,
                "path": f"fonts/{path.name}",
                "size": path.stat().st_size,
                "updated_at": path.stat().st_mtime,
                "source": "project",
                "url": f"/api/projects/{project_id}/fonts/{font_id}/file?v={path.stat().st_mtime_ns}",
            }
    shared = (FONT_LIBRARY_DIR / catalog[font_id].get("file", "")).resolve()
    if shared.is_relative_to(FONT_LIBRARY_DIR.resolve()) and shared.is_file():
        return {
            "font_id": font_id,
            "filename": shared.name,
            "path": shared.relative_to(FONT_LIBRARY_DIR.resolve()).as_posix(),
            "size": shared.stat().st_size,
            "updated_at": shared.stat().st_mtime,
            "source": "shared",
            "url": f"/api/projects/{project_id}/fonts/{font_id}/file?v={shared.stat().st_mtime_ns}",
        }
    return None


def project_fonts(project_id: str) -> list[dict]:
    return [
        {**item, "installed": font_record(project_id, item["id"])}
        for item in font_catalog()
    ]


def font_path(project_id: str, font_id: str) -> Path | None:
    record = font_record(project_id, font_id)
    if not record:
        return None
    if record.get("source") == "shared":
        return FONT_LIBRARY_DIR / record["path"]
    base = store.project_dir(project_id).resolve()
    target = (base / record["path"]).resolve()
    if not target.is_relative_to(base) or target.parent != (base / "fonts"):
        raise ValueError("字体路径必须位于当前项目 fonts 目录")
    return target
