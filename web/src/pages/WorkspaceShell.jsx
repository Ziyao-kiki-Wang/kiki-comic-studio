import { createContext, useContext, useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useMatch } from 'react-router-dom';
import ProjectSidebar from './ProjectSidebar.jsx';
import './workspace.css';

const WorkspaceContext = createContext(() => {});
export const useWorkspaceGuard = () => useContext(WorkspaceContext);
const steps = [
  ['story', '分镜制作', '▦', '故事与画面'],
  ['refine', '画面精修', '◇', '气泡与素材'],
  ['layout', '作品排版', '▤', '长图与创意拼版'],
  ['stickers', '贴纸装饰', '✦', '装饰与导出'],
];

export default function WorkspaceShell() {
  const pid = useMatch('/project/:pid/*')?.params.pid;
  const sid = useMatch('/project/:pid/scene/:sid/edit')?.params.sid;
  const location = useLocation();
  const [guard, setGuard] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(false);
  const active = sid ? 'refine' : (new URLSearchParams(location.search).get('step') || 'story');
  useEffect(() => { if (sid) sessionStorage.setItem(`comic-scene-${pid}`, sid); }, [pid, sid]);
  useEffect(() => { setProjectsOpen(false); }, [location.pathname, location.search]);
  useEffect(() => {
    if (!projectsOpen) return;
    const close = e => { if (e.key === 'Escape') setProjectsOpen(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [projectsOpen]);
  useEffect(() => {
    const leave = e => { if (guard) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', leave);
    return () => window.removeEventListener('beforeunload', leave);
  }, [guard]);
  const confirmLeave = e => {
    if (guard && !window.confirm('有未保存的修改，离开会丢失这些修改。确定离开吗？')) e.preventDefault();
  };
  const navigateStep = e => {
    confirmLeave(e);
    if (!e.defaultPrevented) setProjectsOpen(false);
  };
  return <WorkspaceContext.Provider value={setGuard}>
    <div className="workspace-shell">
      {!pid ? <ProjectSidebar open={projectsOpen} onClose={()=>setProjectsOpen(false)} onNavigate={confirmLeave}/> :
      <aside id="creation-sidebar" className={`project-sidebar creation-sidebar ${projectsOpen ? 'is-open' : ''}`} aria-label="创作导航">
        <Link className="studio-brand" to="/" onClick={navigateStep}><span>漫</span><div><b>漫画工坊</b><small>把灵感画成故事</small></div></Link>
        <Link className="workspace-return" to="/" onClick={navigateStep}>← 返回项目列表</Link>
        <div className="workspace-nav-heading">创作小站 <span aria-hidden="true">✦</span></div>
        <nav className="workspace-steps" aria-label="创作步骤">
        {steps.map(([id, label, icon, hint]) => <Link key={id}
          to={`/project/${encodeURIComponent(pid)}?step=${id}`}
          className={`workspace-step workspace-step-${id} ${active === id ? 'active' : ''}`}
          aria-current={active === id ? 'step' : undefined} onClick={navigateStep}>
          <span className="workspace-icon" aria-hidden="true">{icon}</span>
          <span className="workspace-step-copy"><b>{label}</b><small>{hint}</small></span>
        </Link>)}
        </nav>
        <div className="project-sidebar-foot">一步一步，让故事成形</div>
      </aside>}
      {projectsOpen && <button className="projects-backdrop" aria-label={pid ? '收起创作导航' : '收起项目列表'} onClick={()=>setProjectsOpen(false)}/>}
      <main className="workspace-main">
        <div className="workspace-breadcrumb"><button className="projects-toggle" aria-controls={pid ? 'creation-sidebar' : 'project-sidebar'} aria-expanded={projectsOpen} onClick={()=>setProjectsOpen(!projectsOpen)}>{pid ? '☰ 创作步骤' : '☰ 项目'}</button><span>漫画工坊</span><span>/</span><strong>{pid ? steps.find(s => s[0] === active)?.[1] || '分镜制作' : '新建项目'}</strong><span className="workspace-save-hint">{guard ? '有未保存的修改' : '从故事到作品，在这里完成'}</span></div>
        <Outlet key={pid || 'new-project'} />
      </main>
    </div>
  </WorkspaceContext.Provider>;
}
