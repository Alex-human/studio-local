"""Direct-source playback plan with independent audio and visual-region caches."""
import copy
import hashlib
import json
import os
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from PIL import Image, PngImagePlugin
import graphics
import project
import render
import sounds

CACHE_VERSION=8

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:28]

def media_signature(asset):
    path=Path(asset['path']);stat=path.stat()
    return dict(path=str(path.resolve()),bytes=stat.st_size,modified=stat.st_mtime_ns,**({'lut':asset['lut']} if 'lut' in asset else {}))

def audible_key(p,native_images=False):
    """Native image cues do not invalidate the base mix; legacy playback keeps them."""
    specs=[];offset=0;assets={a['id']:a for a in p['assets']}
    keys=('in','length','speed','volumeDb','fadeIn','fadeOut','fadeOffset','fadeLength')
    for c in p['clips']:
        a=assets[c['asset']]
        if a.get('audio') and not c.get('muted'):
            specs.append(dict(role='voice',start=offset,source=media_signature(a),**{k:c[k] for k in keys if k in c}))
        offset+=c['length']
    for a in p['audio']:
        if a.get('muted') or a['start']>=offset:continue
        specs.append(dict(role=a['role'],start=a['start'],source=media_signature(assets[a['asset']]),**{k:a[k] for k in keys if k in a}))
    for a in p['graphics']:
        if a.get('type')!='video' or a.get('hidden') or a.get('muted') or a['start']>=offset or not assets[a['asset']].get('audio'):continue
        specs.append(dict(role='voice',start=a['start'],source=media_signature(assets[a['asset']]),**{k:a[k] for k in keys if k in a}))
    if not native_images:
        for g in p['graphics']:
            props=g.get('props',{})
            if g.get('hidden') or g['type']!='image' or not props.get('sound') or props.get('animation','pop')=='none':continue
            specs.append(dict(role='image-sound',start=g['start'],length=g['length'],offset=g.get('offset',0),props={k:props.get(k) for k in ('enter','soundDb')}))
    return digest(dict(version=CACHE_VERSION,fps=p['fps'],frames=offset,mixer=p['mixer'],ducking=p.get('ducking',False),specs=specs))

def native_image(item, motion=False):
    """The host advertises animated-image support; older hosts keep exact rendering."""
    return item.get('type')=='image' and (motion or not item.get('keyframes'))

def native_title(item):
    return item.get('type')=='title' and not (set(item.get('keyframes',{}))-{'opacity'})

def native_video_layer(item,p,video):
    if not video or item.get('type')!='video':return False
    asset=next(a for a in p['assets'] if a['id']==item['asset'])
    return Path(asset['path']).suffix.lower() in ('.mp4','.mov','.m4v')

def native_modes(p,native_images=False,native_text=False,motion=False,video=False):
    """The new compositor owns the complete stack, or the renderer keeps that stack."""
    if native_text:
        compatible=all(g.get('hidden') or native_image(g,motion) or native_title(g) or native_video_layer(g,p,video) for g in p['graphics'])
        return compatible,compatible
    return native_images,False

def native_overlay(item,kind,native_images,native_text,motion=False,video=False):
    return native_text if kind=='captions' else (native_images and native_image(item,motion)) or (native_text and native_title(item)) or (video and item.get('type')=='video')

def window(p,start,end,native_images=False,native_text=False,motion=False,video=False):
    """A visual-only immutable interval. Preserve source sampling and motion phase."""
    native_images,native_text=native_modes(p,native_images,native_text,motion,video)
    out=copy.deepcopy(p);out['clips']=[];out['audio']=[];offset=0
    for c in p['clips']:
        first=max(start,offset);last=min(end,offset+c['length'])
        if last>first:
            item=project.slice_item(c,'clips',first-offset,last-offset);item['muted']=True;out['clips'].append(item)
        offset+=c['length']
    for kind in ('graphics','captions'):
        out[kind]=[]
        for item in p[kind]:
            if native_overlay(item,kind,native_images,native_text,motion,video):continue
            first=max(start,item['start']);last=min(end,item['start']+item['length'])
            if last<=first or item.get('hidden'):continue
            new=project.slice_item(item,kind,first-item['start'],last-item['start'])
            new['start']=first-start
            if kind=='graphics':new.setdefault('props',{})['sound']=False
            out[kind].append(new)
    return out

