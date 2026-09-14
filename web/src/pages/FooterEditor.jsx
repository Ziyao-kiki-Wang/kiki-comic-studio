import { useEffect, useRef, useState } from "react";
import { api, pollTask } from "../lib/api.js";
import { assetUrl, generateProjectAsset, uploadProjectAsset } from "../lib/studioAssets.js";
import { Centimeters } from "./PageMargins.jsx";

export default function FooterEditor({pid, project, blocks, onChange, busy, onBusyChange, printWidthCm=20}) {
  const [assets,setAssets] = useState(project.assets || []);
  const [uploading,setUploading] = useState(false);
  const [prompt,setPrompt] = useState("");
  const [references,setReferences] = useState([null,null]);
  const [size,setSize] = useState("1536x1024");
  const [background,setBackground] = useState("auto");
  const [task,setTask] = useState(null);
  const [requesting,setRequesting] = useState(false);
  const [generated,setGenerated] = useState(null);
  const [error,setError] = useState("");
  const [showAI,setShowAI] = useState(false);
  const stop = useRef(null);
  const key = `comic-footer-task:${pid}`;
  const running = requesting || ["pending","running"].includes(task?.status);
  const locked = busy || uploading || running;
  useEffect(()=>{onBusyChange(uploading || running);},[uploading,running,onBusyChange]);
  useEffect(()=>{setAssets(previous=>[...new Map([...previous,...(project.assets || [])].map(a=>[a.asset_id,a])).values()]);},[project.assets]);
  function track(id) {
    setShowAI(true);
    stop.current?.();
    sessionStorage.setItem(key,id);
    setTask({task_id:id,status:"pending",logs:[]});
    stop.current = pollTask(id,t=>{
      setTask(t);
      if(t.status === "done" && t.result?.asset) {
        setGenerated(t.result.asset);
        setAssets(previous=>[...previous.filter(a=>a.asset_id!==t.result.asset.asset_id),t.result.asset]);
      }
    },1000);
  }
  useEffect(()=>{
    const id = project.active_task?.kind === "generate_asset" ? project.active_task.task_id : sessionStorage.getItem(key);
    if(id) {
      let active = true;
      api.getTask(id).then(t=>{
        if(!active) return;
        setPrompt(t.detail?.prompt || "");
        setSize(t.detail?.size || "1536x1024");
        setBackground(t.detail?.background || "auto");
        const savedRefs=(t.detail?.reference_asset_ids || []).map(id=>(project.assets || []).find(a=>a.asset_id===id)).filter(Boolean);
        setReferences([savedRefs[0] || null,savedRefs[1] || null]);
        track(id);
      }).catch(()=>sessionStorage.removeItem(key));
      return ()=>{active=false;stop.current?.();};
    }
    return ()=>stop.current?.();
  },[pid]);
  function add(block) {
    onChange(previous=>previous.length>=12 ? previous : [...previous,{id:crypto.randomUUID(),align:"center",...block}]);
  }
  function update(index,patch) {onChange(previous=>previous.map((b,i)=>i===index?{...b,...patch}:b));}
  function reorder(index,direction) {
    onChange(previous=>{const next=[...previous];[next[index],next[index+direction]]=[next[index+direction],next[index]];return next;});
  }
  async function upload(file, referenceIndex) {
    if(!file || locked) return;
    setUploading(true);setError("");
    try {
      const asset = await uploadProjectAsset(pid,file,"image",file.name);
      setAssets(previous=>[...previous,asset]);
      if(referenceIndex !== undefined) setReferences(previous=>previous.map((r,i)=>i===referenceIndex?asset:r));
      else add({type:"image",asset_id:asset.asset_id,width:800});
    } catch(e) {setError(e.message);} finally {setUploading(false);}
  }
  async function generate() {
    if(!prompt.trim() || locked) return;
    setRequesting(true);setError("");setGenerated(null);
    try {
      const response=await generateProjectAsset(pid,{prompt,reference_asset_ids:references.filter(Boolean).map(a=>a.asset_id),size,background});
      track(response.task_id);
    } catch(e) {setError(e.message);} finally {setRequesting(false);}
  }
  const inserted = generated && blocks.some(b=>b.asset_id===generated.asset_id);
  return <section className="footer-content-editor" aria-label="结尾图文内容">
    <div className="form-row">
      <button type="button" disabled={locked || blocks.length>=12} onClick={()=>add({type:"text",text:"",font_size:32})}>添加结尾文字</button>
      <label className="footer-upload">上传结尾图片<input aria-label="上传结尾图片" type="file" accept="image/png,image/jpeg,image/webp" disabled={locked || blocks.length>=12} onChange={e=>{const f=e.target.files?.[0];e.target.value="";upload(f);}}/></label>
    </div>
    {blocks.map((block,index)=>{
      const asset=assets.find(a=>a.asset_id===block.asset_id);
      const gapBefore = block.gap_before_cm ?? Number((24 * printWidthCm / 1080).toFixed(2));
      return <div className="footer-block" key={block.id || index}>
        <div className="footer-block-head"><b>{index+1}. {block.type==="image"?"图片":"文字"}</b><div>
          <button type="button" aria-label={`上移结尾内容 ${index+1}`} disabled={locked || index===0} onClick={()=>reorder(index,-1)}>↑</button>
          <button type="button" aria-label={`下移结尾内容 ${index+1}`} disabled={locked || index===blocks.length-1} onClick={()=>reorder(index,1)}>↓</button>
          <button type="button" disabled={locked} onClick={()=>onChange(previous=>previous.filter((b,i)=>i!==index))}>删除</button>
        </div></div>
        {block.type==="text" ? <>
          <textarea aria-label={`结尾文字 ${index+1}`} rows={3} maxLength={1000} value={block.text || ""} disabled={locked} placeholder="输入结尾提示、说明或寄语" onChange={e=>update(index,{text:e.target.value})}/>
          <label>字号：{block.font_size || 32}<input aria-label={`结尾字号 ${index+1}`} type="range" min={18} max={72} value={block.font_size || 32} disabled={locked} onChange={e=>update(index,{font_size:Number(e.target.value)})}/></label>
        </> : <>
          {asset && <img className="footer-image-preview" src={assetUrl(asset,pid)} alt={`结尾图片 ${index+1}`}/>}
          <label>图片宽度：{block.width || 800}<input aria-label={`结尾图片宽度 ${index+1}`} type="range" min={160} max={960} value={block.width || 800} disabled={locked} onChange={e=>update(index,{width:Number(e.target.value)})}/></label>
        </>}
        <div className="page-margin-field footer-gap">
          <div><span>与上方内容间距</span><Centimeters label={`结尾内容 ${index+1} 上方间距（厘米）`} value={gapBefore} disabled={locked} onChange={value=>update(index,{gap_before_cm:value})}/></div>
          <input aria-label={`结尾内容 ${index+1} 上方间距滑块`} type="range" min={0} max={20} step={0.1} value={gapBefore} disabled={locked} onChange={e=>update(index,{gap_before_cm:Number(e.target.value)})}/>
        </div>
        <label>对齐<select aria-label={`结尾对齐 ${index+1}`} value={block.align || "center"} disabled={locked} onChange={e=>update(index,{align:e.target.value})}><option value="left">偏左</option><option value="center">居中</option><option value="right">偏右</option></select></label>
      </div>;
    })}
    <details className="footer-ai" open={showAI} onToggle={e=>setShowAI(e.currentTarget.open)}>
      <summary>AI 生成结尾图片</summary>
      <p className="muted">上传最多两张人物或场景参考图，描述想要的画面。生成后预览，再插入结尾。</p>
      <div className="footer-references">{references.map((asset,index)=><div key={index}>
        <label>参考图 {index+1}<input aria-label={`结尾参考图 ${index+1}`} type="file" accept="image/png,image/jpeg,image/webp" disabled={locked} onChange={e=>{const f=e.target.files?.[0];e.target.value="";upload(f,index);}}/></label>
        {asset && <><img src={assetUrl(asset,pid)} alt={`参考图 ${index+1}`}/><button type="button" disabled={locked} onClick={()=>setReferences(previous=>previous.map((r,i)=>i===index?null:r))}>移除参考图</button></>}
      </div>)}</div>
      <label>图片生成要求<textarea aria-label="结尾图片生成要求" rows={4} maxLength={4000} value={prompt} disabled={locked} placeholder="例如：保留图1人物形象，让他拿着图2的牌子，微笑提醒大家核实信息，采用立体动画风格。" onChange={e=>setPrompt(e.target.value)}/></label>
      <div className="form-row"><label>画幅<select value={size} disabled={locked} onChange={e=>setSize(e.target.value)}><option value="1536x1024">横图</option><option value="1024x1024">方图</option><option value="1024x1536">竖图</option></select></label><label>背景<select value={background} disabled={locked} onChange={e=>setBackground(e.target.value)}><option value="auto">按描述生成</option><option value="transparent">透明背景</option></select></label></div>
      <button type="button" className="primary" disabled={locked || !prompt.trim()} onClick={generate}>{running?"正在生成图片…":task?.status==="failed"?"重试生成图片":"生成图片"}</button>
      {task && <div className="footer-generation-status" role="status"><b>{({pending:"等待生成",running:"正在生成",done:"图片生成完成",failed:"图片生成失败"})[task.status]}</b>{task.polling_error && <p>{task.polling_error}</p>}{task.logs?.length>0 && <pre>{task.logs.join("\n")}</pre>}{task.status==="failed" && <p className="error" role="alert">{task.error}</p>}</div>}
      {generated && <div className="footer-generated"><img className="footer-image-preview" src={assetUrl(generated,pid)} alt="AI 生成的结尾图片"/><button type="button" disabled={locked || blocks.length>=12 || inserted} onClick={()=>add({type:"image",asset_id:generated.asset_id,width:800})}>{inserted?"已插入结尾":"插入到结尾"}</button></div>}
    </details>
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
