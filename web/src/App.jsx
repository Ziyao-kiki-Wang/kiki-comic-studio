import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import ProjectList from './pages/ProjectList.jsx'
import ProjectWorkbench from './pages/ProjectWorkbench.jsx'
import SceneEditor from './pages/SceneEditor.jsx'
import WorkspaceShell from './pages/WorkspaceShell.jsx'
import Login from './pages/auth/Login.jsx'
import Register from './pages/auth/Register.jsx'
import Profile from './pages/auth/Profile.jsx'
import { isLoggedIn } from './lib/auth'

// 路由守卫：未登录访问工作台 → 跳登录页，带上回跳目标
function RequireAuth({ children }) {
  const location = useLocation()
  if (!isLoggedIn()) {
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />
  }
  return children
}

export default function App() {
  return (
    <div className="app">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<WorkspaceShell />}>
          <Route path="/" element={<RequireAuth><ProjectList /></RequireAuth>} />
          <Route path="/project/:pid" element={<RequireAuth><ProjectWorkbench /></RequireAuth>} />
          <Route path="/project/:pid/scene/:sid/edit" element={<RequireAuth><SceneEditor /></RequireAuth>} />
          <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
        </Route>
      </Routes>
    </div>
  )
}
