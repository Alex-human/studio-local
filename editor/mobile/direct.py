"""Source proxies and canonical text sprites, independent of timeline revisions."""
import copy
import hashlib
import json
import os
import subprocess
import threading
import tempfile
import time
from pathlib import Path

import graphics
import preview
import project
import render


def transcode(args, seconds):
    result=subprocess.run([str(render.FF),'-hide_banner','-nostdin',*map(str,args)],
                          capture_output=True,timeout=max(90,seconds*4+30))
    if result.returncode:raise ValueError('No se pudo convertir la fuente móvil')


class DirectMedia:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.jobs = {}
        self.queue = []
        self.running = False
        self.files = set()
        self.requested = {}

    def resource(self, asset, color=None, audio=False, source_start=0):
        source = Path(asset['path'])
        stat = source.stat()
        kind = 'audio' if audio else asset['kind']
        key = hashlib.sha256(json.dumps([1, str(source.resolve()), stat.st_size, stat.st_mtime_ns,
                                        kind, color or {}, *([source_start] if audio else []), *([asset['lut']] if 'lut' in asset and not audio else [])], sort_keys=True).encode()).hexdigest()[:32]
        extension = {'video': 'mp4', 'audio': 'm4a', 'image': 'png'}[kind]
        name = key + '.' + extension
        with self.lock:
            self.files.add(name)
            if name not in self.jobs:
                self.jobs[name] = dict(asset=copy.deepcopy(asset), color=color or {}, kind=kind, source_start=source_start, error=False)
            if not (self.folder/name).exists() and name not in self.queue and not self.jobs[name].get('error') and self.jobs[name].get('state') != 'working':
                self.queue.append(name)
        return '/native/' + name

    def start(self):
        with self.lock:
            if not self.running and self.queue:
                self.running = True
                threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        while True:
            with self.lock:
                if not self.queue:
                    self.running = False
                    return
                name = self.queue.pop(0)
                spec = self.jobs[name]
                spec['state'] = 'working'
            try:
                self.build(name, spec)
            except Exception:
                spec['error'] = True
            finally:
                spec['state'] = 'done'

    def build(self, name, spec):
        dest = self.folder/name
        if dest.exists(): return
        a, color, kind = spec['asset'], spec['color'], spec['kind']
        with tempfile.TemporaryDirectory(prefix='.source-', dir=self.folder) as work:
            out = Path(work)/name
            if kind == 'image':
                im = graphics.source_image(a['path'], Path(a['path']).stat().st_mtime_ns).copy()
                im.thumbnail((1280, 1280)); im.save(out)
            elif kind == 'audio':
                transcode(['-v','error','-ss',str(spec['source_start']),'-i',a['path'],'-t','30','-map','0:a:0','-vn','-c:a','aac','-b:a','128k','-ar','48000','-movflags','+faststart',out],30)
            else:
                filters = ['scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2','setsar=1',*render.lut_filter(a.get('lut'))]
                if color:
                    filters += [f"eq=brightness={color.get('exposure',0)*.12}:contrast={color.get('contrast',1)}:saturation={color.get('saturation',1)}"]
                    t = color.get('temperature',0)
                    if t: filters += [f'colorbalance=rs={t*.12}:bs={-t*.12}:rm={t*.07}:bm={-t*.07}']
                output = ['-map','0:v:0','-an',
                            '-c:v','h264_videotoolbox','-b:v','850k','-maxrate','1100k','-bufsize','2200k',
                            '-g',str(max(1,round(a.get('fps',30)/2))),'-pix_fmt','yuv420p','-movflags','+faststart',out]
                info=subprocess.run([str(render.FF),'-hide_banner','-nostdin','-i',a['path']],capture_output=True,timeout=10).stderr.decode(errors='replace')
                video=next((line for line in info.splitlines() if 'Video:' in line),'')
                pixel='p010le' if '10le' in video else 'nv12'
                scale=min(1,640/max(a['width'],a['height']))
                w,h=max(2,round(a['width']*scale/2)*2),max(2,round(a['height']*scale/2)*2)
                hardware=[f'scale_vt=w={w}:h={h}','hwdownload',f'format={pixel}',*filters[1:]]
                try:
                    transcode(['-v','error','-hwaccel','videotoolbox','-hwaccel_output_format','videotoolbox_vld','-i',a['path'],'-vf',','.join(hardware),*output],a['duration'])
                except ValueError:
                    # Some imported codecs have no hardware frames; same output contract.
                    transcode(['-y','-v','error','-i',a['path'],'-vf',','.join(filters),*output],a['duration'])
            os.replace(out, dest)
        self.prune(dest)

    def prune(self, keep):
        files=[p for p in self.folder.iterdir() if p.is_file() and p.suffix in ('.mp4','.m4a','.png','.wav')]
        total=sum(p.stat().st_size for p in files)
        with self.lock: protected={n for n,t in self.requested.items() if time.monotonic()-t<120}
        for path in sorted(files,key=lambda p:p.stat().st_mtime):
            if total<=2*1024**3:break
            if path==keep or path.name in protected:continue
            total-=path.stat().st_size;path.unlink(missing_ok=True)

    def status(self, urls):
        if not isinstance(urls,list) or len(urls)>100: raise ValueError('Lista de medios no válida')
        names = list(dict.fromkeys(url.removeprefix('/native/') for url in urls if isinstance(url,str) and url.startswith('/native/')))
        with self.lock:
            for n in names:
                if n in self.files:self.requested[n]=time.monotonic()
                if n in self.jobs and not (self.folder/n).exists() and n not in self.queue and self.jobs[n].get("state")!="working" and not self.jobs[n].get("error"):self.queue.append(n)
            # Prioritize the currently requested sources; never start an unregistered path.
            priority = [n for n in names if n in self.queue]
            self.queue = priority + [n for n in self.queue if n not in priority]
            result={'ready': ['/native/'+n for n in names if n in self.files and (self.folder/n).is_file()],
                    'failed': ['/native/'+n for n in names if self.jobs.get(n,{}).get('error')],
                    'remaining': len(self.queue) + int(self.running)}
        self.start()
        return result

    def plan(self, p):
        visible = [g for g in p['graphics'] if not g.get('hidden')]
        if p.get('ducking') or any(x.get('speed',1)!=1 for k in ('clips','audio','graphics') for x in p[k]) or any(g['type'] not in ('image','video','title') or
                                   g['type']=='title' and set(g.get('keyframes',{}))-{'opacity'} for g in visible):
            return None
        assets = {a['id']: a for a in p['assets']}
        factor = min(1,640/max(p['width'],p['height']))
        width = round(p['width']*factor/2)*2; height = round(p['height']*factor/2)*2
        plan = dict(width=width, height=height, fps=p['fps'], frames=project.duration(p), clips=[], layers=[], audio=[])
        start = 0
        for clip in p['clips']:
            a = assets[clip['asset']]
            plan['clips'].append(dict(clip, start=start, url=self.resource(a, clip.get('color'))))
            start += clip['length']
        for g in sorted(visible, key=lambda g:g['type']!='video'):
            item = copy.deepcopy(g)
            if g['type']=='title':
                sprite = preview.text_layer(g,'graphics',(width,height),self.folder)
                item.update(sprite); item['url']=self.existing(item.pop('path'))
            else:
                aid = g['asset'] if g['type']=='video' else g['props']['asset']
                item['url'] = self.resource(assets[aid])
                item['sourceWidth'],item['sourceHeight'] = assets[aid]['width'],assets[aid]['height']
            plan['layers'].append(item)
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
                first=int((source+1e-8)//30)*30
                length=min(item['length']-offset,first+30-source)
                piece=dict(item,id=item['id']+':'+str(first),start=item['start']+offset,source=max(0,source-first),length=length,
                           url=self.resource(asset,audio=True,source_start=first),fadeOffset=item.get('fadeOffset',0)+offset)
                if 'deClickLength' in item:piece['deClickOffset']=item.get('deClickOffset',0)+offset
                plan['audio'].append(piece);offset+=length
        for cue in preview.image_cues(p,self.folder):
            cue=dict(cue);cue['url']=self.existing(cue.pop('path'))
            plan['audio'].append(cue)
        order={}
        for item in [*plan['clips'],*plan['layers']]:order[item['url']]=min(order.get(item['url'],float('inf')),item['start']/p['fps'])
        for item in plan['audio']:order[item['url']]=min(order.get(item['url'],float('inf')),item['start'])
        with self.lock:self.queue.sort(key=lambda name:order.get('/native/'+name,float('inf')))
        self.start()
        return plan

    def existing(self, path):
        name = Path(path).name
        with self.lock: self.files.add(name)
        return '/native/'+name
