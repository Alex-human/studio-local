"""Deterministic motion templates. Pixel coordinates use the 1920 x 1080 design grid."""
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageColor, ImageOps, ImageChops

ASSETS = Path(__file__).resolve().parents[2] / 'assets'

def smooth(t):
    t = min(1, max(0, t))
    return t*t*t*(t*(t*6-15)+10)

def progress(t, start, length):
    return smooth((t-start)/max(length, .001))

def lerp(a, b, t):
    return a + (b-a)*t

@lru_cache(maxsize=128)
def font(size, weight=580, italic=False):
    preferred=ASSETS/'fonts/editorial'/('InterVariable-Italic.woff2' if italic else 'InterVariable.ttf')
    paths = [preferred] if preferred.exists() else list((ASSETS / 'fonts/editorial').glob('**/*Inter*.ttf'))
    if not paths:
        paths = list((ASSETS / 'fonts').glob('**/*.ttf'))
    f=ImageFont.truetype(str(paths[0]), max(8, int(size))) if paths else ImageFont.load_default(size=max(8,int(size)))
    try:
        axes=f.get_variation_axes()
        f.set_variation_by_axes([weight if a['name']==b'Weight' else a['default'] for a in axes])
    except (AttributeError,OSError): pass
    return f

def text(draw, xy, content, size=52, color='white', anchor='mm', weight=580):
    draw.text(xy, str(content), font=font(size,weight), fill=color, anchor=anchor, stroke_width=0)

def fit_text(content, max_width, size, weight=580):
    while size > 18 and max((font(size,weight).getlength(line) for line in str(content).splitlines()),default=0) > max_width:
        size -= 1
    return size

@lru_cache(maxsize=128)
def instagram_hook_layout(content, max_width, size):
    lines=[line.strip() for line in content.splitlines() if line.strip()]
    if len(lines)==1:
        words=lines[0].split()
        if len(words)>1:
            regular,italic=font(size,400),font(size,600,True)
            pairs=[(' '.join(words[:i]),' '.join(words[i:])) for i in range(1,len(words))]
            lines=list(min(pairs,key=lambda pair:max(regular.getlength(pair[0]),italic.getlength(pair[1]))+.2*abs(regular.getlength(pair[0])-italic.getlength(pair[1]))))
    while size>8 and any(font(size,600 if i==len(lines)-1 else 400,i==len(lines)-1).getlength(line)>max_width for i,line in enumerate(lines)):
        size-=1
    return lines,size

def instagram_hook_parts(draw, content, x, y, size, width, box=False):
    """Rows, underline and optional black card (as in vertical reels) of an editorial hook."""
    lines,size=instagram_hook_layout(content,width*.9 if box else width,size)
    rows=[]
    for i,line in enumerate(lines):
        last=i==len(lines)-1
        rows.append((line,font(size,600 if last else 400,last),y+(i-(len(lines)-1)/2)*size*1.2))
    line,face,cy=rows[-1];half=face.getlength(line)/2;stroke=max(2,round(size*.09))
    underline=(x-half,cy+size*.68,x+half,cy+size*.68)
    card=None
    if box:
        extents=[draw.textbbox((x,cy),'Hg',font=face,anchor='mm') for _,face,cy in rows]
        widest=max(face.getlength(line) for line,face,_ in rows)/2
        card=(x-widest-size*.5,extents[0][1]-size*.34,x+widest+size*.5,max(extents[-1][3],underline[1]+stroke)+size*.34)
    return rows,underline,stroke,card,size

def instagram_hook(draw, content, x, y, size, width, color, accent, box=False):
    rows,underline,stroke,card,size=instagram_hook_parts(draw,content,x,y,size,width,box)
    if card:draw.rounded_rectangle(card,radius=size*.28,fill=(0,0,0,255))
    for line,face,cy in rows:draw.text((x,cy),line,font=face,fill=color,anchor='mm')
    draw.line(underline,fill=accent,width=stroke)

