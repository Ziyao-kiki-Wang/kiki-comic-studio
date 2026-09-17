"""Decode bounded raster uploads; keep supplied character references out of AI regeneration."""

import base64
import binascii
import io
import re
import time
from PIL import Image, ImageOps, UnidentifiedImageError
from server import store

MAX_UPLOAD = 8 * 1024 * 1024


def decode_image(data_url: str) -> bytes:
    if not isinstance(data_url, str) or len(data_url) > MAX_UPLOAD * 4 // 3 + 100:
        raise ValueError("图片不能超过 8 MB")
    match = re.fullmatch(
        r"data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)", data_url
    )
    if not match:
        raise ValueError("请上传 PNG、JPEG 或 WebP 图片")
    try:
        raw = base64.b64decode(match[1], validate=True)
        if len(raw) > MAX_UPLOAD:
            raise ValueError("图片不能超过 8 MB")
        with Image.open(io.BytesIO(raw)) as im:
            if (
                im.format not in ("PNG", "JPEG", "WEBP")
                or im.width * im.height > 20_000_000
            ):
                raise ValueError("图片尺寸过大或格式不受支持")
            im.load()
            out = io.BytesIO()
            ImageOps.exif_transpose(im).convert("RGBA").save(out, format="PNG")
            return out.getvalue()
    except (
        binascii.Error,
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("图片文件损坏或无法读取") from exc


def save_reference(pid: str, cid: str, png: bytes):
    """保存用户上传的人物图。

    {cid}_original.png 永远保存上传原图；{cid}.png 是实际用于生成的
    生效参考图（原始模式=原图，风格化模式=风格化后的版本）。
    """
    store.valid_id(cid)
    folder = store.project_dir(pid) / "characters"
    folder.mkdir(exist_ok=True)
    path = folder / f"{cid}.png"
    if path.exists():
        archive = folder / "history"
        archive.mkdir(exist_ok=True)
        (archive / f"{cid}_{time.time_ns()}.png").write_bytes(path.read_bytes())
    path.write_bytes(png)
    # 新上传恢复原图记录并回到原始模式；风格化产物已对应旧图，作废
    (folder / f"{cid}_original.png").write_bytes(png)
    (folder / f"{cid}_styled.png").unlink(missing_ok=True)
    (folder / f"{cid}_rgba.png").unlink(missing_ok=True)