def visual_key(p,native_images=False,native_text=False,motion=False,video=False):
    native_images,native_text=native_modes(p,native_images,native_text,motion,video)
    assets={a['id']:a for a in p['assets']};used={c['asset'] for c in p['clips']}
    used.update(g['props']['asset'] for g in p['graphics'] if not g.get('hidden') and g['type']=='image' and not native_overlay(g,'graphics',native_images,native_text,motion,video))
    used.update(g['asset'] for g in p['graphics'] if not g.get('hidden') and g['type']=='video' and not video)
    asset_ids={id:media_signature(assets[id]) for id in used}
    def clean(item,kind):
        keys={'clips':('asset','in','length','speed','zoom','zoomEnd','x','y','color','motionOffset','motionLength'),
              'graphics':('type','asset','in','speed','start','length','offset','motionLength','props','keyframes'),
              'captions':('start','length','offset','motionLength','text')}
        return {k:item[k] for k in keys[kind] if k in item}
    return digest(dict(version=CACHE_VERSION,fps=p['fps'],width=p['width'],height=p['height'],assets=asset_ids,
        **{kind:[clean(x,kind) for x in p[kind] if not x.get('hidden') and (kind=='clips' or not native_overlay(x,kind,native_images,native_text,motion,video))] for kind in ('clips','graphics','captions')}))

def retimed(a,p):return abs(a.get('fps',0)-p['fps'])>=.01

def direct(c,a,p,video=False):
    if p.get('_forcePreviewRender'):return False
    if video:
        # A file at another frame rate plays directly on hosts that sample it with the
        # exporter's phase; speed changes and fractional entries stay canonical.
        return (Path(a['path']).suffix.lower() in ('.mp4','.mov','.m4v') and
                (p.get('_nativeRetime') or not retimed(a,p)) and c.get('speed',1)==1 and
                abs(c.get('in',0)-round(c.get('in',0)))<1e-7)
    color=c.get('color',{})
    return (Path(a['path']).suffix.lower() in ('.mp4','.mov','.m4v') and 'lut' not in a and
        abs(a.get('fps',0)-p['fps'])<.01 and c.get('speed',1)==1 and
        c.get('zoom',1)==c.get('zoomEnd',c.get('zoom',1))==1 and
        c.get('x',.5)==c.get('y',.5)==.5 and
        all(color.get(k,default)==default for k,default in [('exposure',0),('contrast',1),('saturation',1),('temperature',0)]))

def regions(p,native_images=False,native_text=False,motion=False,video=False):
    native_images,native_text=native_modes(p,native_images,native_text,motion,video)
    assets={a['id']:a for a in p['assets']};offset=0;result=[]
    visuals=[g for kind in ('graphics','captions') for g in p[kind] if not g.get('hidden') and not native_overlay(g,kind,native_images,native_text,motion,video)]
    chunk=max(1,round(p['fps']*4))
    for c in p['clips']:
        end=offset+c['length'];points={offset,end}
        overlaps=[g for g in visuals if g['start']<end and g['start']+g['length']>offset]
        for g in overlaps:points.update((max(offset,g['start']),min(end,g['start']+g['length'])))
        points=sorted(points);a=assets[c['asset']]
        for first,last in zip(points,points[1:]):
            affected=not direct(c,a,p,video) or any(g['start']<last and g['start']+g['length']>first for g in overlaps)
            if affected:
                for start in range(first,last,chunk):result.append(dict(start=start,end=min(start+chunk,last),cached=True))
            else:
                clip=project.slice_item(c,'clips',first-offset,last-offset)
                result.append(dict(start=first,end=last,cached=False,path=a['path'],sourceIn=clip.get('in',0),clip=clip,lut=a.get('lut'),retime=retimed(a,p)))
        offset=end
    return result

def image_layers(p,motion=False):
    assets={a['id']:a for a in p['assets']};result=[]
    for g in p['graphics']:
        if g.get('hidden') or not native_image(g,motion):continue
        props=g.get('props',{});asset=assets[props['asset']]
        result.append(dict(path=asset['path'],sourceWidth=asset['width'],sourceHeight=asset['height'],
            start=g['start'],length=g['length'],offset=g.get('offset',0),motionLength=g.get('motionLength',g['length']),props=props,
            keyframes={key:sorted(copy.deepcopy(points),key=lambda point:point['frame']) for key,points in g.get('keyframes',{}).items()}))
    return result