@lru_cache(maxsize=128)
def sticker_hook_parts(content, x, y, size, width):
    """Instagram text sticker, with one black card per line: greedy lines, one padded black card per line."""
    face=ImageFont.truetype(str(ASSETS/'fonts/editorial/BarlowCondensed-Medium.ttf'),max(8,int(size)));lines=[]
    for paragraph in content.splitlines():
        line=''
        for word in paragraph.split():
            if line and face.getlength(line+' '+word)>width:lines.append(line);line=word
            else:line=(line+' '+word).strip()
        if line:lines.append(line)
    lines=lines or [' '];pitch,height,radius=size*1.155,size*1.715,size*.19
    half=[face.getlength(line)/2+size*.405 for line in lines]
    for i in range(len(half)-1):  # near-equal neighbours share one edge
        if abs(half[i]-half[i+1])<radius*1.5:half[i]=half[i+1]=max(half[i],half[i+1])
    tops=[y-(height+(len(lines)-1)*pitch)/2+i*pitch for i in range(len(lines))]
    edges=sorted({*tops,*[top+height for top in tops]});bands=[]
    for a,b in zip(edges,edges[1:]):  # cards overlap; the wider one wins
        w=max(h for top,h in zip(tops,half) if top<=a and b<=top+height)
        if bands and bands[-1][2]==x+w:bands[-1]=(x-w,bands[-1][1],x+w,b)
        else:bands.append((x-w,a,x+w,b))
    return face,[(line,top+size*1.207) for line,top in zip(lines,tops)],bands,radius

def sticker_outline(bands, radius):
    """Outline of stacked bands (left, top, right, bottom) as complex points: rounded outside, filleted where the width steps."""
    corners=[complex(r,v) for l,t,r,b in bands for v in (t,b)]+[complex(l,v) for l,t,r,b in reversed(bands) for v in (b,t)];points=[]
    for i,cur in enumerate(corners):
        prev,nxt=corners[i-1],corners[(i+1)%len(corners)]
        din,dout=abs(cur-prev),abs(nxt-cur);rad=min(radius,din/2,dout/2)
        a,b=cur-(cur-prev)/din*rad,cur+(nxt-cur)/dout*rad;c=a+b-cur
        points+=[c+(a-c)*math.cos(q)+(b-c)*math.sin(q) for q in (math.pi/2*k/6 for k in range(7))]
    return points

def sticker_hook(layer, content, x, y, size, width, color):
    face,rows,bands,radius=sticker_hook_parts(content,x,y,size,width)
    left,top=math.floor(min(b[0] for b in bands)),math.floor(bands[0][1])
    w,h=math.ceil(max(b[2] for b in bands))-left+1,math.ceil(bands[-1][3])-top+1
    mask=Image.new('L',(w*4,h*4))  # supersampled: Pillow polygons are not antialiased; vertices rounded so a sprite's integer shift cannot move one across a subsample
    ImageDraw.Draw(mask).polygon([(round((p.real-left)*4,6),round((p.imag-top)*4,6)) for p in sticker_outline(bands,radius)],fill=255)
    layer.paste((0,0,0,255),(left,top),mask.resize((w,h),Image.BOX))
    draw=ImageDraw.Draw(layer)
    for line,base in rows:draw.text((x,base),line,font=face,fill=color,anchor='ms')

def title_layer(size, props, enter=1, origin=(0,0), canvas_width=None):
    """Canonical title glyphs, also used on a small transparent preview surface."""
    w=canvas_width or size[0];sc=w/1920
    layer=Image.new('RGBA',size);d=ImageDraw.Draw(layer)
    x=float(props.get('x',960))*sc-origin[0]
    y=(float(props.get('y',540))+(1-enter)*35)*sc-origin[1]
    title=props.get('text','Tu idea, con claridad');accent=props.get('accent','#75b8ff')
    color=props.get('color','#ffffff');font_size=float(props.get('size',72))*sc
    if props.get('style')=='instagram':
        instagram_hook(d,title,x,y,font_size,w*.86,color,accent,props.get('box',False))
    elif props.get('style')=='sticker':sticker_hook(layer,title,x,y,font_size,w*.86,color)
    else:
        weight=props.get('weight',580);font_size=fit_text(title,w*.86,font_size,weight)
        shadow=Image.new('RGBA',size)
        text(ImageDraw.Draw(shadow),(x,y+3*sc),title,font_size,(0,0,0,220),weight=weight)
        layer=Image.alpha_composite(layer,shadow.filter(ImageFilter.GaussianBlur(6*sc)))
        d=ImageDraw.Draw(layer);text(d,(x,y),title,font_size,color,weight=weight)
        if props.get('subtitle'):text(d,(x,y+font_size*.9),props['subtitle'],font_size*.43,accent)
    return layer

