import catalog from "../../../schemas/studio.json";
import { FONT_SPECS } from "../lib/studioAssets.js";

export const BUBBLE_TYPES = catalog.bubbles;
export const BUBBLE_PRESETS = catalog.bubble_presets;
export function bubbleAssetFile(b) {
  const spec = BUBBLE_TYPES.find(t=>t.id===b.type);
  const variant = b.bubble_variant || "white";
  const prefix = spec?.asset_prefix || (variant === "3d" ? `original_${b.type}` : null);
  return prefix ? `${prefix}-${variant}.png` : null;
}
export const bubbleAppearance = (b) => ({
  fill: b.bubble_variant === "transparent" ? "transparent" : b.fill ?? "#ffffff",
  stroke: b.stroke ?? "#333333",
  stroke_width: b.stroke_width ?? 3,
  text_color: b.text_color ?? "#222222",
});
export const CAPTION_H = 100;
export const PAD = 22;
export const BUBBLE_FONT = '"Microsoft YaHei", "PingFang SC", sans-serif';
export const fontSpec = (fontId) => FONT_SPECS.find((item) => item.id === fontId) || null;
export const fontStack = (fontId) => {
  const spec = fontSpec(fontId);
  if (!spec) return BUBBLE_FONT;
  return `"${spec.id}", ${spec.fallback}, sans-serif`;
};
export const hasTail = (type) =>
  !!BUBBLE_TYPES.find((b) => b.id === type)?.tail;
let measureCtx;
function ctx() {
  return (measureCtx ||= document.createElement("canvas").getContext("2d"));
}

export function wrapText(text, fontSize, maxWidth, fontFamily = BUBBLE_FONT) {
  const c = ctx();
  c.font = `${fontSize}px ${fontFamily}`;
  const closing = new Set(Array.from("，。！？；：、）》】…,.!?;:)"));
  const lines = [];
  let cur = "";
  for (const ch of text) {
    if (ch === "\n") {
      lines.push(cur);
      cur = "";
    } else if (cur && c.measureText(cur + ch).width > maxWidth) {
      const chars = Array.from(cur);
      if (closing.has(ch) && chars.length > 1) {
        const last = chars.pop();
        lines.push(chars.join(""));
        cur = last + ch;
      } else {
        lines.push(cur);
        cur = ch;
      }
    } else cur += ch;
  }
  lines.push(cur);
  return lines;
}

export function layoutInput(b) {
  return {
    revision: 3,
    text: b.text || "",
    type: b.type || "speech",
    width: b.width ?? 420,
    font_size: b.font_size ?? 36,
    font_family: b.font_id || b.font_family || "system",
    x: b.x ?? 0,
    y: b.y ?? 0,
    tail_side: b.tail_side || "bottom",
    tail_position: b.tail_position ?? (b.tail === "right" ? 0.75 : 0.25),
    tail_tip: b.tail_tip ?? null,
    body_height: b.body_height ?? null,
    rotation: b.rotation || 0,
    scale_x: b.scale_x ?? 1,
    scale_y: b.scale_y ?? 1,
    text_align: b.text_align || "left",
    text_box: b.text_box || null,
    flip_x: !!b.flip_x,
    flip_y: !!b.flip_y,
    tail_local: b.tail_local || null,
  };
}

