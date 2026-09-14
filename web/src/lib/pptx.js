import PptxGenJS from "pptxgenjs";
import { api, fileUrl } from "./api.js";
import { bubbleGeometry, bubbleSvg, bubbleAssetFile, captionGeometry, transformPoint, measureText } from "../editor/bubbleLayout.js";
import fontCatalog from "../../../schemas/fonts.json";
import { listFonts, loadFontFace } from "./studioAssets.js";

const pptxFont = (id) => {
  const spec = fontCatalog.fonts.find((font) => font.id === id);
  return { fontFace: spec?.pptx_face || "Microsoft YaHei", bold: spec?.pptx_bold || false };
};

const inch = (n) => Number(n) / 96;
const pt = (n) => Number(n) * 0.75;
function editableText(slide, box, runs, fontSize, fontId, color) {
  for (const run of runs) {
    if (!run.text) continue;
    const width = (run.width ?? measureText(run.text, fontSize, fontId)) + 3;
    const height = fontSize + 10;
    const [cx,cy] = transformPoint([run.x + width / 2, run.y - fontSize + height / 2], box);
    slide.addText(run.text, {x:inch(cx-width/2), y:inch(cy-height/2), w:inch(width), h:inch(height),
      ...pptxFont(fontId), fontSize:pt(fontSize), color:color.replace("#", ""),
      rotate:((box.rotation || 0) % 360 + 360) % 360, margin:0, breakLine:false, valign:"mid", fit:"resize"});
  }
}
async function imageData(url) {
  const res = await fetch(fileUrl(url));
  if (!res.ok) throw new Error(`素材读取失败：HTTP ${res.status}`);
  const blob = await res.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("素材读取失败"));
    reader.readAsDataURL(blob);
  });
}

