import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, fileUrl, pollTask, readImage } from "../lib/api.js";
import LongImageDesigner from "./LongImageDesigner.jsx";
import DecorationEditor from "./DecorationEditor.jsx";
import { useWorkspaceGuard } from "./WorkspaceShell.jsx";

export default function ProjectWorkbench() {
  const { pid } = useParams();
  const [searchParams] = useSearchParams();
  const step = searchParams.get('step') || 'story';
  const setGuard = useWorkspaceGuard();
  const [project, setProject] = useState(null),
    [sb, setSb] = useState(null);
  const [task, setTask] = useState(null),
    [pending, setPending] = useState(false),
    [dirty, setDirty] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [exporting, setExporting] = useState(false);
  const stopRef = useRef(null);
  const busy =
    pending || task?.status === "pending" || task?.status === "running";
  useEffect(() => { setGuard(dirty); return () => setGuard(false); }, [dirty, setGuard]);
  async function load() {
    const d = await api.getProject(pid);
    setProject(d);
    setSb(d.storyboard);
    setDirty(false);
    return d;
  }
  function watch(id) {
    stopRef.current?.();
    stopRef.current = pollTask(id, (t) => {
      setTask(t);
      if (t.status === "done") {
        setNotice("任务完成");
        load().catch((e) => setError(e.message));
      }
      if (t.status === "failed") setError(t.error || "任务失败，请查看日志");
    });
  }
  useEffect(() => {
    let live = true;
    load()
      .then((d) => {
        if (live && d.active_task) {
          setTask(d.active_task);
          watch(d.active_task.task_id);
        }
      })
      .catch((e) => setError(e.message));
    return () => {
      live = false;
      stopRef.current?.();
    };
  }, [pid]);
  async function action(body, label) {
    if (busy) return;
    setPending(true);
    setError("");
    setNotice("");
    try {
      const result = await api.generate(pid, body);
      setTask({ status: "pending", logs: [], detail: body });
      watch(result.task_id);
      setNotice(`${label}已开始`);
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }
  async function save() {
    setPending(true);
    setError("");
    try {
      await api.saveStoryboard(pid, storyDraft());
      await load();
      setNotice("故事已保存。点击设置下方的「生成漫画」即可更新作品。");
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }
  function storyDraft() {
    // screen_enabled 不再逐格预勾选：按故事内容自动判断，屏幕特写在画面精修中添加
    return { ...sb, scenes: sb.scenes.map(({ retained_props, screen_enabled, ...scene }) => ({ ...scene, background_mode: null })) };
  }
  async function saveAndGenerate() {
    if (busy || sb.characters_confirmed === false) return;
    setPending(true);
    setError("");
    setNotice("");
    let saved = false;
    try {
      const draft = storyDraft();
      await api.saveStoryboard(pid, draft);
      setSb(draft);
      setDirty(false);
      saved = true;
      const result = await api.generate(pid, { action: "run_all" });
      setTask({ status: "pending", logs: [], detail: { action: "run_all" } });
      watch(result.task_id);
      setNotice("故事已保存，正在生成漫画。");
    } catch (e) {
      setError(e.message);
      if (saved) setNotice("故事已保存，生成未能启动。可以点击下方按钮重试。");
    } finally {
      setPending(false);
    }
  }
  async function saveLong(options) {
    if (busy || dirty) return;
    setPending(true);
    setError("");
    setNotice("");
    try {
      await api.saveStoryboard(pid, { ...sb, long_layout: options });
      const { task_id } = await api.generate(pid, { action: "compose_long" });
      setTask({ status: "pending", logs: [] });
      watch(task_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }
  async function replaceCharacter(c, file) {
    if (!file) return;
    setPending(true);
    setError("");
    try {
      await api.replaceReference(pid, c.character_id, {
        name: c.name,
        role: c.role || "",
        description: c.description || "",
        image_data: await readImage(file),
      });
      await load();
      setNotice("形象已替换，请重新确认角色；相关场景已标记为需要更新。");
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }
  function updateScene(index, patch) {
    setSb((prev) => ({
      ...prev,
      scenes: prev.scenes.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    }));
    setDirty(true);
  }
  if (!project || !sb)
    return (
      <div className="page">
        <Link to="/">← 项目列表</Link>
        <p className={error ? "error" : "muted"}>{error || "加载中…"}</p>
      </div>
    );
  const confirmed = sb.characters_confirmed !== false;
  const allReferences = sb.characters.every(
    (c) => project.character_urls[c.character_id],
  );
  const charNames = Object.fromEntries(
    sb.characters.map((c) => [c.character_id, c.name]),
  );
  return (
    <div className="page">
      <Link to="/" className="back-link">
        ← 返回项目列表
      </Link>
      <header className="page-header workbench-header">
        <div>
          <h1>{project.title || pid}</h1>
          <p className="muted">
            {sb.scenes.length} 格 · {project.approved_count} 格已通过 ·{" "}
            {confirmed ? "角色已确认" : "等待确认角色"}
          </p>
        </div>
        <div className="header-actions">
          <button
            disabled={busy || dirty}
            onClick={() => action({ action: "recompose" }, "重新合成")}
          >
            重新合成
          </button>
          <button
            disabled={
              busy ||
              dirty ||
              exporting ||
              !project.scenes.every((s) => s.composite_url && !s.render_stale)
            }
            onClick={async () => {
              setExporting(true);
              setError("");
              try {
                await (await import("../lib/pptx.js")).exportPptx(pid);
              } catch (e) {
                setError(e.message);
              } finally {
                setExporting(false);
              }
            }}
          >
            {exporting ? "导出中…" : "导出 PPTX"}
          </button>
          {project.long_image_url && (
            <a
              className="button"
              href={fileUrl(project.long_image_url)}
              target="_blank"
              rel="noreferrer"
            >
              {project.long_image_stale ? '查看上次成品' : '查看 / 下载成品'}
            </a>
          )}
        </div>
      </header>
      {project.long_image_stale && <p className="stale-badge">成品尚未包含最新修改，请保存当前排版或点击「重新合成」后下载。</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {task && (
        <details
          className="card task-box"
          open={busy || task.status === "failed"}
        >
          <summary>
            任务：{task.status}
            {task.detail?.action ? ` · ${task.detail.action}` : ""}
          </summary>
          <pre className="task-log">
            {(task.logs || []).join("\n") || "正在等待执行…"}
          </pre>
        </details>
      )}

      <div hidden={step !== 'story'}>
      <div className="studio-intro"><div><h2>把故事变成一组画面</h2><p className="muted">确认角色、设置故事与背景后生成；下方集中查看生成结果。</p></div><span className="studio-count">{sb.scenes.length} 个分镜</span></div>
      <div className="story-setup-grid">
      <details className="card workspace-fold" open={!confirmed}>
      <summary>角色与参考形象 · {confirmed ? '已确认' : '待确认'}</summary>
      <section className="card">
        <div className="section-head">
          <h2>1. 确认角色形象</h2>
          <span className={confirmed ? "approved-badge" : "stale-badge"}>
            {confirmed ? "已确认" : "待确认"}
          </span>
        </div>
        <p className="muted">
          上传形象直接作为固定参考。可以替换任意角色，AI 只补齐未提供的形象。
        </p>
        <div className="character-library">
          {sb.characters.map((c) => (
            <article key={c.character_id} className="character-reference">
              {project.character_urls[c.character_id] ? (
                <a
                  href={fileUrl(project.character_urls[c.character_id])}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    className="checkerboard"
                    src={fileUrl(project.character_urls[c.character_id])}
                    alt={`${c.name}参考图`}
                  />
                </a>
              ) : (
                <div className="placeholder">等待生成形象</div>
              )}
              <b>{c.name}</b>
              {project.character_urls[c.character_id] && (
                <div className="scene-actions asset-downloads">
                  <a
                    className="button"
                    href={
                      fileUrl(project.character_urls[c.character_id]) +
                      "&download=true"
                    }
                  >
                    下载角色参考图
                  </a>
                </div>
              )}
              <p className="muted">
                {c.role} ·{" "}
                {c.reference_source === "upload" ? "上传形象" : "AI 创建"}
              </p>
              <label className="upload-button">
                替换参考图
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  disabled={busy || dirty}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    replaceCharacter(c, file);
                  }}
                />
              </label>
              {c.reference_source !== "upload" &&
                project.character_urls[c.character_id] && (
                  <button
                    disabled={busy || dirty}
                    onClick={() => {
                      if (
                        window.confirm("重新生成此角色会调用生图服务，继续吗？")
                      )
                        action(
                          {
                            action: "regen_character",
                            character_id: c.character_id,
                          },
                          "重画角色",
                        );
                    }}
                  >
                    重新设计形象
                  </button>
                )}
              {project.character_rgba_urls?.[c.character_id] ? (
                <a
                  className="button"
                  href={
                    fileUrl(project.character_rgba_urls[c.character_id]) +
                    "&download=true"
                  }
                >
                  透明参考图
                </a>
              ) : (
                <button
                  disabled={
                    busy || dirty || !project.character_urls[c.character_id]
                  }
                  onClick={() =>
                    action(
                      {
                        action: "cutout_character",
                        character_id: c.character_id,
                      },
                      "生成透明参考图",
                    )
                  }
                >
                  生成透明参考图
                </button>
              )}
            </article>
          ))}
        </div>
        <div className="header-actions">
          {!allReferences && (
            <button
              disabled={busy || dirty}
              onClick={() =>
                action({ action: "prepare_characters" }, "补齐角色与道具")
              }
            >
              生成缺失的角色形象
            </button>
          )}
          <button
            className="primary"
            disabled={busy || dirty || !allReferences || confirmed}
            onClick={async () => {
              setPending(true);
              try {
                await api.confirmCharacters(pid);
                await load();
                setNotice("角色已确认，可以开始生成场景。");
              } catch (e) {
                setError(e.message);
              } finally {
                setPending(false);
              }
            }}
          >
            确认这些角色
          </button>
        </div>
      </section>
      </details>
      <details className="card workspace-fold" open>
      <summary>故事脚本与背景设置{dirty ? ' · 有未保存修改' : ''}</summary>
      <section className="card">
        <div className="section-head">
          <h2>2. 故事与背景模式</h2>
        </div>
        <div className="story-background-setting">
        <div><label>
          默认背景模式
          <select
            value={sb.background_mode || "scene"}
            aria-label="默认背景模式"
            disabled={busy}
            onChange={(e) => {
              setSb({ ...sb, background_mode: e.target.value, scenes: sb.scenes.map((scene) => ({ ...scene, background_mode: null })) });
              setDirty(true);
            }}
          >
            <option value="scene">完整场景</option>
            <option value="transparent">透明主体：整组人物与必要道具</option>
          </select>
        </label>
        <p className="muted">整部漫画统一使用这里选择的背景模式。</p>
        <p className="muted">{sb.background_mode === "transparent" ? "保留人物和情节需要的道具，周围透明，方便在排版时搭配文字与气泡。" : "保留人物和周围的环境，适合表现完整的故事场景。"}</p></div>
        <figure className="story-background-preview">
          <img className={sb.background_mode === "transparent" ? "checkerboard" : ""} src={sb.background_mode === "transparent" ? "/style-previews/girl/transparent-subject.png" : "/style-previews/girl/pixar_3d.png"} alt={sb.background_mode === "transparent" ? "小女孩透明主体示意" : "小女孩完整场景示意"} />
          <figcaption>{sb.background_mode === "transparent" ? "透明主体 · 格子表示透明区域" : "完整场景 · 保留周围环境"}<span>背景效果示意，实际画面按你的故事生成</span></figcaption>
        </figure>
        </div>
        <p className="muted">故事中提到手机或屏幕时，会随画面自然绘制（默认拿在手中或融入场景）。生成后进入「画面精修」，可为这一格单独生成手机屏幕特写。</p>
        {dirty && (
          <p className="stale-badge">
            修改后直接点击下方「生成漫画」，会自动保存并开始生成。
          </p>
        )}
        {sb.scenes.map((s, i) => (
          <div className="scene-editor" key={s.scene_id}>
            <h3>
              第 {i + 1} 格 · {s.location}
              {s.stale && (
                <span className="stale-badge">角色已变化，建议重跑</span>
              )}
            </h3>
            {(s.dialogues || []).map((d, j) => (
              <label className="dialogue-row" key={j}>
                <span className="speaker">
                  {charNames[d.speaker] || d.speaker}
                </span>
                <input
                  value={d.text}
                  maxLength={500}
                  disabled={busy}
                  onChange={(e) =>
                    updateScene(i, {
                      dialogues: s.dialogues.map((v, k) =>
                        k === j ? { ...v, text: e.target.value } : v,
                      ),
                    })
                  }
                />
              </label>
            ))}
            <label className="dialogue-row">
              <span className="speaker">旁白</span>
              <textarea
                rows={2}
                maxLength={1000}
                value={s.caption || ""}
                disabled={busy}
                onChange={(e) => updateScene(i, { caption: e.target.value })}
              />
            </label>
            <details>
              <summary>分镜小标题</summary>
              <label>
                小标题
                <input
                  value={s.heading || ""}
                  maxLength={100}
                  disabled={busy}
                  onChange={(e) => updateScene(i, { heading: e.target.value })}
                />
              </label>
              <p className="muted">显示在作品排版的分镜上方，字号和装饰样式在「作品排版」中调整。</p>
              {sb.long_layout?.template_id === "qa" && <><label>
                问答科普 · 本格问题
                <input
                  value={s.question || ""}
                  maxLength={200}
                  disabled={busy}
                  onChange={(e) => updateScene(i, { question: e.target.value })}
                />
              </label>
              <p className="muted">当前使用「问答科普」排版：问题放在分镜上方，旁白作为解答。切换其他模板后，仍使用普通小标题。</p></>}
            </details>
          </div>
        ))}
        <div className="story-generate-actions">
          <div><button className="primary" disabled={busy || !confirmed} onClick={saveAndGenerate}>{busy ? "生成中…" : task?.status === "failed" ? "重试生成漫画" : "生成漫画"}</button>
          <button disabled={busy || !dirty} onClick={save}>仅保存故事</button></div>
          <p className="muted">{!confirmed ? "请先在上方确认角色形象。" : "点击后自动保存设置，生成缺少或需要更新的画面，并更新文字和排版。"}</p>
          {busy && <p role="status">{task?.logs?.at(-1) || "正在保存设置并准备生成…"}</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </div>
      </section>
      </details>
      </div>
      <section>
        <h2>分镜预览</h2>
        <p className="muted">集中查看整部漫画的生成结果，标记满意的画面；AI 改图、本格参考、重跑和版本切换已统一到「画面精修」。</p>
        <div className="scene-grid">
          {project.scenes.map((s, i) => {
            const active = Number(
              /_v(\d+)\.png$/.exec(s.layout?.active_version || "")?.[1] || 0,
            );
            return (
              <article className="card scene-card" key={s.scene_id}>
                <div className="scene-card-head">
                  <b>第 {i + 1} 格</b>
                  <span className="version-badge">v{active}</span>
                  <span className="muted">
                    {s.background_mode === "transparent"
                      ? "透明主体"
                      : "完整场景"}
                  </span>
                  {s.status === "approved" && (
                    <span className="approved-badge">已通过</span>
                  )}
                </div>
                <p className="muted">{sb.scenes[i]?.heading || sb.scenes[i]?.location || '待完善画面'}</p>
                {s.composite_url ? (
                  <img
                    className="scene-img checkerboard"
                    src={fileUrl(s.composite_url)}
                    alt={`第${i + 1}格`}
                  />
                ) : (
                  <div className="placeholder">等待生成</div>
                )}
                {s.reference_stale && <p className="stale-badge">本格参考已更新，可在画面精修中改图或重跑。</p>}
                <div className="scene-actions">
                  <Link
                    className={`button primary ${busy || dirty ? "disabled-link" : ""}`}
                    to={`/project/${pid}/scene/${s.scene_id}/edit`}
                  >
                    编辑这一格
                  </Link>
                  <button
                    disabled={busy || dirty || !s.composite_url}
                    onClick={async () => {
                      try {
                        await api.setSceneStatus(
                          pid,
                          s.scene_id,
                          s.status === "approved" ? "draft" : "approved",
                        );
                        await load();
                      } catch (e) {
                        setError(e.message);
                      }
                    }}
                  >
                    {s.status === "approved" ? "取消通过" : "标记通过"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>
      </div>
      {step === 'refine' && <section>
        <div className="studio-intro"><div><h2>选择要精修的画面</h2><p className="muted">编辑气泡文字、字体和原样贴图，每一格独立保存。</p></div></div>
        <div className="refine-grid">{project.scenes.map((s,i) => <Link key={s.scene_id} className="refine-card" to={`/project/${pid}/scene/${s.scene_id}/edit`} onClick={e => { if (dirty && !window.confirm('故事修改尚未保存，确定离开吗？')) e.preventDefault(); }}>
          {s.composite_url ? <img src={fileUrl(s.composite_url)} alt={`第 ${i+1} 格预览`} /> : <div className="placeholder">等待生成画面</div>}
          <div><b>第 {i+1} 格 · {sb.scenes[i]?.heading || sb.scenes[i]?.location}</b><p className="muted">{s.scene_id === sessionStorage.getItem(`comic-scene-${pid}`) ? '上次编辑 · 继续精修 →' : '进入画面精修 →'}</p></div>
        </Link>)}</div>
      </section>}
      {step === 'layout' && <LongImageDesigner
        pid={pid}
        project={project}
        busy={busy || dirty}
        onSave={saveLong}
      />}
      {step === 'stickers' && <DecorationEditor pid={pid} project={project} busy={busy || dirty} onSave={saveLong} />}
      {step === 'story' && (sb.props || []).length > 0 && (
        <details className="card">
          <summary>道具参考素材</summary>
          <div className="asset-grid">
            {sb.props.map((p) => (
              <div key={p.prop_id}>
                {project.prop_urls[p.prop_id] && (
                  <img
                    className="scene-img"
                    src={fileUrl(project.prop_urls[p.prop_id])}
                    alt={p.name}
                  />
                )}
                <p>{p.name}</p>
                {project.prop_urls[p.prop_id] && (
                  <a
                    className="button"
                    href={
                      fileUrl(project.prop_urls[p.prop_id]) + "&download=true"
                    }
                  >
                    下载道具参考图
                  </a>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
