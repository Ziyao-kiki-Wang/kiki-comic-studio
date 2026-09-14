"""Small, scalable title badges shared by preview and final long-image rendering."""

import math
from PIL import Image, ImageColor, ImageDraw
from server.core.bubbles import wrap_lines
from server.core.studio import HEADING_STYLES


def render_heading(text, options, font, max_width, accent, tracking=0):
    kind = options.get("style", "plain")
    spec = HEADING_STYLES[kind]
    text = text.strip()
    size = int(options.get("font_size", 30))
    if not text:
        return {"image":None,"width":0,"height":0,"lines":[],"style":kind,"font_size":size}
    color = options.get("text_color") or spec["text_color"] or accent
    fill = options.get("fill") or spec["fill"]
    px = 48 if kind == "candy" else 34 if kind == "ribbon" else 24 if spec["background"] else 0
    py = 18 if spec["background"] else 0
    def measure(value):
        return font.getlength(value) + max(0, len(value) - 1) * tracking
    wrapped = wrap_lines(text, measure, max_width - 2 * px)
    line_h = size + 12
    text_h = len(wrapped) * line_h - 12
    w = min(max_width, max(48, math.ceil(max(measure(line) for line in wrapped))) + px * 2)
    h = text_h + py * 2 + (18 if kind == "underline" else 0)
    # Supersampling smooths decorative curves without raster font scaling.
    scale = 3
    image = Image.new("RGBA", (w * scale, h * scale))
    draw = ImageDraw.Draw(image)
    rgb = ImageColor.getrgb(fill)
    ink = ImageColor.getrgb(color)
    shade = tuple(round(channel * .9) for channel in rgb)
    def polygon(points, tint, outline=None):
        draw.polygon([(round(x * scale),round(y * scale)) for x,y in points],fill=tint)
        if outline:
            draw.line([(round(x*scale),round(y*scale)) for x,y in [*points,points[0]]],fill=outline,width=scale,joint="curve")
    def rectangle(box,tint,radius=0,outline=None):
        draw.rounded_rectangle(tuple(round(n*scale) for n in box),radius=radius*scale,fill=tint,outline=outline,width=scale)
    def line(points,tint,width=2):
        draw.line([(round(x*scale),round(y*scale)) for x,y in points],fill=tint,width=width*scale,joint="curve")
    if kind == "block":
        rectangle((5,5,w-1,h-1),(*ink,35),radius=2)
        rectangle((0,0,w-6,h-6),fill,radius=2,outline=(*ink,90))
        line([(9,9),(9,h-15)],(*ink,120),3)
    elif kind == "rounded":
        rectangle((2,4,w-1,h-1),(*ink,25),radius=(h-4)//2)
        rectangle((0,0,w-3,h-5),fill,radius=(h-5)//2)
        line([(24,8),(w-25,8)],(255,255,255,150),2)
    elif kind == "candy":
        polygon([(27,h*.26),(4,8),(8,h*.5),(4,h-8),(27,h*.74)],shade)
        polygon([(w-27,h*.26),(w-4,8),(w-8,h*.5),(w-4,h-8),(w-27,h*.74)],shade)
        for side in (1,-1):
            edge = 0 if side == 1 else w
            line([(edge+side*10,16),(edge+side*29,h*.45)],(*ink,75),1)
            line([(edge+side*10,h-16),(edge+side*29,h*.55)],(*ink,75),1)
        rectangle((25,3,w-25,h-3),fill,radius=16,outline=(*ink,65))
        line([(43,10),(w-43,10)],(255,255,255,170),2)
    elif kind == "wave":
        top = [(x,6+4*math.sin((x-6)*math.pi/16)) for x in range(6,w-5,2)]
        bottom = [(x,h-7+4*math.sin((x-6)*math.pi/16)) for x in range(w-6,5,-2)]
        polygon(top+bottom,fill,(*ink,85))
    elif kind == "ribbon":
        points=[(0,3),(w,3),(w-15,h/2),(w,h-3),(0,h-3),(15,h/2)]
        polygon(points,fill)
        line([(25,9),(w-25,9)],(255,255,255,170),2)
        line([(25,h-9),(w-25,h-9)],(*ink,55),1)
    elif kind == "underline":
        line([(x,h-8+3*math.sin(x*math.pi/14)) for x in range(1,w-1)],color,2)
    image = image.resize((w,h),Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    for i,value in enumerate(wrapped):
        # Center within the badge; plain text keeps its own left-aligned lines.
        x = (w-measure(value))/2 if spec["background"] else 0
        y = py + i*line_h
        if not tracking:
            draw.text((x,y),value,font=font,fill=color,anchor="lt")
        else:
            baseline = y-font.getbbox(value or "国",anchor="ls")[1]
            for j,ch in enumerate(value):
                draw.text((x+font.getlength(value[:j])+j*tracking,baseline),ch,font=font,fill=color,anchor="ls")
    return {"image":image,"width":w,"height":h,"lines":wrapped,"style":kind,"font_size":size}
