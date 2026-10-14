"""Frame-based project model shared by UI, CLI and MCP. Source media is immutable."""
import copy
import json
import math
import os
import re
import uuid
from pathlib import Path
from PIL import ImageColor
import caption_layout

VERSION = 1
ROLES = ('voice', 'music', 'sfx')
SYNC_TRACKS = ('overlays', 'graphics', 'captions', *ROLES)
JOIN_TRACKS = ('video', *SYNC_TRACKS)
TEMPLATES = ('title', 'lower_third', 'stat', 'cards', 'progress', 'image', 'video', 'channel_intro')
IMAGE_ANIMATIONS = ('none', 'pop', 'from-left', 'from-right', 'from-top', 'from-bottom')
LUTS = ('dlogm',)  # editor/assets/luts/<name>.cube

def uid():
    return uuid.uuid4().hex[:12]

def new(name='Proyecto sin título', width=1920, height=1080, fps=60000/1001):
    return dict(schema=VERSION, id=uid(), name=name, revision=0, width=width, height=height,
                fps=fps, assets=[], clips=[], audio=[], graphics=[], captions=[],
                mixer=dict(voice=0, music=0, sfx=0), ducking=False, cacheLimitGB=5)

def duration(p):
    return sum(c['length'] for c in p['clips'])

def audio_gain(db):
    """The minimum fader value is digital silence, including before bus gain."""
    return 0.0 if db <= -60 else 10**(db/20)

def media_item(kind, item):
    return kind in ('clips', 'audio') or kind == 'graphics' and item.get('type') == 'video'

def track(kind, item):
    return item['role'] if kind == 'audio' else 'overlays' if kind == 'graphics' and item.get('type') == 'video' else kind

def linked(p, kind, item):
    return kind == 'clips' or item.get('linked', p.get('syncTracks', {}).get(track(kind, item), True))

