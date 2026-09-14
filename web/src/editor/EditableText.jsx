import { Group, Rect, Shape } from "react-konva";
import { fontStack } from "./bubbleLayout.js";

// Text remains separate from its bubble; the hit rectangle is never exported.
export default function EditableText({ name, box, lines, fontSize, fontId, color, selected, disabled, onSelect, onEdit, onChange, groupRef, onDragStart, onDragMove, onDragEnd }) {
  return <Group ref={groupRef} name={name} x={box.x} y={box.y} width={box.width} height={box.height}
    rotation={box.rotation || 0} draggable={!disabled}
    onClick={onSelect} onTap={onSelect} onDblClick={onEdit} onDblTap={onEdit}
    onDragStart={onDragStart || onSelect} onDragMove={onDragMove}
    onDragEnd={onDragEnd || (e => onChange({x: e.target.x(), y: e.target.y()}))}
    onTransform={e => {
      const node = e.target;
      onChange({x: node.x(), y: node.y(), width: Math.max(80, Math.min(1040, box.width * node.scaleX())),
        rotation: node.rotation()});
      node.scale({x:1,y:1});
    }}>
    <Rect width={box.width} height={box.height} fill="rgba(0,0,0,0)"
      stroke={selected ? "#8a51c7" : undefined} strokeWidth={1} dash={[5,4]} />
    <Shape listening={false} sceneFunc={context => {
      const c = context._context;
      c.save(); c.font = `${fontSize}px ${fontStack(fontId)}`;
      c.fillStyle = color; c.textBaseline = "alphabetic";
      lines.forEach(line => c.fillText(line.text, line.x, line.y));
      c.restore();
    }} />
  </Group>;
}