def caption_layer(size, content, origin=(0,0), canvas_size=None):
    w,h=canvas_size or size;sc=w/1920
    layer=Image.new('RGBA',size);d=ImageDraw.Draw(layer);lines=content.split('\n')[:3]
    for i,line in enumerate(lines):
        font_size=fit_text(line,w*.85,48*sc)
        y=h*.88+(i-(len(lines)-1))*font_size*1.3
        d.text((w/2-origin[0],y-origin[1]),line,font=font(font_size),fill='white',anchor='mm',
            stroke_width=max(1,int(2*sc)),stroke_fill=(0,0,0,190))
    return layer

def text_sprite(size, props=None, caption=None):
    """Tight rest-position glyph texture; integer translation keeps Pillow rasterization."""
    w,h=size;sc=w/1920;d=ImageDraw.Draw(Image.new('L',(1,1)));boxes=[]
    def bounds(x,y,content,font_size,weight=580,italic=False,stroke=0,pad=0):
        box=d.textbbox((x,y),str(content),font=font(font_size,weight,italic),anchor='mm',stroke_width=stroke)
        boxes.append((box[0]-pad,box[1]-pad,box[2]+pad,box[3]+pad))
    if caption is not None:
        lines=caption.split('\n')[:3]
        for i,line in enumerate(lines):
            font_size=fit_text(line,w*.85,48*sc);y=h*.88+(i-(len(lines)-1))*font_size*1.3
            bounds(w/2,y,line,font_size,stroke=max(1,int(2*sc)))
    else:
        x=float(props.get('x',960))*sc;y=float(props.get('y',540))*sc
        title=props.get('text','Tu idea, con claridad');font_size=float(props.get('size',72))*sc
        if props.get('style')=='instagram':
            rows,underline,stroke,card,font_size=instagram_hook_parts(d,title,x,y,font_size,w*.86,props.get('box',False))
            for i,(line,_,cy) in enumerate(rows):
                last=i==len(rows)-1;bounds(x,cy,line,font_size,600 if last else 400,last)
            boxes.append((underline[0]-stroke,underline[1]-stroke,underline[2]+stroke,underline[3]+stroke))
            if card:boxes.append((card[0]-1,card[1]-1,card[2]+1,card[3]+1))
        elif props.get('style')=='sticker':
            face,rows,bands,_=sticker_hook_parts(title,x,y,font_size,w*.86)
            boxes+=[(l-1,t-1,r+2,b+2) for l,t,r,b in bands]+[d.textbbox((x,base),line,font=face,anchor='ms') for line,base in rows]
        else:
            weight=props.get('weight',580);font_size=fit_text(title,w*.86,font_size,weight)
            bounds(x,y,title,font_size,weight)
            bounds(x,y+3*sc,title,font_size,weight,pad=math.ceil(24*sc+4))
            if props.get('subtitle'):bounds(x,y+font_size*.9,props['subtitle'],font_size*.43)
    if not boxes:return Image.new('RGBA',(1,1)),[0,0,1,1]
    # Titles may rest just outside the canvas and enter it during their vertical
    # motion. Keep that overscan, while bounding pathological multiline strings.
    margin=math.ceil(35*sc+24*sc+4) if caption is None else 0
    left=max(-margin,math.floor(min(b[0] for b in boxes)));top=max(-margin,math.floor(min(b[1] for b in boxes)))
    right=min(w+margin,math.ceil(max(b[2] for b in boxes))+1);bottom=min(h+margin,math.ceil(max(b[3] for b in boxes))+1)
    if right<=left or bottom<=top:return Image.new('RGBA',(1,1)),[0,0,1,1]
    extent=(right-left,bottom-top);origin=(left,top)
    layer=caption_layer(extent,caption,origin,size) if caption is not None else title_layer(extent,props,origin=origin,canvas_width=w)
    box=layer.getbbox()
    if box is None:return Image.new('RGBA',(1,1)),[0,0,1,1]
    return layer.crop(box),[left+box[0],top+box[1],box[2]-box[0],box[3]-box[1]]

@lru_cache(maxsize=12)
def stage(w, h, color='#163768'):
    rgb = ImageColor.getrgb(color)
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.clip(1-np.sqrt(((xx/w-.45)*.9)**2+((yy/h-.4)*.8)**2)*1.35, 0, 1)
    arr = np.zeros((h,w,3), np.uint8)
    for i in range(3):
        dark=(4,12,30)[i]
        arr[:,:,i] = dark + r*(rgb[i]-dark)
    return Image.fromarray(arr).convert('RGBA')

