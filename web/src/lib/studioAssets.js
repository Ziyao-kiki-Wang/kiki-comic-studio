/* Shared client helpers for the layout studio.
 *
 * The API intentionally speaks in the same data-url format as readImage().
 * Keeping this small adapter separate means the editor can still be opened
 * while an older server has not implemented the optional asset endpoints.
 */

import fontCatalog from "../../../schemas/fonts.json";
import { fileUrl } from "./api.js";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export const FONT_SPECS = (fontCatalog.fonts || []).map((font) => ({
  ...font,
  fallback: font.family === "serif" ? "STSong, SimSun" : "Microsoft YaHei",
}));

export const TITLE_EFFECTS = [
  { id: "plain", name: "简洁", description: "干净的单色标题" },
  { id: "outline", name: "描边", description: "增加醒目的边缘线" },
  { id: "shadow", name: "柔和投影", description: "轻微阴影，增强层次" },
  { id: "raised", name: "立体浮雕", description: "高光与阴影叠出立体感" },
];

function projectPath(pid, suffix) {
  return `${API_BASE}/api/projects/${encodeURIComponent(pid)}${suffix}`;
}

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // An optional endpoint may be missing on an older server.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function listFonts(pid) {
  return jsonRequest(projectPath(pid, "/fonts"));
}

const fontFaces = new Map();

export async function loadFontFace(pid, row) {
  const id = row.id || row.font_id;
  const installed = row.installed || row;
  const path = installed.url || installed.file_url || installed.path;
  if (!path) throw new Error("字体文件尚未导入");
  const src = path.startsWith("http") ? path : fileUrl(
    path.startsWith("/api/") ? path : `/api/files/${encodeURIComponent(pid)}/${path.split("/").map(encodeURIComponent).join("/")}`,
  );
  const previous = fontFaces.get(id);
  if (previous?.src === src) return previous.promise;
  if (previous) document.fonts.delete(previous.face);
  const face = new FontFace(id, `url("${src}")`);
  const entry = { src, face };
  entry.promise = face.load().then(() => {
    if (fontFaces.get(id) === entry) document.fonts.add(face);
    return { family: id };
  }).catch((error) => {
    if (fontFaces.get(id) === entry) fontFaces.delete(id);
    throw error;
  });
  fontFaces.set(id, entry);
  return entry.promise;
}

export async function uploadFont(pid, fontId, file) {
  const imageData = await readFont(file);
  const extension = String(file?.name || "").toLowerCase().match(/\.(ttf|otf|ttc)$/)?.[1];
  if (!extension) throw new Error("字体文件必须是 TTF、OTF 或 TTC");
  return jsonRequest(projectPath(pid, `/fonts/${encodeURIComponent(fontId)}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: file.name,
      font_data: imageData,
    }),
  });
}

export async function listProjectAssets(pid, kind = "sticker") {
  return jsonRequest(projectPath(pid, `/assets?kind=${encodeURIComponent(kind)}`));
}

export async function uploadProjectAsset(pid, file, kind = "sticker", name = "") {
  const imageData = await readAsset(file, ["image/png", "image/jpeg", "image/webp"], 8 * 1024 * 1024);
  const result = await jsonRequest(projectPath(pid, "/assets"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, name: name || file.name, image_data: imageData }),
  });
  return result.asset || result;
}

export function generateProjectAsset(pid, options) {
  return jsonRequest(projectPath(pid, "/assets/generate"), {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(options),
  });
}

async function readFont(file) {
  const extension = String(file?.name || "").toLowerCase().match(/\.(ttf|otf|ttc)$/)?.[1];
  if (!file || !extension) throw new Error("字体文件必须是 TTF、OTF 或 TTC");
  if (file.size > 32 * 1024 * 1024) throw new Error("字体不能超过 32 MB");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result);
      // Browsers often label local font files as application/octet-stream;
      // the server validates a font-specific data-url MIME type.
      const mime = extension === "ttc" ? "font/collection" : `font/${extension}`;
      resolve(value.replace(/^data:[^;,]+;base64,/i, `data:${mime};base64,`));
    };
    reader.onerror = () => reject(new Error("字体文件读取失败"));
    reader.readAsDataURL(file);
  });
}

export async function readAsset(file, accepted = [], maxSize = 8 * 1024 * 1024) {
  if (!file || (accepted.length && !accepted.includes(file.type))) {
    throw new Error("请选择支持的文件格式");
  }
  if (file.size > maxSize) throw new Error(`文件不能超过 ${Math.round(maxSize / 1024 / 1024)} MB`);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });
}

export function assetPath(asset) {
  if (!asset) return "";
  const value = asset.url || asset.path || asset.file_url || asset.src || "";
  if (!value) return "";
  return value.startsWith("http") || value.startsWith("data:") || value.startsWith("blob:") ? value : `${API_BASE}${value}`;
}

export function assetUrl(asset, pid) {
  const value = assetPath(asset);
  if (value && !value.endsWith(String(asset?.path || ""))) return value;
  const path = asset?.path;
  if (!pid || !path) return value;
  return `${API_BASE}/api/files/${encodeURIComponent(pid)}/${String(path).split("/").map(encodeURIComponent).join("/")}`;
}

export async function listSceneReferences(pid, sceneId) {
  return jsonRequest(projectPath(pid, `/scenes/${encodeURIComponent(sceneId)}/references`));
}

export async function uploadSceneReference(pid, sceneId, file) {
  const imageData = await readAsset(file, ["image/png", "image/jpeg", "image/webp"], 8 * 1024 * 1024);
  return jsonRequest(projectPath(pid, `/scenes/${encodeURIComponent(sceneId)}/references`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: file.name, image_data: imageData }),
  });
}

export function updateSceneReferences(pid, sceneId, references) {
  return jsonRequest(projectPath(pid, `/scenes/${encodeURIComponent(sceneId)}/references`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ references }),
  });
}

export function deleteProjectAsset(pid, assetId) {
  return jsonRequest(projectPath(pid, `/assets/${encodeURIComponent(assetId)}`), { method: "DELETE" });
}

export function assetIsPersisted(asset) {
  return Boolean(asset?.asset_id || asset?.id || asset?.path || asset?.url || asset?.file_url);
}