export function bubbleGeometry(b) {
  const input = layoutInput(b);
  if (b.geometry && JSON.stringify(b.geometry.input) === JSON.stringify(input))
    return b.geometry;
  const { width: w, font_size: fs, type: kind } = input;
  const organic = [
    "ellipse",
    "burst",
    "thought",
    "cloud",
    "shout",
    "handdrawn",
  ].includes(kind);
  const pad = organic ? w * 0.24 : 22,
    py = organic ? fs * 1.1 : 22;
  const textWidth = b.text_box?.width ?? w - pad * 2;
  const texts = wrapText(input.text, fs, textWidth, fontStack(input.font_family)),
    line_height = fs + 14;
  const height = input.body_height ?? Math.max(80, py * 2 + texts.length * line_height);
  const text_box = { x: b.x + pad, y: b.y + py, width: textWidth, rotation: 0, ...b.text_box, height: texts.length * line_height };
  let points = [];
  if (["thought", "cloud"].includes(kind)) {
    for (let lobe = 0; lobe < 10; lobe++) {
      const a = -Math.PI / 2 + (lobe * 2 * Math.PI) / 10,
        z = a + (2 * Math.PI) / 10;
      const start = [Math.cos(a) * w * 0.4, Math.sin(a) * height * 0.36];
      const end = [Math.cos(z) * w * 0.4, Math.sin(z) * height * 0.36];
      const dx = (end[0] - start[0]) / 2,
        dy = (end[1] - start[1]) / 2;
      for (let step = 0; step < 16; step++) {
        const t = (step * Math.PI) / 16;
        points.push([
          (start[0] + end[0]) / 2 - dx * Math.cos(t) + dy * Math.sin(t) * 0.85,
          (start[1] + end[1]) / 2 - dy * Math.cos(t) - dx * Math.sin(t) * 0.85,
        ]);
      }
    }
    const left = Math.min(...points.map((p) => p[0])),
      top = Math.min(...points.map((p) => p[1]));
    const spanX = Math.max(...points.map((p) => p[0])) - left,
      spanY = Math.max(...points.map((p) => p[1])) - top;
    points = points.map(([x, y]) => [
      ((x - left) * w) / spanX,
      ((y - top) * height) / spanY,
    ]);
  } else if (organic) {
    const count = ["burst", "shout"].includes(kind) ? 32 : 128;
    for (let i = 0; i < count; i++) {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / count;
      let k = 1;
      if (["burst", "shout"].includes(kind)) {
        const outer = [1, 0.81, 0.96, 0.86, 1, 0.84, 0.93, 0.79][
          Math.floor(i / 2) % 8
        ];
        k = i % 2 === 0 ? outer : kind === "shout" ? 0.64 : 0.72;
      } else if (["thought", "cloud"].includes(kind))
        k = 0.9 + 0.1 * Math.cos(9 * a);
      else if (kind === "handdrawn")
        k = 0.97 + 0.02 * Math.sin(3 * a) + 0.01 * Math.cos(7 * a);
      points.push([
        w / 2 + ((Math.cos(a) * w) / 2) * k,
        height / 2 + ((Math.sin(a) * height) / 2) * k,
      ]);
    }
  } else {
    const radius =
      kind === "caption"
        ? 4
        : kind === "soft"
          ? Math.min(w, height) * 0.32
          : 24;
    for (const [cx, cy, begin] of [
      [w - radius, radius, -90],
      [w - radius, height - radius, 0],
      [radius, height - radius, 90],
      [radius, radius, 180],
    ]) {
      for (let i = 0; i < 9; i++) {
        const a = ((begin + (i * 90) / 8) * Math.PI) / 180;
        points.push([cx + radius * Math.cos(a), cy + radius * Math.sin(a)]);
      }
    }
    const dense = [];
    points.forEach((a, i) => {
      const z = points[(i + 1) % points.length],
        n = Math.max(1, Math.ceil(Math.hypot(z[0] - a[0], z[1] - a[1]) / 14));
      for (let j = 0; j < n; j++)
        dense.push([
          a[0] + ((z[0] - a[0]) * j) / n,
          a[1] + ((z[1] - a[1]) * j) / n,
        ]);
    });
    points = dense;
  }
  const pos = input.tail_position,
    side = input.tail_side;
  const desired =
    side === "bottom"
      ? [w * pos, height]
      : side === "top"
        ? [w * pos, 0]
        : side === "left"
          ? [0, height * pos]
          : [w, height * pos];
  let index = 0;
  points.forEach((p, i) => {
    if (
      Math.hypot(p[0] - desired[0], p[1] - desired[1]) <
      Math.hypot(points[index][0] - desired[0], points[index][1] - desired[1])
    )
      index = i;
  });
  const anchor = points[index];
  let tip = [anchor[0] + (pos < 0.5 ? -35 : 35), anchor[1] + 65];
  if (side === "top") tip = [anchor[0], -65];
  if (side === "left") tip = [-65, anchor[1] + 35];
  if (side === "right") tip = [w + 65, anchor[1] + 35];
  if (input.tail_local) tip = input.tail_local;
  else if (input.tail_tip)
    tip = untransformPoint([input.tail_tip.x, input.tail_tip.y], b);
  let circles = [];
  if (hasTail(kind)) {
    if (kind === "thought")
      circles = [
        [0.25, 12],
        [0.55, 8],
        [0.85, 4],
      ].map(([p, r]) => ({
        x: anchor[0] + (tip[0] - anchor[0]) * p,
        y: anchor[1] + (tip[1] - anchor[1]) * p,
        r,
      }));
    else {
      const n = points.length;
      points = Array.from(
        { length: n - 3 },
        (_, j) => points[(index + 2 + j) % n],
      ).concat([tip]);
    }
  }
  return {
    input,
    points,
    circles,
    height,
    anchor,
    tip,
    line_height,
    text_box,
    lines: texts.map((text, i) => ({
      text,
      width: measureText(text, fs, input.font_family),
      x: alignedX(textWidth, measureText(text, fs, input.font_family), input.text_align),
      y: fs + i * line_height,
    })),
  };
}

