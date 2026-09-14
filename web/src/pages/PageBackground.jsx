const COLORS = ["#ffffff", "#f5f1e8", "#eaf3ec", "#e9effa", "#fae9ee", "#fff2cf", "#272b35"];

export default function PageBackground({ options, theme, busy, onChange }) {
  const color = options.background_color || theme.background;
  const transparency = Math.round((1 - (options.background_opacity ?? 1)) * 100);
  return <section className="publishing-inspector-section" aria-label="页面背景设置">
    <div className="publishing-inspector-title"><span>◐</span><b>背景底色</b></div>
    <div className="page-background-color">
      <label className="publishing-field">自选底色<input aria-label="背景底色" type="color" value={color} disabled={busy} onChange={e=>onChange({background_color:e.target.value})}/></label>
      <span>{color.toUpperCase()}</span>
      <div className="page-background-sample checkerboard" aria-hidden="true"><i style={{background:color,opacity:1-transparency/100}}/></div>
    </div>
    <div className="page-background-swatches" role="group" aria-label="常用背景颜色">
      {COLORS.map(value=><button key={value} type="button" aria-label={`背景色 ${value}`} aria-pressed={value===color} style={{background:value}} disabled={busy} onClick={()=>onChange({background_color:value})}/>)}
    </div>
    <label className="publishing-field publishing-range-field"><span>背景透明度<b>{transparency}%</b></span><input aria-label="背景透明度" type="range" min={0} max={100} step={1} value={transparency} disabled={busy} onChange={e=>onChange({background_opacity:1-Number(e.target.value)/100})}/></label>
    <p className="heading-note">0% 为实色，100% 为全透明。仅调整页面底色，文字、图片和卡片装饰保留原样；下载 PNG 也会保留透明效果。</p>
    <button type="button" disabled={busy || (!options.background_color && transparency===0)} onClick={()=>onChange({background_color:"",background_opacity:1})}>恢复模板底色</button>
  </section>;
}
