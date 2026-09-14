import { useEffect, useMemo, useRef, useState } from "react";
import {
  Image as KonvaImage,
  Layer,
  Rect,
  Stage,
  Transformer,
} from "react-konva";
import { api, fileUrl } from "../lib/api.js";
import { useWorkspaceGuard } from "./WorkspaceShell.jsx";
import {
  assetPath,
  listProjectAssets,
  uploadProjectAsset,
} from "../lib/studioAssets.js";
import "../styles/publishing.css";
import stickerCatalog from "../../../schemas/stickers.json";

const DESIGN_WIDTH = 1080;
const DISPLAY_WIDTH = 620;

function useImage(src) {
  const [image, setImage] = useState(null);
  useEffect(() => {
    if (!src) {
      setImage(null);
      return undefined;
    }
    const imageElement = new window.Image();
    imageElement.crossOrigin = "anonymous";
    imageElement.onload = () => setImage(imageElement);
    imageElement.onerror = () => setImage(null);
    imageElement.src = src;
    return () => {
      imageElement.onload = null;
      imageElement.onerror = null;
    };
  }, [src]);
  return image;
}

function useImageMap(items) {
  const [images, setImages] = useState({});
  const source = items.map((item) => `${item.id}:${item.src}`).join("|");
  useEffect(() => {
    let live = true;
    const loaded = {};
    Promise.all(items.map((item) => new Promise((resolve) => {
      const imageElement = new window.Image();
      imageElement.crossOrigin = "anonymous";
      imageElement.onload = () => { loaded[item.id] = imageElement; resolve(); };
      imageElement.onerror = () => resolve();
      imageElement.src = item.src;
    }))).then(() => live && setImages(loaded));
    return () => { live = false; };
  }, [source]);
  return images;
}

function resolveImageUrl(path) {
  if (!path) return "";
  return path.startsWith("http") || path.startsWith("data:") || path.startsWith("blob:") ? path : fileUrl(path);
}

function normaliseAssets(value) {
  const source = Array.isArray(value) ? value : value?.assets || value?.items || [];
  return source.map((asset, index) => ({
    ...asset,
    id: asset.asset_id || asset.id || `asset-${index}`,
    builtinId: asset.name?.match(/^builtin-sticker-v1-(\d{2}-\d{2})$/)?.[1] || "",
    name: asset.name?.startsWith("builtin-sticker-v1-") ? "贴纸" : asset.name || asset.file_name || `贴纸 ${index + 1}`,
    src: resolveImageUrl(assetPath(asset)),
    persisted: true,
  })).filter((asset) => asset.src);
}

function normaliseStickers(value, assets = []) {
  if (!Array.isArray(value)) return [];
  const assetById = new Map(assets.map((asset) => [asset.asset_id || asset.id, asset]));
  return value.map((sticker, index) => ({
    id: sticker.id || sticker.sticker_id || `sticker-${index + 1}`,
    name: sticker.name || "贴纸",
    asset_id: sticker.asset_id || sticker.id || "",
    src: resolveImageUrl(sticker.src || sticker.url || sticker.path || sticker.asset_url || assetById.get(sticker.asset_id)?.url),
    x: Number(sticker.x) || 0,
    y: Number(sticker.y) || 0,
    width: clamp(Number(sticker.width) || 180, 24, 1800),
    height: clamp(Number(sticker.height) || 180, 24, 1800),
    rotation: Number(sticker.rotation) || 0,
    opacity: Number.isFinite(Number(sticker.opacity)) ? Number(sticker.opacity) : 1,
    flip_x: Boolean(sticker.flip_x ?? sticker.flipX),
    flip_y: Boolean(sticker.flip_y ?? sticker.flipY),
    z_index: Number.isFinite(Number(sticker.z_index ?? sticker.z)) ? Number(sticker.z_index ?? sticker.z) : index,
  })).filter((sticker) => sticker.src);
}

function imageSize(src) {
  return new Promise((resolve, reject) => {
    const imageElement = new window.Image();
    imageElement.crossOrigin = "anonymous";
    imageElement.onload = () => resolve({ width: imageElement.naturalWidth || imageElement.width, height: imageElement.naturalHeight || imageElement.height });
    imageElement.onerror = () => reject(new Error("贴纸图片无法加载"));
    imageElement.src = src;
  });
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, Number(value) || 0));
}

function serialiseStickers(value) {
  return JSON.stringify(value.map(({ asset_id, x, y, width, height, rotation, opacity, flip_x, flip_y, z_index }) => ({ asset_id, x, y, width, height, rotation, opacity, flip_x, flip_y, z_index })));
}

