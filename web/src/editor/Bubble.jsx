import { useEffect, useState } from "react";
import { Group, Line, Circle, Rect, Image as KonvaImage } from "react-konva";
import { bubbleGeometry, bubbleAppearance, bubbleAssetFile } from "./bubbleLayout.js";
import { fileUrl } from "../lib/api.js";

export default function Bubble({bubble:b,selected,disabled,onSelect,onEdit,onChange,groupRef,onDragStart,onDragMove,onDragEnd}) {
  const g=bubbleGeometry(b), style=bubbleAppearance(b), asset=bubbleAssetFile(b);
  const [image,setImage]=useState(null);
  useEffect(()=>{let active=true;setImage(null);if(asset){const img=new window.Image();img.crossOrigin="anonymous";img.onload=()=>{if(active){setImage(img);}};img.onerror=()=>console.error("Bubble artwork failed to load",asset);img.src=fileUrl(`/api/bubble-assets/${asset}?v=1`);}return()=>{active=false;};},[asset]);
  return <Group ref={groupRef} name={`bubble-${b.bubble_id}`} x={b.x} y={b.y} width={b.width} height={g.height}
    rotation={b.rotation || 0} scaleX={b.scale_x ?? 1} scaleY={b.scale_y ?? 1} draggable={!disabled}
    onClick={e=>onSelect(b.bubble_id,e)} onTap={e=>onSelect(b.bubble_id,e)}
    onDblClick={()=>onEdit?.(b.bubble_id)} onDblTap={()=>onEdit?.(b.bubble_id)}
    onDragStart={onDragStart || (()=>onSelect(b.bubble_id))} onDragMove={onDragMove}
    onDragEnd={onDragEnd || (e=>{if(e.target===e.currentTarget)onChange({x:e.target.x(),y:e.target.y(),tail_local:g.tip});})}
    onTransformEnd={e=>{if(e.target!==e.currentTarget)return;const n=e.target;onChange({x:n.x(),y:n.y(),rotation:n.rotation(),scale_x:Math.max(.1,Math.min(4,n.scaleX())),scale_y:Math.max(.1,Math.min(4,n.scaleY())),tail_local:g.tip});}}>
    <Group x={b.flip_x?b.width:0} y={b.flip_y?g.height:0} scaleX={b.flip_x?-1:1} scaleY={b.flip_y?-1:1}>
      {asset ? (image && <KonvaImage image={image} width={b.width} height={g.height} />) : <>
        <Line points={g.points.flat()} closed fill={style.fill} stroke={style.stroke} strokeWidth={style.stroke_width} strokeScaleEnabled={false} lineJoin="round" dash={b.type==="whisper"?[9,7]:undefined}/>
        {g.circles.map((c,i)=><Circle key={i} x={c.x} y={c.y} radius={c.r} fill={style.fill} stroke={style.stroke} strokeWidth={style.stroke_width} strokeScaleEnabled={false}/>)}
      </>}
      <Rect width={b.width} height={g.height} fill="rgba(0,0,0,0)" />
    </Group>
    {selected && <Rect x={-5} y={-5} width={b.width+10} height={g.height+10} stroke="#2f6fdb" strokeWidth={2} dash={[7,5]} listening={false}/>}
  </Group>;
}
