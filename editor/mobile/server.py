#!/usr/bin/env python3
"""Loopback companion for Studio. Remote access is exclusively through an approved Serve proxy."""
import argparse
import copy
import hashlib
import json
import math
import mimetypes
import re
import sqlite3
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'engine'))
import editor
import feedback
import project
import project_library
import render
import sync
from direct import DirectMedia, spans

ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('Identificador no válido')
    return value


def integer(value, low=0, high=100_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Valor fuera de rango')
    return value


def public_project(p):
    result = copy.deepcopy(p)
    result['assets'] = [{k: v for k, v in a.items() if k in ('id', 'name', 'kind', 'duration', 'width', 'height')}
                        for a in p['assets']]
    return result


def public_note(note):
    return {k: v for k, v in note.items() if k != 'files'}


class Companion:
    def __init__(self, projects, runtime):
        self.projects = Path(projects).resolve()
        self.runtime = Path(runtime)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.cache = self.runtime / 'cache'
        self.cache.mkdir(exist_ok=True)
        self.direct = DirectMedia(self.runtime/'native')
        self.mutations = threading.Lock()
        self.media = threading.Lock()
        self.warm_lock = threading.Lock()
        self.warm_jobs = []
        self.warming = False
        self.active = set()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT, result TEXT)')

    def db(self):
        return sqlite3.connect(self.runtime / 'requests.sqlite3', timeout=30)

    def catalog(self):
        result = {}
        for path in project_library.project_files(self.projects):
            if not path.resolve().is_relative_to(self.projects):
                continue
            p = project.load(path)
            if p['id'] in result:
                raise ValueError('Hay proyectos con la misma identidad; revisa la biblioteca en el Mac')
            result[p['id']] = (path, p)
        return result

    def resolve(self, pid):
        found = self.catalog().get(identifier(pid))
        if not found:
            raise ValueError('Proyecto no encontrado')
        return found[0]

    def read(self, pid, revision=None):
        path = self.resolve(pid)
        with editor.lock(path):
            p = project.load(path)
            if revision is not None:
                p = sync.base_project(path, p, integer(revision))
        return path, p

    def state(self, pid, revision=None):
        path, p = self.read(pid)
        notes = feedback.dispatch(path, p, {'command': 'list'})
        return {'project': public_project(p) if p['revision'] != revision else None,
                'revision': p['revision'], 'notes': [public_note(n) for n in notes['notes']]}

    def query(self, req):
        action = req.get('action')
        if action == 'library':
            library = project_library.load(self.projects)
            catalog = list(self.catalog().values())
            self.direct.queue(1, [])  # Leaving a montage stops preparing the rest of it.
            threading.Thread(target=self.prepare, args=(catalog,), daemon=True).start()
            return {'folders': library['folders'], 'projects': [dict(id=p['id'], name=p['name'], revision=p['revision'],
                width=p['width'], height=p['height'], duration=project.duration(p)/p['fps'],
                folder=library['assignments'].get(p['id'])) for _, p in catalog]}
        if action == 'state':
            return self.state(req['project'], req.get('revision'))
        if action == 'warm':
            return self.warm(req['project'], req['revision'], req['frame'])
        if action == 'directPlan':
            _, p = self.read(req['project'], integer(req['revision']))
            plan = self.direct.plan(p)
            if plan:
                at = integer(req.get('frame', 0))/p['fps']
                # From the playhead onwards, then what lies behind it.
                plan['pending'] = self.direct.missing(url for _, _, url in sorted(spans(plan), key=lambda s: (s[1] <= at, s[0])))
                self.direct.queue(1, plan['pending'])
            return plan
        if action == 'directStatus':
            return self.direct.status(req['urls'])
        if action == 'receipt':
            with self.db() as db:
                row = db.execute('SELECT result FROM requests WHERE id=?', (identifier(req['requestId']),)).fetchone()
            return {'status': 'processing' if req['requestId'] in self.active else 'unknown' if row is None else 'pending' if row[0] is None else 'done',
                    'response': json.loads(row[0]) if row and row[0] else None}
        return self.mutate(req)

    def prepare(self, catalog):
        """Short montages are ready before they are opened; long ones, their first minute. Newest first."""
        urls = []
        for _, p in sorted(catalog, key=lambda item: item[0].stat().st_mtime, reverse=True):
            try:
                plan = self.direct.plan(p)
            except (OSError, KeyError, ValueError):
                continue  # A montage with an unreadable source still lists; opening it reports the problem.
            if plan:
                urls += [url for start, _, url in sorted(spans(plan)) if plan['frames'] <= 900*plan['fps'] or start < 60]
        self.direct.queue(2, urls, 1200)

    def mutate(self, req):
        rid = identifier(req.get('requestId'))
        digest = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
        # Persist intent before the canonical write. An interrupted write is never replayed.
        with self.mutations:
            with self.db() as db:
                row = db.execute('SELECT digest,result FROM requests WHERE id=?', (rid,)).fetchone()
                if row:
                    if row[0] != digest:
                        raise ValueError('La petición ya corresponde a otra acción')
                    if row[1] is None:
                        return {'ok': False, 'uncertain': True, 'error': 'Comprueba el resultado en el proyecto antes de hacer otro cambio.'}
                    return json.loads(row[1])
                db.execute('INSERT INTO requests VALUES(?,?,NULL)', (rid, digest))
            self.active.add(rid)
            try:
                result = {'ok': True, 'result': self.execute(req)}
            except sync.Conflict as exc:
                result = {'ok': False, 'conflict': True, 'error': str(exc)}
            except (ValueError, KeyError, TypeError) as exc:
                result = {'ok': False, 'error': str(exc) if isinstance(exc, ValueError) else 'Petición incompleta'}
            finally:
                self.active.discard(rid)
            # Unexpected I/O errors deliberately leave the receipt pending.
            with self.db() as db:
                db.execute('UPDATE requests SET result=? WHERE id=?', (json.dumps(result), rid))
            return result

    def execute(self, req):
        path, p = self.read(req['project'])
        rev = integer(req.get('revision'))
        action = req.get('action')
        base = dict(project=str(path), revision=rev)
        if action == 'note':
            nid = identifier(req['noteId'])
            text = req.get('text', '')
            if not isinstance(text, str) or len(text) > 12000:
                raise ValueError('Comentario demasiado largo')
            strokes = req.get('strokes', [])
            feedback.strokes_checked(strokes)
            if not text.strip() and not strokes:
                raise ValueError('Escribe un comentario o dibuja una indicación')
            version = req.get('version')
            if version is None:
                with feedback.database(path) as db:
                    if db.execute('SELECT 1 FROM notes WHERE id=?', (nid,)).fetchone():
                        raise sync.Conflict('Este comentario ya existe en el Mac. Abre su versión guardada antes de editarlo.')
                editor.dispatch(dict(base, action='feedback', command='create', id=nid, frame=integer(req['frame'])))
                # Draft text reaches the Mac before potentially slow capture preparation.
                note = editor.dispatch(dict(base, action='feedback', command='update', id=nid, version=1,
                                            values={'text': text, 'strokes': strokes, 'status': 'draft'}))
                version = note['version']
            with self.media:
                editor.dispatch(dict(base, action='feedback', command='capture', id=nid))
            values = dict(text=text, strokes=strokes, status='open')
            note = editor.dispatch(dict(base, action='feedback', command='update', id=nid,
                                         version=integer(version, 1), values=values))
            return {'note': public_note(note)}
        if action not in ('edit', 'undo', 'redo'):
            raise ValueError('Acción no disponible en móvil')
        # Resolve UI coordinates against exactly the version the phone displays.
        # Independent desktop edits may still be merged by Studio's canonical engine.
        _, viewed = self.read(req['project'], rev)
        if action in ('undo', 'redo'):
            result = editor.dispatch(dict(base, action=action))
        else:
            op = req.get('op', {})
            mode = op.get('type')
            if mode == 'linkTrack':
                operation = dict(op='linkTrack', track=op['track'], linked=op['linked'])
            elif mode == 'splitAt':
                operation = dict(op='splitAt', frame=integer(op['frame'], 1))
            else:
                kind, iid = op.get('kind'), identifier(op.get('id'))
                if kind not in ('clips', 'audio', 'graphics', 'captions'):
                    raise ValueError('Capa no válida')
                item = project.find(viewed, kind, iid)
                if item is None:
                    raise ValueError('Elemento no encontrado')
                operation = dict(kind=kind, id=iid)
                if mode == 'text':
                    text = op.get('text')
                    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                        raise ValueError('Escribe un texto de hasta 2000 caracteres')
                    if kind == 'graphics' and item['type'] == 'title':
                        values = {'props': {**item['props'], 'text': text}}
                    elif kind == 'captions':
                        values = {'text': text}
                    else:
                        raise ValueError('Selecciona un texto editable')
                    operation.update(op='set', values=values)
                elif mode == 'linked':
                    if type(op.get('linked')) is not bool:
                        raise ValueError('Vínculo no válido')
                    operation.update(op='set', values={'linked': op['linked']})
                elif mode == 'resize':
                    operation.update(op='resizeEdge', edge=op.get('edge'), delta=integer(op.get('delta'), -100_000_000))
                elif mode == 'split':
                    operation.update(op='split', at=integer(op.get('at'), 1))
                else:
                    raise ValueError('Operación no disponible en móvil')
            result = editor.dispatch(dict(base, action='ops', ops=[operation]))
        return {'project': public_project(result['project'])}

    def snapshot_key(self, p):
        # Cache the rendered interval, not the revision or unrelated timeline items.
        q = {k: copy.deepcopy(p[k]) for k in ('width', 'height', 'fps', 'clips', 'graphics', 'captions', 'audio', 'mixer', 'ducking')}
        used = set()
        for kind in ('clips', 'graphics', 'captions', 'audio'):
            for item in q[kind]:
                for key in ('id', 'linked', 'keepTogether', 'captionGroup', 'captionIndex', 'splitFrom'):
                    item.pop(key, None)
                if item.get('asset'): used.add(item['asset'])
                if item.get('props', {}).get('asset'): used.add(item['props']['asset'])
        q['assets'] = []
        for a in p['assets']:
            if a['id'] not in used: continue
            stat = Path(a['path']).stat()
            q['assets'].append({**a, 'bytes': stat.st_size, 'modified': stat.st_mtime_ns})
        return hashlib.sha256(json.dumps([2, q], sort_keys=True).encode()).hexdigest()[:24]

    def warm(self, pid, revision, frame):
        _, p = self.read(pid, integer(revision))
        integer(frame, 0, max(0, project.duration(p)-1))
        size = max(1, round(p['fps']*6))
        first, count = frame//size, math.ceil(project.duration(p)/size)
        with self.warm_lock:
            # A new seek replaces queued work. Each request ends after at most three intervals.
            self.warm_jobs = [(pid, revision, i) for i in range(first, min(count, first+3))]
            if self.warm_jobs and not self.warming:
                self.warming = True
                threading.Thread(target=self.warm_media, daemon=True).start()
        return {'queued': True}

    def warm_media(self):
        while True:
            with self.warm_lock:
                if not self.warm_jobs:
                    self.warming = False
                    return
                job = self.warm_jobs.pop(0)
            try:
                self.segment(*job, 'ts')
            except Exception:
                pass  # Speculation is optional; the requested media route reports its own error.

    def prune(self, keep):
        files = sorted(self.cache.glob('*.*'), key=lambda f: f.stat().st_mtime)
        size = sum(f.stat().st_size for f in files)
        for f in files:
            if size <= 512 * 1024**2:
                break
            if f != keep and f.suffix in ('.jpg', '.mp4', '.ts'):
                size -= f.stat().st_size
                f.unlink()

    @staticmethod
    def cached(path):
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def image(self, pid, revision, frame):
        _, p = self.read(pid, revision)
        integer(frame, 0, max(0, project.duration(p)-1))
        out = self.cache / f'{self.snapshot_key(p)}-{frame}.jpg'
        data = self.cached(out)
        if data is not None:
            return data, 'image/jpeg'
        with self.media:
            if not out.exists():
                with tempfile.TemporaryDirectory(dir=self.cache) as work:
                    width = max(64, round(min(640, 640*p['width']/p['height'])/2)*2)
                    rendered = render.frame(p, frame, Path(work), width=width)
                    Path(rendered['path']).replace(out)
                self.prune(out)
            return out.read_bytes(), 'image/jpeg'

    def note_image(self, pid, nid):
        path, p = self.read(pid)
        note = feedback.dispatch(path, p, {'command': 'get', 'id': identifier(nid)})
        image = note.get('files', {}).get('image')
        if not image:
            raise ValueError('La captura aún no está lista')
        return Path(image).read_bytes(), 'image/png'

    def segment(self, pid, revision, index, extension):
        _, p = self.read(pid, revision)
        count = max(1, round(p['fps']*6))
        start = integer(index) * count
        end = min(project.duration(p), start+count)
        if start >= end:
            raise ValueError('Tramo fuera del vídeo')
        excerpt = project.excerpt(p, start, end)
        scale = min(1, 640/max(p['width'], p['height']))
        excerpt['width'] = max(64, round(p['width']*scale/2)*2)
        excerpt['height'] = max(64, round(p['height']*scale/2)*2)
        key = self.snapshot_key(excerpt)
        mp4 = self.cache / (key + '.mp4')
        out = self.cache / (key + '.' + extension)
        kind = 'video/mp2t' if extension == 'ts' else 'video/mp4'
        data = self.cached(out)
        if data is not None:
            return data, kind
        with self.media:
            if not mp4.exists():
                with tempfile.TemporaryDirectory(dir=self.cache) as work:
                    result = render.render(excerpt, Path(work), preview=True)
                    Path(result['path']).replace(mp4)
            if extension == 'ts' and not out.exists():
                with tempfile.TemporaryDirectory(dir=self.cache) as work:
                    temp = Path(work)/'segment.ts'
                    render.run(['-v','error','-i',mp4,'-c','copy','-bsf:v','h264_mp4toannexb',
                                '-muxdelay','0','-f','mpegts',temp])
                    temp.replace(out)
            data = out.read_bytes()
            self.prune(out)
            return data, kind

    def playlist(self, pid, revision, first):
        _, p = self.read(pid, revision)
        size = max(1, round(p['fps']*6))
        total = project.duration(p)
        integer(first, 0, max(0, math.ceil(total/size)-1))
        rows = ['#EXTM3U', '#EXT-X-VERSION:3', f'#EXT-X-TARGETDURATION:{math.ceil(size/p["fps"])}',
                '#EXT-X-PLAYLIST-TYPE:VOD', '#EXT-X-MEDIA-SEQUENCE:0']
        for index in range(first, math.ceil(total/size)):
            if index != first:
                rows.append('#EXT-X-DISCONTINUITY')
            rows += [f'#EXTINF:{min(size,total-index*size)/p["fps"]:.9f},', f'/media/{pid}/{revision}/{index}.ts']
        rows.append('#EXT-X-ENDLIST')
        return ('\n'.join(rows)+'\n').encode(), 'application/vnd.apple.mpegurl'