export default function DecorationEditor({ pid, project, busy, onSave }) {
  const setGuard = useWorkspaceGuard();
  const [assets, setAssets] = useState([]);
  const [stickers, setStickers] = useState(() => normaliseStickers(project?.long_layout?.stickers, project?.assets));
  const [selectedId, setSelectedId] = useState(null);
  const [assetLoading, setAssetLoading] = useState(false);
  const [stickerGroup, setStickerGroup] = useState("all");
  const importLock = useRef(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [backgroundSrc, setBackgroundSrc] = useState("");
  const stageRef = useRef(null);
  const transformerRef = useRef(null);
  const nodeRefs = useRef({});
  const backgroundUrlRef = useRef(null);
  const stickerSource = JSON.stringify([project?.long_layout?.stickers || [], project?.assets || []]);
  const background = useImage(backgroundSrc);
  const scale = background ? Math.min(DISPLAY_WIDTH / DESIGN_WIDTH, 0.72) : 0.58;
  const stageWidth = DESIGN_WIDTH * scale;
  // previewLong returns a 540px thumbnail; stretch it to the editor's
  // display width while keeping sticker coordinates in the 1080px design
  // space. This prevents tall long images from being vertically distorted.
  const stageHeight = background ? background.height * (stageWidth / background.width) : 680;
  const designHeight = background ? background.height * DESIGN_WIDTH / background.width : 40000;
  const selected = stickers.find((sticker) => sticker.id === selectedId) || null;
  const sortedStickers = useMemo(() => [...stickers].sort((a, b) => (a.z_index || 0) - (b.z_index || 0)), [stickers]);
  const stickerImages = useImageMap(sortedStickers);
  const savedStickers = normaliseStickers(project?.long_layout?.stickers, project?.assets);
  const stickersSaved = serialiseStickers(stickers) === serialiseStickers(savedStickers);
  const projectBusy = busy || saving || project?.active_task?.status === "pending" || project?.active_task?.status === "running";
  const longImageStale = Boolean(project?.long_image_stale);
  const builtinStickers = stickerCatalog.stickers.filter((item) => stickerGroup === "all" || item.group === stickerGroup);
  const uploadedAssets = assets.filter((asset) => !asset.builtinId);

  useEffect(() => {
    setGuard(!stickersSaved);
    return () => setGuard(false);
  }, [setGuard, stickersSaved, stickerSource]);

  useEffect(() => setStickers(normaliseStickers(project?.long_layout?.stickers, project?.assets)), [stickerSource]);
  useEffect(() => {
    if (!project?.long_image_url) {
      if (backgroundUrlRef.current) URL.revokeObjectURL(backgroundUrlRef.current);
      backgroundUrlRef.current = null;
      setBackgroundSrc("");
      return undefined;
    }
    const abort = new AbortController();
    const options = { ...(project.long_layout || {}), stickers: [] };
    api.previewLong(pid, options, abort.signal)
      .then((blob) => {
        if (abort.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        if (backgroundUrlRef.current) URL.revokeObjectURL(backgroundUrlRef.current);
        backgroundUrlRef.current = url;
        setBackgroundSrc(url);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(`作品背景预览失败：${e.message || "请先保存排版"}`);
      });
    return () => { abort.abort(); };
  }, [pid, project?.long_image_url, JSON.stringify(project?.long_layout || {})]);
  useEffect(() => () => {
    if (backgroundUrlRef.current) URL.revokeObjectURL(backgroundUrlRef.current);
  }, []);
  useEffect(() => {
    let live = true;
    setError("");
    listProjectAssets(pid, "sticker")
      .then((value) => live && setAssets(normaliseAssets(value)))
      .catch((e) => live && setError(`贴纸素材加载失败：${e.message || "请稍后重试"}`));
    return () => { live = false; };
  }, [pid]);

  useEffect(() => {
    const transformer = transformerRef.current;
    if (!transformer) return;
    const node = selectedId ? nodeRefs.current[selectedId] : null;
    transformer.nodes(node ? [node] : []);
    transformer.getLayer()?.batchDraw();
  }, [selectedId, stickers, background]);

  function patchSticker(id, patch) {
    setStickers((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  }

  async function addAsset(asset) {
    if (!asset?.persisted || !asset.src || busy) return;
    if (stickers.length >= 50) {
      setError("一张作品最多添加 50 张贴纸，请先删除不需要的贴纸。");
      return;
    }
    setError("");
    setAssetLoading(true);
    try {
      const size = await imageSize(asset.src);
      const maxSide = 300;
      const ratio = Math.min(1, maxSide / Math.max(size.width, size.height));
      const width = Math.max(24, Math.round(size.width * ratio));
      const height = Math.max(24, Math.round(size.height * ratio));
      const id = `sticker-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const item = {
        id,
        asset_id: asset.asset_id || asset.id,
        name: asset.name,
        src: asset.src,
        x: Math.round((DESIGN_WIDTH - width) / 2),
        y: 220,
        width,
        height,
        rotation: 0,
        opacity: 1,
        flip_x: false,
        flip_y: false,
        z_index: stickers.length,
      };
      setStickers((current) => [...current, { ...item, z_index: current.length }]);
      setSelectedId(id);
    } catch (e) {
      setError(`添加贴纸失败：${e.message || "图片无法加载"}`);
    } finally {
      setAssetLoading(false);
    }
  }

  async function addBuiltin(item) {
    if (projectBusy || importLock.current || assetLoading) return;
    if (stickers.length >= 50) {
      setError("一张作品最多添加 50 张贴纸，请先删除不需要的贴纸。");
      return;
    }
    importLock.current = true;
    setAssetLoading(true);
    setError("");
    try {
      let asset = assets.find((entry) => entry.builtinId === item.id);
      if (!asset) {
        const response = await fetch(`/sticker-assets/${item.id}.png`);
        if (!response.ok) throw new Error("贴纸素材暂时无法加载，请重试");
        const file = new File([await response.blob()], `${item.id}.png`, { type: "image/png" });
        const result = await uploadProjectAsset(pid, file, "sticker", `builtin-sticker-v1-${item.id}`);
        asset = normaliseAssets([result])[0];
        if (!asset) throw new Error("服务器没有返回贴纸素材地址");
        setAssets((current) => [...current, asset]);
      }
      await addAsset(asset);
    } catch (e) {
      setError(`添加贴纸失败：${e.message || "请稍后重试"}`);
    } finally {
      importLock.current = false;
      setAssetLoading(false);
    }
  }

  async function handleUpload(file) {
    if (!file) return;
    setError("");
    setAssetLoading(true);
    try {
      const result = await uploadProjectAsset(pid, file, "sticker", file.name);
      const src = resolveImageUrl(assetPath(result));
      if (!src) throw new Error("服务器没有返回贴纸素材地址");
      const asset = {
        ...result,
        id: result.asset_id || result.id || `asset-${Date.now()}`,
        asset_id: result.asset_id || result.id,
        name: result.name || file.name,
        src,
        persisted: true,
      };
      setAssets((current) => [asset, ...current.filter((item) => item.id !== asset.id)]);
      await addAsset(asset);
    } catch (e) {
      setError(`贴纸上传失败：${e.message || "服务器未接受该文件"}`);
    } finally {
      setAssetLoading(false);
    }
  }

  function handleDragEnd(event, item) {
    const node = event.target;
    patchSticker(item.id, {
      x: Math.round(clamp(node.x() / scale - item.width / 2, -item.width + 8, DESIGN_WIDTH - 8)),
      y: Math.round(clamp(node.y() / scale - item.height / 2, -item.height + 8, Math.max(8, designHeight - 8))),
    });
  }

  function handleTransformEnd(item) {
    const node = nodeRefs.current[item.id];
    if (!node) return;
    const nextWidth = Math.min(1800, Math.max(24, Math.round(item.width * Math.abs(node.scaleX()))));
    const nextHeight = Math.min(1800, Math.max(24, Math.round(item.height * Math.abs(node.scaleY()))));
    const centreX = node.x() / scale;
    const centreY = node.y() / scale;
    patchSticker(item.id, {
      x: Math.round(clamp(centreX - nextWidth / 2, -nextWidth + 8, DESIGN_WIDTH - 8)),
      y: Math.round(clamp(centreY - nextHeight / 2, -nextHeight + 8, Math.max(8, designHeight - 8))),
      width: nextWidth,
      height: nextHeight,
      rotation: Math.round(node.rotation()),
    });
    node.scaleX(item.flip_x ? -1 : 1);
    node.scaleY(item.flip_y ? -1 : 1);
  }

  function reorder(direction) {
    if (!selected) return;
    const ordered = [...stickers].sort((a, b) => (a.z_index || 0) - (b.z_index || 0));
    const index = ordered.findIndex((item) => item.id === selected.id);
    const otherIndex = index + direction;
    if (otherIndex < 0 || otherIndex >= ordered.length) return;
    const current = ordered[index];
    ordered[index] = ordered[otherIndex];
    ordered[otherIndex] = current;
    setStickers(ordered.map((item, z_index) => ({ ...item, z_index })));
  }

  function removeSelected() {
    if (!selected) return;
    setStickers((current) => current.filter((item) => item.id !== selected.id));
    setSelectedId(null);
  }

  async function save() {
    if (busy || saving) return;
    setSaving(true);
    setError("");
    try {
      const clean = stickers.map(({ name, asset_id, x, y, width, height, rotation, opacity, flip_x, flip_y, z_index }) => ({ name, asset_id, x, y, width, height, rotation, opacity, flip_x, flip_y, z_index }));
      await onSave({ ...(project?.long_layout || {}), stickers: clean });
    } catch (e) {
      setError(`保存贴纸失败：${e.message || "请稍后重试"}`);
    } finally {
      setSaving(false);
    }
  }

  function downloadDecorated() {
    if (!background) return;
    if (busy || saving || project?.active_task?.status === "pending" || project?.active_task?.status === "running") {
      setError("作品仍在生成，请完成后再下载。");
      return;
    }
    if (longImageStale) {
      setError("排版已修改，请保存贴纸布局重新生成成品。");
      return;
    }
    if (!stickersSaved) {
      setError("请先保存贴纸布局，再下载最终成品。");
      return;
    }
    if (!project?.long_image_url) {
      setError("还没有可下载的成品。");
      return;
    }
    const link = document.createElement("a");
    link.href = `${resolveImageUrl(project.long_image_url)}${String(project.long_image_url).includes("?") ? "&" : "?"}download=true`;
    link.download = `${project?.storyboard?.title || "漫画作品"}-贴纸版.png`;
    link.click();
  }

  return (
    <section className="card decoration-editor" aria-label="作品贴纸装饰">
      <div className="publishing-header">
        <div><p className="eyebrow">FINAL DECORATION</p><h2>贴纸装饰</h2><p className="muted">挑选喜欢的贴纸，或上传自己的素材，点击添加后自由拖动、缩放和旋转。</p></div>
        <div className="publishing-header-meta"><span className="publishing-status-dot" />{selected ? "已选中贴纸" : "点击素材即可添加"}</div>
      </div>
      <div className="decoration-layout">
        <main className="decoration-canvas">
          <div className="decoration-canvas-toolbar"><div><b>最终成品</b><span className="muted"> · 背景预览不含已保存贴纸</span></div><span className="publishing-zoom-label">拖动 / 缩放 / 旋转</span></div>
          {longImageStale && <p className="decoration-stale-note" role="status">排版已修改，请保存贴纸布局重新生成成品</p>}
          <div className="decoration-stage-wrap">
            {background ? (
              <div className="decoration-stage">
                <Stage ref={stageRef} width={stageWidth} height={stageHeight} onMouseDown={(event) => { if (event.target === event.target.getStage()) setSelectedId(null); }}>
                  <Layer>
                    <KonvaImage image={background} x={0} y={0} width={stageWidth} height={stageHeight} listening={false} />
                    {sortedStickers.map((item) => {
                      const image = stickerImages[item.id];
                      if (!image) return null;
                      const renderX = (item.x + item.width / 2) * scale;
                      const renderY = (item.y + item.height / 2) * scale;
                      return <KonvaImage key={item.id} ref={(node) => { if (node) nodeRefs.current[item.id] = node; }} image={image} x={renderX} y={renderY} offsetX={item.width * scale / 2} offsetY={item.height * scale / 2} width={item.width * scale} height={item.height * scale} rotation={item.rotation} opacity={item.opacity} scaleX={item.flip_x ? -1 : 1} scaleY={item.flip_y ? -1 : 1} draggable={!busy} onClick={() => setSelectedId(item.id)} onTap={() => setSelectedId(item.id)} onDragEnd={(event) => handleDragEnd(event, item)} onTransformEnd={() => handleTransformEnd(item)} />;
                    })}
                    <Transformer ref={transformerRef} rotateEnabled enabledAnchors={["top-left", "top-right", "bottom-left", "bottom-right"]} boundBoxFunc={(oldBox, newBox) => newBox.width < 24 * scale || newBox.height < 24 * scale || newBox.width > 1800 * scale || newBox.height > 1800 * scale ? oldBox : newBox} anchorSize={8} borderStroke="#2b7062" anchorStroke="#2b7062" anchorFill="#fff" />
                  </Layer>
                </Stage>
              </div>
            ) : <div className="decoration-empty">请先生成并保存排版，完成后这里会显示可装饰的成品。</div>}
          </div>
        </main>
        <aside className="decoration-inspector">
          <div className="decoration-library-heading"><h3>内置贴纸</h3><span>{stickerCatalog.stickers.length} 张</span></div>
          <label className="decoration-library-filter">分类
            <select aria-label="贴纸分类" value={stickerGroup} onChange={(event) => setStickerGroup(event.target.value)}>
              <option value="all">全部贴纸</option>
              {stickerCatalog.groups.map((group) => <option key={group.id} value={group.id}>{group.label}</option>)}
            </select>
          </label>
          <div className="decoration-assets decoration-builtin-assets" aria-label="内置贴纸列表" aria-busy={assetLoading}>
            {builtinStickers.map((item) => <button type="button" className="decoration-asset" key={item.id} aria-label={`添加贴纸 ${item.id}`} disabled={projectBusy || assetLoading || !background} onClick={() => addBuiltin(item)}>
              <img src={`/sticker-assets/${item.id}.png`} alt="" loading="lazy" decoding="async" />
            </button>)}
          </div>
          <p className="decoration-library-hint" role="status">{assetLoading ? "正在添加贴纸…" : background ? "点击即可添加，同一张贴纸可以重复使用。" : "先保存作品排版，再选择贴纸。"}</p>
          <details className="decoration-uploaded-library">
          <summary>我的上传{uploadedAssets.length > 0 ? ` · ${uploadedAssets.length}` : ""}</summary>
          <label className="decoration-upload">上传图标 / 贴纸<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy || assetLoading} onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; handleUpload(file); }} /></label>
          <div className="decoration-assets">{uploadedAssets.length ? uploadedAssets.map((asset) => <button type="button" className="decoration-asset" key={asset.id} disabled={busy || assetLoading} onClick={() => addAsset(asset)} title="点击添加到作品"><img src={asset.src} alt="" /><small>{asset.name}</small></button>) : <div className="decoration-empty" style={{ gridColumn: "1 / -1" }}>上传自己的图片，也能作为贴纸使用。</div>}</div>
          </details>
          <div className="decoration-selected">
            <h4>{selected ? `调整：${selected.name}` : "选择画布上的贴纸"}</h4>
            {selected ? <fieldset className="decoration-controls" disabled={projectBusy || assetLoading}>
              <div className="decoration-control-grid">
                <label>X<input type="number" value={selected.x} disabled={busy} onChange={(e) => patchSticker(selected.id, { x: Number(e.target.value) })} /></label>
                <label>Y<input type="number" value={selected.y} disabled={busy} onChange={(e) => patchSticker(selected.id, { y: Number(e.target.value) })} /></label>
                <label>宽度<input type="number" min="24" max="1800" value={selected.width} disabled={busy} onChange={(e) => patchSticker(selected.id, { width: clamp(e.target.value, 24, 1800) })} /></label>
                <label>高度<input type="number" min="24" max="1800" value={selected.height} disabled={busy} onChange={(e) => patchSticker(selected.id, { height: clamp(e.target.value, 24, 1800) })} /></label>
                <label>旋转<input type="number" min="-360" max="360" value={selected.rotation} disabled={busy} onChange={(e) => patchSticker(selected.id, { rotation: Number(e.target.value) })} /></label>
                <label className="decoration-control-wide">透明度：{Math.round(selected.opacity * 100)}%<input type="range" min="0" max="1" step=".01" value={selected.opacity} disabled={busy} onChange={(e) => patchSticker(selected.id, { opacity: Number(e.target.value) })} /></label>
              </div>
              <div className="decoration-checks"><label><input type="checkbox" checked={selected.flip_x} disabled={busy} onChange={(e) => patchSticker(selected.id, { flip_x: e.target.checked })} /> 水平翻转</label><label><input type="checkbox" checked={selected.flip_y} disabled={busy} onChange={(e) => patchSticker(selected.id, { flip_y: e.target.checked })} /> 垂直翻转</label></div>
              <div className="decoration-actions"><button type="button" disabled={busy} onClick={() => reorder(1)}>上移</button><button type="button" disabled={busy} onClick={() => reorder(-1)}>下移</button><button type="button" disabled={busy} onClick={removeSelected}>删除</button></div>
            </fieldset> : <div className="decoration-empty">点击一个贴纸后，可以在这里精确调整位置、大小、旋转和透明度。</div>}
          </div>
          <button type="button" className="decoration-save" disabled={busy || saving || assetLoading || !background} onClick={save}>{saving ? "保存中…" : "保存贴纸布局"}</button>
          <button type="button" className="button" style={{ width: "100%", marginTop: 8 }} disabled={!background || !stickersSaved || projectBusy || longImageStale} onClick={downloadDecorated}>下载已保存最终成品</button>
          {error && <p className="decoration-error" role="alert">{error}</p>}
        </aside>
      </div>
    </section>
  );
}