def rounded_video(video, width, height, radius):
    width, height = max(2,int(width)), max(2,int(height))
    image = video.resize((width,height), Image.Resampling.LANCZOS).convert('RGBA')
    mask = Image.new('L', (width,height))
    ImageDraw.Draw(mask).rounded_rectangle((0,0,width,height), max(0,radius), fill=255)
    image.putalpha(mask)
    return image

def glass_panel(w,h,radius,backdrop=None):
    w,h=max(2,int(w)),max(2,int(h))
    yy,xx=np.mgrid[0:h,0:w]; u=(xx/w+yy/h)/2
    arr=np.zeros((h,w,4),np.uint8)
    for i,(a,b) in enumerate(zip((181,222,255),(25,103,204))):arr[:,:,i]=a*(1-u)+b*u
    arr[:,:,3]=(58+30*np.abs(u-.45)).astype(np.uint8)
    surface=Image.fromarray(arr)
    if backdrop is not None:surface=Image.alpha_composite(backdrop.resize((w,h)).convert('RGBA').filter(ImageFilter.GaussianBlur(max(1,w/28))),surface)
    mask=Image.new('L',(w,h));ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),radius,fill=255);surface.putalpha(mask)
    d=ImageDraw.Draw(surface);d.rounded_rectangle((0,0,w-1,h-1),radius,outline=(192,229,255,180),width=max(1,round(w/110)))
    if radius>=2:
        d.arc((1,1,max(2,min(w-2,radius*2)),max(2,min(h-2,radius*2))),180,270,fill=(250,255,255,235),width=max(1,round(w/80)))
    return surface

def badge(n, size, angle=0, accent='#6db5ff',backdrop=None):
    s = max(20,int(size))
    img=Image.new('RGBA',(s+40,s+40))
    shadow=Image.new('RGBA',img.size);ImageDraw.Draw(shadow).rounded_rectangle((20,25,s+19,s+24),radius=s*.34,fill=(0,15,40,120));img=shadow.filter(ImageFilter.GaussianBlur(max(2,s*.06)))
    panel=glass_panel(s,s,s*.34,backdrop);img.alpha_composite(panel,(20,20))
    d=ImageDraw.Draw(img)
    text(d,(20+s/2,20+s/2+2),n,s*.5125,'#173861')
    text(d,(20+s/2,20+s/2),n,s*.5125,'#ffffff')
    if angle:
        img=img.rotate(angle,Image.Resampling.BICUBIC,expand=True)
    return img

