"""One level of visual folders; project paths and edit history stay unchanged."""
import fcntl
import json
import shutil
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

import project
import sync

TRASH = Path.home()/'.Trash'


def load(root):
    path = Path(root)/'.folders.json'
    return json.loads(path.read_text()) if path.exists() else {'revision': 0, 'folders': [], 'assignments': {}}


@contextmanager
def locked(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.folders.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield load(root)


def save(root, state):
    state['revision'] += 1
    project.atomic_json(Path(root)/'.folders.json', state)


def result(state):
    return {'folders': state['folders'], 'folderRevision': state['revision']}


def folder(state, id):
    found = next((x for x in state['folders'] if x['id'] == id), None)
    if found is None:
        raise ValueError('La carpeta ya no existe. Actualiza tus proyectos.')
    return found


def name(state, value, except_id=None):
    if not isinstance(value, str):
        raise ValueError('Escribe un nombre para la carpeta')
    value = unicodedata.normalize('NFC', ' '.join(value.split()))
    if not value or len(value) > 80:
        raise ValueError('El nombre de la carpeta debe tener entre 1 y 80 caracteres')
    if any(x['id'] != except_id and x['name'].casefold() == value.casefold() for x in state['folders']):
        raise ValueError('Ya existe una carpeta con ese nombre')
    return value


def project_files(root):
    # Deeper .studio files are history and feedback snapshots of a project, not projects.
    root = Path(root)
    for path in sorted([*root.glob('*.studio'), *root.glob('*/*.studio')]):
        if not any(part.startswith('.') for part in path.relative_to(root).parts):
            yield path


def dispatch(root, req):
    with locked(root) as state:
        if 'revision' in req and req['revision'] != state['revision']:
            raise sync.Conflict('Las carpetas cambiaron. Actualiza la biblioteca y repite la operación.')
        command = req.get('command')
        if command == 'create':
            state['folders'].append({'id': project.uid(), 'name': name(state, req.get('name'))})
        elif command == 'rename':
            item = folder(state, req.get('id'))
            item['name'] = name(state, req.get('name'), item['id'])
        elif command == 'delete':
            item = folder(state, req.get('id'))
            for path in project_files(root):
                # An unreadable project must not be silently treated as absent.
                p = project.load(path)
                if state['assignments'].get(p['id']) == item['id'] and not req.get('release'):
                    raise ValueError('Mueve los proyectos a otra carpeta antes de eliminar esta carpeta')
            state['folders'].remove(item)
            state['assignments'] = {k: v for k, v in state['assignments'].items() if v != item['id']}
        elif command == 'trash':
            path = Path(req.get('project', '')).expanduser().resolve()
            if path.suffix != '.studio' or path.parent.parent != Path(root).resolve():
                raise ValueError('Selecciona un proyecto de la biblioteca local')
            p = project.load(path)
            # Only the project's own folder moves; source media outside it is never touched.
            TRASH.mkdir(parents=True, exist_ok=True)
            target = TRASH/path.parent.name
            if target.exists():
                target = TRASH/f'{path.parent.name} {time.strftime("%H.%M.%S")}'
            shutil.move(str(path.parent), str(target))
            state['assignments'].pop(p['id'], None)
        elif command == 'assign':
            destination = req.get('folder')
            if destination is not None:
                folder(state, destination)
            path = Path(req.get('project', '')).expanduser().resolve()
            if path.suffix != '.studio' or not path.is_relative_to(Path(root).resolve()):
                raise ValueError('Selecciona un proyecto de la biblioteca local')
            p = project.load(path)
            if destination is None:
                state['assignments'].pop(p['id'], None)
            else:
                state['assignments'][p['id']] = destination
        else:
            raise ValueError('Operación de carpetas desconocida')
        save(root, state)
        return result(state)
