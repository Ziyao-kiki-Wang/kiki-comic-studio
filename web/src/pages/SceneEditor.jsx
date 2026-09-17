import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Stage,
  Layer,
  Rect,
  Text,
  Image as KonvaImage,
  Group,
  Transformer,
} from "react-konva";
import { api, fileUrl, pollTask } from "../lib/api.js";
import SceneImageTools from "./SceneImageTools.jsx";
import SceneReferenceTools from "./SceneReferenceTools.jsx";
import { useWorkspaceGuard } from "./WorkspaceShell.jsx";
import "./scene-editor.css";
import Bubble from "../editor/Bubble.jsx";
import EditableText from "../editor/EditableText.jsx";
import useBubbleSelection from "../editor/useBubbleSelection.js";
import {
  FONT_SPECS,
  assetUrl,
  listFonts,
  loadFontFace,
  listProjectAssets,
  uploadFont,
  uploadProjectAsset,
} from "../lib/studioAssets.js";
import {
  BUBBLE_TYPES,
  bubbleAssetFile,
  BUBBLE_PRESETS,
  bubbleSvg,
  bubbleAppearance,
  BUBBLE_FONT,
  fontStack,
  bubbleGeometry,
  prepareBubble,
  hasTail,
  wrapText,
  captionGeometry,
  boxBottom,
} from "../editor/bubbleLayout.js";

function useImage(url) {
  const [image, setImage] = useState(null);
  useEffect(() => {
    setImage(null);
    if (!url) return;
    const img = new window.Image();
    // canvas.toDataURL 要求图片不污染画布。同源图片（生产 /api/files）不加
    // crossOrigin 也不会污染；本地跨域开发（5173→8000）才需要它 + 服务端
    // ACAO:*。按是否跨域决定，避免给同源请求无谓升级成 CORS fetch（曾致
    // onload 静默不触发，见 HISTORY 2026-09-15 / CONVENTIONS 前端约定）。
    const src = url?.startsWith("http") || url?.startsWith("data:") ? url : fileUrl(url);
    const isCrossOrigin = /^https?:/.test(src) && !src.startsWith(location.origin);
    if (isCrossOrigin) img.crossOrigin = "anonymous";
    img.onload = () => setImage(img);
    img.src = src;
    return () => {
      img.onload = null;
    };
  }, [url]);
  return image;
}

function SceneOverlay({ overlay, source, selected, disabled, onSelect, onChange, setRef }) {
  const image = useImage(source);
  const id = overlay.overlay_id || overlay.id || overlay.asset_id;
  const width = overlay.width || 200;
  const height = overlay.height || 200;
  return (
    <Group
      ref={setRef}
      name={`overlay-${id}`}
      x={(overlay.x || 0) + width / 2}
      y={(overlay.y || 0) + height / 2}
      offsetX={width / 2}
      offsetY={height / 2}
      rotation={overlay.rotation || 0}
      draggable={!disabled}
      onClick={() => onSelect(`overlay:${id}`)}
      onTap={() => onSelect(`overlay:${id}`)}
      onDragEnd={(e) => onChange(id, {
        x: Math.round(e.target.x() - width / 2),
        y: Math.round(e.target.y() - height / 2),
      })}
      onTransformEnd={(e) => {
        const node = e.target;
        const nextWidth = Math.max(32, Math.round(width * Math.abs(node.scaleX())));
        const nextHeight = Math.max(32, Math.round(height * Math.abs(node.scaleY())));
        onChange(id, {
          x: Math.round(node.x() - nextWidth / 2),
          y: Math.round(node.y() - nextHeight / 2),
          width: nextWidth,
          height: nextHeight,
          rotation: Math.round(node.rotation()),
        });
        node.scaleX(1);
        node.scaleY(1);
      }}
    >
      {image && (
        <KonvaImage
          image={image}
          width={width}
          height={height}
          opacity={overlay.opacity ?? 1}
          x={overlay.flip_x ? width : 0}
          y={overlay.flip_y ? height : 0}
          scaleX={overlay.flip_x ? -1 : 1}
          scaleY={overlay.flip_y ? -1 : 1}
        />
      )}
      {selected && (
        <Rect width={width} height={height} stroke="#286c5a" strokeWidth={2} dash={[6, 4]} listening={false} />
      )}
    </Group>
  );
}

async function loadProjectFonts(pid, usedIds = []) {
  const result = await listFonts(pid);
  const rows = Array.isArray(result) ? result : result.fonts || result.items || [];
  return Promise.all(rows.map(async (row) => {
    const next = { ...row, browser_loaded: false };
    if (!row.installed || !usedIds.includes(row.id)) return next;
    try {
      await loadFontFace(pid, row);
      return { ...next, browser_loaded: true };
    } catch (error) {
      return {
        ...next,
        browser_error: error?.message || "当前浏览器无法解析此字体，画布将使用系统回退",
      };
    }
  }));
}

