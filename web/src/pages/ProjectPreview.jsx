const stylePreviewUrl = id => `/style-previews/girl/${id}.png`;

export default function ProjectPreview({ styles, styleId, sceneCount, onStyleChange, disabled }) {
  const selected = styles.find(style=>style.style_id===styleId);
  return <aside className="creation-preview" aria-label="新建漫画示例预览">
    <div className="creation-preview-heading"><div><p>先看看，你的故事会是什么感觉</p><h2>画风与分镜预览</h2></div><span>实时示例</span></div>
    <div className="creation-frames-heading"><b>分镜数量示意</b><span aria-live="polite">共 {sceneCount} 格</span></div>
    <div className="creation-frames" style={{'--frame-columns':sceneCount===1 ? 1 : sceneCount<=4 ? 2 : 3}} aria-label={`${sceneCount} 格分镜示意`}>
      {Array.from({length:sceneCount},(_,index)=><div className="creation-frame" key={index}><span>{String(index+1).padStart(2,'0')}</span><i/><i/></div>)}
    </div>
    <figure className="creation-style-hero">
      <img key={styleId} src={stylePreviewUrl(styleId)} alt={`${selected?.name || '商业漫画风'}小女孩示例`} />
      <figcaption><b>{selected?.name || '商业漫画风'}</b><span>{selected?.look}</span></figcaption>
    </figure>
    <div className="creation-style-options" role="group" aria-label="选择示例画风">
      {styles.map(style=><button key={style.style_id} type="button" aria-label={`预览${style.name}`} aria-pressed={styleId===style.style_id} disabled={disabled} onClick={()=>onStyleChange(style.style_id)}>
        <img src={stylePreviewUrl(style.style_id)} alt="" loading="lazy"/>
        <span>{style.name.replace('（默认）','')}</span>
      </button>)}
    </div>
    <p className="creation-preview-note">示例用于对比画风，格数框用于示意数量。创建后，AI 会按你的主题和角色生成故事；最终排版可在「作品排版」中选择。</p>
  </aside>;
}
