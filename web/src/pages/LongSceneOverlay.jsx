import { useEffect, useRef, useState } from "react";
import { Stage, Layer, Rect, Image as KonvaImage, Transformer } from "react-konva";
import { fileUrl } from "../lib/api.js";
import Bubble from "../editor/Bubble.jsx";
import EditableText from "../editor/EditableText.jsx";
import {
  bubbleGeometry,
  captionGeometry,
  boxBottom,
  bubbleAppearance,
} from "../editor/bubbleLayout.js";
import { listFonts, loadFontFace } from "../lib/studioAssets.js";

function useImage(url) {
  const [image, setImage] = useState(null);
  useEffect(() => {
    setImage(null);
    if (!url) return;
    const img = new window.Image();
    // 同源图片不污染 canvas；跨域才需 crossOrigin + 服务端 ACAO:*（见
    // SceneEditor.useImage 同一约定）。导出 panel 依赖 toDataURL 不被污染。
    const src = url.startsWith("http") || url.startsWith("data:") ? url : fileUrl(url);
    if (/^https?:/.test(src) && !src.startsWith(location.origin)) img.crossOrigin = "anonymous";
    img.onload = () => setImage(img);
    img.src = src;
    return () => { img.onload = null; };
  }, [url]);
  return image;
}

/*
 * A per-scene editor rendered on top of the long-image preview, positioned
 * exactly over the scene's picture box. Elements inside use the panel's own
 * 1080-wide coordinate space; the Stage scales it to the preview size.
 *
 * The box is fully covered with an opaque backdrop first so the already-baked
 * bubbles/caption in the preview image underneath never show through; the
 * overlay then redraws the raw art + editable elements on top.
 * Dragging updates the scene layout; the caller saves + recomposes.
 */