export async function exportPptx(pid) {
  const project = await api.getProject(pid);
  if (
    project.scenes.some(
      (s) => !s.raw_url || !s.layout?.canvas || s.render_stale,
    )
  )
    throw new Error("请先生成并重新合成所有分镜，再导出 PPTX");
  const usedFonts = new Set([
    ...project.scenes.flatMap((scene) => (scene.layout?.bubbles || []).map((b) => b.font_id || b.font_family)),
    ...project.storyboard.scenes.map((scene) => scene.caption_font_id),
    ...project.scenes.map(scene => scene.layout?.caption_layout?.font_id),
  ].filter(Boolean));
  if (usedFonts.size) {
    const { fonts } = await listFonts(pid);
    await Promise.all(fonts.filter((font) => usedFonts.has(font.id) && font.installed).map((font) => loadFontFace(pid, font)));
  }
  const pptx = new PptxGenJS();
  const maxH = Math.max(...project.scenes.map((s) => s.layout.canvas.height));
  pptx.defineLayout({ name: "COMIC", width: inch(1080), height: inch(maxH) });
  pptx.layout = "COMIC";
  for (const scene of project.scenes) {
    const story = project.storyboard.scenes.find(
      (s) => s.scene_id === scene.scene_id,
    );
    const layout = scene.layout,
      panelH =
        layout.canvas.panel_height ||
        layout.canvas.height - (layout.caption?.height || 100);
    const source =
      scene.background_mode === "transparent"
        ? scene.foreground_url
        : scene.raw_url;
    if (!source)
      throw new Error(`${scene.scene_id} 的透明场景尚未生成，请先重跑这一格，再导出`);
    const actualSlide = pptx.addSlide();
    let currentLayer = "subject";
    const operations = [];
    const slide = {
      addImage: options => operations.push({key:currentLayer, draw:()=>actualSlide.addImage(options)}),
      addText: (text,options) => operations.push({key:currentLayer, draw:()=>actualSlide.addText(text,options)}),
    };
    const subject = scene.background_mode === "transparent" ? layout.subject_layout : null;
    slide.addImage({
      data: await imageData(source),
      x: inch(subject?.x || 0),
      y: inch(subject?.y || 0),
      w: inch(subject?.width || 1080),
      h: inch(subject?.height || panelH),
    });
    const inset = layout.screen_inset;
    if (inset && scene.screen_url) {
      currentLayer = "inset";
      const img = new Image();
      img.src = await imageData(scene.screen_url);
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = inset.width;
      canvas.height = inset.height;
      const ctx = canvas.getContext("2d");
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(0, 0, inset.width, inset.height, 30);
      ctx.clip();
      ctx.drawImage(img, 0, 0, inset.width, inset.height);
      ctx.restore();
      ctx.beginPath();
      ctx.roundRect(4, 4, inset.width - 8, inset.height - 8, 26);
      ctx.strokeStyle = "#1a1a1a";
      ctx.lineWidth = 8;
      ctx.stroke();
      slide.addImage({
        data: canvas.toDataURL("image/png"),
        x: inch(inset.x),
        y: inch(inset.y),
        w: inch(inset.width),
        h: inch(inset.height),
      });
    }
    for (const [i, saved] of (layout.bubbles || []).entries()) {
      if (saved.bubble_visible === false) continue;
      const assetFile = bubbleAssetFile(saved);
      if (assetFile) {
        currentLayer = saved.bubble_id;
        const g = bubbleGeometry(saved), img = new Image();
        img.src = await imageData(`/api/bubble-assets/${assetFile}?v=1`);
        await img.decode();
        const tile = document.createElement("canvas");tile.width=img.width;tile.height=img.height;
        const ctx=tile.getContext("2d");
        ctx.translate(saved.flip_x?tile.width:0,saved.flip_y?tile.height:0);
        ctx.scale(saved.flip_x?-1:1,saved.flip_y?-1:1);ctx.drawImage(img,0,0);
        const width=saved.width*(saved.scale_x??1),height=g.height*(saved.scale_y??1);
        const [cx,cy]=transformPoint([saved.width/2,g.height/2],{...saved,body_height:g.height});
        slide.addImage({data:tile.toDataURL("image/png"),x:inch(cx-width/2),y:inch(cy-height/2),w:inch(width),h:inch(height),rotate:((saved.rotation||0)%360+360)%360});
        continue;
      }
      const b = { ...saved, text: story.dialogues[i]?.text ?? saved.text },
        g = bubbleGeometry(b),
        shape = bubbleSvg(b, panelH);
      currentLayer = saved.bubble_id;
      if (shape) slide.addImage({
        data: "data:image/svg+xml;base64," + btoa(shape.svg),
        x: inch(b.x + shape.x),
        y: inch(b.y + shape.y),
        w: inch(shape.width),
        h: inch(shape.height),
      });
    }
    for (const [i,saved] of (layout.bubbles || []).entries()) {
      if (saved.text_visible === false) continue;
      const b = {...saved,text:story.dialogues[i]?.text ?? saved.text}, g = bubbleGeometry(b);
      currentLayer = `text:${saved.bubble_id}`;
      editableText(slide, g.text_box, g.lines, b.font_size, b.font_id || b.font_family, b.text_color || "#222222");
    }
    for (const overlay of [...(layout.overlays || [])].sort((a,b) => (a.z_index || 0) - (b.z_index || 0))) {
      currentLayer = `overlay:${overlay.overlay_id || overlay.id || overlay.asset_id}`;
      const asset = (project.assets || []).find(a => a.asset_id === overlay.asset_id);
      if (!asset?.url) throw new Error('贴图素材缺失，请刷新工作台后重试');
      const img = new Image();
      img.src = await imageData(asset.url);
      await img.decode();
      const width = overlay.width || img.width, height = overlay.height || img.height;
      const canvas = document.createElement('canvas');
      canvas.width = width; canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.globalAlpha = overlay.opacity ?? 1;
      ctx.translate(overlay.flip_x ? width : 0, overlay.flip_y ? height : 0);
      ctx.scale(overlay.flip_x ? -1 : 1, overlay.flip_y ? -1 : 1);
      ctx.drawImage(img, 0, 0, width, height);
      slide.addImage({data:canvas.toDataURL('image/png'),x:inch(overlay.x),y:inch(overlay.y),w:inch(width),h:inch(height),rotate:overlay.rotation || 0});
    }
    const box = captionGeometry(story.caption || "", layout.caption_layout, panelH, story.caption_font_id);
    currentLayer = "caption";
    editableText(slide, box, box.lines, box.font_size, box.font_id, "#343434");
    const defaultOrder = [...new Set(operations.map(op=>op.key))];
    const savedOrder = scene.background_mode === "transparent" ? layout.layer_order || [] : ["subject", ...(layout.layer_order || []).filter(key=>key!=="subject")];
    const order = [...savedOrder.filter(key=>defaultOrder.includes(key)), ...defaultOrder.filter(key=>!savedOrder.includes(key))];
    for (const key of order) operations.filter(op=>op.key===key).forEach(op=>op.draw());
  }
  const title = project.title || pid;
  await pptx.writeFile({ fileName: `${title}.pptx` });
  return title;
}