def text_layer(item,kind,size,cache):
    """Cache only static glyph pixels; timing, fades and keyframes stay editable."""
    props={k:v for k,v in item.get('props',{}).items() if k not in ('enter','opacity')}
    content=dict(caption=item['text']) if kind=='captions' else dict(props=props)
    path=cache/f'text-{digest(dict(version=CACHE_VERSION,size=size,**content))}.png'
    rect=None
    if path.exists():
        try:
            with Image.open(path) as source:rect=json.loads(source.info['rect'])
        except (OSError,KeyError,ValueError):pass
    if rect is None:
        sprite,rect=graphics.text_sprite(size,**content)
        metadata=PngImagePlugin.PngInfo();metadata.add_text('rect',json.dumps(rect,separators=(',',':')))
        with tempfile.NamedTemporaryFile(prefix='.text-',suffix='.png',dir=cache,delete=False) as temp:temp_path=Path(temp.name)
        try:
            sprite.save(temp_path,format='PNG',pnginfo=metadata)
            os.replace(temp_path,path)
        finally:temp_path.unlink(missing_ok=True)
    animation=dict(animation='none') if kind=='captions' else dict(enter=item.get('props',{}).get('enter',.45),opacity=item.get('props',{}).get('opacity',1))
    return dict(kind='text',path=str(path),start=item['start'],length=item['length'],offset=item.get('offset',0),
        motionLength=item.get('motionLength',item['length']),props=animation,
        keyframes={key:sorted(copy.deepcopy(points),key=lambda point:point['frame']) for key,points in item.get('keyframes',{}).items()},
        rect=rect,canvasWidth=size[0],canvasHeight=size[1])

def overlay_layers(p,size,cache,motion=False):
    """Graphics retain project order; the canonical caption pass is always last."""
    images=iter(image_layers(p,motion));result=[]
    for item in p['graphics']:
        if item.get('hidden') or item.get('type')=='video':continue
        result.append(next(images) if native_image(item,motion) else text_layer(item,'graphics',size,cache))
    result.extend(text_layer(item,'captions',size,cache) for item in p['captions'] if not item.get('hidden'))
    return result

def image_cues(p,cache):
    total=project.duration(p)/p['fps'];result=[]
    for g in p['graphics']:
        props=g.get('props',{});animation=props.get('animation','pop')
        if g.get('hidden') or g.get('type')!='image' or not props.get('sound') or animation=='none':continue
        source=g.get('offset',0)/p['fps'];start=g['start']/p['fps'];duration=max(.12,min(2,float(props.get('enter',.48))))
        if source>=duration or start>=total:continue
        cue=cache/f'cue-{digest(dict(version=CACHE_VERSION,duration=duration))}.wav'
        if not cue.exists():
            with tempfile.NamedTemporaryFile(prefix='.cue-',suffix='.wav',dir=cache,delete=False) as temp:temp_path=Path(temp.name)
            try:sounds.motion_sound(temp_path,animation,duration);os.replace(temp_path,cue)
            finally:temp_path.unlink(missing_ok=True)
        result.append(dict(id=g['id'],path=str(cue),start=start,source=source,length=min(duration-source,g['length']/p['fps'],total-start),
            volume=project.audio_gain(props.get('soundDb',-18))*project.audio_gain(p['mixer']['sfx'])))
    return result

def audio_layers(p):
    """Unmixed source segments for instant native preview; export remains unchanged."""
    assets={a['id']:a for a in p['assets']};result=[];offset=0;duration=project.duration(p)
    for clip in p['clips']:
        asset=assets[clip['asset']]
        if asset.get('audio'):
            result.append(dict(id=clip['id'],path=asset['path'],start=offset/p['fps'],source=clip.get('in',0)/p['fps'],
                length=clip['length']/p['fps'],speed=clip.get('speed',1),role='voice',
                volume=(0 if clip.get('muted') else project.audio_gain(clip.get('volumeDb',0))*project.audio_gain(p['mixer']['voice'])),
                fadeIn=clip.get('fadeIn',0)/p['fps'],fadeOut=clip.get('fadeOut',0)/p['fps'],
                fadeOffset=clip.get('fadeOffset',0)/p['fps'],fadeLength=clip.get('fadeLength',clip['length'])/p['fps'],
                deClickOffset=clip.get('_playbackFadeOffset',0)/p['fps'],deClickLength=clip.get('_playbackFadeLength',clip['length'])/p['fps']))
        offset+=clip['length']
    for clip in p['graphics']:
        if clip.get('type')!='video' or clip.get('hidden') or clip['start']>=duration:continue
        asset=assets[clip['asset']]
        if not asset.get('audio'):continue
        result.append(dict(id=clip['id'],path=asset['path'],start=clip['start']/p['fps'],source=clip.get('in',0)/p['fps'],
            length=min(clip['length'],duration-clip['start'])/p['fps'],speed=clip.get('speed',1),role='voice',
            volume=0 if clip.get('muted') else project.audio_gain(clip.get('volumeDb',0))*project.audio_gain(p['mixer']['voice']),
            fadeIn=clip.get('fadeIn',0)/p['fps'],fadeOut=clip.get('fadeOut',0)/p['fps'],
            fadeOffset=clip.get('fadeOffset',0)/p['fps'],fadeLength=clip.get('fadeLength',clip['length'])/p['fps']))
    for clip in p['audio']:
        if clip['start']>=duration:continue
        length=min(clip['length'],duration-clip['start'])/p['fps']
        result.append(dict(id=clip['id'],path=assets[clip['asset']]['path'],start=clip['start']/p['fps'],source=clip.get('in',0)/p['fps'],
            length=length,speed=clip.get('speed',1),role=clip['role'],
            volume=(0 if clip.get('muted') else project.audio_gain(clip.get('volumeDb',0))*project.audio_gain(p['mixer'][clip['role']])),
            fadeIn=clip.get('fadeIn',0)/p['fps'],fadeOut=clip.get('fadeOut',0)/p['fps'],
            fadeOffset=clip.get('fadeOffset',0)/p['fps'],fadeLength=clip.get('fadeLength',clip['length'])/p['fps']))
    return sorted(result,key=lambda item:(item['start'],item['path'],item['source']))

