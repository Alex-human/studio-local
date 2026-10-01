"""Frame-anchored local review notes. Separate from the editable/rendered project."""
import copy,json,math,re,sqlite3,time,uuid
from contextlib import contextmanager
from pathlib import Path
from PIL import Image,ImageDraw
import project,render,sync

STATES=('draft','open','resolved','deleted')
def root(path):return Path(path).parent/'feedback'
def note_dir(path,id):
    if not isinstance(id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',id):raise ValueError('ID de feedback no válido')
    return root(path)/id
@contextmanager
def database(path,write=False):
    folder=root(path);folder.mkdir(exist_ok=True)
    db=sqlite3.connect(folder/'feedback.sqlite3',timeout=10)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS change_version(value INTEGER NOT NULL); INSERT INTO change_version SELECT 0 WHERE NOT EXISTS(SELECT 1 FROM change_version);')
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db
        db.commit()
    except BaseException:db.rollback();raise
    finally:db.close()
def get(db,id,pid):
    row=db.execute('SELECT body FROM notes WHERE id=?',(id,)).fetchone()
    if not row:raise ValueError('Feedback no encontrado')
    note=json.loads(row[0])
    if note['projectId']!=pid:raise ValueError('El feedback pertenece a otro proyecto')
    return note
def put(db,note):
    db.execute('INSERT OR REPLACE INTO notes VALUES(?,?)',(note['id'],json.dumps(note,ensure_ascii=False)))
    db.execute('UPDATE change_version SET value=value+1')
def anchor(p,frame):
    start=0
    for c in p['clips']:
        if start<=frame<start+c['length']:return dict(id=c['id'],asset=c['asset'],sourceSeconds=(c['in']+(frame-start)*c.get('speed',1))/p['fps'])
        start+=c['length']
    raise ValueError('No hay vídeo en ese fotograma')
def locate(p,note):
    a=note['anchor'];start=0;matches=[]
    for c in p['clips']:
        source=a['sourceSeconds']*p['fps']
        if c['asset']==a['asset'] and c['in']-1e-6<=source<c['in']+c['length']*c.get('speed',1)-1e-6:
            matches.append((c['id'],start+round((source-c['in'])/c.get('speed',1))))
        start+=c['length']
    exact=[m for m in matches if m[0]==a['id']]
    if len(exact)==1:return exact[0][1],'current'
    if len(matches)==1:return matches[0][1],'current'
    return None,'ambiguous' if matches else 'removed'
def describe(path,p,note):
    n=copy.deepcopy(note);n['currentFrame'],n['position']=locate(p,n)
    n['currentSeconds']=n['currentFrame']/p['fps'] if n['currentFrame'] is not None else None
    folder=note_dir(path,n['id']);n['files']={key:str(folder/name) for key,name in [('project','snapshot.studio'),('image','frame.png'),('annotated','annotated.png')] if (folder/name).exists()}
    return n
def strokes_checked(strokes):
    if not isinstance(strokes,list) or len(strokes)>100:raise ValueError('Máximo 100 trazos por comentario')
    for s in strokes:
        if not isinstance(s,dict) or s.get('tool') not in ('pen','ellipse','rect','arrow'):raise ValueError('Herramienta de dibujo no válida')
        if not isinstance(s.get('color'),str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',s['color']):raise ValueError('Color no válido')
        project.number(s.get('width'),.001,.02,'grosor')
        points=s.get('points')
        if not isinstance(points,list) or not 1<=len(points)<=2000:raise ValueError('Trazo no válido')
        if s['tool']!='pen' and len(points)!=2:raise ValueError('La forma necesita dos puntos')
        for point in points:
            if not isinstance(point,list) or len(point)!=2:raise ValueError('Punto no válido')
            for v in point:project.number(v,0,1,'coordenada')
def save_png(image,path):
    temp=path.with_name('.'+uuid.uuid4().hex+'.png');image.save(temp);temp.replace(path)
def annotate(folder,strokes):
    if not (folder/'frame.png').exists():return
    with Image.open(folder/'frame.png') as original:
        w,h=original.size;im=original.convert('RGB').resize((w*2,h*2));draw=ImageDraw.Draw(im)
    for s in strokes:
        points=[(x*w*2,y*h*2) for x,y in s['points']];width=max(2,round(s['width']*min(w,h)*2));color=s['color']
        if s['tool']=='pen':
            if len(points)>1:draw.line(points,fill=color,width=width,joint='curve')
            for x,y in [points[0],points[-1]]:draw.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=color)
        else:
            (x1,y1),(x2,y2)=points;box=(min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2))
            if s['tool']=='ellipse':draw.ellipse(box,outline=color,width=width)
            elif s['tool']=='rect':draw.rectangle(box,outline=color,width=width)
            else:
                draw.line(points,fill=color,width=width);angle=math.atan2(y2-y1,x2-x1);size=max(width*4,min(w,h)*.035*2)
                draw.polygon([(x2,y2),(x2-size*math.cos(angle-.5),y2-size*math.sin(angle-.5)),(x2-size*math.cos(angle+.5),y2-size*math.sin(angle+.5))],fill=color)
    save_png(im.resize((w,h),Image.Resampling.LANCZOS),folder/'annotated.png')
