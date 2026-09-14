import { useRef, useState } from "react";
import { bubbleGeometry } from "./bubbleLayout.js";

export default function useBubbleSelection({ bubbles, setBubbles, bubbleRefs, textRefs, setDirty }) {
  const [ids, setIds] = useState([]);
  const [groups, setGroups] = useState([]);
  const drag = useRef(null);
  const expand = id => groups.find(group => group.includes(id)) || [id];
  const setSelected = id => setIds(id ? expand(id) : []);
  function select(id, event) {
    const incoming = expand(id);
    if (event?.evt?.shiftKey) {
      setIds(previous => incoming.every(key => previous.includes(key))
        ? previous.filter(key => !incoming.includes(key)) : [...new Set([...previous, ...incoming])]);
    } else setIds(incoming);
  }
  const nodeFor = id => id.startsWith("text:") ? textRefs.current[id.slice(5)] : bubbleRefs.current[id];
  function start(id, event) {
    const moving = ids.includes(id) ? ids : expand(id);
    setIds(moving);
    drag.current = { id, start: event.target.position(), moving,
      nodes: moving.map(key => ({key, node:nodeFor(key), start:nodeFor(key)?.position()})).filter(item => item.node) };
  }
  function move(event) {
    const d = drag.current;
    if (!d) return;
    const dx = event.target.x() - d.start.x, dy = event.target.y() - d.start.y;
    d.nodes.forEach(item => { if (item.key !== d.id) item.node.position({x:item.start.x + dx,y:item.start.y + dy}); });
  }
  function end(event) {
    const d = drag.current;
    if (!d) return;
    const dx = event.target.x() - d.start.x, dy = event.target.y() - d.start.y;
    setBubbles(previous => previous.map(b => {
      const shell = d.moving.includes(b.bubble_id), text = d.moving.includes(`text:${b.bubble_id}`);
      if (!shell && !text) return b;
      const g = bubbleGeometry(b);
      return {...b, body_height:g.height, tail_local:g.tip, geometry:undefined,
        x:b.x + (shell ? dx : 0), y:b.y + (shell ? dy : 0),
        text_box:{...g.text_box,x:g.text_box.x + (text ? dx : 0),y:g.text_box.y + (text ? dy : 0)}};
    }));
    setDirty(true);
    drag.current = null;
  }
  const editable = new Set(bubbles.flatMap(b => [
    ...(b.bubble_visible !== false ? [b.bubble_id] : []),
    ...(b.text_visible !== false ? [`text:${b.bubble_id}`] : []),
  ]));
  const canGroup = ids.length >= 2 && ids.every(id => editable.has(id));
  const canUngroup = groups.some(group => group.some(id => ids.includes(id)));
  function group() {
    if (!canGroup) return;
    setGroups(previous => [...previous.filter(g => !g.some(id => ids.includes(id))), [...ids]]);
    setDirty(true);
  }
  function ungroup() {
    setGroups(previous => previous.filter(g => !g.some(id => ids.includes(id))));
    setDirty(true);
  }
  function remove() {
    const removed = ids.filter(id => editable.has(id));
    if (!removed.length) return;
    setBubbles(previous => previous.map(b => ({...b,
      bubble_visible:removed.includes(b.bubble_id) ? false : b.bubble_visible,
      text_visible:removed.includes(`text:${b.bubble_id}`) ? false : b.text_visible,
    })).filter(b => b.bubble_visible !== false || b.text_visible !== false));
    setGroups(previous => previous.map(g => g.filter(id => !removed.includes(id))).filter(g => g.length >= 2));
    setIds([]);
    setDirty(true);
  }
  return {ids, selected:ids.at(-1) || null, setSelected, selectOnly:id=>setIds(id?[id]:[]), select, start, move, end,
    groups, setGroups, canGroup, canUngroup, group, ungroup, remove,
    canRemove:ids.some(id => editable.has(id))};
}