def channel_intro(base, t, props):
    """Editable recreation of the approved reveal: source video stays live, not baked."""
    w,h=base.size; scale=w/1920
    intro=progress(t,.26,.52); grow=progress(t,1.54,1.04); back=progress(t,5.45,1.04)
    opacity=1-progress(t,1.54,.52)
    bg=stage(w,h,props.get('background','#163768')).copy()
    if opacity>0:
        bg=Image.blend(bg,base.convert('RGBA'),opacity)
    x=lerp(160,0,back)*scale
    y=(lerp(lerp(600,150,grow),0,back)+(1-intro)*300)*scale
    cw=lerp(lerp(350,1080,grow),1920,back)*scale
    ch=lerp(lerp(100,607.5,grow),1080,back)*scale
    press=1-.035*math.sin(math.pi*progress(t,1.4,.42))
    cw*=press; ch*=press
    radius=int(lerp(32,0,back)*scale)
    if intro>0:
        shadow=Image.new('RGBA',(w,h)); sd=ImageDraw.Draw(shadow)
        sd.rounded_rectangle((x,y+18*scale,x+cw,y+ch+18*scale),radius,fill=(0,0,0,int(120*(1-back)*intro)))
        bg=Image.alpha_composite(bg,shadow.filter(ImageFilter.GaussianBlur(24*scale)))
        reveal=progress(t,1.83,.64)
        if reveal>=.999:
            panel=rounded_video(base,cw,ch,radius)
        else:
            panel=glass_panel(cw,ch,radius,bg.crop((int(x),int(y),int(x+cw),int(y+ch))))
        if 0<reveal<.999:
            video=rounded_video(base,cw,ch,radius)
            panel=Image.blend(panel,video,reveal)
        label=1-progress(t,1.56,.43)
        if label>0:
            ld=ImageDraw.Draw(panel)
            cx=cw/2; cy=ch/2
            ld.polygon([(cx-112*scale,cy-15*scale),(cx-112*scale,cy+15*scale),(cx-86*scale,cy)],fill=(255,255,255,int(255*label)))
            text(ld,(cx+25*scale,cy),props.get('title','Tu canal'),36*scale,(255,255,255,int(255*label)))
        panel.putalpha(panel.getchannel('A').point(lambda a:int(a*intro)))
        bg.alpha_composite(panel,(int(x),int(y)))
    d=ImageDraw.Draw(bg)
    if .82<t<2.1:
        p=progress(t,.82,.62); a=p*(1-progress(t,1.58,.42))
        px=lerp(490,366,p)*scale; py=lerp(800,640,p)*scale
        d.polygon([(px,py),(px+4*scale,py+45*scale),(px+16*scale,py+32*scale),(px+31*scale,py+30*scale)],fill=(255,255,255,int(a*255)),outline=(10,25,45,255),width=max(1,int(2*scale)))
    for n in range(1,min(5,int(props.get('count',3)))+1):
        p=progress(t,3.88+(n-1)*.27,.62)
        if p<=0: continue
        cy=250+(n-1)*240; dock=progress(t,5.45+(n-1)*.13,1.10)
        dx=lerp(1580,160+(n-1)*125,smooth((dock-.25)/.75))*scale
        dy=lerp(cy,110,smooth(dock/.65))*scale
        ds=lerp(1,.55,dock)*scale
        a=1-progress(t,5.45,.5)
        if a>0:
            sx=1240*scale; sy=lerp(390,520,(n-1)/2)*scale
            points=[]
            for step in range(41):
                u=step/40*p
                px=(1-u)**3*sx+3*(1-u)**2*u*1360*scale+3*(1-u)*u*u*1390*scale+u**3*1470*scale
                py=(1-u)**3*sy+3*(1-u)**2*u*sy+3*(1-u)*u*u*cy*scale+u**3*cy*scale
                points.append((px,py))
            d.line(points,fill=props.get('accent','#65a5ff'),width=max(1,int(4*scale)))
            if p>.95:d.line([(1458*scale,(cy-10)*scale),(1472*scale,cy*scale),(1458*scale,(cy+10)*scale)],fill=props.get('accent','#65a5ff'),width=max(1,int(4*scale)))
        bs=160*ds*(.84+.16*p)
        b=badge(n,bs,-(1-p)*12,props.get('accent','#65a5ff'),bg.crop((int(dx-bs/2),int(dy-bs/2),int(dx+bs/2),int(dy+bs/2))))
        b.putalpha(b.getchannel('A').point(lambda z:int(z*p)))
        bg.alpha_composite(b,(int(dx-b.width/2),int(dy-b.height/2+(1-p)*40*scale)))
    return bg

def keyframed(props, keys, local):
    props=dict(props)
    for key, points in keys.items():
        if not points: continue
        points=sorted(points,key=lambda q:q['frame'])
        value=points[0]['value']
        for a,b in zip(points,points[1:]):
            if local>=b['frame']: value=b['value']; continue
            if local>=a['frame']:
                value=lerp(a['value'],b['value'],smooth((local-a['frame'])/max(1,b['frame']-a['frame'])))
            break
        props[key]=value
    return props

@lru_cache(maxsize=4)
def source_image(path, modified):
    with Image.open(path) as source:return ImageOps.exif_transpose(source).convert('RGBA')

def image_motion(props, seconds):
    animation=props.get('animation','pop');u=min(1,max(0,seconds/max(.01,props.get('enter',.48))))
    eased=1-(1-u)**4
    dx=dy=0;scale=1;alpha=1
    if animation!='none':
        alpha=min(1,u*4)
        if animation=='pop':scale=.88+.12*eased
        if animation=='from-left':dx=-180*(1-eased)
        if animation=='from-right':dx=180*(1-eased)
        if animation=='from-top':dy=-150*(1-eased)
        if animation=='from-bottom':dy=150*(1-eased)
    return dx,dy,scale,alpha

