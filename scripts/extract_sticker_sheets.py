"""Import the supplied transparent sticker sheets without redrawing their artwork.

Usage: python scripts/extract_sticker_sheets.py SOURCE_DIRECTORY
The alpha silhouette separates sprites; explicit seams split touching white rims.
Source RGB and alpha values inside each sprite are retained.
"""
from pathlib import Path
import json
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
SHEETS = [
    ('6c678268-8bbb-422c-8bc2-7d348402adf9', '花草', 13),
    ('e37bdf96-87e5-4bcf-96f7-d6470581dd99', '星空天气', 12),
    ('da7e9642-d541-451c-a5c3-b4250ea27366', '爱心', 12),
    ('facc000c-dcde-4852-be2b-315fb4e074fa', '蝴蝶结', 12),
    ('83741310-b0ae-4f12-a476-fce9f73202dc', '水果', 12),
    ('3849aa18-e54b-47f7-8ade-86738dabdc83', '箭头', 16),
    ('e7eb26c3-3582-43a9-ab50-fb27b29ede1d', '美食', 12),
    ('cba53960-080a-411b-9a11-6821e95e40b2', '手账', 18),
    ('8bdf2eaa-4803-4ed6-bb47-57ae929f0a30', '花边', 20),
    ('d09fb71e-46e3-4c01-a1c8-37c2c0eb03af', '日常', 12),
    ('3d723568-7818-44bc-9822-c1794d42ba8d', '相框', 16),
]
SEAMS = {
    2: [[(641, 560), (641, 820)]],
    6: [[(407, 700), (407, 875)]],
    8: [[(345, 637), (630, 637)],
        [(330, 860), (310, 935), (290, 955), (275, 984), (270, 1020), (261, 1080), (261, 1130)],
        [(455, 1139), (545, 1125), (660, 1104), (790, 1103)],
        [(1125, 900), (1125, 1160)]],
    10: [[(695, 580), (695, 840)]],
    11: [[(907, 690), (907, 981)]],
}


def main(source):
    destination = ROOT / 'web/public/sticker-assets'
    destination.mkdir(parents=True, exist_ok=True)
    qa = ROOT / 'output/sticker-extraction'
    qa.mkdir(parents=True, exist_ok=True)
    catalog = {'groups': [], 'stickers': []}
    for sheet, (source_id, category, expected) in enumerate(SHEETS, 1):
        original = Image.open(source / f'codex-clipboard-{source_id}.png').convert('RGBA')
        pixels = np.asarray(original)
        alpha = pixels[:, :, 3]
        silhouette = Image.fromarray((alpha > 100).astype('uint8') * 255)
        pen = ImageDraw.Draw(silhouette)
        for line in SEAMS.get(sheet, []):
            pen.line(line, fill=0, width=2)
        labels, _ = ndi.label(np.asarray(silhouette) > 0)
        areas = np.bincount(labels.ravel())
        ids = [int(i) for i in np.flatnonzero(areas > 1200) if i]
        if len(ids) != expected:
            raise ValueError(f'Sheet {sheet}: expected {expected}, found {len(ids)}')
        cores = np.where(np.isin(labels, ids), labels, 0)
        distance, nearest = ndi.distance_transform_edt(cores == 0, return_indices=True)
        ownership = cores[tuple(nearest)]
        # Six pixels retain the original soft rim, excluding detached alpha noise.
        ownership[(distance > 6) | (alpha == 0)] = 0
        boxes = {}
        for i in ids:
            ys, xs = np.where(cores == i)
            boxes[i] = (xs.min(), ys.min(), xs.max(), ys.max())
        # Read top-to-bottom, with the nearest artwork row sorted left-to-right.
        remaining = sorted(ids, key=lambda i: boxes[i][1])
        ordered = []
        while remaining:
            top = boxes[remaining[0]][1]
            row = [i for i in remaining if boxes[i][1] < top + 100]
            ordered.extend(sorted(row, key=lambda i: boxes[i][0]))
            remaining = [i for i in remaining if i not in row]
        group_id = f'{sheet:02d}'
        catalog['groups'].append({'id': group_id, 'label': category})
        contact = Image.new('RGB', (800, ((len(ordered) + 3) // 4) * 210), '#e5edf0')
        draw = ImageDraw.Draw(contact)
        for number, i in enumerate(ordered, 1):
            keep = ownership == i
            ys, xs = np.where(keep)
            box = (int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1)
            sprite = original.crop(box)
            sprite_alpha = np.array(sprite.getchannel('A'))
            sprite_alpha[~keep[box[1]:box[3], box[0]:box[2]]] = 0
            sprite.putalpha(Image.fromarray(sprite_alpha))
            padded = Image.new('RGBA', (sprite.width+8, sprite.height+8))
            padded.paste(sprite, (4, 4))
            asset_id = f'{sheet:02d}-{number:02d}'
            padded.save(destination / f'{asset_id}.png', optimize=True)
            catalog['stickers'].append({'id': asset_id, 'group': group_id,
                'width': padded.width, 'height': padded.height})
            thumb = padded.copy()
            thumb.thumbnail((180, 180))
            x, y = ((number-1) % 4) * 200, ((number-1) // 4) * 210
            contact.paste(thumb, (x+(200-thumb.width)//2, y+10+(180-thumb.height)//2), thumb)
            draw.text((x+8, y+190), asset_id, fill='#23403b')
        contact.save(qa / f'{sheet:02d}.jpg', quality=90)
        print(f'{sheet:02d}: {len(ordered)}')
    (ROOT / 'schemas/stickers.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Total: {len(catalog['stickers'])}")


if __name__ == '__main__':
    main(Path(sys.argv[1]))
