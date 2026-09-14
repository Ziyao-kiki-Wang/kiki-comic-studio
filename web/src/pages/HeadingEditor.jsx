import { useState } from "react";
import catalog from "../../../schemas/heading_styles.json";

const DEFAULT_HEADING = { style: "plain", font_size: 30, align: "left" };

function HeadingSample({ style }) {
  const fill = style.fill, ink = style.text_color || "#2b7062";
  return <svg viewBox="0 0 180 60" aria-hidden="true">
    {style.id === "block" && <><rect x="15" y="10" width="153" height="44" rx="2" fill={ink} opacity=".13"/><rect x="12" y="7" width="153" height="44" rx="2" fill={fill}/><path d="M20 15V42" stroke={ink} opacity=".5" strokeWidth="2"/></>}
    {style.id === "rounded" && <><rect x="13" y="9" width="155" height="45" rx="22" fill={ink} opacity=".1"/><rect x="11" y="6" width="155" height="45" rx="22" fill={fill}/><path d="M35 12H144" stroke="white" strokeOpacity=".7" strokeWidth="2"/></>}
    {style.id === "candy" && <><path d="M26 18L5 8 10 29 5 50 26 41M154 18L175 8 170 29 175 50 154 41" fill={fill}/><path d="M9 15L27 26M9 44L27 34M171 15L153 26M171 44L153 34" stroke={ink} opacity=".25"/><rect x="24" y="6" width="132" height="47" rx="12" fill={fill} stroke={ink} strokeOpacity=".2"/><path d="M39 13H141" stroke="white" strokeOpacity=".7" strokeWidth="2"/></>}
    {style.id === "wave" && <path d="M9 10Q19 1 29 10T49 10T69 10T89 10T109 10T129 10T149 10T169 10V49Q159 58 149 49T129 49T109 49T89 49T69 49T49 49T29 49T9 49Z" fill={fill} stroke={ink} strokeOpacity=".25"/>}
    {style.id === "ribbon" && <><path d="M6 8H174L164 30 174 52H6L16 30Z" fill={fill}/><path d="M27 14H153" stroke="white" strokeOpacity=".7"/><path d="M27 46H153" stroke={ink} strokeOpacity=".2"/></>}
    {style.id === "underline" && <path d="M26 47Q33 40 40 47T54 47T68 47T82 47T96 47T110 47T124 47T138 47T152 47" stroke={ink} strokeWidth="2" fill="none"/>}
    <text x="90" y={style.id === "underline" ? 29 : 32} dominantBaseline="middle" textAnchor="middle" fontSize="20" fontWeight="600" fill={ink}>故事的转折</text>
  </svg>;
}

export default function HeadingEditor({ scenes, options, accent, busy, onChange }) {
  const [scope, setScope] = useState("all");
  const scene = scenes.find(item => item.scene_id === scope);
  const own = scene ? options.heading_overrides?.[scope] : null;
  const current = { ...DEFAULT_HEADING, ...options.heading, ...(own || {}) };
  const style = catalog.styles.find(item => item.id === current.style) || catalog.styles[0];
  const originalText = scene ? ((options.template_id === "qa" && scene.question) || scene.heading || scene.location || "") : "";
  function update(patch) {
    onChange(previous => scene
      ? { ...previous, heading_overrides: { ...previous.heading_overrides, [scope]: { ...previous.heading_overrides?.[scope], ...patch } } }
      : { ...previous, heading: { ...DEFAULT_HEADING, ...previous.heading, ...patch } });
  }
  function reset() {
    onChange(previous => {
      const next = { ...previous.heading_overrides };
      delete next[scope];
      return { ...previous, heading_overrides: next };
    });
  }
  return <div className="publishing-inspector-section heading-editor" aria-label="分镜小标题设置">
    <div className="publishing-inspector-title"><span>02</span><b>分镜小标题</b></div>
    <p className="heading-note">不显示序号，样式和字号会同步到左侧预览。</p>
    <label className="publishing-field">应用范围<select value={scene ? scope : "all"} disabled={busy} onChange={e=>setScope(e.target.value)}>
      <option value="all">所有分镜（默认样式）</option>
      {scenes.map((item,index)=><option key={item.scene_id} value={item.scene_id}>第 {index+1} 格 · {item.heading || item.question || item.location || "未设小标题"}{options.heading_overrides?.[item.scene_id] ? " · 已单独设置" : ""}</option>)}
    </select></label>
    {scene ? <>
      <label className="publishing-field">本格小标题<input value={current.text ?? originalText} maxLength={300} placeholder="留空可隐藏本格小标题" disabled={busy} onChange={e=>update({text:e.target.value})}/></label>
      <div className="heading-scope-note"><small>{own ? "本格已单独设置" : "本格跟随默认样式"}</small><button type="button" disabled={busy || !own} onClick={reset}>恢复跟随全局</button></div>
    </> : <p className="heading-note">统一调整未单独设置的选项；已单独修改的选项会保留。</p>}
    <div className="heading-style-grid" role="group" aria-label="小标题样式">
      {catalog.styles.map(item=><button type="button" key={item.id} className={`heading-style ${current.style === item.id ? "is-selected" : ""} ${item.id === "plain" ? "heading-style-plain" : ""}`} aria-pressed={current.style === item.id} aria-label={item.name} title={item.description} disabled={busy} onClick={()=>update({style:item.id,fill:null,text_color:null})}>
        <HeadingSample style={item}/><span>{item.name}<small>{item.background ? "有背景" : "无背景"}</small></span>
      </button>)}
    </div>
    <label className="publishing-field publishing-range-field"><span>小标题字号<b>{current.font_size} px</b></span><input aria-label="小标题字号" type="range" min="18" max="72" step="1" value={current.font_size} disabled={busy} onChange={e=>update({font_size:Number(e.target.value)})}/></label>
    <label className="publishing-field">小标题对齐<select value={current.align} disabled={busy} onChange={e=>update({align:e.target.value})}><option value="left">左对齐</option><option value="center">居中</option><option value="right">右对齐</option></select></label>
    <div className="heading-colors">
      <label>文字颜色<input aria-label="小标题文字颜色" type="color" value={current.text_color || style.text_color || accent} disabled={busy} onChange={e=>update({text_color:e.target.value})}/></label>
      {style.background && <label>背景颜色<input aria-label="小标题背景颜色" type="color" value={current.fill || style.fill} disabled={busy} onChange={e=>update({fill:e.target.value})}/></label>}
      <button type="button" disabled={busy || (!current.fill && !current.text_color)} onClick={()=>update({fill:null,text_color:null})}>还原配色</button>
    </div>
  </div>;
}
