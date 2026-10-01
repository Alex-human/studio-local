"""Merge independent edits against their saved base; overlapping edits stay explicit."""
import copy,json
import project
import caption_layout

class Conflict(ValueError):
    pass

MISSING=object()
def merge(base,current,wanted,path=()):
    if wanted==base:return copy.deepcopy(current) if current is not MISSING else MISSING
    if current==base or wanted==current:return copy.deepcopy(wanted) if wanted is not MISSING else MISSING
    if all(isinstance(v,dict) for v in (base,current,wanted)):
        result={}
        for key in dict.fromkeys([*current,*wanted,*base]):
            if not path and key=='revision':continue
            value=merge(base.get(key,MISSING),current.get(key,MISSING),wanted.get(key,MISSING),path+(key,))
            if value is not MISSING:result[key]=value
        return result
    if len(path)==1 and path[0] in ('clips','audio','graphics','captions','assets') and all(isinstance(v,list) for v in (base,current,wanted)):
        maps=[{i['id']:i for i in v} for v in (base,current,wanted)];orders=[[i['id'] for i in v] for v in (base,current,wanted)]
        if path[0]=='clips':
            if orders[0]==orders[2]:order=orders[1]
            elif orders[0]==orders[1] or orders[1]==orders[2]:order=orders[2]
            else:raise Conflict('Hay dos cambios simultáneos en los cortes. No se ha sobrescrito ninguno; revisa el tramo actualizado antes de repetir el corte.')
        else:order=list(dict.fromkeys(orders[1]+orders[2]))
        result=[]
        for id in dict.fromkeys(order+orders[0]):
            value=merge(*(m.get(id,MISSING) for m in maps),path+(id,))
            if value is not MISSING:result.append(value)
        return result
    field=' / '.join(path)
    raise Conflict('Otro cambio modifica el mismo elemento ('+field+'). Tu cambio no se ha aplicado; revisa la versión actual antes de repetirlo.')

def base_project(path,current,revision):
    if current['revision']==revision:return copy.deepcopy(current)
    history=path.parent/'.history'/current['id'];cursor=history/'cursor.json'
    state=json.loads(cursor.read_text()) if cursor.exists() else {}
    for filename in reversed(state.get('undo',[])+state.get('redo',[])):
        base=project.load(history/filename)
        if base['revision']==revision:return base
    raise Conflict('No está disponible la revisión base. Actualiza el proyecto antes de repetir este cambio.')

def rebase(path,current,revision,ops):
    if not ops:raise Conflict('No hay cambios que combinar.')
    if any(op['op']=='joinTrack' for op in ops):
        raise Conflict('El proyecto cambió antes de unir los tramos. Actualiza y revisa los fragmentos antes de repetir la unión.')
    if any(op['op'] in ('promoteOverlay','addOverlay','source') for op in ops):
        raise Conflict('El proyecto cambió antes de modificar la superposición. Actualiza y repite el cambio.')
    if any(op['op']=='duplicate' for op in ops):
        raise Conflict('El proyecto cambió antes de duplicar. Actualiza y revisa el elemento antes de volver a copiarlo.')
    base=base_project(path,current,revision)
    shape=lambda p:[(c['id'],c['in'],c['length'],c.get('speed',1)) for c in p['clips']]
    if shape(base)!=shape(current) and any(op['op'] not in ('set','mixer','settings','linkTrack') for op in ops):
        raise Conflict('La línea de tiempo cambió mientras editabas. Revisa la posición actual antes de repetir este corte o inserción.')
    for op in ops:
        if op['op'] == 'set' and op['kind'] == 'graphics':
            item = project.find(base, 'graphics', op['id'])
            group = caption_layout.edit_group(base, item, op['values']) if item else []
            if group and not caption_layout.unchanged_group(group, current):
                raise Conflict('El bloque de subtítulos cambió mientras editabas. Revisa su texto actual antes de repetir la corrección.')
    wanted=project.apply(base,ops)
    removed={g['id'] for g in base['graphics']}-{g['id'] for g in wanted['graphics']}
    if removed and any(g.get('keepTogether') for g in base['graphics']+wanted['graphics']):
        raise Conflict('El proyecto cambió antes de reunir el título. Actualiza y revisa sus fragmentos antes de repetir el cambio.')
    result=merge(base,current,wanted);result['revision']=current['revision']+1
    return project.validate(result)
