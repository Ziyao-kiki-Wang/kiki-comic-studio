import { useEffect, useRef, useState } from "react";
import catalog from "../../../schemas/studio.json";
import { api, fileUrl } from "../lib/api.js";
import { useWorkspaceGuard } from "./WorkspaceShell.jsx";
import {
  FONT_SPECS,
  TITLE_EFFECTS,
  assetPath,
  listFonts,
  loadFontFace,
  readAsset,
  uploadFont,
  uploadProjectAsset,
} from "../lib/studioAssets.js";
import "../styles/publishing.css";
import FooterEditor from "./FooterEditor.jsx";
import HeadingEditor from "./HeadingEditor.jsx";
import PageMargins from "./PageMargins.jsx";
import PageBackground from "./PageBackground.jsx";
import LongSceneOverlay from "./LongSceneOverlay.jsx";
import { pollTask } from "../lib/api.js";

const DEFAULT_LAYOUT = {
  template_id: "cards",
  gap: 60,
  gaps: {},
  title: "",
  subtitle: "",
  footer: "",
  footer_blocks: [],
  heading: { style: "plain", font_size: 30, align: "left" },
  heading_overrides: {},
  accent: "",
  background_color: "",
  background_opacity: 1,
  title_top: 48,
  title_bottom: 32,
  margin_top_cm: 0,
  margin_bottom_cm: 0,
  print_width_cm: 20,
  title_line_gap: 18,
  letter_spacing: 0,
  body_line_gap: 14,
  title_style: "plain",
  title_font_id: null,
  body_font_id: null,
  font_size: 58,
  align: "center",
  title_image_asset: null,
};

function TemplateThumb({ template: t }) {
  if (t.layout) {
    const strip = t.id === "comic_strip", editorial = t.id === "editorial_mix", magazine = t.id === "magazine_grid";
    const frames = editorial ? [[8,32,52,34],[40,74,52,34]] : magazine ? [[8,31,84,38],[8,76,39,38],[53,76,39,38]] : strip ? [[7,38,26,57],[37,38,26,57],[67,38,26,57]] : [[8,31,39,38],[53,31,39,38],[8,76,39,38],[53,76,39,38]];
    return <svg viewBox="0 0 100 126" aria-hidden="true"><rect width="100" height="126" fill={t.background}/>
      <path d="M20 12H80M32 19H68" stroke={t.accent} strokeWidth="3"/>
      {t.id === "filmstrip" && Array.from({length:9},(_,i)=><g key={i} fill="#e5dcc9"><rect x="1" y={i*14+2} width="3" height="6"/><rect x="96" y={i*14+2} width="3" height="6"/></g>)}
      {frames.map(([x,y,w,h],i)=><g key={i} transform={`translate(${x} ${y+(t.id === "sketchbook" && i%2 ? 4 : 0)})`}><rect width={w} height={h} rx={t.id === "gallery_grid" ? 3 : 0} fill="white" stroke={t.accent} strokeWidth={strip ? 1.5 : .4}/><rect x="3" y="4" width={w-6} height={h-14} fill={t.accent} opacity=".18"/><path d={`M4 ${h-6}H${w-6}`} stroke={t.accent} strokeWidth="1"/>{t.id === "sketchbook" && <rect x={w/2-8} y="-2" width="16" height="4" fill="#e4c891"/>}</g>)}
      {editorial && <g stroke={t.accent}><path d="M66 39H90M66 46H88M66 53H85M10 83H34M10 90H34M10 97H29" strokeWidth="1.5"/></g>}
    </svg>;
  }
  const timeline = t.id === "timeline";
  const notebook = t.id === "notebook";
  const full = t.id === "poster";
  return (
    <svg viewBox="0 0 100 126" aria-hidden="true">
      <rect width="100" height="126" rx="4" fill={t.background} />
      {notebook && Array.from({ length: 12 }, (_, i) => (
        <path key={i} d={`M 5 ${i * 10 + 8} H 95`} stroke="#cad6df" strokeWidth=".5" />
      ))}
      <rect x="8" y="8" width="84" height={t.id === "magazine" ? 12 : 20} rx={t.id === "stickers" ? 5 : 1} fill={t.accent} />
      {timeline && <path d="M 13 35 V 114" stroke={t.accent} strokeWidth="2" />}
      {[0, 1, 2].map((i) => (
        <g key={i} transform={`translate(0 ${34 + i * 29})`}>
          {timeline && <circle cx="13" cy="6" r="4" fill={t.accent} />}
          <rect x={timeline ? 22 : full ? 0 : 8} width={timeline ? 70 : full ? 100 : 84} height="24" rx={t.id === "cards" ? 4 : 1} fill="#fff" stroke={t.id === "frames" ? t.accent : "#dcdcdc"} strokeWidth={t.id === "frames" ? 2 : 0.5} />
          {t.id === "qa" && <rect x="8" width="84" height="6" fill={t.accent} />}
          <rect x={timeline ? 27 : 14} y="8" width={timeline ? 60 : 72} height="8" fill={t.accent} opacity=".22" />
          <path d={`M ${timeline ? 27 : 14} 20 h ${timeline ? 42 : 53}`} stroke={t.accent} strokeWidth="1" />
          {t.id === "stickers" && <rect x="21" y="-2" width="16" height="4" fill="#dbbe92" />}
          {t.id === "notice" && <rect x="8" width="3" height="24" fill={t.accent} />}
        </g>
      ))}
      {t.id === "scroll" && <path d="M 4 4 V 122 M 96 4 V 122" stroke={t.accent} />}
    </svg>
  );
}

