import { useEffect, useState } from "react";
import {
  assetUrl,
  listSceneReferences,
  updateSceneReferences,
  uploadSceneReference,
} from "../lib/studioAssets.js";

function recordsOf(value) {
  if (Array.isArray(value)) return value;
  return value?.assets || value?.items || value?.references || [];
}

function assetOf(reference) {
  return reference?.asset || reference;
}

/**
 * Scene-only references for the storyboard card.
 *
 * The image is stored in the project asset library and is never silently
 * promoted to a global character reference. The selected mode is committed
 * together with the uploaded reference through the scene reference API.
 */
export default function SceneReferenceTools({ pid, sceneId, busy = false, onChange, characters = [] }) {
  const [references, setReferences] = useState([]);
  const [mode, setMode] = useState("append");
  const [replaceCharacterId, setReplaceCharacterId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    if (!pid || !sceneId) return;
    setLoading(true);
    try {
      const result = await listSceneReferences(pid, sceneId);
      const next = recordsOf(result);
      setReferences(next);
    } catch (e) {
      setError(e.message || "读取本格素材失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // A scene card can remain mounted while the selected scene changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, sceneId]);

  async function upload(file) {
    if (!file || loading || busy) return;
    setLoading(true);
    setError("");
    try {
      if (mode === "replace_character" && !replaceCharacterId.trim()) {
        throw new Error("请先选择要替换的本格角色");
      }
      const result = await uploadSceneReference(pid, sceneId, file);
      const next = recordsOf(result);
      const refs = next.map((item) => ({
        asset_id: item.asset_id,
        mode: item.mode || "append",
        ...(item.replace_character_id ? { replace_character_id: item.replace_character_id } : {}),
      }));
      let final = next;
      if (mode === "replace_character") {
        const latest = next[next.length - 1];
        const selectedRefs = latest
          ? [...refs.filter(item => item.asset_id !== latest.asset_id && !(item.mode === 'replace_character' && item.replace_character_id === replaceCharacterId.trim())), { asset_id: latest.asset_id, mode, replace_character_id: replaceCharacterId.trim() }]
          : refs;
        const saved = await updateSceneReferences(pid, sceneId, selectedRefs);
        final = recordsOf(saved);
      }
      setReferences(final);
      onChange?.({ references: final, mode, replaceCharacterId });
    } catch (e) {
      setError(e.message || "上传本格素材失败");
    } finally {
      setLoading(false);
    }
  }

  async function remove(asset) {
    const assetId = asset?.asset_id || asset?.id;
    if (!assetId || loading || busy) return;
    setLoading(true);
    setError("");
    try {
      const next = references.filter((item) => (item.asset_id || item.id) !== assetId);
      const saved = await updateSceneReferences(
        pid,
        sceneId,
        next.map((item) => ({
          asset_id: item.asset_id || item.id,
          mode: item.mode || "append",
          ...(item.replace_character_id ? { replace_character_id: item.replace_character_id } : {}),
        })),
      );
      const final = recordsOf(saved);
      setReferences(final);
      onChange?.({ references: final, mode, replaceCharacterId });
    } catch (e) {
      setError(e.message || "移除本格素材失败");
    } finally {
      setLoading(false);
    }
  }

  function changeMode(value) {
    setMode(value);
  }

  return (
    <section className="scene-reference-tools" aria-label="本格专属参考素材">
      <div className="scene-reference-head">
        <div>
          <h4>本格专属素材</h4>
          <p className="muted">仅用于当前分镜，其他分镜继续使用原有角色。</p>
        </div>
        <span className="scene-reference-count">{references.length} 张</span>
      </div>
      <div className="scene-reference-form">
        <label>
          使用方式
          <select value={mode} disabled={busy || loading} onChange={(e) => changeMode(e.target.value)}>
            <option value="append">追加到本格参考</option>
            <option value="replace_character">替换本格角色参考</option>
          </select>
        </label>
        {mode === "replace_character" && (
          <label>
            要替换的本格角色
            <select
              value={replaceCharacterId}
              disabled={busy || loading}
              onChange={(e) => {
                setReplaceCharacterId(e.target.value);
              }}
            >
              <option value="">选择角色</option>
              {characters.map((character) => (
                <option key={character.character_id} value={character.character_id}>
                  {character.name || character.character_id}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <label className="scene-reference-upload">
        <span>{loading ? "处理中…" : "添加官方形象 / 本格参考图"}</span>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={busy || loading}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            upload(file);
          }}
        />
      </label>
      {references.length > 0 && (
        <div className="scene-reference-list">
          {references.map((asset) => (
            <article className="scene-reference-item" key={asset.asset_id || asset.id}>
              <img src={assetUrl(assetOf(asset), pid)} alt={assetOf(asset).filename || assetOf(asset).name || "本格参考图"} />
              <div>
                <strong>{assetOf(asset).filename || assetOf(asset).name || "本格参考图"}</strong>
                <small>{asset.mode === "replace_character" ? "替换角色参考" : "追加参考"}</small>
                <button type="button" disabled={busy || loading} onClick={() => remove(asset)}>移除</button>
              </div>
            </article>
          ))}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
