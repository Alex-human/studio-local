"""Streaming native FFmpeg renderer. No browser server, uploads or full-video RAM buffer."""
import json
import hashlib
import os
import re
import shutil
import subprocess
import time
import tempfile
from fractions import Fraction
from pathlib import Path
from PIL import Image, ImageOps
import numpy as np
import graphics
import project
import sounds

ROOT = Path(__file__).resolve().parents[1]
FF = ROOT / 'runtime/ffmpeg'
# dlogm: DJI's official D-Log M → Rec.709 table from the Osmo Pocket 3 download page; probe() assigns it.
LUTS = {name: ROOT / 'assets/luts' / f'{name}.cube' for name in project.LUTS}

def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
    for pipe in (proc.stdin,proc.stdout):
        if pipe:
            try:pipe.close()
            except (BrokenPipeError,OSError):pass

def run(args):
    proc = subprocess.Popen([str(FF), '-hide_banner', '-nostdin', *map(str,args)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate()
        if proc.returncode:
            raise ValueError('El motor de vídeo no pudo completar la operación: '+err.decode(errors='replace')[-1800:])
        return out
    finally:
        stop(proc)

def varints(data, prefix='', depth=0):
    """First value of each protobuf varint by dotted field path; nested messages are tried as protobuf."""
    out={};i=0
    def varint():
        nonlocal i;value=shift=0
        while True:
            if i>=len(data):raise ValueError('truncated')
            byte=data[i];i+=1;value|=(byte&127)<<shift;shift+=7
            if byte<128:return value
    while i<len(data):
        key=varint();field,wire=key>>3,key&7;name=prefix+str(field)
        if not field:raise ValueError('bad field')
        if wire==0:out.setdefault(name,varint())
        elif wire==2:
            size=varint();body=data[i:i+size];i+=size
            if i>len(data):raise ValueError('truncated')
            if depth<6:
                try:
                    for k,v in varints(body,name+'.',depth+1).items():out.setdefault(k,v)
                except ValueError:pass
        elif wire in (1,5):i+=8 if wire==1 else 4
        else:raise ValueError('bad wire type')
    return out

def pocket3_lut(path):
    """The Pocket 3 tags D-Log M as plain BT.709; its mode is field 2.4.1 of the first "DJI meta" packet (19 = D-Log M)."""
    try:return 'dlogm' if varints(run(['-v','error','-i',path,'-map','0:m:handler_name:DJI meta','-frames:d','1','-c','copy','-f','data','-'])).get('2.4.1')==19 else None
    except ValueError:return None

def lut_filter(name):
    """Camera log → Rec.709 before any adjustment. The matrix is fixed because the tag cannot reveal log; 16-bit RGB avoids
    banding while the curve expands. Leaving tagged BT.709 limited range keeps later automatic conversions exact."""
    if not name:return []
    path=str(LUTS[name]).replace('\\','\\\\').replace(':','\\:')
    return ['scale=in_color_matrix=bt709','format=gbrp16le',f"lut3d=file='{path}':interp=tetrahedral",'scale=out_color_matrix=bt709:out_range=tv']

def probe(path):
    path=Path(path).expanduser().resolve()
    if path.suffix.lower() not in ('.mp4','.mov','.m4v','.mkv','.webm','.wav','.mp3','.m4a','.aac','.flac','.png','.jpg','.jpeg','.webp','.tif','.tiff'):
        raise ValueError('Formato no admitido')
    if not path.is_file(): raise ValueError('Archivo no disponible')
    if path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.tif','.tiff'):
        with Image.open(path) as image:w,h=ImageOps.exif_transpose(image).size
        return dict(id=project.uid(),path=str(path),name=path.name,kind='image',duration=0,width=w,height=h,fps=0,audio=False,bytes=path.stat().st_size,hdr=False)
    result=subprocess.run([str(FF),'-hide_banner','-nostdin','-i',str(path)],capture_output=True,text=True)
    desc=result.stderr
    video=next((x for x in desc.splitlines() if 'Video:' in x),'')
    dim=re.search(r'\b(\d{2,5})x(\d{2,5})\b',video)
    fps=re.search(r'([\d.]+) fps',video)
    kind='video' if video else 'audio'
    if not video and 'Audio:' not in desc: raise ValueError('El archivo no contiene vídeo, imagen ni audio legible')
    precise={}
    exact=subprocess.run([str(ROOT/'runtime/probe'),str(path)],capture_output=True,text=True,timeout=30)
    if exact.returncode==0:
        precise=json.loads(exact.stdout)
    else:
        # Unsupported AVFoundation containers: packet timestamps keep full precision.
        packets=run(['-v','error','-i',path,'-map','0:v:0' if video else '0:a:0','-c','copy','-f','framehash','-hash','crc32','-']).decode()
        tb=re.search(r'#tb 0: (\d+)/(\d+)',packets)
        rows=[r.split(',') for r in packets.splitlines() if r and not r.startswith('#')]
        if tb and rows:
            unit=int(tb[1])/int(tb[2]); precise['duration']=max((int(r[2])+int(r[3]))*unit for r in rows)
        else: raise ValueError('No se pudo determinar la duración exacta')
    seconds=precise['duration']
    asset=dict(id=project.uid(),path=str(path),name=path.name,kind=kind,duration=seconds,
               width=precise.get('width',int(dim[1]) if dim else 0),height=precise.get('height',int(dim[2]) if dim else 0),
               fps=precise.get('fps',float(fps[1]) if fps else 0),audio='Audio:' in desc,bytes=path.stat().st_size,
               hdr=any(x in video for x in ('smpte2084','arib-std-b67')))
    if 'OsmoPocket3' in desc and 'DJI meta' in desc and (lut:=pocket3_lut(path)):asset['lut']=lut
    return asset

def waveform(path):
    raw=run(['-v','error','-i',path,'-vn','-ac','1','-ar','500','-f','f32le','-'])
    samples=np.abs(np.frombuffer(raw,dtype=np.float32))
    if not len(samples): return []
    return [round(float(x.max()),4) if len(x) else 0 for x in np.array_split(samples,256)]

def maintain_cache(folder, limit_gb, keep=None):
    """Only regenerable preview/still files managed by this editor. Never exports or media."""
    files=[]; protected=set()
    for sub,pattern in [('frames','frame-*.jpg'),('frames','source-*.png'),('frames','thumbnail-*.jpg'),('frames','motion-preview-*.wav'),('previews','preview-*.mp4'),('playback','clip-*.mp4'),('playback','mix-*.wav'),('playback','text-*.png')]:
        files.extend((Path(folder)/sub).glob(pattern))
    size=sum(f.stat().st_size for f in files)
    if size<=limit_gb*1e9:return {'bytes':size,'removed':0}
    if keep:
        protected.update(Path(f).resolve() for f in (keep if isinstance(keep,(list,tuple,set)) else [keep]))
    manifests=set((ROOT/'projects').glob('**/*.studio'))|set(Path(folder).glob('*.studio'))|set((Path(folder)/'.history').glob('**/*.studio'))
    for manifest in manifests:
        try:
            data=json.loads(manifest.read_text())
            protected.update(Path(a['path']).resolve() for a in data.get('assets',[]))
        except (OSError,ValueError,KeyError):
            # A malformed owned manifest makes references uncertain: keep the cache.
            return {'bytes':0,'removed':0,'deferred':True}
    removed=0
    for f in sorted(files,key=lambda x:x.stat().st_mtime):
        if size<=limit_gb*1e9: break
        if f.resolve() in protected: continue
        size-=f.stat().st_size; f.unlink();removed+=1
        if f.suffix=='.mp4': f.with_suffix('.json').unlink(missing_ok=True)
    return {'bytes':size,'removed':removed}

def rate(p):
    return str(Fraction(p['fps']).limit_denominator(1001))

def video_filter(c, p, w, h, lut=None):
    fps=rate(p); color=c.get('color',{})
    filters=[f'fps={fps}:round=near',f"trim=start_pts={round(c.get('in',0))}:end_pts={round(c.get('in',0)+c['length']*c.get('speed',1))}",
             f"setpts=(PTS-STARTPTS)/{c.get('speed',1)}",f'fps={fps}',
             f'scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos',
             f"crop={w}:{h}:(iw-ow)*{c.get('x',.5)}:(ih-oh)*{c.get('y',.5)}",'setsar=1',*lut_filter(lut)]
    exposure=color.get('exposure',0); contrast=color.get('contrast',1); sat=color.get('saturation',1)
    if exposure or contrast!=1 or sat!=1:
        filters.append(f'eq=brightness={exposure*.12}:contrast={contrast}:saturation={sat}')
    temp=color.get('temperature',0)
    if temp: filters.append(f'colorbalance=rs={temp*.12}:bs={-temp*.12}:rm={temp*.07}:bm={-temp*.07}')
    z0=c.get('zoom',1); z1=c.get('zoomEnd',z0)
    if z0!=1 or z1!=1:
        n=max(1,c.get('motionLength',c['length'])-1)
        u=f'((on+{c.get("motionOffset",0)})/{n})'
        z=f'({z0}+({z1}-{z0})*{u}*{u}*(3-2*{u}))'
        # Recorte de 1/z en (W-W/z)·x, (H-H/z)·y llevado a toda la imagen con interpolación de subpíxel: zoompan redondeaba
        # el recorte a píxeles y el zoom lento avanzaba a saltos de 2–3 px en la vista previa.
        L=f"(W-W/{z})*{c.get('x',.5)}";T=f"(H-H/{z})*{c.get('y',.5)}";R=f"{L}+W/{z}";B=f"{T}+H/{z}"
        filters.append(f"perspective=x0='{L}':y0='{T}':x1='{R}':y1='{T}':x2='{L}':y2='{B}':x3='{R}':y3='{B}':interpolation=cubic:eval=frame")
    return ','.join(filters)

def video_input(c,p,path):
    # Preserve the source's timestamp grid across cuts, including mixed-fps inputs.
    # VideoToolbox decodes the same pixels with a fraction of the CPU; FFmpeg falls back to software when it cannot.
    return ['-hwaccel','videotoolbox','-copyts','-ss',str(max(0,c.get('in',0)/p['fps']-2)),'-i',str(path)]

def overlay_filter(item, p, first=0, last=None, lut=None):
    # Preserve source presentation timestamps, including VFR. Rounding upwards
    # picks the frame containing each output time instead of the next frame.
    # One nanosecond removes rational-to-nanosecond rounding at exact boundaries.
    origin=item.get('in',0)/p['fps'];speed=item.get('speed',1)
    end=item['length'] if last is None else last
    # A file can open with an empty edit (encoder delay): its first picture arrives a few
    # milliseconds after zero. Hold it from the requested frame, as the native player does;
    # a first decoded picture at or before that frame keeps its timestamp.
    pts=f'(PTS-{origin}/TB-1)/{speed}'
    pts=f'if(eq(N\\,0)\\,min({pts}\\,({first}-0.5)/({rate(p)})/TB)\\,{pts})'
    return ','.join([f'settb=1/1000000000,setpts={pts},fps={rate(p)}:round=up,trim=start_pts={first}:end_pts={end},setsar=1',*lut_filter(lut)])

def overlay_frame(p, item, frame, folder):
    """Cache source pixels only; editing position, crop or text never invalidates the decode."""
    asset=next(a for a in p['assets'] if a['id']==item['asset'])
    local=frame-item['start'];nearby={**item,'in':item.get('in',0)+local*item.get('speed',1)}
    args=['-v','error',*video_input(nearby,p,asset['path']),'-vf',overlay_filter(item,p,local,local+1,asset.get('lut')),'-frames:v','1','-an','-f','image2pipe','-vcodec','png','-']
    source=Path(asset['path']);stat=source.stat()
    key=hashlib.sha256(json.dumps(['overlay',str(source.resolve()),stat.st_size,stat.st_mtime_ns,args]).encode()).hexdigest()[:28]
    cached=Path(folder)/f'source-{key}.png'
    if not cached.exists():
        raw=run(args)
        if not raw:raise ValueError('No se pudo leer el vídeo superpuesto: '+asset['name'])
        with tempfile.NamedTemporaryFile(prefix='.source-',suffix='.png',dir=folder,delete=False) as temp:
            temp.write(raw);tmp=Path(temp.name)
        try:os.replace(tmp,cached)
        finally:tmp.unlink(missing_ok=True)
    with Image.open(cached) as image:return image.convert('RGBA' if 'A' in image.getbands() else 'RGB')

class OverlayDecoders:
    """One streaming decoder per currently visible video; all handles close on failure."""
    def __init__(self,p,work):
        self.p=p;self.work=work;self.active={};self.assets={a['id']:a for a in p['assets']}
    def close(self):
        for decoder,log in self.active.values():stop(decoder);log.close()
        self.active.clear()
    def frames(self,frame):
        items=[g for g in self.p['graphics'] if g.get('type')=='video' and not g.get('hidden') and g['start']<=frame<g['start']+g['length']]
        ids={g['id'] for g in items}
        for id in set(self.active)-ids:
            decoder,log=self.active.pop(id);stop(decoder);log.close()
        result={}
        for item in items:
            a=self.assets[item['asset']];width,height=a['width'],a['height'];local=frame-item['start']
            if item['id'] not in self.active:
                nearby={**item,'in':item.get('in',0)+local*item.get('speed',1)}
                log=(self.work/('overlay-'+item['id']+'.log')).open('w')
                try:
                    decoder=subprocess.Popen([str(FF),'-hide_banner','-nostdin','-v','error',*video_input(nearby,self.p,a['path']),'-vf',overlay_filter(item,self.p,local,lut=a.get('lut')),'-frames:v',str(item['length']-local),'-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=log)
                except BaseException:log.close();raise
                self.active[item['id']]=(decoder,log)
            raw=self.active[item['id']][0].stdout.read(width*height*3)
            if len(raw)!=width*height*3:raise ValueError('Faltan fotogramas del vídeo superpuesto: '+a['name'])
            result[item['id']]=Image.frombytes('RGB',(width,height),raw)
        return result

def atempo(speed):
    if speed==1:return 'anull'
    result=[]
    while speed>2: result.append('atempo=2'); speed/=2
    while speed<.5: result.append('atempo=0.5'); speed/=.5
    result.append(f'atempo={speed}')
    return ','.join(result)

def audio_specs(p, work, image_sounds=True):
    total=project.duration(p)/p['fps']; assets={a['id']:a for a in p['assets']}
    specs=[]; offset=0
    for c in p['clips']:
        a=assets[c['asset']]
        if a['audio'] and not c.get('muted'):
            specs.append(dict(path=a['path'],start=offset/p['fps'],source=c.get('in',0)/p['fps'],
                              length=c['length']/p['fps'],role='voice',db=c.get('volumeDb',0),speed=c.get('speed',1),
                              fadeIn=c.get('fadeIn',0)/p['fps'],fadeOut=c.get('fadeOut',0)/p['fps'],
                              fadeOffset=c.get('fadeOffset',0)/p['fps'],fadeLength=c.get('fadeLength',c['length'])/p['fps']))
        offset+=c['length']
    for c in [*p['audio'],*(g for g in p['graphics'] if g.get('type')=='video')]:
        if not assets[c['asset']].get('audio') or c.get('hidden') or c.get('muted') or c['start']>=project.duration(p): continue
        specs.append(dict(path=assets[c['asset']]['path'],start=c['start']/p['fps'],source=c.get('in',0)/p['fps'],
                          length=min(c['length'],project.duration(p)-c['start'])/p['fps'],role=c.get('role','voice'),
                          db=c.get('volumeDb',0),speed=c.get('speed',1),fadeIn=c.get('fadeIn',0)/p['fps'],fadeOut=c.get('fadeOut',0)/p['fps'],
                          fadeOffset=c.get('fadeOffset',0)/p['fps'],fadeLength=c.get('fadeLength',c['length'])/p['fps']))
    if image_sounds:
        # Export mixes the cue into the master. Native playback schedules the same
        # short cue independently so an image never rebuilds a full-length WAV.
        for g in p['graphics']:
            props=g.get('props',{}); animation=props.get('animation','pop')
            if g['type']!='image' or g.get('hidden') or not props.get('sound') or animation=='none':continue
            source=g.get('offset',0)/p['fps']; start=g['start']/p['fps']
            length=max(.12,min(2,float(props.get('enter',.48))))
            if source>=length or start>=total:continue
            cue=work/('motion-'+g['id']+'.wav');sounds.motion_sound(cue,animation,length)
            specs.append(dict(path=str(cue),start=start,source=source,length=min(length-source,g['length']/p['fps'],total-start),role='sfx',db=props.get('soundDb',-18),speed=1))
    return specs

def render_audio(p, work, image_sounds=True):
    """Mix only occupied audio regions; never pad every clip across the full video."""
    total=project.duration(p)/p['fps']; samples=round(total*48000)
    specs=audio_specs(p,work,image_sounds=image_sounds); buffers={}; role_paths={}; active=set()
    for role in project.ROLES:
        path=work/(role+'.f32'); role_paths[role]=path
        with path.open('wb') as file:file.truncate(samples*2*4)
        buffers[role]=np.memmap(path,dtype=np.float32,mode='r+',shape=(samples,2))
    try:
        for base in range(0,len(specs),8):
            batch=specs[base:base+8];inputs=[];chains=[];outputs=[]
            for i,s in enumerate(batch):
                active.add(s['role'])
                inputs+=['-ss',s['source'],'-t',s['length']*s['speed'],'-i',s['path']]
                gain=project.audio_gain(s['db'])*project.audio_gain(p['mixer'][s['role']])
                chain=f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,{atempo(s['speed'])},volume={gain}"
                if s['role']=='voice':chain+=f",afade=t=in:d=0.003,afade=t=out:st={max(0,s['length']-.003)}:d=0.003"
                if s.get('fadeIn') or s.get('fadeOut'):
                    span=s['fadeLength'];chain+=f",asetpts=PTS+{s['fadeOffset']}/TB"
                    if s.get('fadeIn'):chain+=f",afade=t=in:d={min(s['fadeIn'],span)}"
                    if s.get('fadeOut'):chain+=f",afade=t=out:st={max(0,span-s['fadeOut'])}:d={min(s['fadeOut'],span)}"
                    chain+=",asetpts=PTS-STARTPTS"
                chains.append(chain+f'[a{i}]');outputs+=['-map',f'[a{i}]','-f','f32le',work/f'part-{i}.f32']
            run(['-y','-v','error',*inputs,'-filter_complex',';'.join(chains),*outputs])
            for i,s in enumerate(batch):
                part=work/f'part-{i}.f32';position=round(s['start']*48000)
                end=min(samples,round((s['start']+s['length'])*48000))
                with part.open('rb') as file:
                    while raw:=file.read(65536*8):
                        values=np.frombuffer(raw,dtype=np.float32).reshape(-1,2)
                        count=max(0,min(len(values),end-position))
                        if count:buffers[s['role']][position:position+count]+=values[:count]
                        position+=len(values)
                part.unlink()
        for values in buffers.values():values.flush()
        inputs=[]
        for role in project.ROLES:inputs+=['-f','f32le','-ar','48000','-ac','2','-i',role_paths[role]]
        filters=[f'[{i}:a]anull[{role}]' for i,role in enumerate(project.ROLES)]
        if p.get('ducking') and {'voice','music'}<=active:
            filters+=['[voice]asplit=2[voiceout][side]', '[music][side]sidechaincompress=threshold=0.035:ratio=6:attack=20:release=350[duck]',
                '[voiceout][duck][sfx]amix=inputs=3:normalize=0:dropout_transition=0,alimiter=limit=0.95:level=0:latency=1[out]']
        else:filters.append('[voice][music][sfx]amix=inputs=3:normalize=0:dropout_transition=0,alimiter=limit=0.95:level=0:latency=1[out]')
        dest=work/'mix.wav'
        run(['-y','-v','error',*inputs,'-filter_complex',';'.join(filters),'-map','[out]','-t',total,'-c:a','pcm_s24le',dest])
        return dest
    finally:
        for values in buffers.values():values._mmap.close()
        for path in role_paths.values():path.unlink(missing_ok=True)

def progress_file(work, state, current=0, total=0):
    project.atomic_json(work.parent/'status.json',dict(state=state,frame=current,total=total))

# VideoToolbox: quality 75 beats x264 medium crf 16 against a lossless reference (51.9 vs 51.2 dB) with half the energy.
ENCODER={'preview':['-c:v','h264_videotoolbox','-q:v','60'],'master':['-c:v','h264_videotoolbox','-q:v','75']}

def render(p, folder, preview=False, with_audio=True, label=''):
    project.validate(p,check_files=True)
    if not p['clips']: raise ValueError('Añade al menos un clip de vídeo')
    total=project.duration(p); fps=p['fps']; stamp=project.uid()
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    disk=shutil.disk_usage(folder)
    required=max(512*1024**2,total/fps*2_000_000)
    if disk.free<required: raise ValueError('No hay espacio suficiente para el render y sus temporales')
    work=folder/('.work-'+stamp); work.mkdir()
    w,h=p['width'],p['height']
    if preview and w>960:
        h=round(h*960/w/2)*2; w=960
    assets={a['id']:a for a in p['assets']}
    if preview:filename=f'preview-r{p["revision"]}-{label+"-" if label else ""}{stamp}.mp4'
    else:
        name=re.sub(r'[/\\:]+','-',p.get('name','Vídeo')).strip() or 'Vídeo'
        filename=f'{name} - r{p["revision"]} - {stamp}.mp4'
    out=folder/filename
    temp=work/'video.mp4'; log=(work/'encode.log').open('w')
    encoder=subprocess.Popen([str(FF),'-hide_banner','-y','-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{w}x{h}',
                              '-framerate',rate(p),'-i','pipe:0','-an',*ENCODER['preview' if preview else 'master'],'-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(temp)],
                             stdin=subprocess.PIPE,stderr=log)
    tick=time.monotonic(); global_frame=0;overlays=OverlayDecoders(p,work)
    try:
        for c in p['clips']:
            a=assets[c['asset']]
            if a.get('hdr'): raise ValueError('Este editor exporta SDR Rec.709. Convierte el original HDR antes de importarlo.')
            # Frames hidden by an opaque full-canvas overlay skip the camera decode; the output is identical.
            # Splitting keeps source time and motion phase only at speed 1.
            hid=[c.get('speed',1)==1 and graphics.hidden_base(p,global_frame+f,(w,h)) for f in range(c['length'])]
            f0=0
            while f0<c['length']:
                f1=f0
                while f1<c['length'] and hid[f1]==hid[f0]: f1+=1
                if hid[f0]:
                    for _ in range(f0,f1):
                        encoder.stdin.write(graphics.composite(None,p,global_frame,overlays.frames(global_frame),(w,h)).tobytes())
                        global_frame+=1
                        if global_frame%10==0: progress_file(work,'rendering',global_frame,total)
                    f0=f1; continue
                part=project.slice_item(c,'clips',f0,f1)
                dec_log=(work/(c['id']+'.log')).open('w')
                decoder=subprocess.Popen([str(FF),'-hide_banner','-nostdin','-v','error',*video_input(part,p,a['path']),
                                          '-vf',video_filter(part,p,w,h,a.get('lut')),'-frames:v',str(f1-f0),'-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=dec_log)
                try:
                    for _ in range(f0,f1):
                        raw=decoder.stdout.read(w*h*3)
                        if len(raw)!=w*h*3: raise ValueError('Faltan fotogramas al decodificar: '+a['name'])
                        img=graphics.composite(Image.frombytes('RGB',(w,h),raw),p,global_frame,overlays.frames(global_frame))
                        encoder.stdin.write(img.tobytes())
                        global_frame+=1
                        if global_frame%10==0: progress_file(work,'rendering',global_frame,total)
                    decoder.stdout.close()
                    if decoder.wait(): raise ValueError('Error de decodificación del medio')
                finally:
                    stop(decoder)
                    dec_log.close()
                f0=f1
        encoder.stdin.close()
        if encoder.wait(): raise ValueError('No se pudo codificar el vídeo')
        progress_file(work,'mixing',total,total)
        if with_audio:
            audio=render_audio(p,work)
            run(['-v','error','-i',temp,'-i',audio,'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','320k',
                 '-t',total/fps,'-ar','48000','-movflags','+faststart',out])
        else:run(['-v','error','-i',temp,'-an','-c:v','copy','-movflags','+faststart',out])
        run(['-v','error','-hwaccel','videotoolbox','-i',out,'-f','null','-'])
        metadata=dict(path=str(out.resolve()),frames=total,duration=total/fps,width=w,height=h,revision=p['revision'],
                      seconds=round(time.monotonic()-tick,2),bytes=out.stat().st_size,preview=preview)
        project.atomic_json(out.with_suffix('.json'),metadata)
        progress_file(work,'done',total,total)
        return metadata
    except BaseException:
        progress_file(work,'error',global_frame,total)
        raise
    finally:
        stop(encoder)
        overlays.close()
        log.close()
        # Only private intermediates produced by this render, never sources or deliverables.
        shutil.rmtree(work)

def save_frame(im, p, n, folder):
    out=folder/f"frame-{p['revision']}-{n}.jpg"
    im.save(out,quality=92)
    return {'path':str(out.resolve()),'frame':n,'revision':p['revision']}

def frame(p, n, folder, width=960):
    n=max(0,min(int(n),project.duration(p)-1)); offset=0
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    assets={a['id']:a for a in p['assets']}
    for c in p['clips']:
        if n<offset+c['length']:
            a=assets[c['asset']]; w=width; h=round(p['height']*w/p['width']/2)*2
            video_frames={g['id']:overlay_frame(p,g,n,folder) for g in p['graphics'] if g.get('type')=='video' and not g.get('hidden') and g['start']<=n<g['start']+g['length']}
            if graphics.hidden_base(p,n,(w,h),video_frames):
                return save_frame(graphics.composite(None,p,n,video_frames,(w,h)),p,n,folder)
            cc=dict(c); local=n-offset
            u=(local+c.get('motionOffset',0))/max(1,c.get('motionLength',c['length'])-1)
            u=min(1,max(0,u))
            cc['zoom']=graphics.lerp(c.get('zoom',1),c.get('zoomEnd',c.get('zoom',1)),u*u*(3-2*u))
            cc['zoomEnd']=cc['zoom']
            # Keep the original retiming phase while seeking close to the requested
            # frame. A one-frame trimmed source cannot round-trip fractional speed.
            nearby={**cc,'in':c.get('in',0)+local*c.get('speed',1)}
            filters=video_filter(cc,p,w,h,a.get('lut')).replace('PTS-STARTPTS',f"PTS-{round(c.get('in',0))}")
            filters=filters.replace(f'fps={rate(p)},scale=',f'fps={rate(p)},select=eq(pts\\,{local}),scale=')
            args=['-v','error',*video_input(nearby,p,a['path']),
                  '-vf',filters,'-frames:v','1','-an','-f','rawvideo','-pix_fmt','rgb24','-']
            source=Path(a['path']);stat=source.stat()
            key=hashlib.sha256(json.dumps([1,str(source.resolve()),stat.st_size,stat.st_mtime_ns,args],sort_keys=True).encode()).hexdigest()[:28]
            cached=folder/f'source-{key}.png'
            if cached.exists():
                with Image.open(cached) as decoded:base=decoded.convert('RGB')
            else:
                raw=run(args)
                if len(raw)<w*h*3: raise ValueError('No se pudo leer el fotograma')
                base=Image.frombytes('RGB',(w,h),raw[:w*h*3])
                with tempfile.NamedTemporaryFile(prefix='.source-',suffix='.png',dir=folder,delete=False) as temp:tmp=Path(temp.name)
                try:base.save(tmp,compress_level=1);os.replace(tmp,cached)
                finally:tmp.unlink(missing_ok=True)
            # Text edits reuse the decoded source, while every overlay is redrawn.
            return save_frame(graphics.composite(base,p,n,video_frames),p,n,folder)
        offset+=c['length']
    raise ValueError('El proyecto no tiene vídeo')
