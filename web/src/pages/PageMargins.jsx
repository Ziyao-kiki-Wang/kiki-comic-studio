import { useEffect, useRef, useState } from "react";

export function Centimeters({ label, value, min=0, max=20, disabled, onChange }) {
  const [draft, setDraft] = useState(String(value));
  const input = useRef(null);
  useEffect(() => {
    if (document.activeElement !== input.current) setDraft(String(value));
  }, [value]);
  function commit() {
    const number = draft.trim() === "" ? value : Number(draft);
    const next = Math.min(max, Math.max(min, Number.isFinite(number) ? number : value));
    setDraft(String(next));
    onChange(next);
  }
  return <span className="page-margin-number"><input ref={input} type="number" aria-label={label} min={min} max={max} step="0.1" value={draft} disabled={disabled}
    onChange={e=>{
      setDraft(e.target.value);
      const next=e.target.valueAsNumber;
      if (Number.isFinite(next) && next>=min && next<=max) onChange(next);
    }} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();e.currentTarget.blur();}}}/><span>厘米</span></span>;
}

export default function PageMargins({ options, busy, onChange }) {
  const width = options.print_width_cm ?? 20;
  return <div className="publishing-inspector-section page-margins" aria-label="作品上下留白">
    <div className="publishing-inspector-title"><span>↕</span><b>上下留白</b></div>
    <p className="heading-note">在整张排版外侧增加空白，上方留在标题之前，下方留在结尾图文之后。</p>
    {[["margin_top_cm","顶部外侧留白"],["margin_bottom_cm","底部外侧留白"]].map(([key,label])=><div className="page-margin-field" key={key}>
      <div><span>{label}</span><Centimeters label={`${label}（厘米）`} value={options[key] ?? 0} disabled={busy} onChange={value=>onChange({[key]:value})}/></div>
      <input type="range" aria-label={`${label}滑块`} min="0" max="20" step="0.1" value={options[key] ?? 0} disabled={busy} onChange={e=>onChange({[key]:Number(e.target.value)})}/>
    </div>)}
    <div className="page-margin-summary"><small>按成品宽 {width} 厘米换算，屏幕预览会自动缩放。</small><button type="button" disabled={busy || (!options.margin_top_cm && !options.margin_bottom_cm)} onClick={()=>onChange({margin_top_cm:0,margin_bottom_cm:0})}>清除外侧留白</button></div>
    <details className="publishing-details"><summary>设置成品宽度</summary><div className="page-margin-width"><span>成品宽度</span><Centimeters label="成品宽度（厘米）" value={width} min={5} max={100} disabled={busy} onChange={value=>onChange({print_width_cm:value})}/></div><p className="heading-note">宽度用于厘米换算，也会写入下载图片的尺寸信息。打印时选择原尺寸可保留设定的厘米数。</p></details>
  </div>;
}
