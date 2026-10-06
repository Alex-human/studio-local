"""Source proxies in short chunks and canonical text sprites, independent of timeline revisions."""
import copy
import functools
import hashlib
import json
import math
import os
import subprocess
import threading
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import graphics
import preview
import project
import render

CHUNK, BLOCK = 10, 30  # Source seconds per video proxy and per audio block.


def transcode(args, seconds):
    result=subprocess.run([str(render.FF),'-hide_banner','-nostdin',*map(str,args)],
                          capture_output=True,timeout=max(90,seconds*4+30))
    if result.returncode:raise ValueError('No se pudo convertir la fuente móvil')


@functools.lru_cache
def pixel(path):
    info=subprocess.run([str(render.FF),'-hide_banner','-nostdin','-i',path],capture_output=True,timeout=10).stderr.decode(errors='replace')
    return 'p010le' if '10le' in next((line for line in info.splitlines() if 'Video:' in line),'') else 'nv12'


def cadence(fps):
    """Nominal constant rate of a source; a phone's variable rate averages just under it."""
    ntsc=round(fps*1.001)
    return Fraction(ntsc*1000,1001) if abs(fps*1.001-ntsc)<.01 else Fraction(max(1,round(fps)))


def spans(plan):
    """(start, end, url) in seconds for every piece of media of a plan."""
    fps=plan['fps']
    return [(x['start']/fps,(x['start']+x['length'])/fps,x['url']) for x in plan['clips']+plan['layers']]+[(x['start'],x['start']+x['length'],x['url']) for x in plan['audio']]


