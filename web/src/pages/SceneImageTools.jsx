import { useState } from "react";
import { fileUrl } from "../lib/api.js";

export function AssetDownloads({ scene }) {
  return (
    <div className="scene-actions asset-downloads">
      {[
        [scene.raw_url, "下载原图"],
        [scene.foreground_url, "下载透明素材"],
        [scene.panel_url, "下载画面（含气泡）"],
        [scene.composite_url, "下载单格成品"],
        [scene.screen_url, "下载屏幕素材"],
      ]
        .filter(([url]) => url)
        .map(([url, label]) => (
          <a
            className="button"
            key={label}
            href={fileUrl(url) + "&download=true"}
          >
            {label}
          </a>
        ))}
    </div>
  );
}

export default function SceneImageTools({ scene, busy, onEdit }) {
  const [instruction, setInstruction] = useState("");
  return (
    <div className="image-edit-tools">
      <label>
        图片修改要求
        <textarea
          rows={3}
          maxLength={4000}
          value={instruction}
          disabled={busy}
          placeholder="例如：保留人物和桌椅，去掉房间背景；让人物把手机自然地展示给对方，表情更生动。"
          onChange={(e) => setInstruction(e.target.value)}
        />
      </label>
      <p className="muted">
        这是给绘图模型的修改命令，可以按自己的想法填写。以当前原图为基础修改，会调用生图服务并保留旧版本。
      </p>
      <button
        disabled={busy || !scene.raw_url || !instruction.trim()}
        onClick={() => onEdit(instruction.trim())}
      >
        按要求修改图片
      </button>
      <details>
        <summary>查看当前生成提示词</summary>
        <pre className="generation-prompt">{scene.generation_prompt}</pre>
      </details>
      {scene.last_generation && (
        <details>
          <summary>查看当前版本实际使用的命令</summary>
          <pre className="generation-prompt">
            {scene.last_generation.prompt}
          </pre>
        </details>
      )}
      <AssetDownloads scene={scene} />
    </div>
  );
}