def lut_spec(item):
    """The native compositor reads the same .cube file as the exporter."""
    return {'lut':str(render.LUTS[item['lut']])} if item.get('lut') else {}

def video_layers(p):
    assets={a['id']:a for a in p['assets']};total=project.duration(p)
    return [dict(id=g['id'],path=assets[g['asset']]['path'],sourceWidth=assets[g['asset']]['width'],sourceHeight=assets[g['asset']]['height'],
        start=g['start'],length=min(g['length'],total-g['start']),sourceIn=g.get('in',0),speed=g.get('speed',1),props=g.get('props',{}),
        keyframes=g.get('keyframes',{}),offset=g.get('offset',0),motionLength=g.get('motionLength',g['length']),**lut_spec(assets[g['asset']]))
        for g in p['graphics'] if g.get('type')=='video' and not g.get('hidden') and g['start']<total]

def playback_window(p,start,end):
    """A local playback interval, including source audio and every visible layer."""
    out=copy.deepcopy(p);out['clips']=[];offset=0
    for clip in p['clips']:
        first,last=max(start,offset),min(end,offset+clip['length'])
        if first<last:
            part=project.slice_item(clip,'clips',first-offset,last-offset)
            part['_playbackFadeOffset']=first-offset;part['_playbackFadeLength']=clip['length']
            out['clips'].append(part)
        offset+=clip['length']
    for kind in ('graphics','captions','audio'):
        out[kind]=[]
        for item in p[kind]:
            first,last=max(start,item['start']),min(end,item['start']+item['length'])
            if first>=last:continue
            part=project.slice_item(item,kind,first-item['start'],last-item['start']);part['start']=first-start
            out[kind].append(part)
    return out

def playback_interval(p,frame,motion,video,look_ahead=False):
    """Render a bounded window, never an entire unsupported effect stack.

    Direct stretches stay long. Complete stacks are baked only where needed,
    preserving z-order without omitting or approximating any graphic type.
    """
    total=project.duration(p);frame=max(0,min(int(frame),total-1));affected=[];offset=0
    assets={a['id']:a for a in p['assets']}
    for clip in p['clips']:
        if not direct(clip,assets[clip['asset']],p,video):affected.append((offset,offset+clip['length']))
        offset+=clip['length']
    for g in p['graphics']:
        if not g.get('hidden') and not (native_image(g,motion) or native_title(g) or native_video_layer(g,p,video)):
            affected.append((g['start'],g['start']+g['length']))
    if not affected:return 0,total
    if any(first<=frame<last for first,last in affected):
        return frame,min(total,frame+max(1,round(p['fps']*(2 if look_ahead else .5))))
    next_start=min((first for first,last in affected if first>frame),default=total)
    return frame,min(total,next_start)