def dispatch(path,p,req):
    command=req.get('command','list')
    if command=='list':
        if not (root(path)/'feedback.sqlite3').exists():return {'version':0,'projectRevision':p['revision'],'notes':[]}
        with database(path) as db:
            version=db.execute('SELECT value FROM change_version').fetchone()[0]
            if req.get('since')==version and req.get('projectRevision')==p['revision']:return {'version':version,'unchanged':True}
            notes=[json.loads(row[0]) for row in db.execute('SELECT body FROM notes')]
        status=req.get('status');notes=[n for n in notes if n['projectId']==p['id'] and (n['status']==status if status else n['status']!='deleted')]
        items=[describe(path,p,n) for n in notes];items.sort(key=lambda n:(n['currentFrame'] if n['currentFrame'] is not None else 1e12,n['createdAt']))
        return {'version':version,'projectRevision':p['revision'],'notes':items}
    id=req.get('id');folder=note_dir(path,id)
    if command=='create':
        frame=req.get('frame');project.number(frame,0,max(0,project.duration(p)-1),'fotograma')
        if type(frame)!=int:raise ValueError('El fotograma debe ser entero')
        with database(path,True) as db:
            if db.execute('SELECT 1 FROM notes WHERE id=?',(id,)).fetchone():return describe(path,p,get(db,id,p['id']))
            folder.mkdir(exist_ok=True);project.atomic_json(folder/'snapshot.studio',p)
            note=dict(id=id,projectId=p['id'],version=1,status='draft',text='',strokes=[],frame=frame,fps=p['fps'],seconds=frame/p['fps'],width=p['width'],height=p['height'],revision=p['revision'],anchor=anchor(p,frame),capture='pending',createdAt=time.time(),updatedAt=time.time(),resolution='',targets={kind:[i['id'] for i in p[kind] if i['start']<=frame<i['start']+i['length']] for kind in ('graphics','captions','audio')})
            put(db,note)
        return describe(path,p,note)
    if command=='capture':
        with database(path) as db:note=get(db,id,p['id'])
        if note['capture']=='ready' and (folder/'frame.png').exists():return describe(path,p,note)
        snapshot=project.load(folder/'snapshot.studio')
        try:
            result=render.frame(snapshot,note['frame'],folder,width=min(snapshot['width'],1920))
            with Image.open(result['path']) as im:save_png(im.convert('RGB'),folder/'frame.png')
            with database(path,True) as db:
                note=get(db,id,p['id']);annotate(folder,note['strokes']);note['capture']='ready';put(db,note)
        except Exception:
            with database(path,True) as db:
                note=get(db,id,p['id']);note['capture']='error';put(db,note)
            raise
        return describe(path,p,note)
    if command=='get':
        with database(path) as db:return describe(path,p,get(db,id,p['id']))
    if command!='update':raise ValueError('Operación de feedback desconocida')
    values=req.get('values',{})
    if not isinstance(values,dict) or any(k not in ('text','strokes','status','resolution','appliedRevision') for k in values):raise ValueError('Campos de feedback no válidos')
    with database(path,True) as db:
        note=get(db,id,p['id'])
        if req.get('version')!=note['version']:raise sync.Conflict('Este feedback cambió en otra sesión. Tu borrador se conserva; recarga la nota antes de guardar.')
        for field in ('text','resolution'):
            if field in values and (not isinstance(values[field],str) or len(values[field])>12000):raise ValueError('Comentario demasiado largo')
        if 'strokes' in values:strokes_checked(values['strokes'])
        if 'status' in values and values['status'] not in STATES:raise ValueError('Estado no válido')
        if 'appliedRevision' in values:project.number(values['appliedRevision'],0,p['revision'],'revisión aplicada')
        note.update(values)
        if note['status'] in ('open','resolved') and (not note['text'].strip() and not note['strokes']):raise ValueError('Escribe un comentario o dibuja una indicación')
        if note['status'] in ('open','resolved') and note['capture']!='ready':raise ValueError('Espera a que esté lista la captura antes de guardar')
        if 'strokes' in values:annotate(folder,note['strokes'])
        note['version']+=1;note['updatedAt']=time.time();put(db,note)
    return describe(path,p,note)