function normalizeFontStatus(value) {
  const source = Array.isArray(value) ? value : value?.fonts || [];
  return source.reduce((result, item) => {
    const id = item.font_id || item.id;
    if (id) result[id] = { ...item, loaded: Boolean(item.loaded || item.installed) };
    return result;
  }, {});
}

function titleFamily(options, localFonts) {
  const spec = FONT_SPECS.find((font) => font.id === options.title_font_id) || FONT_SPECS.find((font) => font.id === "microsoft_yahei_regular");
  return localFonts[spec.id]?.family || spec.fallback || "Microsoft YaHei";
}

function TitleEffectSample({ effect, options, localFonts }) {
  const style = {
    fontFamily: titleFamily(options, localFonts),
    fontSize: `${Math.min(34, Math.max(20, Number(options.font_size || 58) * 0.58))}px`,
    color: options.accent || "#2b7062",
    textAlign: options.align || "center",
  };
  if (effect === "outline") style.textShadow = "-1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff";
  if (effect === "shadow") style.textShadow = "0 5px 10px rgba(25,58,52,.2)";
  if (effect === "raised") style.textShadow = "1px 2px 0 #fff, 3px 5px 0 rgba(39,90,78,.22)";
  return <span className="title-effect-sample" style={style}>标题预览</span>;
}

