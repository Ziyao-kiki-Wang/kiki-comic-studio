import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, pollTask, readImage } from "../lib/api.js";
import ProjectPreview from "./ProjectPreview.jsx";
import { useWorkspaceGuard } from "./WorkspaceShell.jsx";

export default function ProjectList() {
  const navigate = useNavigate();
  const setGuard = useWorkspaceGuard();
  const [styles, setStyles] = useState([]);
  const [topic, setTopic] = useState("");
  const [sceneCount, setSceneCount] = useState(5);
  const [styleId, setStyleId] = useState("commercial_comic");
  const [backgroundMode, setBackgroundMode] = useState("scene");
  const [characters, setCharacters] = useState([]);
  const [creating, setCreating] = useState(false);
  const [task, setTask] = useState(null);
  const [error, setError] = useState("");
  const stopRef = useRef(null);
  useEffect(() => {
    setGuard(Boolean(topic.trim() || characters.length || creating));
    return () => setGuard(false);
  }, [setGuard, topic, characters.length, creating]);

  const watchCreation = (project_id, task_id) => {
    stopRef.current?.();
    setCreating(true);
    stopRef.current = pollTask(task_id, (t) => {
      setTask(t);
      if (t.status === "done") {
        setCreating(false);
        setTask(null);
        navigate(`/project/${project_id}`);
      } else if (t.status === "failed") {
        setCreating(false);
        setError(`创建失败：${t.error || "未知错误"}`);
        window.dispatchEvent(new Event("comic-projects-changed"));
      }
    });
  };

  useEffect(() => {
    api
      .listStyles()
      .then((d) => setStyles(d.styles || []))
      .catch((e) => setError("加载画风列表失败：" + e.message));
    return () => {
      if (stopRef.current) stopRef.current();
    };
  }, []);

  const onCreate = async (e) => {
    e.preventDefault();
    if (!topic.trim() || creating) return;
    setError("");
    setTask(null);
    setCreating(true);
    try {
      const { project_id, task_id } = await api.createProject(
        topic.trim(),
        sceneCount,
        styleId,
        { background_mode: backgroundMode, characters },
      );
      watchCreation(project_id, task_id);
      window.dispatchEvent(new Event("comic-projects-changed"));
    } catch (err) {
      setCreating(false);
      setError("创建失败：" + err.message);
    }
  };

  const selectedStyle = styles.find((s) => s.style_id === styleId);

  return (
    <div className="page creation-page">
      <header className="page-header">
        <p className="creation-eyebrow">从一个想法，开始一则漫画</p>
        <h1>今天，想讲一个什么故事？</h1>
        <p className="muted">选择格数与画风，右侧就能看到示例。已有作品可从左侧项目列表继续编辑。</p>
      </header>

      <div className="creation-layout">
      <section className="card creation-form-card">
        <h2>新建项目</h2>
        <form onSubmit={onCreate} className="create-form">
          <label>
            主题
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="例如：银行防诈骗宣传，提醒中老年客户警惕陌生来电"
              disabled={creating}
            />
          </label>
          <div className="form-row">
            <label>
              格数
              <select
                aria-label="格数"
                value={sceneCount}
                onChange={(e) => setSceneCount(Number(e.target.value))}
                disabled={creating}
              >
                {[1, 2, 3, 4, 5, 6, 8, 10, 12].map((n) => (
                  <option key={n} value={n}>
                    {n} 格
                  </option>
                ))}
              </select>
            </label>
            <label className="grow">
              风格
              <select
                aria-label="风格"
                value={styleId}
                onChange={(e) => setStyleId(e.target.value)}
                disabled={creating}
              >
                {styles.map((s) => (
                  <option key={s.style_id} value={s.style_id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selectedStyle && (
            <p className="muted style-hint">
              {selectedStyle.look}；适合：{selectedStyle.suitable_for}
            </p>
          )}
          <label>
            场景背景
            <select
              value={backgroundMode}
              onChange={(e) => setBackgroundMode(e.target.value)}
              disabled={creating}
            >
              <option value="scene">完整场景：人物与环境背景</option>
              <option value="transparent">
                透明主体：保留整组人物和必要道具
              </option>
            </select>
          </label>
          <div className="section-head">
            <h3>提供主人公形象（可选）</h3>
            <span className="muted">最多 6 位</span>
          </div>
          <p className="muted">
            上传现成漫画或 IP 形象，尽量保留外观与服装。未提供的配角由 AI
            创建，故事完成后可确认全部角色。
          </p>
          <div className="upload-grid">
            {characters.map((c, i) => (
              <div className="upload-character" key={i}>
                <img
                  className="checkerboard"
                  src={c.image_data}
                  alt={`角色 ${i + 1} 参考图`}
                />
                <label>
                  角色名称
                  <input
                    required
                    maxLength={80}
                    value={c.name}
                    disabled={creating}
                    onChange={(e) =>
                      setCharacters((list) =>
                        list.map((it, j) =>
                          j === i ? { ...it, name: e.target.value } : it,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  故事身份
                  <input
                    maxLength={150}
                    value={c.role}
                    disabled={creating}
                    onChange={(e) =>
                      setCharacters((list) =>
                        list.map((it, j) =>
                          j === i ? { ...it, role: e.target.value } : it,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  保留特征或补充说明
                  <textarea
                    value={c.description}
                    maxLength={1200}
                    disabled={creating}
                    onChange={(e) =>
                      setCharacters((list) =>
                        list.map((it, j) =>
                          j === i ? { ...it, description: e.target.value } : it,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  disabled={creating}
                  onClick={() =>
                    setCharacters((list) => list.filter((_, j) => j !== i))
                  }
                >
                  移除角色
                </button>
              </div>
            ))}
          </div>
          <label className="upload-button">
            添加人物参考图
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={creating || characters.length >= 6}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                try {
                  const image_data = await readImage(file);
                  setCharacters((list) => [
                    ...list,
                    {
                      name: `角色${list.length + 1}`,
                      role: list.length ? "配角" : "主人公",
                      description: "",
                      image_data,
                    },
                  ]);
                  setError("");
                } catch (error) {
                  setError(error.message);
                }
              }}
            />
          </label>
          <button
            type="submit"
            className="primary"
            disabled={creating || !topic.trim()}
          >
            {creating ? "正在创建（AI 写故事中）…" : task?.status === "failed" ? "重新创建故事" : "创建故事并确认角色"}
          </button>
        </form>
        {task && (
          <div className="task-box" aria-live="polite">
            <div>
              任务状态：<b>{({pending: "排队中", running: "正在生成", done: "已完成", failed: "生成失败"})[task.status] || task.status}</b>
            </div>
            {task.polling_error && <p role="alert" className="error">{task.polling_error}</p>}
            {task.status === "failed" && <div role="alert" className="error">
              <p>{task.error || "生成失败，请查看下方日志。"}</p>
              <button type="button" disabled={creating} onClick={onCreate}>重试生成故事</button>
              <p className="muted">将按上方填写的内容重新创建故事，已上传的人物参考图会继续使用。</p>
            </div>}
            <pre className="task-log">
              {(task.logs || []).slice(-8).join("\n")}
            </pre>
          </div>
        )}
        {error && <p className="error">{error}</p>}
      </section>

      <ProjectPreview styles={styles} styleId={styleId} sceneCount={sceneCount} onStyleChange={setStyleId} disabled={creating}/>
      </div>
    </div>
  );
}
