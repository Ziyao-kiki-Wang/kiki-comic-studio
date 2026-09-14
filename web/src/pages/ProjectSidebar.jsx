import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../lib/api.js";

export default function ProjectSidebar({ pid, open, onClose, onNavigate }) {
  const [projects, setProjects] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const location = useLocation();
  const load = useCallback(async () => {
    try {
      const list = await api.listProjects();
      setProjects(list.sort((a,b)=>(b.updated_at || 0)-(a.updated_at || 0)));
      setError("");
    } catch(e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load, location.pathname]);
  useEffect(() => {
    window.addEventListener("comic-projects-changed",load);
    window.addEventListener("focus",load);
    return () => {
      window.removeEventListener("comic-projects-changed",load);
      window.removeEventListener("focus",load);
    };
  }, [load]);
  function navigate(e) { onNavigate(e); if (!e.defaultPrevented) onClose(); }
  const filtered = projects.filter(p=>(p.title || p.project_id).toLowerCase().includes(query.trim().toLowerCase()));
  return <aside id="project-sidebar" className={`project-sidebar ${open ? 'is-open' : ''}`} aria-label="项目列表">
    <Link className="studio-brand" to="/" onClick={navigate}><span>漫</span><div><b>漫画工坊</b><small>让每个故事，都有画面</small></div></Link>
    <Link className={`project-new ${!pid ? 'active' : ''}`} to="/" onClick={navigate}>＋ 新建漫画项目</Link>
    <div className="project-sidebar-heading"><b>我的项目</b><span>{projects.length}</span></div>
    <input className="project-search" aria-label="搜索项目" type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索项目名称"/>
    {error && <div className="project-list-error" role="alert">项目列表加载失败<button type="button" onClick={load}>重试</button></div>}
    <nav className="project-sidebar-list" aria-label="切换漫画项目">
      {loading && <p className="muted">正在加载项目…</p>}
      {!loading && !error && !filtered.length && <p className="muted">{query ? '没有匹配的项目' : '还没有项目，从一个故事开始吧。'}</p>}
      {filtered.map(p=><Link key={p.project_id} to={`/project/${p.project_id}`} onClick={navigate} className={`project-sidebar-item ${pid===p.project_id ? 'active' : ''}`} aria-current={pid===p.project_id ? 'page' : undefined}>
        <b>{p.title || p.project_id}</b>
        <span>{p.scene_count} 格<span>·</span>{p.updated_at ? new Date(p.updated_at*1000).toLocaleDateString('zh-CN') : '新项目'}</span>
        {p.status==='approved' && <small>✓ 已完成</small>}
        {p.stale_scenes?.length>0 && <small>有 {p.stale_scenes.length} 格待更新</small>}
      </Link>)}
    </nav>
    <div className="project-sidebar-foot">故事 · 绘画 · 排版 · 出版</div>
  </aside>;
}