export default function SceneEditor() {
  const textRef = useRef(null);
  const subjectRef = useRef(null);
  const [subjectLayout, setSubjectLayout] = useState(null);
  const [layerOrder, setLayerOrder] = useState([]);
  const [bubbleAvailability, setBubbleAvailability] = useState({});
  useEffect(()=>{fetch(fileUrl("/api/bubble-catalog")).then(r=>r.json()).then(setBubbleAvailability).catch(()=>{});},[]);
  const { pid, sid } = useParams();
  const navigate = useNavigate();
  const setGuard = useWorkspaceGuard();
  const [project, setProject] = useState(null),
    [bubbles, setBubbles] = useState([]),
    [inset, setInset] = useState(null),
    [caption, setCaption] = useState("");
  const [overlays, setOverlays] = useState([]),
    [captionLayout, setCaptionLayout] = useState(null),
    [assets, setAssets] = useState([]),
    [fontRecords, setFontRecords] = useState([]),
    [fontsReady, setFontsReady] = useState(true),
    [dirty, setDirty] = useState(false),
    [assetBusy, setAssetBusy] = useState(false),
    [referenceStale, setReferenceStale] = useState(false),
    [screenPrompt, setScreenPrompt] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [scale, setScale] = useState(0.8);
  const stageRef = useRef(null),
    wrapRef = useRef(null),
    insetRef = useRef(null),
    transformerRef = useRef(null),
    overlayRefs = useRef({}),
    bubbleRefs = useRef({}),
    textRefs = useRef({}),
    captionRef = useRef(null),
    stopRef = useRef(null);
  const selection = useBubbleSelection({bubbles,setBubbles,bubbleRefs,textRefs,setDirty});
  const {selected,setSelected} = selection;
  // Right-click context menu + floating delete button (bubble/text only).
  const [ctxMenu, setCtxMenu] = useState(null); // {x, y, kind} kind: 'canvas' | 'element'
  const [insertPicker, setInsertPicker] = useState(null); // 'bubble' | 'text' | null
  const deleteBtnRef = useRef(null);
  const [deletePos, setDeletePos] = useState(null); // {x, y} in wrap coords
  const [insertFontOpen, setInsertFontOpen] = useState(false);
  async function load() {
    const data = await api.getProject(pid),
      scene = data.scenes.find((s) => s.scene_id === sid),
      story = data.storyboard.scenes.find((s) => s.scene_id === sid);
    if (!scene || !story) throw new Error("这一格不存在");
    setProject(data);
    const saved = new Map(
      (scene.layout?.bubbles || []).map((b) => [b.bubble_id, b]),
    );
    setBubbles(
      (story.dialogues || []).map((d, i) => {
        const bid = d.bubble_id || `b${String(i + 1).padStart(2, "0")}`;
        return {
          bubble_id: bid,
          type: d.bubble_type || "speech",
          x: 60,
          y: 40 + i * 170,
          width: 420,
          font_size: 36,
          font_id: story.bubble_font_id || null,
          ...saved.get(bid),
          text: d.text,
          speaker: d.speaker,
        };
      }),
    );
    setInset(scene.layout?.screen_inset || null);
    setOverlays(scene.layout?.overlays || scene.layout?.asset_overlays || []);
    setCaption(story.caption || "");
    setScreenPrompt(story.screen_inset?.screen_prompt_en || "");
    setCaptionLayout(scene.layout?.caption_layout || null);
    setSubjectLayout(scene.layout?.subject_layout || null);
    setLayerOrder(scene.layout?.layer_order || []);
    setReferenceStale(false);
    selection.setGroups(scene.layout?.element_groups || []);
    setDirty(false);
    try {
      const result = await listProjectAssets(pid, "sticker");
      setAssets(Array.isArray(result) ? result : result.assets || result.items || []);
    } catch {
      // Older servers simply do not expose the optional asset library yet.
      setAssets([]);
    }
    if (data.active_task) {
      setBusy(true);
      watch(data.active_task.task_id);
    }
  }
  function watch(id, destination) {
    stopRef.current?.();
    stopRef.current = pollTask(id, (t) => {
      if (t.status === "done") {
        setBusy(false);
        setNotice("已保存并更新当前分镜");
        if (destination) {
          setGuard(false);
          navigate(destination);
        } else load().catch((e) => setError(e.message));
      }
      if (t.status === "failed") {
        setBusy(false);
        setError(t.error || "合成失败");
      }
    });
  }
  useEffect(() => {
    setSelected(null);
    setError("");
    setNotice("");
    load().catch((e) => setError(e.message));
    return () => stopRef.current?.();
  }, [pid, sid]);
  const usedFontIds = JSON.stringify([...new Set([...bubbles.map((b) => b.font_id || b.font_family), captionLayout?.font_id].filter(Boolean))]);
  useEffect(() => {
    let active = true;
    setFontsReady(false);
    loadProjectFonts(pid, JSON.parse(usedFontIds))
      .then((rows) => {
        if (!active) return;
        setFontRecords(rows);
      })
      .catch(() => {
        if (active) setFontRecords([]);
      })
      .finally(() => {
        if (active) setFontsReady(true);
      });
    return () => {
      active = false;
    };
  }, [pid, usedFontIds]);
  useEffect(() => {
    setGuard(Boolean(dirty));
    return () => setGuard(false);
  }, [dirty, setGuard]);
  useEffect(() => {
    if (!wrapRef.current) return;
    const observer = new ResizeObserver((entries) =>
      // Match the full checkerboard area, including on wide screens.
      setScale(entries[0].contentRect.width / 1080),
    );
    observer.observe(wrapRef.current);
    return () => observer.disconnect();
  }, [project]);
  useEffect(() => {
    if (transformerRef.current) {
      transformerRef.current.nodes(
        // Konva's multi-node Transformer starts proxy drags on every member.
        // Our selection hook owns group translation; individual outlines show selection.
        selection.ids.length > 1 ? [] :
        selected === "subject" && subjectRef.current ? [subjectRef.current] : selected === "inset" && insetRef.current
          ? [insetRef.current]
          : selected?.startsWith("overlay:") && overlayRefs.current[selected.slice(8)]
            ? [overlayRefs.current[selected.slice(8)]]
            : selected === "caption" && captionRef.current ? [captionRef.current]
            : selected?.startsWith("text:") && textRefs.current[selected.slice(5)] ? [textRefs.current[selected.slice(5)]]
            : bubbleRefs.current[selected] ? [bubbleRefs.current[selected]]
            : [],
      );
      transformerRef.current.getLayer()?.batchDraw();
    }
    if (import.meta.env.DEV) window.__editorStage = stageRef.current;
  }, [JSON.stringify(selection.ids), inset, project, bubbles, captionLayout, fontsReady, subjectLayout]);
  const scene = project?.scenes.find((s) => s.scene_id === sid);
  const storyScene = project?.storyboard.scenes.find((s) => s.scene_id === sid);
  const sceneCharacters = (project?.storyboard.characters || []).filter((c) =>
    (storyScene?.characters || []).includes(c.character_id),
  );
  const charactersConfirmed = project?.storyboard.characters_confirmed !== false;
  const sceneVersions = (scene?.layout?.versions || []).map((v) =>
    Number(/_v(\d+)\.png$/.exec(v)?.[1] || 0),
  );
  const activeVersion = Number(
    /_v(\d+)\.png$/.exec(scene?.layout?.active_version || "")?.[1] || 0,
  );
  const transparent = scene?.background_mode === "transparent";
  const bg = useImage(transparent ? scene?.foreground_url || scene?.raw_url : scene?.raw_url);
  const screen = useImage(scene?.screen_url);
  const panelH =
    scene?.layout?.canvas?.panel_height ||
    (scene?.layout?.canvas?.height || 820) -
      (scene?.layout?.caption?.height || 100);
  const capBox = captionGeometry(caption, captionLayout, panelH, project?.storyboard.scenes.find(s => s.scene_id === sid)?.caption_font_id);
  const capH = captionLayout ? Math.max(0, Math.ceil(boxBottom(capBox) + 22 - panelH)) : Math.max(100, 32 + capBox.height);
  const subjectBox = subjectLayout || {x:0, y:0, width:1080, height:panelH};
  const defaultLayers = [...(transparent?["subject"]:[]), ...(inset ? ["inset"] : []), ...bubbles.filter(b=>b.bubble_visible!==false).map(b => b.bubble_id), ...bubbles.filter(b=>b.text_visible!==false).map(b => `text:${b.bubble_id}`), ...[...overlays].sort((a,b)=>(a.z_index||0)-(b.z_index||0)).map(o => `overlay:${overlayId(o)}`), "caption"];
  const orderedLayers = [...layerOrder.filter(id => defaultLayers.includes(id)), ...defaultLayers.filter(id => !layerOrder.includes(id))];
  useEffect(() => {

    const nodes = {subject:subjectRef.current, inset:insetRef.current, caption:captionRef.current, ...bubbleRefs.current};
    Object.entries(textRefs.current).forEach(([id,node]) => {nodes[`text:${id}`]=node;});
    Object.entries(overlayRefs.current).forEach(([id,node]) => {nodes[`overlay:${id}`]=node;});
    orderedLayers.forEach(id => nodes[id]?.moveToTop());
  }, [JSON.stringify(orderedLayers), transparent, fontsReady, bg, bubbles, captionLayout, overlays]);
  function changeSubject(patch) {setSubjectLayout({...subjectBox,...patch});setDirty(true);}
  function moveLayerEdge(edge) { // 'top' | 'up' | 'down' | 'bottom'
    const list = [...orderedLayers], index = list.indexOf(selected);
    if (index < 0) return;
    const id = list.splice(index, 1)[0];
    if (edge === 'top') list.push(id);
    else if (edge === 'bottom') list.unshift(id);
    else {
      const target = edge === 'up' ? Math.min(list.length, index + 1) : Math.max(0, index - 1);
      list.splice(target, 0, id);
    }
    setLayerOrder(list);setDirty(true);
  }
  // Apply one font size (and font) to every dialogue text in this scene.
  function applyFontToAll() {
    if (!selectedBubble) return;
    const size = selectedBubble.font_size;
    const fontId = selectedBubble.font_id || selectedBubble.font_family || null;
    setDirty(true);
    setBubbles(list => list.map(b => ({ ...b, font_size: size,
      font_id: fontId, font_family: fontId || b.font_family, geometry: undefined })));
    setNotice(`已将本格全部文字统一为 ${size}px`);
  }
  function openContextMenu(e, kind) {
    e.evt.preventDefault();
    e.evt.stopPropagation();
    const stageBox = wrapRef.current?.getBoundingClientRect();
    if (!stageBox) return;
    setCtxMenu({
      x: e.evt.clientX - stageBox.left,
      y: e.evt.clientY - stageBox.top,
      clientX: e.evt.clientX, clientY: e.evt.clientY,
      kind,
    });
  }
  function closeCtx() { setCtxMenu(null); }
  // Position the floating delete button at the top-right of the current selection.
  useEffect(() => {
    if (!selected || !wrapRef.current) { setDeletePos(null); return; }
    const isBubbleOrText = selected.startsWith?.('text:') || bubbleRefs.current[selected];
    const isOverlayOrInset = selected.startsWith?.('overlay:') || selected === 'inset';
    if (!isBubbleOrText && !isOverlayOrInset) { setDeletePos(null); return; }
    const node = selected.startsWith?.('text:') ? textRefs.current[selected.slice(5)]
      : selected.startsWith?.('overlay:') ? overlayRefs.current[selected.slice(8)]
      : selected === 'inset' ? insetRef.current
      : bubbleRefs.current[selected];
    if (!node) { setDeletePos(null); return; }
    // getClientRect(relativeTo container) already returns coordinates in the
    // stage container's own pixel space, which fills the wrap box 1:1.
    const r = node.getClientRect({ relativeTo: stageRef.current?.container() });
    setDeletePos({ x: r.x + r.width, y: r.y });
  }, [JSON.stringify(selection.ids), selected, bubbles, overlays, inset, subjectLayout, scale]);
  const selectedBubble = bubbles.find((b) => b.bubble_id === (selected?.startsWith("text:") ? selected.slice(5) : selected));
  const selectedGeometry = selectedBubble ? bubbleGeometry(selectedBubble) : null;
  const sceneIndex = project?.scenes.findIndex(s => s.scene_id === sid) ?? 0;
  const nextScene = project?.scenes[sceneIndex + 1];
  const selectedOverlay = overlays.find(
    (item) => (item.overlay_id || item.id || item.asset_id) === selected?.slice?.(8),
  );
  const installedFontIds = new Set(
    fontRecords
      .filter((item) => Boolean(item.installed))
      .map((item) => item.id || item.font_id || item.installed?.font_id)
      .filter(Boolean),
  );
  const browserFontState = new Map(
    fontRecords.map((item) => [item.id || item.font_id || item.installed?.font_id, item]),
  );
  function update(id, patch) {
    if (id?.startsWith("text:")) id = id.slice(5);
    setDirty(true);
    setBubbles((list) =>
      list.map((b) =>
        b.bubble_id === id ? { ...b, body_height: bubbleGeometry(b).height,
          text_box: bubbleGeometry(b).text_box, tail_local: bubbleGeometry(b).tip, ...patch, geometry: undefined } : b,
      ),
    );
  }
  function changeText(id, patch) {
    const b = bubbles.find(item => item.bubble_id === id);
    const {font_size, ...box} = patch;
    update(id, {text_box: {...bubbleGeometry(b).text_box, ...box}, ...(font_size ? {font_size} : {})});
  }
  function addTextElement(kind) {
    if (bubbles.length >= 20) return;
    const bid = `b_${crypto.randomUUID().replaceAll("-", "").slice(0,12)}`;
    const offset = (bubbles.length % 6) * 28;
    const b = {bubble_id:bid, type:"speech", x:80 + offset, y:60 + offset,
      width:420, body_height:130, font_size:36, text:kind === "bubble" ? "" : "请输入文字",
      bubble_visible:kind !== "text", text_visible:kind !== "bubble",
      text_box:{x:102 + offset,y:82 + offset,width:376,rotation:0},
      text_align:"center", bubble_variant:"white"};
    setBubbles(previous => [...previous,b]);
    setSelected(kind === "text" ? `text:${bid}` : bid);
    setDirty(true);
  }
  function bringBubbleIntoCanvas() {
    const node = bubbleRefs.current[selectedBubble?.bubble_id];
    if (!node) return;
    // Measure the whole rotated shape, including the fixed tail, in canvas units.
    const bounds = node.getClientRect({ relativeTo: node.getLayer() });
    const margin = 16;
    const fit = Math.min(1, (1080 - margin * 2) / bounds.width,
      (panelH + capH - margin * 2) / bounds.height);
    const left = selectedBubble.x + (bounds.x - selectedBubble.x) * fit;
    const top = selectedBubble.y + (bounds.y - selectedBubble.y) * fit;
    const x = Math.max(margin, Math.min(left, 1080 - margin - bounds.width * fit));
    const y = Math.max(margin, Math.min(top, panelH + capH - margin - bounds.height * fit));
    update(selectedBubble.bubble_id, {
      x: selectedBubble.x + x - left,
      y: selectedBubble.y + y - top,
      scale_x: (selectedBubble.scale_x ?? 1) * fit,
      scale_y: (selectedBubble.scale_y ?? 1) * fit,
    });
    setSelected(selectedBubble.bubble_id);
  }
  function changeCaption(patch) {
    const {lines, height, line_height, ...box} = capBox;
    setCaptionLayout({...box, ...patch});
    setDirty(true);
  }
  function changeInset(next) {
    setDirty(true);
    setInset(next);
  }
  function updateOverlay(id, patch) {
    setDirty(true);
    setOverlays((list) =>
      list.map((item) =>
        (item.overlay_id || item.id || item.asset_id) === id
          ? { ...item, ...patch }
          : item,
      ),
    );
  }
  function overlayId(item) {
    return item.overlay_id || item.id || item.asset_id;
  }
  function addOverlayRecord(record) {
    const asset = record?.asset || record?.item || record;
    if (!asset) return;
    const id = asset.asset_id || asset.id;
    if (!id) return;
    const sourceWidth = Number(asset.width) || 360;
    const sourceHeight = Number(asset.height) || 360;
    const fit = Math.min(1, 360 / Math.max(sourceWidth, sourceHeight));
    setAssets((list) => list.some((item) => (item.asset_id || item.id) === id) ? list : [...list, asset]);
    const next = {
      overlay_id: `overlay_${crypto.randomUUID()}`,
      asset_id: id,
      name: asset.filename || asset.name || "贴纸",
      x: 120,
      y: 100,
      // Fit the first placement into a 360 px box without stretching a
      // portrait official character or an icon with a transparent margin.
      width: Math.max(32, Math.round(sourceWidth * fit)),
      height: Math.max(32, Math.round(sourceHeight * fit)),
      rotation: 0,
      opacity: 1,
      flip_x: false,
      flip_y: false,
      z_index: overlays.length,
    };
    setOverlays((list) => [...list, next]);
    // Keep the same selection key used by canvas clicks ("overlay:<id>") so
    // the inspector resolves the newly added layer immediately.
    setSelected(`overlay:${next.overlay_id}`);
    setDirty(true);
  }
  async function uploadOverlay(file) {
    if (!file || assetBusy) return;
    setAssetBusy(true);
    setError("");
    try {
      const record = await uploadProjectAsset(pid, file, "sticker", file.name);
      addOverlayRecord(record);
      setNotice("贴纸已添加到当前分镜，可拖动、缩放或旋转");
    } catch (e) {
      setError(e.message);
    } finally {
      setAssetBusy(false);
    }
  }
  function addExistingOverlay(asset) {
    addOverlayRecord(asset);
  }
  function removeSelectedOverlay() {
    if (!selectedOverlay) return;
    setOverlays((list) => list.filter((item) => overlayId(item) !== overlayId(selectedOverlay)));
    setSelected(null);
    setDirty(true);
  }
  async function generateScreenInset() {
    const promptText = screenPrompt.trim();
    if (!promptText || busy || assetBusy || dirty) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { task_id } = await api.generate(pid, {
        action: "screen_scene",
        scene_id: sid,
        instruction: promptText,
      });
      watch(task_id);
    } catch (e) {
      setBusy(false);
      setError(e.message);
    }
  }
  async function runSceneAction(body, confirmText) {
    if (busy || assetBusy || dirty) return;
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { task_id } = await api.generate(pid, body);
      watch(task_id);
    } catch (e) {
      setBusy(false);
      setError(e.message);
    }
  }
  async function save(goNext = false) {
    if (busy || assetBusy) return;
    if (!fontsReady) {
      setError("字体仍在加载，请稍后再保存");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const unavailable = bubbles.find(b => b.font_id && !browserFontState.get(b.font_id)?.browser_loaded);
      if (unavailable) throw new Error('当前气泡字体无法在浏览器中加载，请重新导入可用的 TTF / OTF 字体或选择系统字体后保存。');
      // 前端接管合成：Konva 画布即成品，导出 PNG 随 layout 一起发给后端落盘，
      // 不再触发服务端 Pillow recompose（见 DECISIONS 2026-09-16）。
      // 导出前清空选中态与 Transformer，避免选中框/高亮被画进成品图；
      // 双 rAF 等 React 把 selected=false 重渲染到画布再截图。
      const prevSelection = selection.ids;
      selection.setSelected(null);
      transformerRef.current?.nodes([]);
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      const panelPng = stageRef.current?.toDataURL({ pixelRatio: 1 / scale, mimeType: "image/png" });
      selection.setSelected(prevSelection.length ? prevSelection[prevSelection.length - 1] : null);
      await api.saveLayout(pid, sid, {
        bubbles: bubbles.map(prepareBubble),
        screen_inset: inset,
        overlays,
        caption,
        caption_layout: captionLayout,
        subject_layout: subjectLayout,
        layer_order: orderedLayers,
        element_groups: selection.groups,
        panel_png: panelPng,
        // 画布尺寸供后端裁切模板旁白的 caption 区、同步 meta.canvas
        canvas: { width: 1080, height: panelH + capH, panel_height: panelH },
      });
      setDirty(false);
      setGuard(false);
      setBusy(false);
      setNotice("已保存当前分镜");
      if (goNext) {
        setGuard(false);
        navigate(nextScene ? `/project/${pid}/scene/${nextScene.scene_id}/edit` : `/project/${pid}?step=layout`);
      } else {
        load().catch((e) => setError(e.message));
      }
    } catch (e) {
      setBusy(false);
      setError(e.message);
    }
  }
  if (!project)
    return (
      <div className="page">
        <Link to={`/project/${pid}`}>← 工作台</Link>
        <p className={error ? "error" : "muted"}>{error || "加载中…"}</p>
      </div>
    );
  return (
    <div className="page editor-page">
      <button
        type="button"
        className="back-link scene-back-button"
        onClick={() => {
          if (!dirty || window.confirm("有未保存的修改，返回后会丢失。确定返回吗？"))
            navigate(`/project/${pid}?step=story`);
        }}
      >
        ← 返回工作台
      </button>
      <header className="workbench-header">
        <div>
          <h1>编辑 {sid}</h1>
          <p className="muted">
            点击轮廓调整气泡，点击文字调整文本框；拖文字框左右手柄自动换行，旁白也可拖动。
          </p>
        </div>
        <button className="primary" disabled={busy || assetBusy || !fontsReady} onClick={() => save()}>
          {busy ? "保存与合成中…" : "保存当前分镜"}
        </button>
      </header>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <details className="card">
        <summary>修改图片与下载素材</summary>
        <SceneImageTools
          scene={scene}
          busy={busy}
          onEdit={async (instruction) => {
            if (!fontsReady) {
              setError("字体仍在加载，请稍后再生成");
              return;
            }
            setBusy(true);
            setError("");
            try {
              if (bubbles.some(b => b.font_id && !browserFontState.get(b.font_id)?.browser_loaded)) throw new Error('当前气泡字体无法在浏览器中加载，请重新导入字体或选择系统字体。');
              await api.saveLayout(pid, sid, {
                bubbles: bubbles.map(prepareBubble),
                screen_inset: inset,
                overlays,
                caption,
                caption_layout: captionLayout,
        subject_layout: subjectLayout,
        layer_order: orderedLayers,
        element_groups: selection.groups,
              });
              setDirty(false);
              const { task_id } = await api.generate(pid, {
                action: "edit_scene",
                scene_id: sid,
                instruction,
              });
              watch(task_id);
            } catch (e) {
              setBusy(false);
              setError(e.message);
            }
          }}
        />
      </details>
      <details className="card">
        <summary>本格参考、重跑与版本</summary>
        <SceneReferenceTools
          pid={pid}
          sceneId={sid}
          characters={sceneCharacters}
          busy={busy || assetBusy}
          onChange={() => {
            setReferenceStale(true);
            setNotice("本格参考已更新，下次修改图片或重跑时使用。");
          }}
        />
        {(scene.reference_stale || referenceStale) && (
          <p className="stale-badge">本格参考已更新，下次修改图片或重跑时使用。</p>
        )}
        <div className="scene-actions">
          <button
            disabled={busy || assetBusy || dirty || !charactersConfirmed}
            onClick={() =>
              runSceneAction(
                { action: "rerun_scene", scene_id: sid },
                "重跑这一格将调用生图服务并保留旧版本，继续吗？",
              )
            }
          >
            按故事描述重跑这一格
          </button>
        </div>
        {sceneVersions.length > 1 && (
          <label>
            原图版本
            <select
              value={activeVersion}
              disabled={busy || assetBusy || dirty}
              onChange={(e) =>
                runSceneAction({
                  action: "rollback_scene",
                  scene_id: sid,
                  version: Number(e.target.value),
                })
              }
            >
              {sceneVersions.map((v) => (
                <option key={v} value={v}>
                  v{v}
                  {v === activeVersion ? " · 当前" : ""}
                </option>
              ))}
            </select>
          </label>
        )}
        {dirty && (
          <p className="muted">当前有未保存的修改，请先保存后再重跑或切换版本。</p>
        )}
      </details>
      {transparent && !scene.foreground_url && (
        <p className="stale-badge">
          {scene.raw_url ? "当前原图没有透明背景，请重跑这一格，由模型直接生成透明图。" : "透明场景尚未生成，请先生成分镜。"}
        </p>
      )}
      <div className="editor-columns editor-three-columns">
        <aside className="card editor-scene-rail">
          <div className="scene-rail-title">
            <h2>分镜</h2>
            <span>{project.scenes.length} 格</span>
          </div>
          <div className="scene-rail-list">
            {project.scenes.map((item, index) => (
              <button
                type="button"
                key={item.scene_id}
                className={`scene-rail-item ${item.scene_id === sid ? "active" : ""}`}
                onClick={() => {
                  if (item.scene_id === sid || busy) return;
                  if (dirty && !window.confirm("当前分镜有未保存的修改，切换后会丢失。确定切换吗？")) return;
                  navigate(`/project/${pid}/scene/${item.scene_id}/edit`);
                }}
              >
                {item.composite_url ? (
                  <img src={fileUrl(item.composite_url)} alt="" />
                ) : (
                  <span className="scene-rail-placeholder">{String(index + 1).padStart(2, "0")}</span>
                )}
                <span>第 {index + 1} 格</span>
                {item.status === "approved" && <small>已通过</small>}
              </button>
            ))}
          </div>
        </aside>
        <div ref={wrapRef} className="editor-wrap checkerboard">
          <Stage
            ref={stageRef}
            width={1080 * scale}
            height={(panelH + capH) * scale}
            scaleX={scale}
            scaleY={scale}
            onMouseDown={(e) => {
              if (e.target === e.target.getStage()) { setSelected(null); closeCtx(); setInsertPicker(null); }
            }}
            onContextMenu={(e) => {
              // e.target is the innermost hit shape (no name); walk up the
              // ancestor chain to find the named interactive node.
              let node = e.target, name = "";
              while (node && node !== stageRef.current) {
                name = node.name?.() || "";
                if (name) break;
                node = node.getParent();
              }
              const map = { "screen-inset": "inset", caption: "caption", subject: "subject" };
              const selId = name.startsWith("bubble-") ? name.slice(7)
                : name.startsWith("text-") ? `text:${name.slice(5)}`
                : name.startsWith("overlay-") ? `overlay:${name.slice(8)}`
                : map[name];
              if (!selId) { openContextMenu(e, "canvas"); return; }
              // Right-click selects what was clicked (Shift keeps multi-select)
              // so 顶层/底层/组合/删除 all target the correct element.
              if (e.evt.shiftKey) selection.select(selId, e);
              else if (!selection.ids.includes(selId)) setSelected(selId);
              openContextMenu(e, "element");
            }}
          >
            <Layer listening={false}>
              {!transparent && bg && <KonvaImage image={bg} width={1080} height={panelH} />}
              {!transparent && (
                <Rect
                  x={0}
                  y={panelH}
                  width={1080}
                  height={capH}
                  fill="white"
                />
              )}
            </Layer>
            <Layer>
              {transparent && bg && <KonvaImage ref={subjectRef} name="subject" image={bg} {...subjectBox} draggable={!busy}
                onClick={() => setSelected("subject")} onTap={() => setSelected("subject")}
                onDragStart={() => setSelected("subject")}
                onDragEnd={e=>changeSubject({x:e.target.x(),y:e.target.y()})}
                onTransformEnd={e=>{const n=e.target;changeSubject({x:n.x(),y:n.y(),width:Math.max(50,Math.min(3000,subjectBox.width*n.scaleX())),height:Math.max(50,Math.min(3000,subjectBox.height*n.scaleY()))});n.scale({x:1,y:1});}} />}

              {inset && (
                <Group
                  ref={insetRef}
                  name="screen-inset"
                  x={inset.x}
                  y={inset.y}
                  draggable={!busy}
                  onClick={() => setSelected("inset")}
                  onTap={() => setSelected("inset")}
                  onDragEnd={(e) =>
                    changeInset({
                      ...inset,
                      x: Math.round(e.target.x()),
                      y: Math.round(e.target.y()),
                    })
                  }
                  onTransformEnd={() => {
                    const n = insetRef.current;
                    changeInset({
                      ...inset,
                      x: Math.round(n.x()),
                      y: Math.round(n.y()),
                      width: Math.max(
                        80,
                        Math.min(1800, Math.round(inset.width * n.scaleX())),
                      ),
                      height: Math.max(
                        80,
                        Math.min(1800, Math.round(inset.height * n.scaleY())),
                      ),
                    });
                    n.scaleX(1);
                    n.scaleY(1);
                  }}
                >
                  {screen && (
                    <Group
                      clipFunc={(ctx) => {
                        ctx.beginPath();
                        ctx.roundRect(0, 0, inset.width, inset.height, 30);
                      }}
                    >
                      <KonvaImage
                        image={screen}
                        width={inset.width}
                        height={inset.height}
                      />
                    </Group>
                  )}
                  <Rect
                    x={4}
                    y={4}
                    width={inset.width - 8}
                    height={inset.height - 8}
                    stroke={selected === "inset" ? "#2f6fdb" : "#1a1a1a"}
                    strokeWidth={8}
                    cornerRadius={26}
                  />
                </Group>
              )}
              {fontsReady && bubbles.filter(b=>b.bubble_visible!==false).map((b) => (
                <Bubble
                  key={b.bubble_id}
                  bubble={b}
                  selected={selection.ids.includes(b.bubble_id)}
                  groupRef={node => { bubbleRefs.current[b.bubble_id] = node; }}
                  disabled={busy}
                  onSelect={selection.select}
                  onDragStart={e=>selection.start(b.bubble_id,e)} onDragMove={selection.move} onDragEnd={selection.end}
                  onEdit={(id) => {
                    setSelected(id);
                    setTimeout(() => textRef.current?.focus(), 0);
                  }}
                  onChange={(patch) => update(b.bubble_id, patch)}
                />
              ))}
              {fontsReady && bubbles.filter(b=>b.text_visible!==false).map(b => {
                const g = bubbleGeometry(b);
                return <EditableText key={`text-${b.bubble_id}`} name={`text-${b.bubble_id}`} box={g.text_box} lines={g.lines}
                  fontSize={b.font_size} fontId={b.font_id || b.font_family} color={bubbleAppearance(b).text_color}
                  selected={selection.ids.includes(`text:${b.bubble_id}`)} disabled={busy}
                  groupRef={node => { textRefs.current[b.bubble_id] = node; }}
                  onSelect={e => selection.select(`text:${b.bubble_id}`,e)}
                  onDragStart={e=>selection.start(`text:${b.bubble_id}`,e)} onDragMove={selection.move} onDragEnd={selection.end}
                  onEdit={() => {setSelected(`text:${b.bubble_id}`); setTimeout(() => textRef.current?.focus(), 0);}}
                  onChange={patch => changeText(b.bubble_id, patch)} />;
              })}
              {overlays
                .slice()
                .sort((a, b) => (a.z_index || 0) - (b.z_index || 0))
                .map((overlay) => {
                  const id = overlayId(overlay);
                  const record = assets.find((item) => (item.asset_id || item.id) === overlay.asset_id);
                  return (
                    <SceneOverlay
                      key={id}
                      setRef={(node) => {
                        if (node) overlayRefs.current[id] = node;
                        else delete overlayRefs.current[id];
                      }}
                      overlay={overlay}
                      source={assetUrl(record || overlay, pid)}
                      selected={selected === `overlay:${id}`}
                      disabled={busy || assetBusy}
                      onSelect={setSelected}
                      onChange={updateOverlay}
                    />
                  );
                })}
              {fontsReady && caption && <EditableText name="caption" box={capBox} lines={capBox.lines}
                fontSize={capBox.font_size} fontId={capBox.font_id} color="#343434"
                groupRef={captionRef} selected={selected === "caption"} disabled={busy}
                onSelect={() => setSelected("caption")} onChange={changeCaption} />}
            </Layer>
            <Layer>
              <Transformer
                ref={transformerRef}
                rotateEnabled={selection.ids.length === 1 && selected !== "inset" && selected !== "subject" && !busy}
                flipEnabled={false}
                anchorSize={10 / scale}
                borderStrokeWidth={1 / scale}
                rotateAnchorOffset={26 / scale}
                keepRatio={selected === "subject"}
                enabledAnchors={
                  busy || selection.ids.length > 1
                    ? []
                    : selected === "caption" || selected?.startsWith("text:") ? ["middle-left", "middle-right"] : ["top-left", "top-center", "top-right", "middle-left", "middle-right", "bottom-left", "bottom-center", "bottom-right"]
                }
                boundBoxFunc={(old, n) =>
                  Math.abs(n.width) < 16 || Math.abs(n.height) < 12 ? old : n
                }
              />
            </Layer>
          </Stage>
          {deletePos && !busy && (
            <button
              ref={deleteBtnRef}
              type="button"
              className="floating-delete"
              style={{ left: deletePos.x, top: deletePos.y }}
              title="删除选中元素"
              onClick={() => {
                if (selected?.startsWith('overlay:')) removeSelectedOverlay();
                else if (selected === 'inset') changeInset(null);
                else selection.remove();
                setDeletePos(null);
              }}
            >✕</button>
          )}
          {ctxMenu && (
            <ContextMenu
              pos={ctxMenu}
              canGroup={selection.canGroup}
              canUngroup={selection.canUngroup}
              canRemove={selection.canRemove || selected?.startsWith('overlay:') || selected === 'inset'}
              isElement={ctxMenu.kind === 'element'}
              bubblesFull={bubbles.length >= 20}
              onClose={closeCtx}
              onAdd={(kind) => { addTextElement(kind); closeCtx(); }}
              onGroup={() => { selection.group(); closeCtx(); }}
              onUngroup={() => { selection.ungroup(); closeCtx(); }}
              onLayer={(edge) => { moveLayerEdge(edge); closeCtx(); }}
              onDelete={() => {
                if (selected?.startsWith('overlay:')) removeSelectedOverlay();
                else if (selected === 'inset') changeInset(null);
                else selection.remove();
                closeCtx();
              }}
            />
          )}
        </div>
        <aside className="card bubble-inspector">
          {!selected && (
            <section className="insert-panel" aria-label="插入文字或气泡">
              <h2>插入到画布</h2>
              <button type="button" className="insert-big bubble-insert" disabled={busy || bubbles.length>=20}
                onClick={()=>setInsertPicker(insertPicker==='bubble'?null:'bubble')}>
                💬 插入新气泡
              </button>
              {insertPicker==='bubble' && (
                <div className="insert-variant-grid">
                  {BUBBLE_TYPES.map(t=>(
                    <button key={t.id} type="button" disabled={busy||(t.asset_prefix && !(bubbleAvailability[t.id]||[]).length)}
                      onClick={()=>{addTextElement('bubble'); setInsertPicker(null);}}>
                      <img alt="" src={t.asset_prefix ? `/bubble-references/${t.asset_prefix}${t.reference_ext || '.jpg'}` : `data:image/svg+xml,${encodeURIComponent(bubbleSvg({type:t.id,text:'',x:0,y:0,width:240,body_height:150,font_size:28}).svg)}`}/>
                      {t.name}
                    </button>
                  ))}
                </div>
              )}
              <button type="button" className="insert-big text-insert" disabled={busy || bubbles.length>=20}
                onClick={()=>{addTextElement('text');}}>
                🔤 插入新文字
              </button>
              <p className="muted">也可在画布上点右键快速添加；选中元素后右上角有 ✕ 删除。</p>
            </section>
          )}
          {selected && selected !== 'caption' && (
            <section className="selection-hint">
              <button type="button" className="link" onClick={()=>{setSelected(null);setInsertPicker(null);}}>✕ 取消选择</button>
              {selection.ids.length>1 && <span className="muted">已选 {selection.ids.length} 个，右键可组合</span>}
            </section>
          )}
          {selectedBubble && selected?.startsWith('text:') ? (
            /* Only text selected: keep it minimal — content, font, size, one-click apply-all. */
            <section className="text-edit-panel">
              <h2>对话文字</h2>
              <label>文字内容
                <textarea ref={textRef} rows={3} value={selectedBubble.text} maxLength={500} disabled={busy}
                  onChange={e=>update(selected,{text:e.target.value})}/>
              </label>
              <label>字体
                <select value={selectedBubble.font_id || selectedBubble.font_family || "system"} disabled={busy || !fontsReady}
                  onChange={(e) => update(selected, { font_id: e.target.value === "system" ? null : e.target.value, font_family: e.target.value })}>
                  <option value="system">系统默认（微软雅黑）</option>
                  {FONT_SPECS.map((font) => <option key={font.id} value={font.id} disabled={!installedFontIds.has(font.id)}>{font.name}{installedFontIds.has(font.id) ? "" : " · 待导入"}</option>)}
                </select>
              </label>
              <label>字号：{selectedBubble.font_size}px
                <input type="range" min="18" max="72" step="2" value={selectedBubble.font_size} disabled={busy}
                  onChange={(e) => update(selected, { font_size: Number(e.target.value) })} />
              </label>
              <button type="button" className="apply-all-btn" disabled={busy} onClick={applyFontToAll}>✨ 一键全适配 · 统一整格字号字体</button>
              <p className="muted">点气泡轮廓可改气泡样式；拖文字框左右手柄可换行。</p>
            </section>
          ) : selectedBubble ? (
            <>
              <div className="form-row object-mode">
                <button disabled={selectedBubble.bubble_visible===false} aria-pressed={selected === selectedBubble.bubble_id} onClick={() => selection.selectOnly(selectedBubble.bubble_id)}>气泡轮廓</button>
                <button disabled={selectedBubble.text_visible===false} aria-pressed={selected === `text:${selectedBubble.bubble_id}`} onClick={() => selection.selectOnly(`text:${selectedBubble.bubble_id}`)}>对话文字</button>
              </div>
              {selectedBubble.bubble_visible===false && <button disabled={busy} onClick={()=>{update(selected,{bubble_visible:true});setSelected(selectedBubble.bubble_id);}}>为此文字添加气泡</button>}
              {selectedBubble.text_visible===false && <button disabled={busy} onClick={()=>{update(selected,{text_visible:true,text:selectedBubble.text || "请输入文字"});setSelected(`text:${selectedBubble.bubble_id}`);}}>为此气泡添加文字</button>}
              {selectedBubble.text_visible!==false && <label>文字内容
                <textarea ref={textRef} rows={3} value={selectedBubble.text} maxLength={500} disabled={busy}
                  onChange={e=>update(selected,{text:e.target.value})}/>
              </label>}
              <button type="button" disabled={busy} onClick={bringBubbleIntoCanvas}>气泡移回画布</button>
              <p className="muted">棋盘格边界就是图片边界，超出的部分不会导出。气泡和文字可以分别拖动。</p>
              <label>文字对齐
                <select value={selectedBubble.text_align || "left"} disabled={busy} onChange={e => update(selected, {text_align:e.target.value})}>
                  <option value="left">居左</option><option value="center">居中</option><option value="right">居右</option>
                </select>
              </label>
              <label>文字框宽度
                <input type="range" min="80" max="1040" value={selectedGeometry.text_box.width} disabled={busy}
                  onChange={e => changeText(selectedBubble.bubble_id, {width:Number(e.target.value)})} />
              </label>
              <div className="form-row">
                <label className="grow">气泡旋转
                  <input type="number" min="-360" max="360" value={Math.round(selectedBubble.rotation || 0)} disabled={busy}
                    onChange={e => update(selected, {rotation:Math.max(-360, Math.min(360, Number(e.target.value)))})} />
                </label>
                <label className="grow">文字旋转
                  <input type="number" min="-360" max="360" value={Math.round(selectedGeometry.text_box.rotation || 0)} disabled={busy}
                    onChange={e => changeText(selectedBubble.bubble_id, {rotation:Math.max(-360, Math.min(360, Number(e.target.value)))})} />
                </label>
              </div>
              <div className="form-row">
                <button disabled={busy} onClick={()=>update(selected,{flip_x:!selectedBubble.flip_x, tail_local:selectedGeometry.tip})}>水平翻转气泡</button>
                <button disabled={busy} onClick={()=>update(selected,{flip_y:!selectedBubble.flip_y, tail_local:selectedGeometry.tip})}>垂直翻转气泡</button>
              </div>
              <button disabled={busy} onClick={() => changeText(selectedBubble.bubble_id,{x:selectedBubble.x+selectedBubble.width*.2,y:selectedBubble.y+selectedGeometry.height*.2,width:selectedBubble.width*.6})}>文字放回气泡内</button>
              <label>气泡版本
                <select value={selectedBubble.bubble_variant || "white"} disabled={busy} onChange={e=>update(selected,{bubble_variant:e.target.value})}>
                  {[["transparent","透明内底"],["white","白色内底"],["3d","立体动画"]].map(([id,name])=><option key={id} value={id} disabled={!(bubbleAvailability[selectedBubble.type] || (selectedBubble.type.startsWith("asset_")?[]:["transparent","white"])).includes(id)}>{name}{!(bubbleAvailability[selectedBubble.type] || (selectedBubble.type.startsWith("asset_")?[]:["transparent","white"])).includes(id)?" · 制作中":""}</option>)}
                </select>
              </label>
              <div className="bubble-library">
                {BUBBLE_TYPES.map((t) => (
                  <button
                    type="button"
                    key={t.id}
                    disabled={busy || (t.asset_prefix && !(bubbleAvailability[t.id] || []).length)}
                    aria-pressed={selectedBubble.type === t.id}
                    className={selectedBubble.type === t.id ? "selected" : ""}
                    onClick={() => {
                      const variants = bubbleAvailability[t.id] || ["transparent","white"];
                      const variant = variants.includes(selectedBubble.bubble_variant || "white") ? selectedBubble.bubble_variant || "white" : variants[0];
                      update(selected, {type:t.id,bubble_variant:variant,body_height:t.asset_prefix?selectedBubble.width/(t.asset_aspect || 1.25):selectedGeometry.height,tail_local:null,tail_tip:null});
                    }}
                  >
                    <img
                      crossOrigin="anonymous"
                      alt=""
                      src={t.asset_prefix || selectedBubble.bubble_variant === "3d"
                        ? ((bubbleAvailability[t.id] || []).includes(selectedBubble.bubble_variant || "white")
                          ? fileUrl(`/api/bubble-assets/${bubbleAssetFile({type:t.id,bubble_variant:selectedBubble.bubble_variant || "white"})}?v=1`)
                          : t.asset_prefix ? `/bubble-references/${t.asset_prefix}${t.reference_ext || ".jpg"}` : `data:image/svg+xml,${encodeURIComponent(bubbleSvg({type:t.id,text:"",x:0,y:0,width:240,body_height:150,font_size:28}).svg)}`)
                        : `data:image/svg+xml,${encodeURIComponent(bubbleSvg({type:t.id,text:"",x:0,y:0,width:240,body_height:150,font_size:28,bubble_variant:selectedBubble.bubble_variant}).svg)}`}
                    />
                    {t.name}
                  </button>
                ))}
              </div>
              {!bubbleAssetFile(selectedBubble) && <>
              <div className="bubble-presets">
                {BUBBLE_PRESETS.map((p) => (
                  <button
                    key={p.id}
                    disabled={busy}
                    style={{
                      background: p.fill,
                      color: p.text_color,
                      borderColor: p.stroke,
                    }}
                    onClick={() =>
                      update(selected, {
                        fill: p.fill,
                        stroke: p.stroke,
                        stroke_width: p.stroke_width,
                        text_color: p.text_color,
                      })
                    }
                  >
                    {p.name}
                  </button>
                ))}
              </div>
              <div className="form-row">
                {[
                  ["fill", "底色"],
                  ["stroke", "边框色"],
                  ["text_color", "文字色"],
                ].map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="color"
                      disabled={busy}
                      value={bubbleAppearance(selectedBubble)[key]}
                      onChange={(e) =>
                        update(selected, { [key]: e.target.value })
                      }
                    />
                  </label>
                ))}
              </div>
              <label>
                边框粗细（0 为无边框）：{selectedBubble.stroke_width ?? 3}
                <input
                  type="range"
                  min="0"
                  max="12"
                  step="1"
                  disabled={busy}
                  value={selectedBubble.stroke_width ?? 3}
                  onChange={(e) =>
                    update(selected, { stroke_width: Number(e.target.value) })
                  }
                />
              </label>
              </>}
              {bubbleAssetFile(selectedBubble) && <label>文字色<input type="color" value={selectedBubble.text_color || "#222222"} disabled={busy} onChange={e=>update(selected,{text_color:e.target.value})}/></label>}
              <label>
                气泡字体
                <select
                  value={selectedBubble.font_id || selectedBubble.font_family || "system"}
                  disabled={busy || !fontsReady}
                  onChange={(e) => update(selected, {
                    font_id: e.target.value === "system" ? null : e.target.value,
                    font_family: e.target.value,
                  })}
                >
                  <option value="system">系统默认（微软雅黑）</option>
                  {FONT_SPECS.map((font) => (
                    <option
                      key={font.id}
                      value={font.id}
                      disabled={!installedFontIds.has(font.id)}
                    >
                      {font.name}{installedFontIds.has(font.id) ? "" : " · 待导入"}
                    </option>
                  ))}
                </select>
              </label>
              {(selectedBubble.font_id || selectedBubble.font_family) &&
                (selectedBubble.font_id || selectedBubble.font_family) !== "system" &&
                !installedFontIds.has(selectedBubble.font_id || selectedBubble.font_family) && (
                <p className="stale-badge">当前字体尚未导入，画布暂用系统回退；导入后会自动加载。</p>
              )}
              <label>
                字号：{selectedBubble.font_size}
                <input
                  type="range"
                  min="18"
                  max="72"
                  step="2"
                  value={selectedBubble.font_size}
                  disabled={busy}
                  onChange={(e) =>
                    update(selected, { font_size: Number(e.target.value) })
                  }
                />
              </label>
              {[['scale_x','水平拉伸'],['scale_y','垂直拉伸']].map(([key,label])=><label key={key}>
                气泡{label}：{Math.round((selectedBubble[key] ?? 1)*100)}%
                <input type="range" min="0.1" max="4" step="0.05" value={selectedBubble[key] ?? 1} disabled={busy} onChange={e=>update(selected,{[key]:Number(e.target.value)})}/>
              </label>)}
              <p className="muted">尾巴固定在气泡上，随整个气泡一起移动、旋转和翻转。</p>
            </>
          ) : null}
          {selectedOverlay && (
            <div className="sticker-controls">
              <p><b>{selectedOverlay.name || "当前贴图"}</b></p>
              <label>
                透明度：{Math.round((selectedOverlay.opacity ?? 1) * 100)}%
                <input type="range" min="0.1" max="1" step="0.05" value={selectedOverlay.opacity ?? 1} disabled={busy || assetBusy} onChange={(e) => updateOverlay(overlayId(selectedOverlay), { opacity: Number(e.target.value) })} />
              </label>
              <label>
                旋转：{selectedOverlay.rotation || 0}°
                <input type="range" min="-180" max="180" step="1" value={selectedOverlay.rotation || 0} disabled={busy || assetBusy} onChange={(e) => updateOverlay(overlayId(selectedOverlay), { rotation: Number(e.target.value) })} />
              </label>
              <div className="form-row sticker-actions">
                <button type="button" disabled={busy || assetBusy} onClick={() => updateOverlay(overlayId(selectedOverlay), { flip_x: !selectedOverlay.flip_x })}>水平翻转</button>
                <button type="button" disabled={busy || assetBusy} onClick={() => updateOverlay(overlayId(selectedOverlay), { flip_y: !selectedOverlay.flip_y })}>垂直翻转</button>
              </div>
              <div className="form-row sticker-actions">
                <button type="button" disabled={busy || assetBusy} onClick={() => moveLayerEdge('down')}>下移一层</button>
                <button type="button" disabled={busy || assetBusy} onClick={() => moveLayerEdge('up')}>上移一层</button>
                <button type="button" disabled={busy || assetBusy} onClick={removeSelectedOverlay}>删除图层</button>
              </div>
              <p className="muted">在画布上拖动、缩放四角，旋转手柄可调整角度；右键可调层级。</p>
            </div>
          )}
          <details className="font-import-link">
            <summary>导入自定义字体</summary>
            <p className="muted">选一个要替换的字体槽位，上传 TTF / OTF / TTC。</p>
            {FONT_SPECS.map((font) => {
              const installed = installedFontIds.has(font.id);
              return (
                <label className="font-slot" key={font.id}>
                  <span>
                    <b>{font.name}</b>
                    <small>{!installed ? "待导入" : browserFontState.get(font.id)?.browser_error ? "已导入 · 画布回退" : browserFontState.get(font.id)?.installed?.source === "shared" ? "内置可用" : "已导入"}</small>
                  </span>
                  <input type="file" accept=".ttf,.otf,.ttc,font/ttf,font/otf,application/x-font-ttf" disabled={busy || assetBusy}
                    onChange={async (e) => {
                      const file = e.target.files?.[0]; e.target.value = "";
                      if (!file) return;
                      setAssetBusy(true); setFontsReady(false); setError("");
                      try {
                        await uploadFont(pid, font.id, file);
                        const next = await loadProjectFonts(pid, [...JSON.parse(usedFontIds), font.id]);
                        setFontRecords(next);
                        setBubbles(items => items.map(b => b.font_id === font.id ? {...b, geometry: undefined} : b));
                        if (bubbles.some(b => b.font_id === font.id)) setDirty(true);
                        setFontsReady(true);
                        setNotice(`${font.name} 已导入，点击“保存”后更新当前分镜`);
                      } catch (err) { setFontsReady(true); setError(err.message); }
                      finally { setAssetBusy(false); }
                    }} />
                </label>
              );
            })}
          </details>
          <label className="caption-block">
            旁白
            <textarea
              value={caption}
              maxLength={1000}
              disabled={busy}
              onChange={(e) => {
                setCaption(e.target.value);
                setDirty(true);
              }}
            />
          </label>
          <div className="form-row">
            <button disabled={busy || !caption} onClick={() => setSelected("caption")}>移动旁白</button>
            <button disabled={busy} onClick={() => {setCaptionLayout(null); setDirty(true);}}>恢复旁白默认位置</button>
          </div>
          {selected === "caption" && <div className="sticker-controls">
            <p className="muted">拖动旁白移动位置；拖动左右边框调整换行宽度，角点可调整字号。</p>
            <label>旁白对齐<select value={capBox.align} disabled={busy} onChange={e => changeCaption({align:e.target.value})}>
              <option value="left">居左</option><option value="center">居中</option><option value="right">居右</option>
            </select></label>
            <label>旁白字号<input type="range" min="18" max="72" value={capBox.font_size} disabled={busy} onChange={e => changeCaption({font_size:Number(e.target.value)})} /></label>
          </div>}
        </aside>
      </div>
      <div className="editor-save-bar">
        <span role="status">第 {sceneIndex + 1} / {project.scenes.length} 格 · {busy ? "正在保存与合成…" : dirty ? "有未保存的修改" : "可继续编辑"}</span>
        <button disabled={busy || assetBusy || !fontsReady} onClick={() => save()}>保存</button>
        <button className="primary" disabled={busy || assetBusy || !fontsReady} onClick={() => save(true)}>{nextScene ? "保存并编辑下一张 →" : "保存并进入作品排版 →"}</button>
      </div>
      {scene.composite_url && (
        <details>
          <summary>查看已保存的单格成品</summary>
          <img
            className="scene-img editor-preview checkerboard"
            src={fileUrl(scene.composite_url)}
            alt="已保存单格"
          />
        </details>
      )}
    </div>
  );
}

