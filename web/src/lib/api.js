// 后端地址：开发时直连 8000 端口（后端 CORS 已全开）
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

import { getToken, clearLoginState } from "./auth";

class UnauthorizedError extends Error {
  constructor(msg) {
    super(msg || "登录已过期");
    this.unauthorized = true;
  }
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401) {
    // 全局 401：清登录态并跳登录页（登录/注册页自身除外，避免死循环）
    clearLoginState();
    if (!location.pathname.startsWith("/login") && !location.pathname.startsWith("/register")) {
      location.href = "/login";
    }
    throw new UnauthorizedError();
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      const d = data.detail;
      if (typeof d === "string") detail = d;
      else if (d && d.message) detail = d.message;  // {code,message} 形式
      else if (d) detail = JSON.stringify(d);
    } catch {
      /* 忽略解析失败 */
    }
    const err = new Error(detail);
    err.status = res.status;
    if (res.status === 402) err.insufficientPoints = true;
    throw err;
  }
  return res.json();
}

export function fileUrl(path) {
  // 后端返回的 /api/files/... 相对路径补全成绝对地址。
  // <img>/<a> 带不了 Authorization header，所以拼 ?token= query（后端 files.py 同时认两者）
  if (!path) return null;
  const token = getToken();
  const sep = path.includes("?") ? "&" : "?";
  return API_BASE + path + (token ? `${sep}token=${encodeURIComponent(token)}` : "");
}

export const api = {
  listProjects: () => request("/api/projects"),
  createProject: (topic, scene_count, style_id, options = {}) =>
    request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, scene_count, style_id, ...options }),
    }),
  getProject: (pid) => request(`/api/projects/${encodeURIComponent(pid)}`),
  saveStoryboard: (pid, storyboard) =>
    request(`/api/projects/${encodeURIComponent(pid)}/storyboard`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(storyboard),
    }),
  saveLayout: (pid, sceneId, layout) =>
    request(
      `/api/projects/${encodeURIComponent(pid)}/scenes/${encodeURIComponent(sceneId)}/layout`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(layout),
      },
    ),
  setSceneStatus: (pid, sceneId, status) =>
    request(
      `/api/projects/${encodeURIComponent(pid)}/scenes/${encodeURIComponent(sceneId)}/status`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      },
    ),
  generate: (pid, body) =>
    request(`/api/projects/${encodeURIComponent(pid)}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getTask: (taskId) => request(`/api/tasks/${encodeURIComponent(taskId)}`, {
    signal: AbortSignal.timeout(20000),
  }),
  listStyles: () => request("/api/styles"),
  replaceReference: (pid, cid, body) =>
    request(
      `/api/projects/${encodeURIComponent(pid)}/characters/${encodeURIComponent(cid)}/reference`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),
  confirmCharacters: (pid) =>
    request(`/api/projects/${encodeURIComponent(pid)}/characters/confirm`, {
      method: "POST",
    }),
  previewLong: async (pid, options, signal) => {
    const token = getToken();
    const res = await fetch(
      `${API_BASE}/api/projects/${encodeURIComponent(pid)}/long-preview`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(options),
        signal,
      },
    );
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "长图预览失败");
    }
    const blob = await res.blob();
    const header = res.headers.get("X-Long-Layout");
    if (header) {
      try {
        blob.longLayout = JSON.parse(decodeURIComponent(header));
      } catch { /* header is best-effort */ }
    }
    return blob;
  },
};

export function readImage(file) {
  if (!file || !["image/png", "image/jpeg", "image/webp"].includes(file.type))
    return Promise.reject(new Error("请上传 PNG、JPEG 或 WebP 图片"));
  if (file.size > 8 * 1024 * 1024)
    return Promise.reject(new Error("图片不能超过 8 MB"));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

// 轮询任务直到 done/failed；onTick 每次拿到最新任务对象
export function pollTask(taskId, onTick, interval = 1500) {
  let stopped = false;
  let timer = null;
  let lastTask = { task_id: taskId, status: "running", logs: [] };
  const tick = async () => {
    try {
      const t = await api.getTask(taskId);
      if (stopped) return;
      lastTask = t;
      onTick(t);
      if (t.status === "pending" || t.status === "running") {
        timer = setTimeout(tick, interval);
      }
    } catch (e) {
      if (!stopped) {
        onTick({ ...lastTask, polling_error: "暂时无法获取任务状态，正在重新连接。请勿重复提交。" });
        timer = setTimeout(tick, interval);
      }
    }
  };
  timer = setTimeout(tick, interval);
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
  };
}