def image_layer(size, project, props, seconds, source=None, decorate=True):
    w,h=size;sc=w/1920;layer=Image.new('RGBA',size)
    if source is None:
        asset=next((a for a in project['assets'] if a['id']==props.get('asset')),None)
        if not asset:return layer
        source=source_image(asset['path'],Path(asset['path']).stat().st_mtime_ns)
    source=source.convert('RGBA')
    sw,sh=source.size
    left=min(sw-1,max(0,round(sw*props.get('cropLeft',0))));top=min(sh-1,max(0,round(sh*props.get('cropTop',0))))
    box=(left,top,max(left+1,round(sw*(1-props.get('cropRight',0)))),max(top+1,round(sh*(1-props.get('cropBottom',0)))))
    im=source.crop(box); dx,dy,scale,alpha=image_motion(props,seconds)
    iw=max(2,round(props.get('width',760)*sc*scale));ih=max(2,round(iw*im.height/max(1,im.width)))
    im=im.resize((iw,ih),Image.Resampling.LANCZOS)
    photo=props.get('style','photo')=='photo';pad=max(2,round(12*sc)) if photo else 0
    panel=Image.new('RGBA',(iw+2*pad,ih+2*pad));d=ImageDraw.Draw(panel)
    if photo:d.rounded_rectangle((0,0,panel.width-1,panel.height-1),max(2,18*sc),fill='#f6f7fa')
    if decorate:
        mask=Image.new('L',im.size);ImageDraw.Draw(mask).rounded_rectangle((0,0,iw-1,ih-1),max(1,8*sc),fill=255)
        im.putalpha(ImageChops.multiply(im.getchannel('A'),mask))
    panel.alpha_composite(im,(pad,pad))
    if props.get('rotation',0):panel=panel.rotate(-props['rotation'],Image.Resampling.BICUBIC,expand=True)
    x=(props.get('x',960)+dx)*sc-panel.width/2;y=(props.get('y',540)+dy)*sc-panel.height/2
    if decorate:
        shadow=Image.new('RGBA',size);silhouette=Image.new('RGBA',panel.size,(0,0,0,0));silhouette.putalpha(panel.getchannel('A').point(lambda a:int(a*.32)))
        shadow.alpha_composite(silhouette,(round(x),round(y+12*sc)))
        layer=shadow.filter(ImageFilter.GaussianBlur(max(1,18*sc)))
    layer.alpha_composite(panel,(round(x),round(y)))
    layer.putalpha(layer.getchannel('A').point(lambda a:int(a*alpha)))
    return layer

def opaque_box(g, project, frame, size):
    """(x, y, width, height) of video overlay g at frame when it paints fully opaque, with the same maths as image_layer
    and composite; None otherwise."""
    if g.get('type')!='video' or g.get('hidden') or not g['start']<=frame<g['start']+g['length']:return None
    local=frame-g['start']+g.get('offset',0);p=keyframed(g.get('props',{}),g.get('keyframes',{}),local)
    if p.get('style','photo')=='photo' or p.get('rotation',0) or any(p.get(k,0) for k in ('cropLeft','cropTop','cropRight','cropBottom')):return None
    dx,dy,scale,alpha=image_motion(p,local/project['fps'])
    if alpha<1 or float(p.get('opacity',1))<1:return None
    a=next(x for x in project['assets'] if x['id']==g['asset']);w,h=size;sc=w/1920
    iw=max(2,round(p.get('width',760)*sc*scale));ih=max(2,round(iw*a['height']/max(1,a['width'])))
    return round((p.get('x',960)+dx)*sc-iw/2),round((p.get('y',540)+dy)*sc-ih/2),iw,ih

def covers(g, project, frame, size, video_frames=None):
    if video_frames and g['id'] in video_frames and video_frames[g['id']].mode!='RGB':return False   # a source with alpha may show what lies below
    box=opaque_box(g,project,frame,size)
    return box is not None and box[0]<=0 and box[1]<=0 and box[0]+box[2]>=size[0] and box[1]+box[3]>=size[1]

def hidden_base(project, frame, size, video_frames=None):
    return any(covers(g,project,frame,size,video_frames) for g in project['graphics'])