export function measureText(text, size, fontId) {
  const c = ctx();
  c.font = `${size}px ${fontStack(fontId)}`;
  return c.measureText(text).width;
}
const alignedX = (width, textWidth, align) => align === "right" ? width - textWidth : align === "center" ? (width - textWidth) / 2 : 0;
export function transformPoint([x, y], b) {
  if (b.flip_x) x = b.width - x;
  if (b.flip_y) y = (b.body_height || b.height) - y;
  const angle = (b.rotation || 0) * Math.PI / 180;
  x *= b.scale_x ?? 1; y *= b.scale_y ?? 1;
  return [b.x + x * Math.cos(angle) - y * Math.sin(angle), b.y + x * Math.sin(angle) + y * Math.cos(angle)];
}
export function untransformPoint([x, y], b) {
  const angle = (b.rotation || 0) * Math.PI / 180;
  x -= b.x; y -= b.y;
  const local = [(x * Math.cos(angle) + y * Math.sin(angle)) / (b.scale_x ?? 1), (-x * Math.sin(angle) + y * Math.cos(angle)) / (b.scale_y ?? 1)];
  if (b.flip_x) local[0] = b.width - local[0];
  if (b.flip_y) local[1] = (b.body_height || b.height) - local[1];
  return local;
}
export function captionGeometry(text, saved, panelHeight, fontId) {
  const box = { x: 32, y: panelHeight + 22, width: 1016, font_size: 34, align: "center", rotation: 0, font_id: fontId, ...saved };
  const lineHeight = box.font_size + 14;
  const lines = wrapText(text, box.font_size, box.width, fontStack(box.font_id)).map((text, i) => {
    const width = measureText(text, box.font_size, box.font_id);
    return { text, width, x: alignedX(box.width, width, box.align), y: box.font_size + i * lineHeight };
  });
  return { ...box, height: Math.max(lineHeight, lines.length * lineHeight), lines, line_height: lineHeight };
}
export function boxBottom(box) {
  return Math.max(...[[0,0],[box.width,0],[0,box.height],[box.width,box.height]].map(p => transformPoint(p, box)[1]));
}

export function prepareBubble(b) {
  const geometry = bubbleGeometry(b);
  return { ...b, height: geometry.height, geometry };
}

export function bubbleSvg(b, panelHeight) {
  const g = bubbleGeometry(b),
    all = [
      ...g.points,
      ...g.circles.flatMap((c) => [
        [c.x - c.r, c.y - c.r],
        [c.x + c.r, c.y + c.r],
      ]),
    ].map(p => { const [x,y] = transformPoint(p, {...b,x:0,y:0}); return [x,y]; });
  let minX = Math.floor(Math.min(...all.map((p) => p[0]))) - 5,
    minY = Math.floor(Math.min(...all.map((p) => p[1]))) - 5;
  let maxX = Math.ceil(Math.max(...all.map((p) => p[0]))) + 5,
    maxY = Math.ceil(Math.max(...all.map((p) => p[1]))) + 5;
  if (panelHeight !== undefined) {
    minX = Math.max(minX, -b.x);
    minY = Math.max(minY, -b.y);
    maxX = Math.min(maxX, 1080 - b.x);
    maxY = Math.min(maxY, panelHeight - b.y);
  }
  const width = maxX - minX,
    height = maxY - minY;
  if (width <= 0 || height <= 0) return null;
  const style = bubbleAppearance(b);
  const polygon = `<polygon points="${g.points.map((p) => p.join(",")).join(" ")}" fill="${style.fill}" stroke="${style.stroke}" stroke-width="${style.stroke_width}" stroke-linejoin="round" vector-effect="non-scaling-stroke" ${b.type === "whisper" ? 'stroke-dasharray="9 7"' : ""}/>`;
  const circles = g.circles
    .map(
      (c) =>
        `<circle cx="${c.x}" cy="${c.y}" r="${c.r}" fill="${style.fill}" stroke="${style.stroke}" stroke-width="${style.stroke_width}" vector-effect="non-scaling-stroke"/>`,
    )
    .join("");
  return {
    svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${minX} ${minY} ${width} ${height}"><g transform="rotate(${b.rotation || 0}) scale(${b.scale_x ?? 1} ${b.scale_y ?? 1}) translate(${b.flip_x ? b.width : 0} ${b.flip_y ? g.height : 0}) scale(${b.flip_x ? -1 : 1} ${b.flip_y ? -1 : 1})">${polygon}${circles}</g></svg>`,
    x: minX,
    y: minY,
    width,
    height,
  };
}