class DirectMedia:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.jobs = {}  # name -> build spec; None for the sprites plan() writes itself
        self.queues = [[], [], []]  # playhead, open montage, library
        self.active = set()
        self.background = False
        self.workers = 0

    def resource(self, asset, color=None, audio=False, start=0):
        source = Path(asset['path'])
        stat = source.stat()
        kind = 'audio' if audio else asset['kind']
        spec = dict(path=str(source.resolve()), kind=kind, color=color or {}, start=start, lut=None if audio else asset.get('lut'))
        key = hashlib.sha256(json.dumps([2, spec, stat.st_size, stat.st_mtime_ns], sort_keys=True).encode()).hexdigest()[:32]
        name = key + '.' + {'video': 'mp4', 'audio': 'm4a', 'image': 'png'}[kind]
        with self.lock:
            self.jobs.setdefault(name, dict(spec, fps=asset.get('fps'), width=asset.get('width'), height=asset.get('height')))
        return '/native/' + name

    def existing(self, path):
        name = Path(path).name
        with self.lock: self.jobs.setdefault(name, None)
        return '/native/'+name

    def queue(self, tier, urls, limit=None):
        """Replace one tier with what is still to build, in order. limit bounds its media, built or not."""
        with self.lock:
            names=[n for n in dict.fromkeys(url.removeprefix('/native/') for url in urls) if self.jobs.get(n) and not self.jobs[n].get('error')][:limit]
            self.queues[tier]=[n for n in names if not (self.folder/n).exists()]
        self.start()

    def start(self):
        with self.lock:
            while self.workers<2 and any(self.queues):
                self.workers+=1
                threading.Thread(target=self.work, daemon=True).start()

    def take(self):
        for tier,queue in enumerate(self.queues):
            if tier and self.background:break  # One worker stays free for the playhead.
            while queue:
                name=queue.pop(0)
                if name not in self.active and not self.jobs[name].get('error') and not (self.folder/name).exists():
                    self.active.add(name)
                    return name,tier
        return None,0

    def work(self):
        while True:
            with self.lock:
                name,tier=self.take()
                if not name:
                    self.workers-=1
                    return
                if tier:self.background=True
                spec=self.jobs[name]
            try:
                self.build(name, spec)
            except Exception:
                spec['error'] = True
            finally:
                with self.lock:
                    self.active.discard(name)
                    if tier:self.background=False
            self.prune()

    def build(self, name, spec):
        dest = self.folder/name
        if dest.exists(): return
        color, kind, start = spec['color'], spec['kind'], spec['start']
        with tempfile.TemporaryDirectory(prefix='.source-', dir=self.folder) as work:
            out = Path(work)/name
            if kind == 'image':
                im = graphics.source_image(spec['path'], Path(spec['path']).stat().st_mtime_ns).copy()
                im.thumbnail((1280, 1280)); im.save(out)
            elif kind == 'audio':
                transcode(['-v','error','-ss',start,'-i',spec['path'],'-t',BLOCK,'-map','0:a:0','-vn','-c:a','aac','-b:a','128k','-ar','48000','-movflags','+faststart',out],BLOCK)
            else:
                # A constant rate from the chunk's own zero: every proxy starts on a frame and lasts CHUNK.
                rate=cadence(spec['fps'])
                filters = ['scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2',f'fps={rate}:start_time=0','setsar=1',*render.lut_filter(spec['lut'])]
                if color:
                    filters += [f"eq=brightness={color.get('exposure',0)*.12}:contrast={color.get('contrast',1)}:saturation={color.get('saturation',1)}"]
                    t = color.get('temperature',0)
                    if t: filters += [f'colorbalance=rs={t*.12}:bs={-t*.12}:rm={t*.07}:bm={-t*.07}']
                source = ['-ss',start,'-t',CHUNK+1,'-i',spec['path']]
                output = ['-frames:v',math.ceil(CHUNK*rate),'-map','0:v:0','-an',
                            '-c:v','h264_videotoolbox','-b:v','850k','-maxrate','1100k','-bufsize','2200k',
                            '-g',max(1,round(rate/2)),'-pix_fmt','yuv420p','-movflags','+faststart',out]
                scale=min(1,640/max(spec['width'],spec['height']))
                w,h=max(2,round(spec['width']*scale/2)*2),max(2,round(spec['height']*scale/2)*2)
                hardware=[f'scale_vt=w={w}:h={h}','hwdownload',f"format={pixel(spec['path'])}",*filters[1:]]
                try:
                    transcode(['-v','error','-hwaccel','videotoolbox','-hwaccel_output_format','videotoolbox_vld',*source,'-vf',','.join(hardware),*output],CHUNK)
                except ValueError:
                    # Some imported codecs have no hardware frames; same output contract.
                    transcode(['-y','-v','error',*source,'-vf',','.join(filters),*output],CHUNK)
            os.replace(out, dest)

    def prune(self):
        """Above 2 GiB the longest unused go first; nothing used in the last two minutes."""
        try:
            files=sorted((f.stat().st_mtime,f.stat().st_size,f.path) for f in os.scandir(self.folder) if f.is_file() and f.name.endswith(('.mp4','.m4a','.png','.wav')))
            total=sum(size for _,size,_ in files)
            for modified,size,path in files:
                if total<=2*1024**3 or time.time()-modified<120:break
                total-=size;os.unlink(path)
        except OSError:pass  # A file vanished meanwhile; the next build prunes again.

    def missing(self, urls):
        """Mark what exists as just used and return the rest."""
        result=[]
        for url in dict.fromkeys(urls):
            try:os.utime(self.folder/url.removeprefix('/native/'))
            except OSError:result.append(url)
        return result

    def status(self, urls):
        if not isinstance(urls,list) or len(urls)>100: raise ValueError('Lista de medios no válida')
        # Never touch, start or report an unregistered path.
        urls=[url for url in urls if isinstance(url,str) and url.removeprefix('/native/') in self.jobs]
        self.queue(0, urls)
        missing=self.missing(urls)
        # A failure is reported once; asking again retries it.
        failed=[url for url in missing if (self.jobs[url.removeprefix('/native/')] or {'error':True}).pop('error',None)]
        return {'ready': [url for url in dict.fromkeys(urls) if url not in missing], 'failed': failed}

    def pieces(self, item, asset, start, fps, color=None):
        """Split a video item where its source crosses a chunk, so every piece plays from one small proxy."""
        last=int(max(0,asset['duration']-.5)//CHUNK);done=0
        while done<item['length']:
            source=(item.get('in',0)+done)/fps
            index=min(int((source+1e-9)//CHUNK),last)
            length=item['length']-done if index==last else min(item['length']-done,math.ceil(((index+1)*CHUNK-source)*fps-1e-9))
            yield dict(item,id=f"{item['id']}:{index}",start=start+done,length=length,url=self.resource(asset,color,start=index*CHUNK),
                       **{'in':item.get('in',0)+done-index*CHUNK*fps}),done
            done+=length

    def plan(self, p):
        visible = [g for g in p['graphics'] if not g.get('hidden')]
        if p.get('ducking') or any(x.get('speed',1)!=1 for k in ('clips','audio','graphics') for x in p[k]) or any(g['type'] not in ('image','video','title') or
                                   g['type']=='title' and set(g.get('keyframes',{}))-{'opacity'} for g in visible):
            return None
        assets = {a['id']: a for a in p['assets']}
        factor = min(1,640/max(p['width'],p['height']))
        width = round(p['width']*factor/2)*2; height = round(p['height']*factor/2)*2
        fps = p['fps']; total = project.duration(p)
        plan = dict(width=width, height=height, fps=fps, frames=total, clips=[], layers=[], audio=[])
        start = 0
        for clip in p['clips']:
            for piece,done in self.pieces(clip, assets[clip['asset']], start, fps, clip.get('color')):
                plan['clips'].append(dict(piece, base=True, motionOffset=clip.get('motionOffset',0)+done, motionLength=clip.get('motionLength',clip['length'])))
            start += clip['length']
        for g in sorted(visible, key=lambda g:g['type']!='video'):
            if g['type']=='title':
                item = {**g, **preview.text_layer(g,'graphics',(width,height),self.folder)}
                item['url']=self.existing(item.pop('path')); plan['layers'].append(item)
                continue
            a = assets[g['asset'] if g['type']=='video' else g['props']['asset']]
            size = dict(sourceWidth=a['width'], sourceHeight=a['height'])
            if g['type']=='image':
                plan['layers'].append(dict(g, url=self.resource(a), **size))
                continue
            for piece,done in self.pieces(dict(g, length=min(g['length'],total-g['start'])), a, g['start'], fps):
                plan['layers'].append(dict(piece, offset=g.get('offset',0)+done, **size))
        for c in p['captions']:
            if c.get('hidden'): continue
            sprite = preview.text_layer(c,'captions',(width,height),self.folder)
            plan['layers'].append({**c, **sprite, 'type':'text', 'url':self.existing(sprite['path'])})
            plan['layers'][-1].pop('path',None)
        paths = {a['path']:a for a in p['assets']}
        for item in preview.audio_layers(p):
            if item['volume']<=0: continue
            item=copy.deepcopy(item);asset=paths[item.pop('path')]
            offset=0
            while offset<item['length']-1e-8:
                source=item['source']+offset
                first=int((source+1e-8)//BLOCK)*BLOCK
                length=min(item['length']-offset,first+BLOCK-source)
                piece=dict(item,id=item['id']+':'+str(first),start=item['start']+offset,source=max(0,source-first),length=length,
                           url=self.resource(asset,audio=True,start=first),fadeOffset=item.get('fadeOffset',0)+offset)
                if 'deClickLength' in item:piece['deClickOffset']=item.get('deClickOffset',0)+offset
                plan['audio'].append(piece);offset+=length
        for cue in preview.image_cues(p,self.folder):
            cue=dict(cue);cue['url']=self.existing(cue.pop('path'))
            plan['audio'].append(cue)
        return plan