def composite(base, project, frame, video_frames=None, size=None):
    # Painting starts at the topmost overlay that hides the canvas: what lies below it cannot show (base may then be None).
    w,h=size or base.size; sc=w/1920
    order=sorted(project['graphics'],key=lambda item:item.get('type')!='video')
    top=next((i for i in range(len(order)-1,-1,-1) if covers(order[i],project,frame,(w,h),video_frames)),-1)
    if top>=0 and video_frames and order[top]['id'] in video_frames and video_frames[order[top]['id']].size==(w,h)\
       and opaque_box(order[top],project,frame,(w,h))==(0,0,w,h)\
       and not any(not g.get('hidden') and g['start']<=frame<g['start']+g['length'] for g in order[top+1:])\
       and not any(not c.get('hidden') and c['start']<=frame<c['start']+c['length'] for c in project['captions']):
        return video_frames[order[top]['id']].convert('RGB')   # the canvas is exactly that overlay frame
    image=base.convert('RGBA') if top<0 else None
    for g in order[max(0,top):]:
        if g.get('hidden') or not g['start']<=frame<g['start']+g['length']: continue
        local=frame-g['start']+g.get('offset',0); t=local/project['fps']
        p=keyframed(g.get('props',{}),g.get('keyframes',{}),local)
        if g['type']=='channel_intro':
            image=channel_intro(image,t,p); continue
        layer=Image.new('RGBA',(w,h)); d=ImageDraw.Draw(layer)
        enter=progress(t,0,float(p.get('enter',.45)))
        exitp=progress((g.get('motionLength',g['length'])-local)/project['fps'],0,.2)
        alpha=enter*exitp*float(p.get('opacity',1))
        x=float(p.get('x',960))*sc; y=(float(p.get('y',540))+(1-enter)*35)*sc
        title=p.get('text','Tu idea, con claridad'); accent=p.get('accent','#75b8ff')
        color=p.get('color','#ffffff')
        kind=g['type']
        if kind=='title':
            layer=title_layer((w,h),p,enter)
        elif kind=='lower_third':
            y=float(p.get('y',880))*sc; x=float(p.get('x',150))*sc
            d.rounded_rectangle((x-25*sc,y-52*sc,x+800*sc,y+98*sc),20*sc,fill=(9,19,33,215))
            d.rounded_rectangle((x-25*sc,y-52*sc,x-18*sc,y+98*sc),3*sc,fill=accent)
            text(d,(x+8*sc,y),title,fit_text(title,750*sc,52*sc),color,'lm')
            text(d,(x+8*sc,y+55*sc),p.get('subtitle',''),30*sc,'#a6b5c9','lm')
        elif kind=='stat':
            value=p.get('value',100); shown=round(float(value)*enter)
            text(d,(x,y-25*sc),str(shown)+p.get('suffix','%'),140*sc,color)
            text(d,(x,y+90*sc),title,fit_text(title,1500*sc,40*sc),accent)
        elif kind=='cards':
            labels=p.get('labels',['Idea','Proceso','Resultado'])[:5]
            for i,label in enumerate(labels):
                ep=progress(t,i*.13,.6); bw=360*sc; bx=x+(i-(len(labels)-1)/2)*410*sc
                by=y+(1-ep)*55*sc
                d.rounded_rectangle((bx-bw/2,by-100*sc,bx+bw/2,by+100*sc),24*sc,fill=(228,240,253,int(240*ep)),outline=(255,255,255,int(255*ep)),width=max(1,int(2*sc)))
                text(d,(bx,by),label,fit_text(label,310*sc,38*sc),'#152b49')
        elif kind=='progress':
            frac=min(1,max(0,float(p.get('value',.75))*enter)); bw=1000*sc
            d.rounded_rectangle((x-bw/2,y,x+bw/2,y+16*sc),8*sc,fill=(255,255,255,40))
            if frac: d.rounded_rectangle((x-bw/2,y,x-bw/2+bw*frac,y+16*sc),8*sc,fill=accent)
            text(d,(x,y-55*sc),title,44*sc,color)
        elif kind=='video':
            if video_frames is None or g['id'] not in video_frames:raise ValueError('Falta el fotograma del vídeo superpuesto')
            layer=image_layer((w,h),project,p,t,source=video_frames[g['id']],decorate=p.get('style','clean')=='photo')
            alpha=float(p.get('opacity',1))
        elif kind=='image':
            layer=image_layer((w,h),project,p,t)
            alpha=exitp*float(p.get('opacity',1))
        layer.putalpha(layer.getchannel('A').point(lambda a:int(a*max(0,min(1,alpha)))))
        image=layer if image is None else Image.alpha_composite(image,layer)
    for c in project['captions']:
        if c['start']<=frame<c['start']+c['length'] and not c.get('hidden'):
            layer=caption_layer((w,h),c['text'])
            image=Image.alpha_composite(image,layer)
    return image.convert('RGB')
