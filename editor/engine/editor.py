#!/usr/bin/env python3
"""Studio Local: JSON CLI, native bridge and MCP stdio over one command surface."""
import argparse
import base64
import copy
import fcntl
import hashlib
import io
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
import project
import render
import sounds
import preview
import sync
import feedback
import audio_library
import project_library
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT/'projects'
EXPORTS = Path.home()/'Movies'/'Studio Local'

@contextmanager
def lock(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield

def project_path(req):
    path=Path(req.get('project','')).expanduser().resolve()
    if path.suffix!='.studio': raise ValueError('Selecciona un proyecto .studio')
    return path

def summary(path, p):
    return dict(project=p,path=str(path),frames=project.duration(p),duration=project.duration(p)/p['fps'],joinable=project.join_counts(p))

def import_srt(path, fps):
    contents=Path(path).read_text(encoding='utf-8-sig')
    result=[]
    def seconds(v):
        h,m,s=re.split('[:,.]',v)[:3]
        ms=re.split('[:,.]',v)[3]
        return int(h)*3600+int(m)*60+int(s)+int(ms)/1000
    for block in re.split(r'\r?\n\s*\r?\n',contents.strip()):
        lines=block.splitlines(); i=next((n for n,l in enumerate(lines) if '-->' in l),-1)
        if i<0: continue
        a,b=lines[i].split('-->'); start=round(seconds(a.strip())*fps); end=round(seconds(b.strip().split()[0])*fps)
        if end>start: result.append(dict(id=project.uid(),start=start,length=end-start,text='\n'.join(lines[i+1:])))
    if not result: raise ValueError('No se encontraron subtítulos SRT válidos')
    return result

def dispatch(req):
    action=req.get('action','list')
    if action=='projectFolders':return project_library.dispatch(PROJECTS,req)
    if action=='audioLibrary':return audio_library.synchronize(ROOT.parent,req.get('role','sfx'))
    if action in ('sessionRead','sessionSave'):
        session=ROOT/'.session.json'
        if action=='sessionSave':project.atomic_json(session,req['session'])
        return json.loads(session.read_text()) if session.exists() else None
    if action=='list':
        PROJECTS.mkdir(parents=True,exist_ok=True)
        items=[]
        library=project_library.load(PROJECTS)
        for path in project_library.project_files(PROJECTS):
            try:
                p=project.load(path)
                items.append(dict(id=p['id'],folder=library['assignments'].get(p['id']),path=str(path),name=p['name'],revision=p['revision'],duration=project.duration(p)/p['fps'],
                                  width=p['width'],height=p['height'],fps=p['fps'],modified=path.stat().st_mtime))
            except (OSError,ValueError,KeyError): pass
        return {'projects':items,**project_library.result(library),'templates':list(project.TEMPLATES),'version':'1.0.0','runtime':'native-ffmpeg'}
    if action=='create':
        name=req.get('name','Proyecto sin título').strip()[:120] or 'Proyecto sin título'
        folder=PROJECTS/(re.sub(r'[^\w -]','',name).strip()[:60]+'-'+project.uid())
        path=folder/'Proyecto.studio'
        p=project.new(name,int(req.get('width',1920)),int(req.get('height',1080)),float(req.get('fps',60000/1001)))
        with project_library.locked(PROJECTS) as library:
            destination=req.get('folder')
            if destination is not None:
                project_library.folder(library,destination)
                library['assignments'][p['id']]=destination
                project_library.save(PROJECTS,library)
            project.save(path,p)
        return summary(path,p)
    if action=='probe': return render.probe(req['path'])
    path=project_path(req)
    if action=='feedback':
        with lock(path):
            p=project.load(path)
            if req.get('command') in ('create','list','get') and 'revision' in req:p=sync.base_project(path,p,req['revision'])
        return feedback.dispatch(path,p,req)
    with lock(path):
        p=project.load(path)
        if action=='poll':return {'changed':False} if req.get('revision')==p['revision'] else {'changed':True,**summary(path,p)}
        stale='revision' in req and req['revision']!=p['revision']
        if stale and action!='ops':
            raise sync.Conflict('El proyecto cambió. Vuelve a abrirlo antes de aplicar esta modificación.')
        if action=='open': return summary(path,p)
        if action in ('render','frame','thumbnail','analyze','previewSound','preparePlayback'):
            snapshot=copy.deepcopy(p)
        elif action in ('undo','redo'):
            history=path.parent/'.history'/p['id']
            statepath=history/'cursor.json'
            state=json.loads(statepath.read_text()) if statepath.exists() else {'undo':[],'redo':[]}
            src,dest=('undo','redo') if action=='undo' else ('redo','undo')
            if not state[src]: raise ValueError('No hay cambios que '+('deshacer' if action=='undo' else 'rehacer'))
            restored=project.load(history/state[src].pop())
            filename=f"snapshot-{project.uid()}.studio"; project.atomic_json(history/filename,p); state[dest].append(filename)
            restored['revision']=p['revision']+1
            project.save(path,restored,p); project.atomic_json(statepath,state)
            return summary(path,restored)
        else:
            previous=copy.deepcopy(p)
            if action in ('import','importImageData'):
                library_role=req.get('libraryRole')
                if library_role is not None:
                    audio_library.role_name(library_role)
                    if action!='import':raise ValueError('Selecciona un archivo de audio')
                if action=='importImageData':
                    encoded=req.get('png','')
                    if not isinstance(encoded,str) or len(encoded)>90_000_000:raise ValueError('La imagen del portapapeles es demasiado grande')
                    raw=base64.b64decode(encoded,validate=True)
                    with Image.open(io.BytesIO(raw)) as image:
                        image=ImageOps.exif_transpose(image).convert('RGBA')
                        buf=io.BytesIO();image.save(buf,format='PNG');raw=buf.getvalue()
                    digest=hashlib.sha256(raw).hexdigest()[:24]
                    media=path.parent/'media'/('Captura-'+digest+'.png');media.parent.mkdir(exist_ok=True)
                    if not media.exists():
                        with tempfile.NamedTemporaryFile(dir=media.parent,delete=False) as f:f.write(raw);temp=f.name
                        os.replace(temp,media)
                    req={**req,'path':str(media)}
                media_path=str(Path(req['path']).expanduser().resolve())
                existing=None if library_role else next((x for x in p['assets'] if x['path']==media_path),None)
                a=existing or render.probe(media_path)
                if library_role and (a['kind']!='audio' or not a['audio']):raise ValueError('Selecciona un archivo que contenga solo audio')
                if req.get('overlay') and a['kind']!='video':raise ValueError('Selecciona un vídeo para superponer')
                if a['audio'] and not existing: a['waveform']=render.waveform(a['path'])
                if not existing: p['assets'].append(a)
                length=max(1,round(a['duration']*p['fps']))
                if a['kind']=='video':
                    if a.get('hdr'): raise ValueError('Convierte el HDR a SDR Rec.709 antes de añadirlo a este proyecto')
                    if req.get('overlay'):
                        if req.get('replaceOverlay'):project.replace_overlay(p,req['replaceOverlay'],a['id'])
                        else:project.add_overlay(p,a['id'],int(req.get('start',0)))
                    else:p['clips'].append(dict(id=project.uid(),asset=a['id'],**{'in':0},length=length,volumeDb=0,zoom=1,zoomEnd=1,x=.5,y=.5,color={}))
                elif a['kind']=='audio':
                    role=library_role or req.get('role','music')
                    clip=dict(id=project.uid(),asset=a['id'],**{'in':0},start=int(req.get('start',0)),length=length,role=role,volumeDb=0)
                    if library_role=='music':clip.update(volumeDb=-24,fadeIn=min(length,max(1,round(p['fps']*.5))),fadeOut=min(length,max(1,round(p['fps']*.5))))
                    p['audio'].append(clip)
                else:
                    start=max(0,min(int(req.get('start',0)),max(0,project.duration(p)-1)))
                    width=min(880,780*max(1,a['width'])/max(1,a['height']))
                    p['graphics'].append(dict(id=project.uid(),type='image',start=start,length=max(1,min(round(p['fps']*4),(project.duration(p) or round(p['fps']*4))-start)),props={'asset':a['id'],'width':width,'x':960,'y':960*p['height']/p['width'],'animation':'pop','enter':.48,'style':'photo','sound':True,'soundDb':-18}))
                p['revision']+=1
                project.validate(p)
                if library_role:
                    saved=audio_library.retain(ROOT.parent,media_path,library_role)
                    reusable=next((x for x in p['assets'] if x['id']!=a['id'] and x['path']==str(saved)),None)
                    if reusable:
                        p['assets'].remove(a);clip['asset']=reusable['id']
                    else:a.update(path=str(saved),name=saved.name)
            elif action=='ops': p=sync.rebase(path,p,req['revision'],req['ops']) if stale else project.apply(p,req['ops'])
            elif action=='captions':
                p['captions'].extend(import_srt(req['path'],p['fps'])); p['revision']+=1
            else: raise ValueError('Acción desconocida')
            history=path.parent/'.history'/p['id']; statepath=history/'cursor.json'
            state=json.loads(statepath.read_text()) if statepath.exists() else {'undo':[],'redo':[]}
            filename=f"snapshot-{project.uid()}.studio"; project.atomic_json(history/filename,previous)
            state['undo'].append(filename); state['redo']=[]
            project.save(path,p,previous); project.atomic_json(statepath,state)
            return summary(path,p)
    if action=='thumbnail':
        if not snapshot['clips']:return {'path':None}
        # A project-content key also catches direct edits that retain the revision.
        key=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()[:20]
        folder=path.parent/'frames'; dest=folder/('thumbnail-'+key+'.jpg')
        if not dest.exists():
            try:
                frame=render.frame(snapshot,min(round(snapshot['fps']*.8),project.duration(snapshot)-1),folder)
                with Image.open(frame['path']) as im:
                    im.thumbnail((480,270));im.save(dest,quality=85)
            except (OSError,ValueError):return {'path':None,'error':'No se pudo crear la miniatura. Abre el proyecto para revisar sus medios.'}
        render.maintain_cache(path.parent,snapshot.get('cacheLimitGB',5),dest)
        return {'path':str(dest)}
    if action=='previewSound':
        animation=req.get('animation','pop');seconds=req.get('seconds',.48)
        if animation not in project.IMAGE_ANIMATIONS:raise ValueError('Animación desconocida')
        project.number(seconds,.12,2,'duración del sonido')
        dest=path.parent/'frames'/('motion-preview-'+project.uid()+'.wav');dest.parent.mkdir(exist_ok=True)
        sounds.motion_sound(dest,animation,seconds)
        render.maintain_cache(path.parent,p.get('cacheLimitGB',5),dest)
        return {'path':str(dest)}
    if action=='preparePlayback':
        frame=req.get('frame',0);project.number(frame,0,100_000_000,'fotograma de reproducción')
        if int(frame)!=frame:raise ValueError('El fotograma debe ser entero')
        return preview.prepare(snapshot,path.parent,bool(req.get('nativeImages')),bool(req.get('nativeText')),bool(req.get('nativeMotion')),bool(req.get('nativeVideo')),bool(req.get('interactive')),int(frame),bool(req.get('lookAhead')),bool(req.get('forceRaster')),bool(req.get('nativeLut')))
    if action=='render':
        # Renders are immutable snapshots; later edits cannot change a running export.
        span=req.get('range')
        if span is not None:
            if not (isinstance(span,list) and len(span)==2 and all(type(x) is int for x in span)):raise ValueError('El tramo debe ser [inicio, fin) en fotogramas enteros')
            snapshot=project.excerpt(snapshot,*span)
        is_preview=bool(req.get('preview')) or span is not None
        folder=path.parent/'previews' if is_preview else EXPORTS
        result=render.render(snapshot,folder,is_preview,label='-'.join(map(str,span)) if span else '')
        result['cache']=render.maintain_cache(path.parent,snapshot.get('cacheLimitGB',5),result['path'])
        return result
    if action=='frame':
        result=render.frame(snapshot,req.get('frame',0),path.parent/'frames')
        render.maintain_cache(path.parent,snapshot.get('cacheLimitGB',5),result['path'])
        return result
    if action=='analyze':
        voice=copy.deepcopy(snapshot)
        voice['audio']=[a for a in voice['audio'] if a['role']=='voice']
        voice['mixer']={r:0 for r in project.ROLES}; voice['ducking']=False
        with tempfile.TemporaryDirectory(prefix='studio-silence-') as d:
            audio=render.render_audio(voice,Path(d))
            result=subprocess.run([str(render.FF),'-hide_banner','-nostdin','-i',str(audio),'-af','silencedetect=noise=-38dB:d=0.35','-f','null','-'],capture_output=True,text=True)
            if result.returncode: raise ValueError('No se pudo analizar la voz')
        candidates=[]; start=None
        for line in result.stderr.splitlines():
            m=re.search(r'silence_start: ([\d.]+)',line)
            if m: start=float(m[1])
            m=re.search(r'silence_end: ([\d.]+)',line)
            if m and start is not None:
                a=math.ceil((start+.12)*p['fps']); b=math.floor((float(m[1])-.15)*p['fps'])
                if b-a>=round(.15*p['fps']): candidates.append(dict(start=a,end=b,reason='silence'))
                start=None
        return {'revision':snapshot['revision'],'candidates':candidates,'automaticCuts':False}

def mcp():
    """MCP JSON-RPC stdio. No network listener or dependency on an MCP SDK."""
    description='Read/edit a local Studio project with the same frame-based operations as the native UI. Actions: list, audioLibrary (role sfx/music, no project; synchronize persistent audio folders), create, open, poll (revision check), import (optional libraryRole sfx/music copies validated audio into the persistent library; overlay=true adds a muted video above the main track at start; replaceOverlay=id replaces its media preserving placement), ops, undo, redo, captions, frame, thumbnail, preparePlayback (native playback plan with cached audio/effect ranges), render (encoded file), importImageData (base64 png), previewSound. List includes duration, dimensions, fps and modification time; thumbnail returns a cached poster without editing the project. Image props include cropLeft/Top/Right/Bottom fractions, width, x/y, rotation, animation (pop/from-left/from-right/from-top/from-bottom/none), enter seconds, sound boolean and soundDb; sound follows the image. Video overlays are graphics of type video, with top-level asset/in/speed/muted/volumeDb and image geometry in props. Video overlays composite above the main video and below other graphics. Ops addOverlay(asset,start), source(id,in), and promoteOverlay(id) add an existing video, change its source position, or replace the underlying main-track interval at full-screen framing without changing duration. These operations reject stale revisions. Ops include duplicate(kind,id,newId?,start?,length?) for an independent copy: video inserts after the selected clip and repeats linked layers; other elements default to immediately after the source and require the whole copy inside the video, with optional explicit start and shorter length. Duplication rejects stale revisions. Ops also include splitAt(frame) for video and linked layers, linkTrack(track, linked) for all/overlays/graphics/captions/voice/music/sfx, joinTrack(track) for video/overlays/graphics/captions/voice/music/sfx to reunite compatible fragments of one element (stale joins conflict), and set(values.linked) for a per-item override. Project summaries include joinable counts per track. A title without keyframes can set keepTogether=true to reunite compatible pieces after cuts; explicitly splitting that item clears the flag. Distinct caption words stay independent. cutRange and video trim/delete keep independent layers unchanged. Always use revision for edits. Independent stale ops merge against their saved base; overlaps and ambiguous timeline edits return a conflict without writing. Re-read and reconsider after conflicts; never force-write or replace the whole project. Feedback action manages frame-anchored review notes without changing the project. Commands list/get/create/capture/update; create needs id, frame and displayed project revision, capture creates the original snapshot image. Update needs id, note version and values (text, strokes, status, resolution, appliedRevision); read annotated PNG and currentFrame before applying an explicitly requested edit, then resolve only after verification. Notes and captures stay in project/feedback. Never overwrite source media.'
    for line in sys.stdin:
        try:
            msg=json.loads(line); method=msg.get('method'); id=msg.get('id')
            if id is None: continue
            if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'studio-local','version':'1.0.0'}}
            elif method=='ping': result={}
            elif method=='tools/list': result={'tools':[{'name':'studio','description':description,'inputSchema':{'type':'object','properties':{'action':{'type':'string'},'command':{'type':'string'},'id':{'type':'string'},'version':{'type':'integer'},'values':{'type':'object'},'status':{'type':'string'},'since':{'type':'integer'},'projectRevision':{'type':'integer'},'png':{'type':'string'},'animation':{'type':'string'},'seconds':{'type':'number'},'project':{'type':'string'},'revision':{'type':'integer'},'ops':{'type':'array','items':{'type':'object'}},'path':{'type':'string'},'name':{'type':'string'},'preview':{'type':'boolean'},'range':{'type':'array','items':{'type':'integer'}},'frame':{'type':'integer'},'role':{'type':'string'},'libraryRole':{'type':'string','enum':['sfx','music']},'start':{'type':'integer'},'overlay':{'type':'boolean'},'replaceOverlay':{'type':'string'},'nativeImages':{'type':'boolean'},'nativeText':{'type':'boolean'},'nativeMotion':{'type':'boolean'},'nativeVideo':{'type':'boolean'},'interactive':{'type':'boolean'},'lookAhead':{'type':'boolean'},'forceRaster':{'type':'boolean'},'width':{'type':'integer'},'height':{'type':'integer'},'fps':{'type':'number'}},'required':['action']}}]}
            elif method=='tools/call':
                if msg['params']['name']!='studio': raise ValueError('Herramienta desconocida')
                try:
                    data=dispatch(msg['params'].get('arguments',{})); result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}]}
                except Exception as e: result={'content':[{'type':'text','text':str(e)}],'isError':True}
            else:
                print(json.dumps({'jsonrpc':'2.0','id':id,'error':{'code':-32601,'message':'Method not found'}}),flush=True); continue
            print(json.dumps({'jsonrpc':'2.0','id':id,'result':result}),flush=True)
        except Exception as e:
            print(json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':str(e)}}),flush=True)

def main():
    parser=argparse.ArgumentParser(description='Studio Local JSON CLI / MCP')
    parser.add_argument('--request'); parser.add_argument('--request-file'); parser.add_argument('--mcp',action='store_true')
    args=parser.parse_args()
    if args.mcp: mcp(); return
    req=json.loads(Path(args.request_file).read_text() if args.request_file else (args.request or sys.stdin.read()))
    try: print(json.dumps({'ok':True,'result':dispatch(req)},ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'ok':False,'error':str(e),'conflict':isinstance(e,sync.Conflict)},ensure_ascii=False)); sys.exit(1)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(InterruptedError('Operación cancelada')))
    main()