/* ---- Right-click context menu (PPT-style, with submenu) ---- */
const CTX_SUB_GAP = 4;   // submenu overlaps parent by this much (matches left:calc(100% - 4px))
const CTX_SUB_W = 150;   // .ctx-sub min-width
const CTX_EDGE = 8;      // keep this much breathing room from the wrap edge
function ContextMenu({ pos, isElement, canGroup, canUngroup, canRemove, bubblesFull, onClose, onAdd, onGroup, onUngroup, onLayer, onDelete }) {
  const [sub, setSub] = useState(null); // 'add' | 'top' | 'bottom'
  const [flipX, setFlipX] = useState(false); // open submenus to the left when near the right edge
  const menuRef = useRef(null);
  useEffect(() => {
    const close = (e) => { if (!e.target.closest?.('.ctx-menu')) onClose(); };
    window.addEventListener('pointerdown', close);
    window.addEventListener('blur', onClose);
    return () => { window.removeEventListener('pointerdown', close); window.removeEventListener('blur', onClose); };
  }, [onClose]);
  // Measure once open: if the submenu would overflow the wrap's right edge,
  // flip it to open on the left so 置于顶层/底层 stays clickable on right-edge bubbles.
  useLayoutEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const wrap = el.offsetParent;
    if (!wrap) return;
    const wrapW = wrap.clientWidth;
    const wrapH = wrap.clientHeight;
    const menuW = el.offsetWidth;
    const menuH = el.offsetHeight;
    const subW = el.querySelector('.ctx-sub')?.offsetWidth || CTX_SUB_W;
    const needRight = pos.x + menuW - CTX_SUB_GAP + subW + CTX_EDGE > wrapW;
    setFlipX(needRight && pos.x - subW + CTX_SUB_GAP - CTX_EDGE >= 0);
    // Clamp the menu itself inside the wrap so it never gets clipped either.
    const clampedX = Math.max(CTX_EDGE, Math.min(pos.x, wrapW - menuW - CTX_EDGE));
    const clampedY = Math.max(CTX_EDGE, Math.min(pos.y, wrapH - menuH - CTX_EDGE));
    if (clampedX !== pos.x) el.style.left = `${clampedX}px`;
    if (clampedY !== pos.y) el.style.top = `${clampedY}px`;
  }, [pos.x, pos.y, isElement]);
  return (
    <div ref={menuRef} className={`ctx-menu${flipX ? ' ctx-menu--flip' : ''}`} style={{ left: pos.x, top: pos.y }} onContextMenu={e => e.preventDefault()}>
      {!isElement ? (
        <div className="ctx-item ctx-parent" onMouseEnter={() => setSub('add')} onClick={() => setSub(sub === 'add' ? null : 'add')}>
          {flipX && <span className="ctx-arrow">◂</span>}添加 {!flipX && <span className="ctx-arrow">▸</span>}
          {sub === 'add' && (
            <div className="ctx-sub">
              <button type="button" disabled={bubblesFull} onClick={() => onAdd('text')}>添加文字框</button>
              <button type="button" disabled={bubblesFull} onClick={() => onAdd('bubble')}>添加气泡</button>
              <button type="button" disabled={bubblesFull} onClick={() => onAdd('both')}>添加文字和气泡</button>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="ctx-item ctx-parent" onMouseEnter={() => setSub('top')}>
            {flipX && <span className="ctx-arrow">◂</span>}置于顶层 {!flipX && <span className="ctx-arrow">▸</span>}
            {sub === 'top' && (
              <div className="ctx-sub">
                <button type="button" onClick={() => onLayer('top')}>置于顶层</button>
                <button type="button" onClick={() => onLayer('up')}>上移一层</button>
              </div>
            )}
          </div>
          <div className="ctx-item ctx-parent" onMouseEnter={() => setSub('bottom')}>
            {flipX && <span className="ctx-arrow">◂</span>}置于底层 {!flipX && <span className="ctx-arrow">▸</span>}
            {sub === 'bottom' && (
              <div className="ctx-sub">
                <button type="button" onClick={() => onLayer('bottom')}>置于底层</button>
                <button type="button" onClick={() => onLayer('down')}>下移一层</button>
              </div>
            )}
          </div>
          {canGroup && <button type="button" className="ctx-item" onClick={onGroup}>组合</button>}
          {canUngroup && <button type="button" className="ctx-item" onClick={onUngroup}>取消组合</button>}
          {canRemove && <button type="button" className="ctx-item ctx-danger" onClick={onDelete}>删除</button>}
        </>
      )}
    </div>
  );
}
