"""Prepare the user-authorized bubble cutouts from reference scans and API renders.

Only derived assets are written; reference images and raw generation results stay intact.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "web/public/bubble-assets"

def trim(image):
    alpha = image.getchannel("A")
    bounds = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bounds:
        raise ValueError("Empty bubble artwork")
    tile = image.crop(bounds)
    result = Image.new("RGBA", (tile.width + 32, tile.height + 32))
    result.alpha_composite(tile, (16, 16))
    return result

def ink_variants(source):
    gray = np.asarray(source.convert("L"), dtype=float)
    alpha = np.clip((210-gray)*255/80, 0, 255).astype(np.uint8)
    ink = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    ink[:,:,3] = alpha
    # Fill only closed regions; the exterior remains truly transparent.
    outline = alpha > 32
    filled = ndimage.binary_fill_holes(outline)
    # Scanned brush lines can have tiny breaks. Seal only for the interior mask;
    # the visible ink itself remains unchanged.
    for radius in (3, 8, 16):
        if filled[filled.shape[0]//2, filled.shape[1]//2]:
            break
        barrier = ndimage.binary_dilation(outline, iterations=radius)
        filled = ndimage.binary_erosion(ndimage.binary_fill_holes(barrier), iterations=radius)
    white = np.zeros_like(ink)
    white[filled] = [255,255,255,255]
    face = Image.fromarray(white)
    face.alpha_composite(Image.fromarray(ink))
    return trim(Image.fromarray(ink)), trim(face)

def cutout_render(source):
    rgb = np.asarray(source.convert("RGB"), dtype=float)
    red, green, blue = rgb[:,:,0], rgb[:,:,1], rgb[:,:,2]
    keyed = (green > red * 1.25 + 10) & (green > blue * 1.25 + 10)
    if keyed.mean() > .02:
        # Recover antialiased edges from a pure green matte, removing green spill.
        alpha = 1 - np.clip((green-np.maximum(red,blue))/255, 0, 1)
        rgb[:,:,1] -= (1-alpha)*255
        rgb /= np.maximum(alpha[:,:,None], 1/255)
        alpha[keyed] = 0
        rgb[:,:,1] = np.minimum(rgb[:,:,1], np.maximum(rgb[:,:,0],rgb[:,:,2])+3)
    else:
        neutral = (rgb.min(axis=2) > 165) & ((rgb.max(axis=2)-rgb.min(axis=2)) < 35)
        seeds = np.zeros(neutral.shape, dtype=bool)
        seeds[0,:]=neutral[0,:];seeds[-1,:]=neutral[-1,:]
        seeds[:,0]=neutral[:,0];seeds[:,-1]=neutral[:,-1]
        outside = ndimage.binary_propagation(seeds, mask=neutral)
        alpha = (~outside).astype(float)
    rgba = np.dstack((np.clip(rgb,0,255).astype(np.uint8), np.round(alpha*255).astype(np.uint8)))
    return trim(Image.fromarray(rgba))

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    catalog_path=ROOT / "schemas/studio.json"
    catalog=json.loads(catalog_path.read_text(encoding="utf-8"))
    for spec in catalog["bubbles"]:
        prefix=spec.get("asset_prefix", "original_"+spec["id"])
        if spec.get("asset_prefix"):
            source=ROOT / "web/public/bubble-references" / (prefix+spec["reference_ext"])
            with Image.open(source) as image:
                transparent,white=ink_variants(image)
            transparent.save(DEST/f"{prefix}-transparent.png")
            white.save(DEST/f"{prefix}-white.png")
            spec["asset_aspect"]=white.width/white.height
        raw=ROOT / "output/imagegen/raw" / f"{prefix}-3d.png"
        refined=ROOT / "output/imagegen/raw" / f"{prefix}-refined.png"
        if refined.exists():
            raw=refined
        if prefix=="cloud" and not raw.exists():
            raw=ROOT / "output/imagegen/rejected/cloud-3d-checkerboard.png"
        if raw.exists():
            with Image.open(raw) as image:
                result=cutout_render(image)
            result.save(DEST/f"{prefix}-3d.png")
    catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Prepared {len(list(DEST.glob('*.png')))} bubble assets")

if __name__=="__main__":
    main()