export default function LongSceneOverlay({ pid, scene, story, box, displayScale, backdrop, onDone, onCancel }) {
  // box.picture: {x,y,width,height,panel_w,panel_h,transparent,caption_layout}
  const pic = box.picture || box;
  const panelW = pic.panel_w;
  const panelH = pic.panel_h;
  const innerScale = pic.width / panelW; // panel-space -> box-space
  const captionText = story.caption || "";
  const hasLayoutCaption = Boolean(scene.layout?.caption_layout);
  // Extra room below the picture so the caption can be grabbed when it is
  // still a template caption (not yet a free caption_layout inside the panel).
  const capExtra = !hasLayoutCaption && captionText ? 160 : 0;
  const stagePanelH = panelH + capExtra;
  const stageW = pic.width * displayScale;
  const stageH = (stagePanelH / panelH) * pic.height * displayScale;

  const [bubbles, setBubbles] = useState(() =>
    (story.dialogues || []).map((d, i) => {
      const bid = d.bubble_id || `b${String(i + 1).padStart(2, "0")}`;
      const saved = (scene.layout?.bubbles || []).find(b => b.bubble_id === bid);
      return {
        bubble_id: bid, type: d.bubble_type || "speech",
        x: 60, y: 40 + i * 170, width: 420, font_size: 36,
        ...saved, text: d.text, speaker: d.speaker,
      };
    })
  );
  const [captionLayout, setCaptionLayout] = useState(scene.layout?.caption_layout || null);
  const [subjectLayout, setSubjectLayout] = useState(scene.layout?.subject_layout || null);
  const [sel, setSel] = useState(null);
  const transformerRef = useRef(null);
  const stageRef = useRef(null);
  const refsMap = useRef({});
  const transparent = scene.background_mode === "transparent";
  const bgUrl = transparent ? (scene.foreground_url || scene.raw_url) : scene.raw_url;
  const bg = useImage(bgUrl);
  const capFontId = story.caption_font_id;
  const capBox = captionGeometry(captionText, captionLayout, panelH, capFontId);
  const subjectBox = subjectLayout || { x: 0, y: 0, width: panelW, height: panelH };

  // Load the fonts this scene actually uses so overlay text matches.
  const usedIds = JSON.stringify([...new Set([...bubbles.map(b => b.font_id || b.font_family), captionLayout?.font_id, capFontId].filter(Boolean))]);
  useEffect(() => {
    let live = true;
    listFonts(pid).then(rows => {
      const list = Array.isArray(rows) ? rows : rows.fonts || rows.items || [];
      const wanted = list.filter(r => r.installed && JSON.parse(usedIds).includes(r.id));
      return Promise.all(wanted.map(row => loadFontFace(pid, row).then(f => [row.id, f]).catch(() => null)));
    }).then(() => {}).catch(() => {});
    return () => { live = false; };
  }, [pid, usedIds]);

  useEffect(() => {
    const t = transformerRef.current;
    if (!t) return;
    const node = sel ? refsMap.current[sel] : null;
    t.nodes(node ? [node] : []);
    t.getLayer()?.batchDraw();
  }, [sel, bubbles, captionLayout, subjectLayout, bg]);

  function update(id, patch) {
    if (id?.startsWith("text:")) id = id.slice(5);
    setBubbles(list => list.map(b => b.bubble_id === id
      ? { ...b, body_height: bubbleGeometry(b).height, text_box: bubbleGeometry(b).text_box, tail_local: bubbleGeometry(b).tip, ...patch, geometry: undefined }
      : b));
  }
  function changeText(id, patch) {
    const b = bubbles.find(x => x.bubble_id === id);
    const { font_size, ...boxPart } = patch;
    update(id, { text_box: { ...bubbleGeometry(b).text_box, ...boxPart }, ...(font_size ? { font_size } : {}) });
  }
  function changeCaption(patch) {
    const { lines, height, line_height, ...boxPart } = capBox;
    setCaptionLayout({ ...boxPart, ...patch });
  }

  async function finish() {
    // 前端接管合成：overlay 画布即成品 panel，导出 1080 全分辨率 PNG 一并回传，
    // 由调用方随 saveLayout 发给后端落盘，不再走服务端 recompose_scene。
    // 先清选中态并等一帧，避免选中框/Transformer 画进成品图。
    const prevSel = sel;
    setSel(null);
    transformerRef.current?.nodes([]);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const panel_png = stageRef.current?.toDataURL({ pixelRatio: panelW / stageW, mimeType: "image/png" });
    setSel(prevSel);
    onDone({
      bubbles: bubbles.map(b => ({ ...b, height: bubbleGeometry(b).height, geometry: bubbleGeometry(b) })),
      caption_layout: captionLayout,
      subject_layout: subjectLayout,
      caption: captionText,
      panel_png,
      // stagePanelH = panelH + 可拖 caption 扩展区；panel_height 是画面区高度
      canvas: { width: panelW, height: stagePanelH, panel_height: panelH },
    });
  }

  return (
    <div className="long-overlay" style={{ left: pic.x * displayScale, top: pic.y * displayScale, width: stageW, height: stageH }}>
      <Stage ref={stageRef} width={stageW} height={stageH} scaleX={innerScale * displayScale} scaleY={innerScale * displayScale}
        onMouseDown={e => { if (e.target === e.target.getStage()) setSel(null); }}>
        <Layer>
          {/* Opaque backdrop hides the baked content in the preview underneath. */}
          <Rect x={0} y={0} width={panelW} height={stagePanelH} fill={backdrop || "#ffffff"} listening={false} />
          {bg && transparent
            ? <KonvaImage ref={n => refsMap.current.subject = n} image={bg} {...subjectBox} draggable
                onClick={() => setSel("subject")} onDragStart={() => setSel("subject")}
                onDragEnd={e => setSubjectLayout({ ...subjectBox, x: e.target.x(), y: e.target.y() })}
                onTransformEnd={e => { const n = e.target; setSubjectLayout({ x: n.x(), y: n.y(), width: Math.max(50, subjectBox.width * n.scaleX()), height: Math.max(50, subjectBox.height * n.scaleY()) }); n.scale({ x: 1, y: 1 }); }} />
            : bg && <KonvaImage image={bg} width={panelW} height={panelH} listening={false} />}
          {bubbles.filter(b => b.bubble_visible !== false).map(b => (
            <Bubble key={b.bubble_id} bubble={b} selected={sel === b.bubble_id} disabled={false}
              onSelect={() => setSel(b.bubble_id)}
              onDragEnd={e => update(b.bubble_id, { x: e.target.x(), y: e.target.y(), tail_local: bubbleGeometry(b).tip })}
              onChange={patch => update(b.bubble_id, patch)} />
          ))}
          {bubbles.filter(b => b.text_visible !== false).map(b => {
            const g = bubbleGeometry(b);
            return <EditableText key={`t-${b.bubble_id}`} box={g.text_box} lines={g.lines}
              fontSize={b.font_size} fontId={b.font_id || b.font_family} color={bubbleAppearance(b).text_color}
              selected={sel === `text:${b.bubble_id}`} disabled={false}
              groupRef={n => refsMap.current[`text:${b.bubble_id}`] = n}
              onSelect={() => setSel(`text:${b.bubble_id}`)}
              onDragEnd={e => changeText(b.bubble_id, { x: e.target.x(), y: e.target.y() })}
              onChange={patch => changeText(b.bubble_id, patch)} />;
          })}
          {captionText && <EditableText box={capBox} lines={capBox.lines}
            fontSize={capBox.font_size} fontId={capBox.font_id} color="#343434"
            groupRef={n => refsMap.current.caption = n} selected={sel === "caption"} disabled={false}
            onSelect={() => setSel("caption")}
            onDragEnd={e => changeCaption({ x: e.target.x(), y: e.target.y() })}
            onChange={changeCaption} />}
        </Layer>
        <Layer>
          <Transformer ref={transformerRef} rotateEnabled={false} flipEnabled={false}
            enabledAnchors={sel === "caption" || sel?.startsWith?.("text:") ? ["middle-left", "middle-right"]
              : ["top-left", "top-center", "top-right", "middle-left", "middle-right", "bottom-left", "bottom-center", "bottom-right"]}
            boundBoxFunc={(o, n) => Math.abs(n.width) < 16 || Math.abs(n.height) < 12 ? o : n} />
        </Layer>
      </Stage>
      <div className="long-overlay-actions">
        <button type="button" className="primary" onClick={finish}>应用并刷新长图</button>
        <button type="button" onClick={onCancel}>取消</button>
      </div>
    </div>
  );
}
