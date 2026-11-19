#!/usr/bin/env python3
"""Loopback companion for Studio. Remote access is exclusively through an approved Serve proxy."""
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
import math
import mimetypes
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
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

PLAYER = 2  # The page's player these plans and media are for; a page loaded before it changed is told to reload.

ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def running():
    """What tells the executable and the code this process loaded apart from others; None while one is being replaced."""
    try:
        found = os.stat(sys.executable)
        return found.st_ino, found.st_mtime_ns, *((f.name, f.stat().st_mtime_ns)
                                                  for folder in (ROOT, ROOT.parent/'engine') for f in sorted(folder.glob('*.py')))
    except OSError:
        return None


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('Identificador no válido')
    return value


def integer(value, low=0, high=100_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Valor fuera de rango')
    return value


def percent_db(value):
    """Percentage of the original sound (100 = unchanged, 0 = silent) in dB, as the desktop volume control does."""
    if type(value) not in (int, float) or not 0 <= value <= 400:
        raise ValueError('Volumen no válido')
    return -60 if value <= 0 else max(-59.999, 20 * math.log10(value / 100))


def public_project(p):
    """What the phone sees of a project just read: only ever serialised, so it shares the rest of that read."""
    return {**p, 'assets': [{k: v for k, v in a.items() if k in ('id', 'name', 'kind', 'duration', 'width', 'height', 'audio')}
                            for a in p['assets']]}


def public_note(note):
    return {k: v for k, v in note.items() if k != 'files'}


def signature(path):
    """Saves replace a file (os.replace), so another inode, time or size is another file; None if there is none."""
    try:
        found = os.stat(path)
    except FileNotFoundError:
        return None
    return found.st_ino, found.st_mtime_ns, found.st_size


class Companion:
    RETRY = 30  # seconds before taking again a picture that failed, doubling up to half an hour

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
        self.activity = threading.Lock()
        self.active = Counter()
        self.planned = {}
        self.known = {}  # montage file -> what the library lists of it, with the signature it was read with
        self.ids = {}
        self.noted = {}  # montage file -> (signatures, notes) of the last full state
        self.swept = {}  # montage file -> signatures of its notes when last looked for pictures to take
        self.capture_lock = threading.Lock()
        self.waiting = {}  # (montage file, note) -> (when, failures) of a picture still to take
        self.capturing = False
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT, result TEXT)')

    def db(self):
        return sqlite3.connect(self.runtime / 'requests.sqlite3', timeout=30)

    def entry(self, path):
        """What the library lists of a montage; its file is read again only when it changed."""
        stamp = signature(path)
        if stamp is None:
            raise FileNotFoundError(path)
        entry = self.known.get(path)
        if entry is None or entry['stamp'] != stamp:
            p = project.load(path)
            entry = self.known[path] = dict(stamp=stamp, id=p['id'], name=p['name'], revision=p['revision'], width=p['width'],
                                            height=p['height'], duration=project.duration(p)/p['fps'])
        return entry

    def catalog(self):
        result = {}
        for path in project_library.project_files(self.projects):
            if not path.resolve().is_relative_to(self.projects):
                continue
            entry = self.entry(path)
            if entry['id'] in result:
                raise ValueError('Hay proyectos con la misma identidad; revisa la biblioteca en el Mac')
            result[entry['id']] = (path, entry)
        self.known, self.ids = dict(result.values()), {pid: path for pid, (path, _) in result.items()}
        return result

    def locate(self, pid):
        """A request on one montage reads that montage, not the library."""
        pid = identifier(pid)
        try:
            path = self.ids[pid]
            entry = self.entry(path)
            if entry['id'] == pid:
                return path, entry
        except (OSError, ValueError, KeyError):
            pass
        found = self.catalog().get(pid)
        if not found:
            raise ValueError('Proyecto no encontrado')
        return found

    def resolve(self, pid):
        return self.locate(pid)[0]

    def read(self, pid, revision=None):
        path = self.resolve(pid)
        with editor.lock(path):
            p = project.load(path)
            if revision is not None and p['revision'] != integer(revision):
                p = sync.base_project(path, p, revision)
        return path, p

    def state(self, pid, revision=None):
        path, entry = self.locate(pid)
        # Every open page asks every five seconds: an unchanged montage with unchanged notes is answered without reading them.
        notes = feedback.root(path)/'feedback.sqlite3'
        stamp = entry['stamp'], signature(notes), signature(notes.with_name(notes.name+'-wal'))
        known = self.noted.get(path)
        if revision == entry['revision'] and known and known[0] == stamp:
            return {'project': None, 'revision': revision, 'notes': known[1]}
        path, p = self.read(pid)
        listed = [public_note(n) for n in feedback.dispatch(path, p, {'command': 'list'})['notes']]
        self.noted[path] = stamp, listed
        return {'project': public_project(p) if p['revision'] != revision else None, 'revision': p['revision'], 'notes': listed}

    def client_log(self, entries):
        """What the phone's player measured: timings and failures, bounded, never content."""
        if not isinstance(entries, list):
            raise ValueError('Registro no válido')
        log = self.runtime/'client.log'
        if log.exists() and log.stat().st_size > 2_000_000:
            log.replace(self.runtime/'client.log.1')
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with log.open('a') as file:
            file.write(''.join(json.dumps({'t': stamp, **entry}, ensure_ascii=False)[:2000]+'\n' for entry in entries if isinstance(entry, dict)))

    def query(self, req):
        action = req.get('action')
        if action == 'library':
            library = project_library.load(self.projects)
            catalog = list(self.catalog().values())
            self.direct.queue(1, [])  # Leaving a montage stops preparing the rest of it.
            threading.Thread(target=self.prepare, args=(catalog,), daemon=True).start()
            return {'folders': library['folders'], 'projects': [dict(id=e['id'], name=e['name'], revision=e['revision'],
                width=e['width'], height=e['height'], duration=e['duration'],
                folder=library['assignments'].get(e['id'])) for _, e in catalog]}
        if action == 'state':
            return self.state(req['project'], req.get('revision'))
        if action == 'warm':
            return self.warm(req['project'], req['revision'], req['frame'])
        if action == 'directPlan':
            _, p = self.read(req['project'], integer(req['revision']))
            plan = self.direct.plan(p, req.get('size', 640))
            if plan:
                at = integer(req.get('frame', 0))/p['fps']
                # From the playhead onwards, then what lies behind it.
                plan['pending'] = self.direct.missing(url for _, _, url in sorted(spans(plan), key=lambda s: (s[1] <= at, s[0])))
                self.direct.queue(1, plan['pending'])
            return plan
        if action == 'directStatus':
            return self.direct.status(req['urls'])
        if action == 'clientLog':
            return self.client_log(req['entries'])
        if action == 'receipt':
            rid = identifier(req['requestId'])
            with self.activity, self.db() as db:
                if rid in self.active:
                    return {'status': 'processing', 'response': None}
                row = db.execute('SELECT result FROM requests WHERE id=?', (rid,)).fetchone()
                if row is None and req.get('settle') is True:
                    # Fence an unseen delivery: if it arrives later, this ID can never execute.
                    result = json.dumps({'ok': False, 'cancelled': True, 'error': 'La acción no llegó a guardarse. Tu borrador se conserva.'})
                    db.execute('INSERT INTO requests VALUES(?,?,?)', (rid, '', result))
                    row = (result,)
                return {'status': 'unknown' if row is None else 'pending' if row[0] is None else 'done',
                        'response': json.loads(row[0]) if row and row[0] else None}
        return self.mutate(req)

    def prepare(self, catalog):
        """Short montages are ready before they are opened; long ones, their first minute. Newest first."""
        urls = []
        for path, entry in sorted(catalog, key=lambda item: item[1]['stamp'][1], reverse=True):
            stamp = entry['stamp']
            if self.planned.get(path, (0,))[0] != stamp:  # Only a montage that changed is planned again.
                try:
                    plan = self.direct.plan(project.load(path), 1280)  # What a phone asks for first.
                except (OSError, KeyError, ValueError):
                    plan = None  # A montage with an unreadable source still lists; opening it reports the problem.
                self.planned[path] = (stamp, [url for start, _, url in sorted(spans(plan)) if plan['frames'] <= 900*plan['fps'] or start < 60] if plan else [])
            urls += self.planned[path][1]
        self.direct.queue(2, urls, 2400)

    def watch(self):
        """A montage created or changed on the Mac is prepared before the phone asks for it."""
        seen, started = None, running()
        while True:
            try:
                stamp = [(path, path.stat().st_mtime_ns) for path in project_library.project_files(self.projects)]
                if stamp != seen:
                    self.prepare(list(self.catalog().values()))
                    seen = stamp
                self.sweep()
            except (OSError, KeyError, ValueError, sqlite3.Error):
                pass
            # macOS stops letting a process read Documents once the file it runs from is replaced, as a Codex update
            # does, and an engine changed on the Mac writes montages the one loaded here rejects, which fails the
            # whole library: leaving lets launchd start the service again from the new ones. Never in the middle of a write.
            with self.activity:
                if running() not in (None, started) and not self.active:
                    os._exit(0)
            time.sleep(20)

    def sweep(self):
        """A note published before its picture was taken, here before a restart or by anyone, gets it."""
        for path in list(self.known):
            notes = feedback.root(path)/'feedback.sqlite3'
            stamp = signature(notes), signature(notes.with_name(notes.name+'-wal'))
            if stamp[0] is None or self.swept.get(path) == stamp:
                continue
            self.swept[path] = stamp
            with feedback.database(path) as db:
                waiting = [n['id'] for n in (json.loads(row[0]) for row in db.execute('SELECT body FROM notes'))
                           if n['status'] in ('open', 'resolved') and n['capture'] != 'ready']
            for nid in waiting:
                self.capture_later(path, nid)

    def capture_later(self, path, nid):
        """Pictures of saved notes are taken here, one at a time; one that fails is taken again, ever less often."""
        with self.capture_lock:
            self.waiting.setdefault((path, nid), (time.monotonic(), 0))
            if not self.capturing:
                self.capturing = True
                threading.Thread(target=self.captures, daemon=True).start()

    def captures(self):
        while True:
            with self.capture_lock:
                if not self.waiting:
                    self.capturing = False
                    return
                key, (due, failures) = min(self.waiting.items(), key=lambda item: item[1])
                now = time.monotonic()
                if due <= now:
                    del self.waiting[key]
            if due > now:
                time.sleep(min(5, due - now))
                continue
            try:
                self.capture(*key)
            except Exception:
                if signature(key[0]):  # A montage that is gone has nothing left to capture.
                    with self.capture_lock:
                        self.waiting.setdefault(key, (time.monotonic() + min(1800, self.RETRY * 2**failures), failures + 1))

    def capture(self, path, nid):
        """The picture of a note, taken once: a reader asking for it while it is being taken waits for that one."""
        with self.media:
            return editor.dispatch(dict(project=str(path), action='feedback', command='capture', id=nid))

    def mutate(self, req):
        rid = identifier(req.get('requestId'))
        digest = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
        # Register before waiting, and retain visibility until the receipt is durable.
        with self.activity:
            self.active[rid] += 1
        try:
            with self.mutations:
                with self.db() as db:
                    row = db.execute('SELECT digest,result FROM requests WHERE id=?', (rid,)).fetchone()
                    if row:
                        if row[0] and row[0] != digest:
                            raise ValueError('La petición ya corresponde a otra acción')
                        if row[1] is None:
                            return {'ok': False, 'uncertain': True, 'error': 'Comprueba el resultado en el proyecto antes de hacer otro cambio.'}
                        return json.loads(row[1])
                    db.execute('INSERT INTO requests VALUES(?,?,NULL)', (rid, digest))
                try:
                    result = {'ok': True, 'result': self.execute(req)}
                except sync.Conflict as exc:
                    result = {'ok': False, 'conflict': True, 'error': str(exc)}
                except (ValueError, KeyError, TypeError) as exc:
                    result = {'ok': False, 'error': str(exc) if isinstance(exc, ValueError) else 'Petición incompleta'}
                # Unexpected I/O errors deliberately leave the receipt pending; never replay it.
                with self.db() as db:
                    db.execute('UPDATE requests SET result=? WHERE id=?', (json.dumps(result), rid))
                return result
        finally:
            with self.activity:
                self.active[rid] -= 1
                if not self.active[rid]:
                    del self.active[rid]

    def execute(self, req):
        path = self.resolve(req['project'])
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
                version = 1
            # Published as soon as its text and drawing are on the Mac; its snapshot is, so the picture comes after.
            note = editor.dispatch(dict(base, action='feedback', command='update', id=nid, version=integer(version, 1),
                                        values=dict(text=text, strokes=strokes, status='open')))
            if note['capture'] != 'ready':
                self.capture_later(path, nid)
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
            elif mode == 'mixer':
                if op.get('role') not in ('voice', 'music', 'sfx'):
                    raise ValueError('Pista no válida')
                operation = dict(op='mixer', values={op['role']: percent_db(op.get('percent'))})
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
                elif mode == 'volume':
                    db = percent_db(op.get('percent'))
                    if kind == 'audio' or (kind == 'clips' or item.get('type') == 'video') and next((a for a in viewed['assets'] if a['id'] == item.get('asset')), {}).get('audio'):
                        values = {'volumeDb': db, 'muted': False}
                    elif item.get('type') == 'image' and item['props'].get('sound') and item['props'].get('animation') != 'none':
                        values = {'props': {**item['props'], 'soundDb': min(db, 6)}}
                    else:
                        raise ValueError('Este elemento no tiene sonido')
                    operation.update(op='set', values=values)
                elif mode == 'resize':
                    operation.update(op='resizeEdge', edge=op.get('edge'), delta=integer(op.get('delta'), -100_000_000))
                elif mode == 'split':
                    operation.update(op='split', at=integer(op.get('at'), 1))
                elif mode == 'delete':
                    operation.update(op='delete')
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
        if note['capture'] != 'ready' or 'image' not in note['files']:
            note = self.capture(path, note['id'])  # Asked for before the background took it: taken now.
        return Path(note['files']['image']).read_bytes(), 'image/png'

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
    # One connection carries many requests: a new one per request costs a thread and the GIL a handover each time.
    protocol_version = 'HTTP/1.1'
    timeout = 300
    answering = False

    def log_message(self, *args):
        pass  # No request bodies, identity headers, filenames or private URLs in logs.

    def allowed(self, write=False):
        server = self.server
        if self.headers.get('Host') != urlsplit(server.origin).netloc:
            return False
        if server.user and self.headers.get('Tailscale-User-Login', '').casefold() != server.user.casefold():
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site' and not (   # la página sí se abre desde fuera: icono de inicio o enlace
                self.command == 'GET' and urlsplit(self.path).path == '/' and self.headers.get('Sec-Fetch-Dest') == 'document'):
            return False
        origin = self.headers.get('Origin')
        if origin and origin != server.origin:
            return False
        return not write or (origin == server.origin and self.headers.get('X-Studio-Mobile') == '1'
                             and self.headers.get('Content-Type', '').split(';')[0] == 'application/json')

    def send(self, data, content_type, status=200, headers=None):
        if len(data) > 1024 and content_type.startswith(('application/json', 'text/')) and 'gzip' in self.headers.get('Accept-Encoding', ''):
            data, headers = gzip.compress(data, 5), {**(headers or {}), 'Content-Encoding': 'gzip'}
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if self.close_connection:
            self.send_header('Connection', 'close')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def error(self, status, message):
        if self.answering:  # Half an answer is already out: the connection cannot carry another.
            self.close_connection = True
            return
        self.send(json.dumps({'ok': False, 'error': message}).encode(), 'application/json', status)

    def end_headers(self):
        super().end_headers()
        self.answering = True

    def parse_request(self):
        self.answering = False
        return super().parse_request()

    def do_POST(self):
        allowed = self.allowed(True)
        if not allowed or self.path != '/api':
            self.close_connection = True  # Its body was not read: what follows on the connection is not a request.
            return self.error(403, 'Acceso no autorizado') if not allowed else self.error(404, 'No encontrado')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 512_000:
                self.close_connection = True
                return self.error(413, 'Petición demasiado grande')
            req = json.loads(self.rfile.read(length))
            if not isinstance(req, dict):
                raise ValueError('Petición no válida')
            if req.get('action') == 'directPlan' and req.get('player') != PLAYER:
                return self.error(409, 'Studio móvil se ha actualizado: recarga la página.')
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
    threading.Thread(target=server.companion.watch, daemon=True).start()
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