export default function LongImageDesigner({ pid, project, busy, onSave }) {
  const setGuard = useWorkspaceGuard();
  const [examples, setExamples] = useState({});
  const [exampleError, setExampleError] = useState("");
  const [templateFilter, setTemplateFilter] = useState("all");
  const [options, setOptions] = useState({ ...DEFAULT_LAYOUT, ...(project?.long_layout || {}) });
  const [preview, setPreview] = useState(null);
  const [layoutBoxes, setLayoutBoxes] = useState(null);
  const [editSceneId, setEditSceneId] = useState(null);
  const [applying, setApplying] = useState(false);
  const previewImgRef = useRef(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [footerBusy, setFooterBusy] = useState(false);
  const [inspectorWidth, setInspectorWidth] = useState(350);
  const resizeStart = useRef(null);
  useEffect(() => () => resizeStart.current?.(), []);
  function resizeInspector(e) {
    e.preventDefault();
    resizeStart.current?.();
    const startX = e.clientX, startWidth = inspectorWidth;
    const move = event => setInspectorWidth(Math.max(260, Math.min(520, startWidth + startX - event.clientX)));
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      resizeStart.current = null;
    };
    resizeStart.current = stop;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  }
  const [fontStatus, setFontStatus] = useState({});
  const [fontBusy, setFontBusy] = useState("");
  const [localFonts, setLocalFonts] = useState({});
  const [titleImage, setTitleImage] = useState("");
  const [titleImagePersisted, setTitleImagePersisted] = useState(true);
  const urlRef = useRef(null);
  const titleImageRef = useRef(null);
  const source = JSON.stringify(project?.long_layout || {});

  useEffect(() => setOptions({ ...DEFAULT_LAYOUT, ...(project?.long_layout || {}) }), [source]);
  useEffect(() => {
    let live = true;
    listFonts(pid).then((value) => live && setFontStatus(normalizeFontStatus(value))).catch(() => {});
    return () => { live = false; };
  }, [pid]);
  useEffect(() => {
    let live = true;
    const id = options.title_font_id;
    const row = fontStatus[id];
    if (!id || !row?.installed) return undefined;
    loadFontFace(pid, row).then((font) => {
      if (live) setLocalFonts((previous) => ({ ...previous, [id]: font }));
    }).catch((e) => { if (live) setError(`字体预览加载失败：${e.message}`); });
    return () => { live = false; };
  }, [pid, options.title_font_id, fontStatus]);
  useEffect(() => {
    const asset = (project?.assets || []).find((item) => item.asset_id === options.title_image_asset && (item.kind === "title_image" || item.kind === "image"));
    if (!asset) {
      if (!options.title_image_asset) setTitleImage("");
      return undefined;
    }
    setTitleImage(assetPath(asset));
    setTitleImagePersisted(true);
    return undefined;
  }, [options.title_image_asset, project?.assets]);

  const ready = Boolean(project?.scenes?.every((scene) => scene.composite_url && !scene.render_stale));
  const assetRevision = (project?.scenes || []).map((scene) => scene.panel_url || scene.composite_url).join("|");

  useEffect(() => {
    if (!ready || busy) return undefined;
    const abort = new AbortController();
    const urls = [];
    setExamples({});
    setExampleError("");
    (async () => {
      for (const template of catalog.templates) {
        try {
          const blob = await api.previewLong(pid, { ...options, template_id: template.id, gap: 60, thumbnail: true }, abort.signal);
          if (abort.signal.aborted) return;
          const url = URL.createObjectURL(blob);
          urls.push(url);
          setExamples((previous) => ({ ...previous, [template.id]: url }));
        } catch {
          if (!abort.signal.aborted) setExampleError("样式实图暂时无法加载，仍可使用线框预览。");
          break;
        }
      }
    })();
    return () => { abort.abort(); urls.forEach((url) => URL.revokeObjectURL(url)); };
  }, [pid, ready, busy, assetRevision]);

  useEffect(() => {
    if (!ready || busy) return undefined;
    const abort = new AbortController();
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const blob = await api.previewLong(pid, options, abort.signal);
        if (abort.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = url;
        setPreview(url);
        setLayoutBoxes(blob.longLayout || null);
        setError("");
      } catch (e) {
        if (!abort.signal.aborted) setError(e.message || "排版预览失败");
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    }, 350);
    return () => { abort.abort(); clearTimeout(timer); };
  }, [pid, JSON.stringify(options), ready, busy, project?.updated_at]);

  useEffect(() => () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    if (titleImageRef.current) URL.revokeObjectURL(titleImageRef.current);
    Object.values(localFonts).forEach((font) => font.url && URL.revokeObjectURL(font.url));
  }, []);

  const update = (patch) => setOptions((previous) => ({ ...previous, ...patch }));
  const theme = catalog.templates.find((template) => template.id === options.template_id) || catalog.templates[0];
  const sceneRows = [];
  const layoutScenes = project?.storyboard?.scenes || [];
  const columns = !theme.layout || theme.id === "editorial_mix" ? 1 : Math.min(theme.id === "comic_strip" ? 3 : 2, layoutScenes.length || 1);
  for (let index = 0; index < layoutScenes.length;) {
    const count = theme.id === "magazine_grid" && index === 0 ? 1 : columns;
    sceneRows.push(layoutScenes.slice(index, index+count));
    index += count;
  }

  useEffect(() => {
    const saved = { ...DEFAULT_LAYOUT, ...(project?.long_layout || {}) };
    const comparable = (value) => JSON.stringify({
      template_id: value.template_id,
      gap: value.gap,
      gaps: value.gaps || {},
      title: value.title || "",
      subtitle: value.subtitle || "",
      footer: value.footer || "",
      footer_blocks: value.footer_blocks || [],
      heading: value.heading,
      heading_overrides: value.heading_overrides || {},
      accent: value.accent || "",
      background_color: value.background_color || "",
      background_opacity: value.background_opacity ?? 1,
      title_top: value.title_top,
      title_bottom: value.title_bottom,
      margin_top_cm: value.margin_top_cm,
      margin_bottom_cm: value.margin_bottom_cm,
      print_width_cm: value.print_width_cm,
      title_line_gap: value.title_line_gap,
      letter_spacing: value.letter_spacing,
      body_line_gap: value.body_line_gap,
      title_style: value.title_style,
      title_font_id: value.title_font_id,
      body_font_id: value.body_font_id,
      font_size: value.font_size,
      align: value.align,
      title_image_asset: value.title_image_asset,
    });
    setGuard(comparable(options) !== comparable(saved) || !titleImagePersisted);
    return () => setGuard(false);
  }, [setGuard, JSON.stringify(options), source, titleImagePersisted]);

  async function handleFont(file, spec) {
    if (!file) return;
    setError("");
    setFontBusy(spec.id);
    try {
      const result = await uploadFont(pid, spec.id, file);
      const row = result.font;
      const font = await loadFontFace(pid, row);
      setLocalFonts((previous) => ({ ...previous, [spec.id]: font }));
      setFontStatus((previous) => ({ ...previous, [spec.id]: { ...row, loaded: true } }));
      update({ title_font_id: spec.id });
    } catch (e) {
      setError(`${spec.name} 导入失败：${e.message || "服务器未接受该字体"}`);
    } finally {
      setFontBusy("");
    }
  }

  async function handleTitleImage(file) {
    if (!file) return;
    setError("");
    let localUrl = "";
    try {
      await readAsset(file, ["image/png", "image/jpeg", "image/webp"], 8 * 1024 * 1024);
      localUrl = URL.createObjectURL(file);
      if (titleImageRef.current) URL.revokeObjectURL(titleImageRef.current);
      titleImageRef.current = localUrl;
      setTitleImage(localUrl);
      setTitleImagePersisted(false);
      const result = await uploadProjectAsset(pid, file, "title_image", file.name);
      const remote = result?.path || result?.url || result?.file_url;
      if (!remote) throw new Error("服务器没有返回标题素材地址");
      setTitleImagePersisted(true);
      update({ title_image_asset: result.asset_id });
    } catch (e) {
      setError(`标题图片上传失败：${e.message || "请稍后重试"}`);
    }
  }

  function removeTitleImage() {
    if (titleImageRef.current) URL.revokeObjectURL(titleImageRef.current);
    titleImageRef.current = null;
    setTitleImage("");
    setTitleImagePersisted(true);
    update({ title_image_asset: null });
  }

  /* ---- Click a scene in the preview to fine-tune its bubbles/caption/subject ---- */
  function previewClick(e) {
    if (!layoutBoxes?.scenes?.length || !previewImgRef.current || applying) return;
    const img = previewImgRef.current;
    const rect = img.getBoundingClientRect();
    const scale = rect.width / (layoutBoxes.width || 1080);
    const x = (e.clientX - rect.left) / scale;
    const y = (e.clientY - rect.top) / scale;
    const hit = layoutBoxes.scenes.find(b => x >= b.x && x <= b.x + b.width && y >= b.y && y <= b.y + b.height);
    if (hit) setEditSceneId(hit.scene_id);
  }
  const editBox = layoutBoxes?.scenes?.find(b => b.scene_id === editSceneId);
  const editScene = project?.scenes?.find(s => s.scene_id === editSceneId);
  const editStory = project?.storyboard?.scenes?.find(s => s.scene_id === editSceneId);
  const displayScale = previewImgRef.current ? previewImgRef.current.getBoundingClientRect().width / (layoutBoxes?.width || 1080) : 0.5;

  async function applySceneEdit(changed) {
    if (!editSceneId) return;
    setApplying(true);
    setError("");
    try {
      await api.saveLayout(pid, editSceneId, {
        bubbles: changed.bubbles,
        caption_layout: changed.caption_layout,
        subject_layout: changed.subject_layout,
        caption: changed.caption,
      });
      const { task_id } = await api.generate(pid, { action: "recompose_scene", scene_id: editSceneId });
      await new Promise((resolve, reject) => {
        const stop = pollTask(task_id, (t) => {
          if (t.status === "done") { stop(); resolve(); }
          if (t.status === "failed") { stop(); reject(new Error(t.error || "合成失败")); }
        });
      });
      setEditSceneId(null);
      // recompose_scene already rebuilds the panel + long image; re-fetch the
      // preview so the just-dragged elements appear in their new positions.
      const blob = await api.previewLong(pid, options);
      const url = URL.createObjectURL(blob);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = url;
      setPreview(url);
      setLayoutBoxes(blob.longLayout || null);
    } catch (e) {
      setError(e.message || "应用修改失败");
    } finally {
      setApplying(false);
    }
  }

  return (
    <section className="card publishing-studio" aria-label="漫画作品排版">
      <div className="publishing-header">
        <div><p className="eyebrow">COMIC DESIGN STUDIO</p><h2>漫画排版工坊</h2><p className="muted">长图、图文交错、杂志拼版与横向漫画，让故事有更多呈现方式。</p></div>
        <div className="publishing-header-meta"><span className="publishing-status-dot" />{loading ? "预览更新中" : ready ? "实时预览已就绪" : "等待分镜完成"}</div>
      </div>
      <div className="publishing-layout" style={{"--inspector-width":`${inspectorWidth}px`}}>
        <aside className="publishing-sidebar">
          <div className="publishing-sidebar-heading"><span>01</span><div><b>排版模板</b><small>{catalog.templates.length} 套样式</small></div></div>
          <div className="publishing-template-filters" role="group" aria-label="筛选排版模板">{[['all','全部'],['classic','经典长图'],['creative','创意拼版']].map(([key,label])=><button key={key} type="button" aria-pressed={templateFilter===key} onClick={()=>setTemplateFilter(key)}>{label}</button>)}</div>
          <div className="publishing-template-list">
            {['classic','creative'].filter(group=>templateFilter==='all' || templateFilter===group).map(group=><div key={group} className="publishing-template-group">
              <div className="publishing-template-group-title">{group==='classic'?'经典长图':'创意拼版'}{group==='creative' && <span>新增 6 款</span>}</div>
              {catalog.templates.filter(template=>Boolean(template.layout)===(group==='creative')).map((template) => (
              <button type="button" key={template.id} title={template.description} aria-label={template.name} className={`publishing-template ${template.layout ? "publishing-creative-template" : ""} ${options.template_id === template.id ? "is-selected" : ""}`} aria-pressed={options.template_id === template.id} disabled={busy} onClick={() => update({ template_id: template.id, accent: "" })}>
                <span className="publishing-template-preview">{examples[template.id] ? <img src={examples[template.id]} alt="" /> : <TemplateThumb template={template} />}</span>
                <span className="publishing-template-copy"><b>{template.name}</b><small>{template.format || template.description}</small></span>
                {options.template_id === template.id && <span className="publishing-check">✓</span>}
              </button>
            ))}</div>)}
          </div>
          {exampleError && <p className="muted publishing-inline-note">{exampleError}</p>}
        </aside>
        <main className="publishing-canvas">
          <div className="publishing-canvas-toolbar"><div><b>{theme.name}</b><span className="muted"> · {theme.format || '经典长图'}</span></div><span className="publishing-zoom-label">适配预览</span></div>
          <p className="publishing-template-description">{theme.description}{theme.layout && ' · 按从左到右、从上到下阅读'}</p>
          <div className="publishing-preview-frame">
            {preview ? (
              <div className="preview-interactive" onClick={previewClick}>
                <img ref={previewImgRef} src={preview} alt={`${theme.name}排版预览`} style={{ opacity: loading ? 0.52 : 1 }} />
                {editBox && editScene && editStory && (
                  <LongSceneOverlay
                    pid={pid} scene={editScene} story={editStory} box={editBox}
                    displayScale={displayScale} backdrop={theme.background}
                    onDone={applySceneEdit}
                    onCancel={() => setEditSceneId(null)}
                  />
                )}
                {applying && <p className="preview-applying">正在应用修改并刷新…</p>}
              </div>
            ) : project?.long_image_url ? <img src={fileUrl(project.long_image_url)} alt="已保存作品" /> : <div className="publishing-empty"><span>✦</span><b>完成分镜后显示作品</b><small>中间区域会实时展示真实排版效果</small></div>}
          </div>
        </main>
        <div className="publishing-divider" role="separator" aria-label="调整设置栏宽度" aria-orientation="vertical" tabIndex={0}
          aria-valuenow={inspectorWidth} aria-valuemin={260} aria-valuemax={520}
          onPointerDown={resizeInspector}
          onKeyDown={e => {if (["ArrowLeft","ArrowRight"].includes(e.key)) {e.preventDefault(); setInspectorWidth(w => Math.max(260,Math.min(520,w + (e.key === "ArrowLeft" ? 20 : -20))));}}} />
        <aside className="publishing-inspector" aria-label="标题与文字设置">
          <PageBackground options={options} theme={theme} busy={busy} onChange={update}/>
          <PageMargins options={options} busy={busy} onChange={update}/>
          <HeadingEditor scenes={project?.storyboard?.scenes || []} options={options} accent={options.accent || theme.accent} busy={busy} onChange={setOptions}/>
          <div className="publishing-inspector-section">
            <div className="publishing-inspector-title"><span>03</span><b>标题与字体</b></div>
            <label className="publishing-field">作品标题<input value={options.title || ""} placeholder={project?.title || "输入作品标题"} maxLength={300} disabled={busy} onChange={(e) => update({ title: e.target.value })} /></label>
            <label className="publishing-field">副标题<input value={options.subtitle || ""} maxLength={300} disabled={busy} onChange={(e) => update({ subtitle: e.target.value })} /></label>
            <div className="publishing-field"><span className="publishing-label">标题效果</span><div className="title-effect-grid">{TITLE_EFFECTS.map((effect) => <button type="button" key={effect.id} className={options.title_style === effect.id ? "is-selected" : ""} disabled={busy} onClick={() => update({ title_style: effect.id })}><TitleEffectSample effect={effect.id} options={options} localFonts={localFonts} /><small>{effect.name}</small></button>)}</div></div>
            <label className="publishing-field">标题字体<select value={options.title_font_id || ""} disabled={busy} onChange={(e) => update({ title_font_id: e.target.value || null })}><option value="">系统默认（微软雅黑）</option>{FONT_SPECS.map((spec) => <option key={spec.id} value={spec.id} disabled={!fontStatus[spec.id]?.loaded}>{spec.name}{fontStatus[spec.id]?.loaded ? " · 可用" : " · 待导入"}</option>)}</select></label>
            <label className="publishing-field">正文与章节字体<select value={options.body_font_id || ""} disabled={busy} onChange={(e) => update({ body_font_id: e.target.value || null })}><option value="">系统默认（微软雅黑）</option>{FONT_SPECS.map((spec) => <option key={spec.id} value={spec.id} disabled={!fontStatus[spec.id]?.loaded}>{spec.name}{fontStatus[spec.id]?.loaded ? " · 可用" : " · 待导入"}</option>)}</select></label>
            <details className="publishing-font-import"><summary>导入自定义字体<small>{fontBusy ? " · 导入中…" : ""}</small></summary>
              <p className="muted">选一个要替换的字体槽位，再上传 TTF / OTF / TTC，导入后标题与正文可直接选用。</p>
              {FONT_SPECS.map((spec) => <label key={spec.id} className="publishing-font-row"><span>{spec.name}</span><span className={fontStatus[spec.id]?.loaded ? "font-ready" : "font-pending"}>{fontStatus[spec.id]?.loaded ? "可用" : "待导入"}</span><input type="file" accept=".ttf,.otf,.ttc,font/ttf,font/otf,font/collection" disabled={busy || Boolean(fontBusy)} onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; handleFont(file, spec); }} /><button type="button" disabled={busy || Boolean(fontBusy)} onClick={(e) => e.currentTarget.parentElement?.querySelector("input")?.click()}>{fontBusy === spec.id ? "导入中" : "导入"}</button></label>)}
            </details>
            <label className="publishing-field">标题字号：{options.font_size || 58} px<input type="range" min="30" max="100" value={options.font_size || 58} disabled={busy} onChange={(e) => update({ font_size: Number(e.target.value) })} /></label>
            <label className="publishing-field">标题对齐<select value={options.align || "center"} disabled={busy} onChange={(e) => update({ align: e.target.value })}><option value="left">左对齐</option><option value="center">居中</option><option value="right">右对齐</option></select></label>
            <label className="publishing-field">主题色<input type="color" value={options.accent || theme.accent} disabled={busy} onChange={(e) => update({ accent: e.target.value })} /></label>
            <label className="publishing-upload-title">上传艺术字标题图片<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; handleTitleImage(file); }} /></label>
            {titleImage && <div className="publishing-title-image-preview"><img src={titleImage} alt="已上传的艺术字标题" /><span>{titleImagePersisted ? "标题图已上传，保存后替换文字标题" : "上传未完成，不能保存排版"}</span><button type="button" onClick={removeTitleImage}>移除</button></div>}
          </div>
          <div className="publishing-inspector-section">
            <div className="publishing-inspector-title"><span>04</span><b>留白与文字</b></div>
            {[['title_top','标题顶部留白',400,48],['title_bottom','标题区底部留白',300,32],['title_line_gap','标题行间距',100,18],['letter_spacing','文字字间距',20,0],['body_line_gap','正文行间距',80,14]].map(([key, label, max, fallback]) => <label className="publishing-field publishing-range-field" key={key}><span>{label}<b>{options[key] ?? fallback} px</b></span><input type="range" min="0" max={max} step="1" value={options[key] ?? fallback} disabled={busy} onChange={(e) => update({ [key]: Number(e.target.value) })} /></label>)}
            <label className="publishing-field">旁白对齐<select value={options.caption_align || "center"} disabled={busy} onChange={(e) => update({ caption_align: e.target.value })}><option value="left">居左</option><option value="center">居中</option><option value="right">居右</option></select></label>
            <label className="publishing-field publishing-range-field"><span>{columns > 1 ? '统一行间距' : '统一格间距'}<b>{options.gap ?? 60} px</b></span><input type="range" min="0" max="400" step="4" value={options.gap ?? 60} disabled={busy} onChange={(e) => update({ gap: Number(e.target.value), gaps: {} })} /></label>
            {sceneRows.length>1 && <details className="publishing-details"><summary>{columns>1 ? '单独调整每行之后的距离' : '单独调整两格之间的距离'}</summary>{sceneRows.slice(0,-1).map((row,index)=><label className="publishing-field" key={row[0].scene_id}>{columns>1 ? `第 ${index+1} 行之后` : `第 ${index+1} 格与第 ${index+2} 格`}<input type="number" min="0" max="400" value={Math.max(...row.map(scene=>options.gaps?.[scene.scene_id] ?? options.gap ?? 60))} disabled={busy} onChange={e=>update({gaps:{...options.gaps,...Object.fromEntries(row.map(scene=>[scene.scene_id,Math.max(0,Math.min(400,Number(e.target.value)))]))}})}/></label>)}</details>}
          </div>
          <div className="publishing-inspector-section publishing-footer-editor">
            <label className="publishing-field">结尾提示<textarea value={options.footer || ""} maxLength={300} rows={2} disabled={busy} onChange={(e) => update({ footer: e.target.value })} /></label>
            <FooterEditor pid={pid} project={project} busy={busy} printWidthCm={options.print_width_cm} blocks={options.footer_blocks || []} onBusyChange={setFooterBusy}
              onChange={next=>setOptions(previous=>({...previous,footer_blocks:typeof next==="function"?next(previous.footer_blocks || []):next}))}/>
            <button className="primary publishing-save" disabled={busy || footerBusy || !ready || !titleImagePersisted} onClick={() => onSave(options)}>保存排版并生成图片 <span>→</span></button>
            {!ready && <p className="muted">各格完成合成后即可生成排版图片。</p>}{error && <p className="error" role="alert">{error}</p>}
          </div>
        </aside>
      </div>
    </section>
  );
}