class Handler(BaseHTTPRequestHandler):
    server_version = 'StudioMobile'

    def log_message(self, *args):
        pass  # No request bodies, identity headers, filenames or private URLs in logs.

    def allowed(self, write=False):
        server = self.server
        if self.headers.get('Host') != urlsplit(server.origin).netloc:
            return False
        if server.user and self.headers.get('Tailscale-User-Login', '').casefold() != server.user.casefold():
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        origin = self.headers.get('Origin')
        if origin and origin != server.origin:
            return False
        return not write or (origin == server.origin and self.headers.get('X-Studio-Mobile') == '1'
                             and self.headers.get('Content-Type', '').split(';')[0] == 'application/json')

    def send(self, data, content_type, status=200, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def error(self, status, message):
        self.send(json.dumps({'ok': False, 'error': message}).encode(), 'application/json', status)

    def do_POST(self):
        if not self.allowed(True):
            return self.error(403, 'Acceso no autorizado')
        if self.path != '/api':
            return self.error(404, 'No encontrado')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 512_000:
                return self.error(413, 'Petición demasiado grande')
            req = json.loads(self.rfile.read(length))
            if not isinstance(req, dict):
                raise ValueError('Petición no válida')
            result = self.server.companion.query(req)
            if req.get('action') in ('library', 'state', 'receipt', 'warm', 'directPlan', 'directStatus'):
                result = {'ok': True, 'result': result}
            self.send(json.dumps(result, ensure_ascii=False).encode(), 'application/json')
        except (ValueError, KeyError, TypeError):
            self.error(400, 'Petición no válida o proyecto no disponible. Revisa el proyecto en el Mac.')
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.error(500, 'No se pudo completar. Comprueba el estado de la acción antes de repetirla.')

    def do_HEAD(self):
        self.do_GET()

    def send_file(self, path):
        # Range reads stay bounded even for long source proxies; Safari seeks via Range.
        size = path.stat().st_size
        start, end, status = 0, size-1, 200
        value = self.headers.get('Range')
        if value:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
            if not match or not any(match.groups()):
                return self.send(b'', 'application/octet-stream', 416, {'Content-Range':f'bytes */{size}'})
            lo, hi = match.groups()
            start = int(lo) if lo else max(0,size-int(hi))
            end = min(size-1,int(hi)) if lo and hi else size-1
            if start>end or start>=size:
                return self.send(b'', 'application/octet-stream', 416, {'Content-Range':f'bytes */{size}'})
            status=206
        self.send_response(status)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','private, max-age=31536000, immutable')
        self.send_header('X-Content-Type-Options','nosniff')
        if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if self.command=='HEAD': return
        with path.open('rb') as source:
            source.seek(start); remaining=end-start+1
            while remaining:
                chunk=source.read(min(256*1024,remaining))
                if not chunk: break
                self.wfile.write(chunk); remaining-=len(chunk)

    def do_GET(self):
        if not self.allowed():
            return self.error(403, 'Acceso no autorizado')
        url = urlsplit(self.path)
        try:
            static = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css',
                      '/direct-player.js':'direct-player.js', '/vendor/soundtouch-processor.js':'vendor/soundtouch-processor.js',
                      '/manifest.webmanifest': 'manifest.webmanifest', '/icon.png': '../assets/app-icon/StudioIcon.png'}
            if url.path in static:
                file = ROOT / static[url.path]
                return self.send(file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/json')
            native = re.fullmatch(r'/native/((?:[a-f0-9]{32}|(?:text|cue)-[a-f0-9]{28})\.(?:mp4|m4a|png|wav))',url.path)
            if native:
                path=self.server.companion.direct.folder/native[1]
                if not path.is_file(): return self.error(404,'Medio aún no preparado')
                return self.send_file(path)
            note = re.fullmatch(r'/note/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)\.png', url.path)
            if note:
                return self.send(*self.server.companion.note_image(*note.groups()))
            match = re.fullmatch(r'/media/([A-Za-z0-9_-]+)/([0-9]+)/([0-9]+)\.(jpg|mp4|ts|m3u8)', url.path)
            if not match:
                return self.error(404, 'No encontrado')
            pid, rev, frame, ext = match.groups()
            companion = self.server.companion
            if ext == 'jpg':
                data, kind = companion.image(pid, int(rev), int(frame))
            elif ext == 'm3u8':
                data, kind = companion.playlist(pid, int(rev), int(frame))
            else:
                data, kind = companion.segment(pid, int(rev), int(frame), ext)
            # Safari requires byte ranges for MP4 playback and seeking.
            range_header = self.headers.get('Range')
            if range_header:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header)
                if not match or not any(match.groups()):
                    return self.send(b'', kind, 416, {'Content-Range': f'bytes */{len(data)}'})
                lo, hi = match.groups()
                start = int(lo) if lo else max(0, len(data)-int(hi))
                end = min(len(data)-1, int(hi)) if lo and hi else len(data)-1
                if start > end or start >= len(data):
                    return self.send(b'', kind, 416, {'Content-Range': f'bytes */{len(data)}'})
                return self.send(data[start:end+1], kind, 206,
                                 {'Accept-Ranges': 'bytes', 'Content-Range': f'bytes {start}-{end}/{len(data)}'})
            self.send(data, kind, headers={'Accept-Ranges': 'bytes'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, KeyError, OSError):
            self.error(409, 'No se pudo preparar esta revisión. Actualiza el proyecto.')


def serve(projects, runtime, port=8766, origin=None, user=None):
    if bool(origin) != bool(user):
        raise ValueError('El acceso remoto requiere --origin HTTPS y --user de Tailscale juntos')
    if origin and (not re.fullmatch(r'https://[a-z0-9.-]+\.ts\.net', origin) or not user.strip()):
        raise ValueError('Usa el origen HTTPS privado de Tailscale y la cuenta autorizada')
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.origin = origin or f'http://127.0.0.1:{server.server_port}'
    server.user = user
    server.companion = Companion(projects, runtime)
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--projects', type=Path, default=ROOT.parent/'projects')
    parser.add_argument('--runtime', type=Path, default=ROOT/'.runtime')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--origin')
    parser.add_argument('--user')
    args = parser.parse_args()
    server = serve(args.projects, args.runtime, args.port, args.origin, args.user)
    print('Studio móvil · servidor local activo. Ctrl+C para detener.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