def number(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{name}: fuera de rango ({lo}–{hi})')

def validate(p, check_files=False):
    if p.get('schema') != VERSION:
        raise ValueError('Versión de proyecto no compatible')
    def valid_id(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):raise ValueError('Identificador de proyecto o elemento no válido')
    valid_id(p.get('id'))
    sync = p.get('syncTracks', {})
    if not isinstance(sync, dict) or any(k not in SYNC_TRACKS or type(v) is not bool for k,v in sync.items()):
        raise ValueError('Vínculos de pistas no válidos')
    number(p['fps'], 1, 120, 'fps')
    for k in ('width', 'height'):
        number(p[k], 64, 4096, k)
        if p[k] % 2:
            raise ValueError('Las dimensiones deben ser pares')
    assets = {a['id']: a for a in p['assets']}
    if len(assets) != len(p['assets']):
        raise ValueError('ID de medio duplicado')
    ids = set()
    for a in p['assets']:
        valid_id(a.get('id'))
        if 'lut' in a and a['lut'] not in LUTS:raise ValueError('LUT de color no admitida')
        if check_files and not Path(a['path']).is_file():
            raise ValueError('Medio no disponible: ' + a['name'])
    for kind in ('clips', 'audio', 'graphics', 'captions'):
        for item in p[kind]:
            valid_id(item.get('id'))
            if item['id'] in ids:
                raise ValueError('ID de elemento duplicado')
            ids.add(item['id'])
            if 'linked' in item and (type(item['linked']) is not bool or kind == 'clips' and not item['linked']):
                raise ValueError('Vínculo no válido; el vídeo es la base del montaje')
            if 'keepTogether' in item and (type(item['keepTogether']) is not bool or kind != 'graphics' or item.get('type') != 'title' or item['keepTogether'] and item.get('keyframes')):
                raise ValueError('Mantener de una pieza solo admite títulos sin fotogramas clave')
            if kind == 'captions' and 'splitFrom' in item:valid_id(item['splitFrom'])
            if 'captionGroup' in item:
                valid_id(item['captionGroup'])
                if kind != 'graphics' or item.get('type') != 'title' or type(item.get('captionIndex')) is not int or item['captionIndex'] < 0:
                    raise ValueError('Grupo de palabras no válido')
            number(item['length'], 1, 100_000_000, 'duración')
            if int(item['length']) != item['length']:
                raise ValueError('La duración debe usar fotogramas enteros')
            if kind != 'clips':
                number(item['start'], 0, 100_000_000, 'inicio')
                if int(item['start'])!=item['start']:raise ValueError('El inicio debe usar fotogramas enteros')
            if media_item(kind, item):
                if item.get('asset') not in assets:
                    raise ValueError('Referencia a medio inexistente')
                number(item.get('in', 0), 0, 100_000_000, 'entrada')
                number(item.get('speed', 1), .25, 4, 'velocidad')
                a = assets[item['asset']]
                if kind == 'graphics' and (a.get('kind') != 'video' or a.get('hdr')):raise ValueError('La superposición necesita un vídeo SDR')
                if 'muted' in item and type(item['muted']) is not bool:raise ValueError('Silencio no válido')
                end = (item.get('in', 0) + item['length'] * item.get('speed', 1)) / p['fps']
                if a.get('duration', 0) and end > a['duration'] + 1/p['fps']:
                    raise ValueError('El corte excede el final del medio: ' + a['name'])
                number(item.get('volumeDb', 0), -60, 18, 'volumen')
                for fade in ('fadeIn','fadeOut'):number(item.get(fade,0),0,100_000_000,fade)
                for key in ('fadeOffset','fadeLength'):
                    if key in item:number(item[key],0,100_000_000,key)
            if kind == 'clips':
                number(item.get('zoom', 1), 1, 3, 'zoom')
                number(item.get('zoomEnd', item.get('zoom', 1)), 1, 3, 'zoom final')
                for k in ('x', 'y'):
                    number(item.get(k, .5), 0, 1, k)
                color = item.get('color', {})
                for k, bounds in {'exposure': (-2, 2), 'contrast': (.5, 1.5), 'saturation': (0, 2), 'temperature': (-1, 1)}.items():
                    number(color.get(k, 1 if k in ('contrast', 'saturation') else 0), *bounds, k)
            if kind == 'audio' and item.get('role') not in ROLES:
                raise ValueError('Pista de audio desconocida')
            if kind == 'graphics' and item.get('type') not in TEMPLATES:
                raise ValueError('Plantilla gráfica desconocida')
            if kind=='graphics':
                props=item.get('props',{})
                if not isinstance(props,dict):raise ValueError('Parámetros gráficos no válidos')
                if 'weight' in props:number(props['weight'],100,900,'Peso de texto')
                if item['type']=='title' and props.get('style','plain') not in ('plain','instagram','sticker'):
                    raise ValueError('Estilo de título no válido')
                if type(props.get('box',False)) is not bool:raise ValueError('Caja del gancho no válida')
                limits={'x':(-1920,3840),'y':(-1080,3840),'size':(8,500),'opacity':(0,1),'enter':(.01,10),'width':(1,3840),'value':(-1e9,1e9),'count':(1,5),'rotation':(-180,180),'soundDb':(-60,6),'cropLeft':(0,.98),'cropRight':(0,.98),'cropTop':(0,.98),'cropBottom':(0,.98)}
                for k,bounds in limits.items():
                    if k in props:number(props[k],*bounds,k)
                for k in ('text','title','subtitle','suffix'):
                    if k in props and (not isinstance(props[k],str) or len(props[k])>2000):raise ValueError('Texto gráfico no válido')
                for k in ('accent','color','background'):
                    if k in props:
                        try:ImageColor.getrgb(props[k])
                        except (ValueError,TypeError,AttributeError):raise ValueError('Color gráfico no válido')
                if 'labels' in props and (not isinstance(props['labels'],list) or not all(isinstance(x,str) and len(x)<300 for x in props['labels']) or len(props['labels'])>5):raise ValueError('Etiquetas no válidas')
                if not isinstance(item.get('keyframes',{}),dict):raise ValueError('Keyframes no válidos')
                for k,points in item.get('keyframes',{}).items():
                    if k not in limits or not isinstance(points,list):raise ValueError('Keyframes no válidos')
                    for key in points:
                        if not isinstance(key,dict):raise ValueError('Keyframe no válido')
                        number(key.get('frame'),0,100_000_000,'fotograma clave')
                        number(key.get('value'),*limits[k],k)
                if item['type'] in ('image','video'):
                    if item['type']=='image' and props.get('asset') not in assets:raise ValueError('Falta la imagen del gráfico')
                    if props.get('animation','pop') not in IMAGE_ANIMATIONS:raise ValueError('Animación de imagen no válida')
                    if props.get('style','photo') not in ('photo','clean'):raise ValueError('Marco de imagen no válido')
                    if 'sound' in props and not isinstance(props['sound'],bool):raise ValueError('Sonido de animación no válido')
                    for a,b in [('cropLeft','cropRight'),('cropTop','cropBottom')]:
                        if props.get(a,0)+props.get(b,0)>.98:raise ValueError('El recorte debe conservar parte de la imagen')
    for role in ROLES:
        number(p['mixer'][role], -60, 18, 'mezclador')
    number(p.get('cacheLimitGB',5), .1, 30, 'límite de caché')
    return p

def load(path):
    return validate(json.loads(Path(path).read_text()))

def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.' + uid() + '.tmp')
    with temp.open('w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

def save(path, p, previous=None):
    validate(p)
    atomic_json(path, p)

def slice_item(item, kind, first, last, fresh=False):
    """Keep source time, motion phase and fade envelope when a piece is split/trimmed."""
    part = copy.deepcopy(item)
    if kind == 'captions':part.setdefault('splitFrom', item['id'])
    part['length'] = last-first
    if fresh:part['id'] = uid()
    if kind != 'clips':part['start'] += first
    if media_item(kind,item):part['in'] = item.get('in',0)+first*item.get('speed',1)
    if kind in ('clips','graphics'):
        key = 'motionOffset' if kind == 'clips' else 'offset'
        part['motionLength'] = item.get('motionLength',item['length'])
        part[key] = item.get(key,0)+first
    if kind == 'audio' or kind == 'graphics' and item.get('type') == 'video' or kind == 'clips' and any(key in item for key in ('fadeIn','fadeOut','fadeOffset','fadeLength')):
        part['fadeLength'] = item.get('fadeLength',item['length'])
        part['fadeOffset'] = item.get('fadeOffset',0)+first
    return part

def static_title(item, fps):
    """Every retained frame has finished entering and has not begun its exit."""
    if item.get('type') != 'title' or item.get('keyframes'):return False
    first = item.get('offset', 0)
    last = first + item['length'] - 1
    return first >= item.get('props', {}).get('enter', .45) * fps and item.get('motionLength', item['length']) - last >= .2 * fps

def joined_pair(p, kind, left, right):
    """Remove one edit seam only when one flat element preserves both pieces."""
    if kind != 'clips' and left['start'] + left['length'] != right['start']:return None
    if linked(p, kind, left) != linked(p, kind, right):return None
    ignored = {'id', 'start', 'length', 'linked'}
    if media_item(kind,left):ignored.update(('in','fadeLength','fadeOffset'))
    if kind in ('clips', 'graphics'):ignored.update(('motionLength', 'motionOffset' if kind == 'clips' else 'offset'))
    if {k:v for k,v in left.items() if k not in ignored} != {k:v for k,v in right.items() if k not in ignored}:return None
    if kind == 'captions' and not left.get('splitFrom'):return None
    if media_item(kind,left) and not math.isclose(left.get('in', 0) + left['length'] * left.get('speed', 1), right.get('in', 0), rel_tol=0, abs_tol=1e-7):return None
    merged = copy.deepcopy(left)
    merged['length'] += right['length']
    if kind in ('clips', 'graphics'):
        key = 'motionOffset' if kind == 'clips' else 'offset'
        span = left.get('motionLength', left['length'])
        merged['motionLength'] = span
        continuous = span == right.get('motionLength', right['length']) and left.get(key, 0) + left['length'] == right.get(key, 0)
        stationary_video = kind == 'clips' and left.get('zoom', 1) == left.get('zoomEnd', left.get('zoom', 1))
        # Legacy hooks have no lineage field. Equal original motion spans and
        # advancing source phases distinguish cut pieces from repeated words.
        flat_title = kind == 'graphics' and span == right.get('motionLength', right['length']) and right.get('offset', 0) >= left.get('offset', 0) + left['length'] and all(static_title(item, p['fps']) for item in (left, right, merged))
        if not (continuous or stationary_video or flat_title):return None
    if media_item(kind,left) and (left.get('fadeIn', 0) or left.get('fadeOut', 0)):
        span = left.get('fadeLength', left['length'])
        if span != right.get('fadeLength', right['length']) or left.get('fadeOffset', 0) + left['length'] != right.get('fadeOffset', 0):return None
        merged['fadeLength'] = span
    return merged

def join_plan(p, target, kept_only=False):
    """Shared preview/apply plan; preserve collection order and the first ID."""
    if target not in JOIN_TRACKS:raise ValueError('Pista no válida para unir tramos')
    kind = 'clips' if target == 'video' else 'audio' if target in ROLES else 'graphics' if target == 'overlays' else target
    items = p[kind]
    indices = [i for i,item in enumerate(items) if (kind == 'clips' or track(kind,item) == target)]
    if kind == 'audio':indices.sort(key=lambda i:(items[i]['start'], i))
    replacements = {};removed = set();first = None
    for index in indices:
        item = items[index]
        previous = replacements.get(first, items[first]) if first is not None else None
        allowed = previous is not None and (not kept_only or previous.get('keepTogether') and item.get('keepTogether'))
        merged = joined_pair(p, kind, previous, item) if allowed else None
        if merged is None:first = index
        else:
            replacements[first] = merged;removed.add(index)
    if not kept_only and kind == 'graphics':
        for item in replacements.values():
            if static_title(item, p['fps']):item['keepTogether'] = True
    return kind, [replacements.get(i, item) for i,item in enumerate(items) if i not in removed], len(removed)

def join_counts(p):
    return {target:join_plan(p, target)[2] for target in JOIN_TRACKS}

def split_at(p, frame):
    if not 0 < frame < duration(p):raise ValueError('Sitúa el cabezal dentro del vídeo')
    offset = 0
    for kind in ('clips','audio','graphics','captions'):
        pieces = []
        for item in p[kind]:
            start = offset if kind == 'clips' else item['start']
            if kind == 'clips':offset += item['length']
            at = frame-start
            if linked(p,kind,item) and 0 < at < item['length']:
                pieces.extend([slice_item(item,kind,0,at),slice_item(item,kind,at,item['length'],True)])
            else:pieces.append(item)
        p[kind] = pieces

def excerpt(p, start, end):
    """Only [start,end) of the timeline, every layer cut in sync, for partial previews."""
    total = duration(p)
    if not 0 <= start < end <= total:raise ValueError('Tramo no válido')
    q = copy.deepcopy(p); q['syncTracks'] = {}
    for kind in ('audio', 'graphics', 'captions'):
        for item in q[kind]:item.pop('linked', None)
    ops = [dict(op='cutRange', start=a, end=b) for a, b in ((end, total), (0, start)) if a < b]
    return {**apply(q, ops), 'revision': p['revision']} if ops else q

def remove_span(p, start, length):
    """Close a video gap on linked layers; independent items keep their exact times."""
    if not length:return
    end = start + length
    for kind in ('audio', 'graphics', 'captions'):
        kept = []
        for item in p[kind]:
            if not linked(p,kind,item):
                kept.append(item);continue
            s, e = item['start'], item['start'] + item['length']
            if e <= start:kept.append(item)
            elif s >= end:
                item['start'] -= length;kept.append(item)
            else:
                if s < start:kept.append(slice_item(item,kind,0,start-s))
                if e > end:
                    right = slice_item(item,kind,end-s,item['length'],s<start)
                    right['start'] -= length;kept.append(right)
        p[kind] = kept

def source_handle(p, item, edge):
    """Available timeline frames outside a media item's current source range."""
    asset = next(a for a in p['assets'] if a['id'] == item['asset'])
    speed = item.get('speed', 1)
    if edge == 'start':
        return max(0, int(math.floor((item.get('in', 0) + 1e-7) / speed)))
    source_end = item.get('in', 0) + item['length'] * speed
    return max(0, int(math.floor((asset.get('duration', 0) * p['fps'] - source_end + 1e-7) / speed)))

def video_edge_handle(p, item, edge):
    """Do not let one source-backed clip grow across an adjacent piece of that source."""
    index = p['clips'].index(item)
    available = source_handle(p, item, edge)
    if edge == 'start' and index:
        neighbour = p['clips'][index - 1]
        if neighbour['asset'] == item['asset']:
            neighbour_end = neighbour.get('in', 0) + neighbour['length'] * neighbour.get('speed', 1)
            available = min(available, max(0, int(math.floor((item.get('in', 0) - neighbour_end + 1e-7) / item.get('speed', 1)))))
    elif edge == 'end' and index + 1 < len(p['clips']):
        neighbour = p['clips'][index + 1]
        if neighbour['asset'] == item['asset']:
            source_end = item.get('in', 0) + item['length'] * item.get('speed', 1)
            available = min(available, max(0, int(math.floor((neighbour.get('in', 0) - source_end + 1e-7) / item.get('speed', 1)))))
    return available

def insert_linked_span(p, boundary, length, edge):
    """Insert restored time and recover boundary media on linked layers when handles exist."""
    for kind in ('audio', 'graphics', 'captions'):
        for item in p[kind]:
            if not linked(p, kind, item):
                continue
            start, end = item['start'], item['start'] + item['length']
            if edge == 'end' and end == boundary:
                if not media_item(kind,item) or source_handle(p, item, 'end') >= length:
                    item['length'] += length
                continue
            if edge == 'start' and start == boundary:
                if media_item(kind,item) and source_handle(p, item, 'start') < length:
                    item['start'] += length
                    continue
                item['length'] += length
                if media_item(kind,item):
                    item['in'] = item.get('in', 0) - length * item.get('speed', 1)
                    if 'fadeOffset' in item:item['fadeOffset'] = max(0, item['fadeOffset'] - length)
                if kind == 'graphics' and 'offset' in item:
                    item['offset'] = max(0, item['offset'] - length)
                continue
            if start >= boundary:
                item['start'] += length
            elif start < boundary < end:
                # A linked item crossing the edit has no recoverable boundary piece.
                # Keep its beginning fixed and extend non-media overlays; media remains valid.
                if not media_item(kind,item):item['length'] += length

def duplicate_linked_span(p, start, end):
    """Replay linked content in [start, end), then resume its original clocks."""
    length = end - start
    for kind in ('audio', 'graphics', 'captions'):
        pieces = []
        for item in p[kind]:
            if not linked(p, kind, item):
                pieces.append(item);continue
            first, last = item['start'], item['start'] + item['length']
            if kind == 'graphics' and item.get('keepTogether') and first <= start and last >= end and static_title(item, p['fps']):
                # A completely flat hook can cover the inserted interval as one
                # element. Extending both spans preserves its full opacity.
                extended = copy.deepcopy(item)
                extended['length'] += length
                extended['motionLength'] = item.get('motionLength', item['length']) + length
                if static_title(extended, p['fps']):
                    pieces.append(extended);continue
            if first < end:
                pieces.append(item if last <= end else slice_item(item, kind, 0, end-first))
            copy_start, copy_end = max(first, start), min(last, end)
            if copy_start < copy_end:
                duplicate = slice_item(item, kind, copy_start-first, copy_end-first, True)
                duplicate['start'] += length
                if kind == 'captions':duplicate['splitFrom'] = duplicate['id']
                pieces.append(duplicate)
            if last > end:
                if first >= end:
                    item['start'] += length;pieces.append(item)
                else:
                    remainder = slice_item(item, kind, end-first, item['length'], True)
                    remainder['start'] += length;pieces.append(remainder)
        # Keep each original element's fragments together to retain painter order.
        p[kind] = pieces

def duplicate_item(p, kind, item, op):
    """Create one selected copy, with video insertion moving only linked layers."""
    duplicate_id = op['newId'] if 'newId' in op else uid()
    if not isinstance(duplicate_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', duplicate_id):
        raise ValueError('Identificador de la copia no válido')
    if any(other['id'] == duplicate_id for collection in ('clips', 'audio', 'graphics', 'captions') for other in p[collection]):
        raise ValueError('ID de elemento duplicado')
    index = p[kind].index(item)
    if kind == 'clips':
        if 'start' in op or 'length' in op:
            raise ValueError('El vídeo se duplica completo justo después del clip seleccionado')
        start = sum(c['length'] for c in p['clips'][:index])
        duplicate_linked_span(p, start, start + item['length'])
        duplicate = copy.deepcopy(item)
    else:
        start = op.get('start', item['start'] + item['length'])
        length = op.get('length', item['length'])
        number(start, 0, 100_000_000, 'inicio de la copia')
        number(length, 1, item['length'], 'duración de la copia')
        if int(start) != start or int(length) != length:
            raise ValueError('La copia debe usar fotogramas enteros')
        if start + length > duration(p):
            raise ValueError('La copia no cabe dentro del vídeo. Elige otra posición o una duración menor.')
        duplicate = copy.deepcopy(item) if length == item['length'] else slice_item(item, kind, 0, int(length))
        duplicate['start'] = int(start)
    duplicate['id'] = duplicate_id
    if kind == 'captions':duplicate['splitFrom'] = duplicate['id']
    p[kind].insert(index + 1, duplicate)

def add_overlay(p, asset_id, start=0):
    if not duration(p):raise ValueError('Añade primero el vídeo principal')
    a = next((a for a in p['assets'] if a['id'] == asset_id), None)
    if not a or a.get('kind') != 'video' or a.get('hdr'):raise ValueError('Selecciona un vídeo SDR para superponer')
    number(start, 0, duration(p)-1, 'inicio de superposición')
    if int(start) != start:raise ValueError('El inicio debe usar fotogramas enteros')
    item = dict(id=uid(), type='video', asset=asset_id, start=int(start), length=min(duration(p)-int(start), max(1,int(a['duration']*p['fps']+1e-6))),
                **{'in':0}, speed=1, volumeDb=0, muted=True,
                props={'width':960,'x':960,'y':960*p['height']/p['width'],'style':'clean','animation':'none','opacity':1})
    p['graphics'].append(item)
    return item

def replace_overlay(p, id, asset_id):
    item = find(p, 'graphics', id)
    a = next((a for a in p['assets'] if a['id'] == asset_id), None)
    if not item or item.get('type') != 'video':raise ValueError('Selecciona la superposición que quieres cambiar')
    if not a or a.get('kind') != 'video' or a.get('hdr'):raise ValueError('Selecciona un vídeo SDR para superponer')
    item['asset'] = asset_id
    # A different video starts at its beginning; placement, motion and sound settings survive.
    item['in'] = 0
    item['length'] = min(item['length'], max(1,int(a['duration']*p['fps']/item.get('speed',1)+1e-6)), duration(p)-item['start'])
    if item['length'] < 1:raise ValueError('La superposición queda fuera del vídeo principal')

def promote_overlay(p, id):
    item = find(p, 'graphics', id)
    if not item or item.get('type') != 'video':raise ValueError('Selecciona un vídeo superpuesto')
    start, end = item['start'], min(duration(p),item['start']+item['length'])
    if start >= end:raise ValueError('La superposición queda fuera del vídeo principal')
    moved = {key:copy.deepcopy(item[key]) for key in ('id','asset','in','speed','volumeDb','muted','fadeIn','fadeOut','fadeOffset','fadeLength') if key in item}
    moved.update(length=end-start,zoom=1,zoomEnd=1,x=.5,y=.5,color={})
    clips=[];offset=0;inserted=False
    for clip in p['clips']:
        first,last=offset,offset+clip['length'];offset=last
        if last <= start or first >= end:
            clips.append(clip);continue
        if first < start:clips.append(slice_item(clip,'clips',0,start-first))
        if not inserted:clips.append(moved);inserted=True
        if last > end:clips.append(slice_item(clip,'clips',end-first,clip['length'],first<start))
    p['clips']=clips;p['graphics'].remove(item)

def find(p, kind, id):
    if kind not in ('clips', 'audio', 'graphics', 'captions'):
        raise ValueError('Tipo de pista no válido')
    return next((x for x in p[kind] if x['id'] == id), None)

def apply(p, ops):
    p = copy.deepcopy(p)
    for op in ops:
        action = op['op']
        if action == 'addOverlay':
            add_overlay(p, op['asset'], op.get('start',0))
        elif action == 'pruneAssets':
            used = {i['asset'] for k in ('clips','audio','graphics') for i in p[k] if media_item(k, i)} | {g['props'].get('asset') for g in p['graphics'] if g['type'] == 'image'}
            p['assets'] = [a for a in p['assets'] if a['id'] in used]
        elif action == 'promoteOverlay':
            promote_overlay(p, op['id'])
        elif action == 'source':
            item=find(p,'graphics',op['id'])
            if not item or item.get('type')!='video':raise ValueError('Selecciona un vídeo superpuesto')
            item['in']=op['in']
        elif action == 'linkTrack':
            target, value = op['track'], op['linked']
            if target not in (*SYNC_TRACKS,'all') or type(value) is not bool:raise ValueError('Vínculo de pista no válido')
            targets = SYNC_TRACKS if target == 'all' else (target,)
            p.setdefault('syncTracks',{}).update({t:value for t in targets})
            for kind in ('audio','graphics','captions'):
                for item in p[kind]:
                    if track(kind,item) in targets:item.pop('linked',None)
        elif action == 'joinTrack':
            kind, items, count = join_plan(p, op.get('track'))
            if not count:raise ValueError('No hay tramos compatibles que unir en esta pista')
            p[kind] = items
        elif action == 'splitAt':
            frame = op['frame'];number(frame,1,duration(p)-1,'fotograma de corte')
            if int(frame) != frame:raise ValueError('El corte debe usar fotogramas enteros')
            split_at(p,int(frame))
        elif action == 'cutRange':
            start, end = int(op['start']), int(op['end'])
            if not 0 <= start < end <= duration(p):
                raise ValueError('Intervalo de corte no válido')
            if end-start == duration(p):
                raise ValueError('El corte eliminaría todo el vídeo')
            clips=[]; offset=0
            for c in p['clips']:
                cs,ce=offset,offset+c['length']; offset=ce
                if ce<=start or cs>=end:
                    clips.append(c); continue
                if cs<start:clips.append(slice_item(c,'clips',0,start-cs))
                if ce>end:clips.append(slice_item(c,'clips',end-cs,c['length'],True))
            p['clips']=clips
            remove_span(p,start,end-start)
        elif action == 'mixer':
            p['mixer'].update(op['values'])
        elif action == 'settings':
            for k, v in op['values'].items():
                if k not in ('name', 'width', 'height', 'fps', 'ducking', 'cacheLimitGB'):
                    raise ValueError('Ajuste no permitido: ' + k)
                if k == 'fps' and p['clips']:
                    raise ValueError('Configura los fps antes de importar clips')
                p[k] = v
        elif action == 'add':
            kind = op['kind']
            if kind not in ('clips', 'audio', 'graphics', 'captions'):
                raise ValueError('Tipo de elemento no válido')
            item = copy.deepcopy(op['item'])
            item.setdefault('id', uid())
            p[kind].append(item)
        elif action in ('set', 'delete', 'split', 'trim', 'move', 'duration', 'resizeEdge', 'duplicate'):
            kind, id = op['kind'], op['id']
            item = find(p, kind, id)
            if item is None:
                raise ValueError('Elemento no encontrado')
            if action == 'duplicate':
                duplicate_item(p, kind, item, op)
            elif action == 'set':
                if any(k in op['values'] for k in ('id', 'length', 'in', 'start')):
                    raise ValueError('Usa trim/move para cambiar tiempos')
                group = caption_layout.edit_group(p, item, op['values']) if kind == 'graphics' else []
                item.update(op['values'])
                if group:
                    validate(p)
                    caption_layout.reflow(group)
                if media_item(kind,item) and any(k in op['values'] for k in ('fadeIn','fadeOut')):
                    item.pop('fadeOffset',None);item.pop('fadeLength',None)
            elif action == 'duration':
                if kind not in ('graphics','captions'):raise ValueError('La duración directa se aplica a imágenes, gráficos y texto')
                item['length']=op['length'];item['motionLength']=item['length']+item.get('offset',0)
            elif action == 'move':
                if kind == 'clips':
                    raise ValueError('Reordenar vídeo requiere recolocar sus gráficos; usa cortes explícitos')
                item['start'] = int(op['start'])
            elif action == 'delete':
                if kind == 'clips':
                    pos = sum(x['length'] for x in p['clips'][:p['clips'].index(item)])
                    remove_span(p, pos, item['length'])
                p[kind].remove(item)
            elif action == 'split':
                at = int(op['at'])
                if not 0 < at < item['length']:
                    raise ValueError('El corte debe estar dentro del clip')
                i = p[kind].index(item)
                item.pop('keepTogether', None)
                p[kind][i:i+1] = [slice_item(item,kind,0,at),slice_item(item,kind,at,item['length'],True)]
            elif action == 'trim':
                head, tail = int(op.get('head', 0)), int(op.get('tail', 0))
                if head < 0 or tail < 0 or head+tail >= item['length']:
                    raise ValueError('Recorte no válido')
                if kind == 'clips':
                    pos = sum(x['length'] for x in p['clips'][:p['clips'].index(item)])
                    remove_span(p, pos+item['length']-tail, tail)
                    remove_span(p, pos, head)
                p[kind][p[kind].index(item)] = slice_item(item,kind,head,item['length']-tail)
            elif action == 'resizeEdge':
                edge, delta = op.get('edge'), op.get('delta')
                if edge not in ('start', 'end'):raise ValueError('Borde no válido')
                number(delta, -100_000_000, 100_000_000, 'desplazamiento de borde')
                if int(delta) != delta or delta == 0:raise ValueError('El ajuste debe usar fotogramas enteros')
                delta = int(delta)
                if kind == 'clips':
                    pos = sum(x['length'] for x in p['clips'][:p['clips'].index(item)])
                    if edge == 'start':
                        if delta >= item['length']:raise ValueError('El ajuste eliminaría todo el clip')
                        if delta > 0:
                            remove_span(p, pos, delta)
                            p['clips'][p['clips'].index(item)] = slice_item(item, 'clips', delta, item['length'])
                        else:
                            amount = -delta
                            if amount > video_edge_handle(p, item, edge):raise ValueError('No queda más material antes de este clip')
                            item['in'] = item.get('in', 0) - amount * item.get('speed', 1)
                            item['length'] += amount
                            if 'motionOffset' in item:item['motionOffset'] = max(0, item['motionOffset'] - amount)
                            insert_linked_span(p, pos, amount, edge)
                    else:
                        if -delta >= item['length']:raise ValueError('El ajuste eliminaría todo el clip')
                        if delta < 0:
                            remove_span(p, pos + item['length'] + delta, -delta)
                            item['length'] += delta
                        else:
                            if delta > video_edge_handle(p, item, edge):raise ValueError('No queda más material después de este clip')
                            boundary = pos + item['length']
                            item['length'] += delta
                            insert_linked_span(p, boundary, delta, edge)
                else:
                    if edge == 'start':
                        if delta >= item['length']:raise ValueError('El ajuste eliminaría todo el elemento')
                        if delta > 0:
                            index = p[kind].index(item)
                            item = slice_item(item, kind, delta, item['length'])
                            p[kind][index] = item
                        else:
                            amount = -delta
                            available = item['start']
                            if media_item(kind,item):available = min(available, source_handle(p, item, edge))
                            if amount > available:raise ValueError('No queda más espacio o material antes de este elemento')
                            item['start'] -= amount
                            item['length'] += amount
                            if media_item(kind,item):
                                item['in'] = item.get('in', 0) - amount * item.get('speed', 1)
                                if 'fadeOffset' in item:item['fadeOffset'] = max(0, item['fadeOffset'] - amount)
                            if kind == 'graphics' and 'offset' in item:
                                item['offset'] = max(0, item['offset'] - amount)
                    else:
                        if -delta >= item['length']:raise ValueError('El ajuste eliminaría todo el elemento')
                        if delta > 0:
                            available = duration(p) - item['start'] - item['length']
                            if media_item(kind,item):available = min(available, source_handle(p, item, edge))
                            if delta > available:raise ValueError('No queda más espacio o material después de este elemento')
                        item['length'] += delta
                    if kind == 'graphics':item['motionLength'] = item['length'] + item.get('offset', 0)
        else:
            raise ValueError('Operación desconocida: ' + action)
    _, p['graphics'], _ = join_plan(p, 'graphics', kept_only=True)
    p['revision'] += 1
    return validate(p)
