import { useEffect, useRef, useState } from "react";
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
    img.crossOrigin = "anonymous";
    img.onload = () => setImage(img);
    img.src = url?.startsWith("http") || url?.startsWith("data:") ? url : fileUrl(url);
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
  function moveLayer(direction) {
    const list = [...orderedLayers], index = list.indexOf(selected);
    if (index < 0) return;
    const target = Math.max(0,Math.min(list.length-1,index+direction));
    [list[index],list[target]]=[list[target],list[index]];
    setLayerOrder(list);setDirty(true);
  }
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
  function moveOverlayLayer(direction) {
    if (!selectedOverlay) return;
    const id = overlayId(selectedOverlay);
    setOverlays((list) => {
      const ordered = [...list].sort((a, b) => (a.z_index || 0) - (b.z_index || 0));
      const index = ordered.findIndex((item) => overlayId(item) === id);
      const target = direction > 0 ? Math.min(ordered.length - 1, index + 1) : Math.max(0, index - 1);
      if (index === target) return list;
      [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
      return ordered.map((item, i) => ({ ...item, z_index: i }));
    });
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
      setGuard(false);
      const { task_id } = await api.generate(pid, { action: "recompose_scene", scene_id: sid });
      watch(task_id, goNext ? (nextScene ? `/project/${pid}/scene/${nextScene.scene_id}/edit` : `/project/${pid}?step=layout`) : null);
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
              if (e.target === e.target.getStage()) setSelected(null);
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
              {transparent && bg && <KonvaImage ref={subjectRef} image={bg} {...subjectBox} draggable={!busy}
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
        </div>
        <aside className="card bubble-inspector">
          <section className="element-tools" aria-label="文字与气泡编辑">
            <h2>文字与气泡</h2>
            <div className="form-row">
              <button type="button" disabled={busy || bubbles.length>=20} onClick={()=>addTextElement("text")}>添加文字框</button>
              <button type="button" disabled={busy || bubbles.length>=20} onClick={()=>addTextElement("bubble")}>添加气泡</button>
              <button type="button" disabled={busy || bubbles.length>=20} onClick={()=>addTextElement("both")}>添加文字和气泡</button>
            </div>
            <p className="muted">按住 Shift 点击文字或气泡可多选，拖动任意选中元素即可一起移动。组合后单击即可选中整组。</p>
            <div className="form-row">
              <button type="button" disabled={busy || !selection.canGroup} onClick={selection.group}>组合</button>
              <button type="button" disabled={busy || !selection.canUngroup} onClick={selection.ungroup}>取消组合</button>
              <button type="button" disabled={busy || !selection.canRemove} onClick={selection.remove}>删除选中元素</button>
            </div>
            {selection.ids.length>1 && <p className="muted" role="status">已选中 {selection.ids.length} 个元素，可一起拖动</p>}
          </section>
          {<section>
            <h2>主体与图层</h2>
            {transparent && <button type="button" disabled={busy} onClick={()=>setSelected("subject")}>选择主体图片</button>}
            <p className="muted">图层列表由底到顶。气泡和文字可分别调整层级；透明主体还可以移动和缩放。</p>
            <select aria-label="选择图层" value={selected || ""} onChange={e=>setSelected(e.target.value)}>
              <option value="">选择图层</option>
              {orderedLayers.filter(id=>id!=="inset" || inset).map(id=><option key={id} value={id}>{id==="subject"?"主体图片":id==="caption"?"旁白":id.startsWith("text:")?`对话文字 ${id.slice(5)}`:id.startsWith("overlay:")?"贴图":id==="inset"?"屏幕特写":`气泡 ${id}`}</option>)}
            </select>
            <button type="button" disabled={busy || !selected} onClick={()=>moveLayer(-1)}>下移一层</button>
            <button type="button" disabled={busy || !selected} onClick={()=>moveLayer(1)}>上移一层</button>
            {transparent && <button type="button" disabled={busy} onClick={()=>{setSubjectLayout(null);setDirty(true);}}>还原主体大小与位置</button>}
          </section>}
          <p className="muted">选中文字后拖左右手柄调整宽度并自动换行；字号在下方单独调整。</p>
          <h2>气泡库</h2>
          <label>
            当前对话
            <select
              value={selectedBubble?.bubble_id || ""}
              disabled={busy}
              onChange={(e) => {const b=bubbles.find(b=>b.bubble_id===e.target.value);setSelected(b?.bubble_visible===false?`text:${b.bubble_id}`:e.target.value);}}
            >
              <option value="">选择气泡</option>
              {bubbles.map((b, i) => (
                <option key={b.bubble_id} value={b.bubble_id}>
                  对话 {i + 1}
                </option>
              ))}
            </select>
          </label>
          {selectedBubble ? (
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
          ) : (
            <p className="muted">点击画布中的气泡，或从上方选择对话。</p>
          )}
          <details className="font-library">
            <summary>字体库（{FONT_SPECS.length} 款字体）</summary>
            <p className="muted">内置字体可直接选择，所有项目共用。也可上传字体替换当前项目中的同名选项。</p>
            {FONT_SPECS.map((font) => {
              const installed = installedFontIds.has(font.id);
              return (
                <label className="font-slot" key={font.id}>
                  <span>
                    <b>{font.name}</b>
                    <small>
                      {!installed
                        ? "待导入"
                        : browserFontState.get(font.id)?.browser_error
                          ? "已导入 · 画布回退"
                          : browserFontState.get(font.id)?.installed?.source === "shared" ? "内置可用" : "已导入"}
                    </small>
                  </span>
                  {installed && browserFontState.get(font.id)?.browser_error && (
                    <em title={browserFontState.get(font.id).browser_error}>浏览器回退</em>
                  )}
                  <input
                    type="file"
                    accept=".ttf,.otf,.ttc,font/ttf,font/otf,application/x-font-ttf"
                    disabled={busy || assetBusy}
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (!file) return;
                      setAssetBusy(true);
                      setFontsReady(false);
                      setError("");
                      try {
                        await uploadFont(pid, font.id, file);
                        const next = await loadProjectFonts(pid, [...JSON.parse(usedFontIds), font.id]);
                        setFontRecords(next);
                        setBubbles(items => items.map(b => b.font_id === font.id ? {...b, geometry: undefined} : b));
                        if (bubbles.some(b => b.font_id === font.id)) setDirty(true);
                        setFontsReady(true);
                        setNotice(`${font.name} 已导入，点击“保存”后会更新当前分镜`);
                      } catch (err) {
                        setFontsReady(true);
                        setError(err.message);
                      } finally {
                        setAssetBusy(false);
                      }
                    }}
                  />
                </label>
              );
            })}
          </details>
          <section className="sticker-panel">
            <div className="inspector-section-title">
              <h2>单格贴图</h2>
              <span className="muted">可调整位置的官方形象或图标</span>
            </div>
            <label className="upload-button">
              导入图片贴纸
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                disabled={busy || assetBusy}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  uploadOverlay(file);
                }}
              />
            </label>
            {assets.length > 0 && (
              <div className="sticker-library">
                {assets.map((asset) => (
                  <button type="button" key={asset.asset_id || asset.id} disabled={busy || assetBusy} onClick={() => addExistingOverlay(asset)}>
                    <img src={assetUrl(asset, pid)} alt="" />
                    <span>{asset.filename || asset.name || "贴纸"}</span>
                  </button>
                ))}
              </div>
            )}
            {selectedOverlay ? (
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
                  <button type="button" disabled={busy || assetBusy} onClick={() => moveOverlayLayer(-1)}>下移一层</button>
                  <button type="button" disabled={busy || assetBusy} onClick={() => moveOverlayLayer(1)}>上移一层</button>
                  <button type="button" disabled={busy || assetBusy} onClick={removeSelectedOverlay}>删除图层</button>
                </div>
                <p className="muted">在画布上拖动、缩放四角，旋转手柄可调整角度。</p>
              </div>
            ) : (
              <p className="muted">上传或点击素材后，再在画布中移动和调整。</p>
            )}
          </section>
          <label>
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
          <section className="element-tools" aria-label="手机屏幕特写">
            <h2>手机屏幕特写</h2>
            <p className="muted">画面里有手机或屏幕时，可以单独生成一张屏幕特写叠加在分镜上；生成后在画布中拖动、缩放，也可以随时隐藏。</p>
            <label>屏幕上显示什么
              <textarea
                rows={2}
                maxLength={2000}
                value={screenPrompt}
                disabled={busy}
                placeholder="例如：一条提醒「不要向陌生账户转账」的短信界面。"
                onChange={(e) => setScreenPrompt(e.target.value)}
              />
            </label>
            <button
              disabled={busy || assetBusy || dirty || !screenPrompt.trim() || !scene.raw_url}
              onClick={generateScreenInset}
            >
              {scene.screen_url ? "按新描述重新生成特写" : "生成屏幕特写"}
            </button>
            {dirty && <p className="muted">有未保存的修改，先保存再生成特写。</p>}
            {scene.screen_url && (
              <button
                disabled={busy}
                onClick={() =>
                  changeInset(
                    inset
                      ? null
                      : {
                          asset: `screens/${sid}_screen.png`,
                          x: 710,
                          y: 50,
                          width: 320,
                          height: 480,
                        },
                  )
                }
              >
                {inset ? "隐藏屏幕特写" : "显示屏幕特写"}
              </button>
            )}
          </section>
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
