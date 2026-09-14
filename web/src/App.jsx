import { Routes, Route } from 'react-router-dom'
import ProjectList from './pages/ProjectList.jsx'
import ProjectWorkbench from './pages/ProjectWorkbench.jsx'
import SceneEditor from './pages/SceneEditor.jsx'
import WorkspaceShell from './pages/WorkspaceShell.jsx'

export default function App() {
  return (
    <div className="app">
      <Routes>
        <Route element={<WorkspaceShell />}>
          <Route path="/" element={<ProjectList />} />
          <Route path="/project/:pid" element={<ProjectWorkbench />} />
          <Route path="/project/:pid/scene/:sid/edit" element={<SceneEditor />} />
        </Route>
      </Routes>
    </div>
  )
}