def prepare(p,folder,native_images=False,native_text=False,native_motion=False,native_video=False,interactive=False,frame=0,look_ahead=False,force_raster=False,native_lut=False,native_retime=False):
    tick=time.monotonic();project.validate(p,check_files=True)
    if not p['clips']:raise ValueError('Añade primero un vídeo.')
    # A host without the LUT would show log footage flat: those frames keep the exporter's painter.
    if not native_lut and any('lut' in a for a in p['assets']):native_video=False
    if force_raster:
        p=copy.deepcopy(p);p['_forcePreviewRender']=True;native_images=native_text=native_motion=native_video=False
    if native_retime:p={**p,'_nativeRetime':True}
    original=p;total=project.duration(p);start,end=(playback_interval(p,frame,native_motion,native_video,look_ahead) if interactive else (0,total))
    if start or end<total:p=playback_window(p,start,end)
    native_images,native_text=native_modes(p,native_images,native_text,native_motion,native_video)
    # Baked intervals own the whole stack, including video overlays. This keeps
    # channel-intro and overlapping templates faithful to the export renderer.
    composited_video=native_video and native_text
    folder=Path(folder);cache=folder/'playback';cache.mkdir(parents=True,exist_ok=True)
    outputs=[];rendered=0;hit=0
    for region in regions(p,native_images,native_text,native_motion,composited_video):
        length=region['end']-region['start']
        if region['cached']:
            portion=window(p,region['start'],region['end'],native_images,native_text,native_motion,composited_video)
            if interactive:
                # Playback can use a smaller proxy; paused frames and exports
                # continue through the original high-quality renderer.
                scale=min(1,640/max(portion['width'],portion['height']))
                portion['width']=max(64,round(portion['width']*scale/2)*2);portion['height']=max(64,round(portion['height']*scale/2)*2)
            key=visual_key(portion,native_images,native_text,native_motion,composited_video);dest=cache/f'clip-{key}.mp4'
            if not dest.exists():
                with tempfile.TemporaryDirectory(prefix='.visual-',dir=cache) as temp:
                    result=render.render(portion,Path(temp),preview=True,with_audio=False)
                    os.replace(result['path'],dest)
                rendered+=length
            else:hit+=length
            outputs.append(dict(path=str(dest),sourceIn=0,length=length,start=region['start']))
        else:
            clip=region['clip'];spec=dict(path=region['path'],sourceIn=region['sourceIn'],length=length,start=region['start'],**lut_spec(region))
            if native_video:spec.update({key:clip[key] for key in ('speed','zoom','zoomEnd','x','y','color','motionOffset','motionLength') if key in clip},**({'retime':True} if region['retime'] else {}))
            outputs.append(spec)
    native_audio=(native_images or interactive) and not p.get('ducking',False)
    sources=audio_layers(p) if native_audio else []
    native_cues=native_images or interactive
    # Ducking retains one continuous compressor history across chunk boundaries.
    audio_project=original if interactive else p
    key=audible_key(audio_project,native_cues);audio=cache/f'mix-{key}.wav';audio_cached=native_audio or audio.exists()
    if not native_audio and not audio_cached:
        with tempfile.TemporaryDirectory(prefix='.audio-',dir=cache) as temp:
            dest=render.render_audio(audio_project,Path(temp),image_sounds=not native_cues);os.replace(dest,audio)
    fps=Fraction(p['fps']).limit_denominator(1001);width=min(960,p['width']);height=round(p['height']*width/p['width']/2)*2
    images=overlay_layers(p,(width,height),cache,native_motion) if native_text else image_layers(p,native_motion) if native_images else []
    cues=image_cues(p,cache) if native_cues else []
    result=dict(revision=p['revision'],frames=project.duration(p),fps=p['fps'],fpsNum=fps.numerator,fpsDen=fps.denominator,
        width=width,height=height,clips=outputs,audio=None if native_audio else str(audio),audioSources=sources,
        renderedFrames=rendered,cachedFrames=hit,directFrames=project.duration(p)-rendered-hit,
        audioCached=audio_cached,images=images,audioCues=cues,videoOverlays=video_layers(p) if composited_video else [],
        windowStart=start,windowEnd=end,totalFrames=total,progressive=bool(start or end<total),rasterFallback=force_raster,audioSourceIn=start/p['fps'] if interactive else 0,
        ducking=bool(p.get('ducking')),seconds=round(time.monotonic()-tick,3))
    result['mediaKey']=digest({k:result[k] for k in ('clips','videoOverlays','audio','audioSourceIn','audioSources','ducking','width','height','fps','frames','windowStart')})
    result['key']=digest({k:result[k] for k in ('mediaKey','images','audioCues')})
    project.atomic_json(cache/'latest.json',result)
    keep=[*[c['path'] for c in outputs],*[c['path'] for c in cues],*[c['path'] for c in images]]
    if not native_audio:keep.append(audio)
    render.maintain_cache(folder,p.get('cacheLimitGB',5),keep=keep)
    return result
