"""Persistent music/SFX copies. Originals and already referenced copies are immutable."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import project

ROLES = {'sfx': 'Efectos', 'music': 'Música'}
EXTENSIONS = {'.wav', '.mp3', '.m4a', '.aac', '.flac'}
SOURCES = (('assets/audio/sfx', 'sfx'), ('assets/audio/music', 'music'),
           ('assets/sfx/editorial', 'sfx'), ('editor/assets/sfx', 'sfx'))


def role_name(role):
    if role not in ('sfx', 'music'):
        raise ValueError('Biblioteca de audio desconocida')
    return ROLES[role]


def clean_name(value):
    value = re.sub(r'^(?:[a-fA-F0-9]{8,64}[-_ ]+)+', '', value)
    value = re.sub(r'[\x00-\x1f\x7f/\\:]+', ' ', value).replace('_', ' ')
    return re.sub(r'\s+', ' ', value).strip(' .')[:180] or 'Audio'


def audio_files(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        return
    for folder, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(folder)/d).is_symlink())
        for name in sorted(files):
            path = Path(folder)/name
            if not name.startswith('.') and path.suffix.lower() in EXTENSIONS and not path.is_symlink() and path.is_file():
                yield path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


@contextmanager
def library_lock(base):
    root = Path(base)/'assets/audio/Biblioteca'
    if root.is_symlink():
        raise ValueError('La biblioteca debe ser una carpeta local')
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield root


def directory(root, role, folder=''):
    name = role_name(role)
    parts = Path(folder).parts
    if Path(folder).is_absolute() or any(p in ('.', '..') or p.startswith('.') for p in parts):
        raise ValueError('Carpeta de audio no válida')
    dest = root
    for part in (name, *(clean_name(p) for p in parts)):
        dest = dest/part
        if dest.is_symlink():
            raise ValueError('La biblioteca debe contener carpetas locales')
        dest.mkdir(exist_ok=True)
    return dest


def copy_unique(source, preferred):
    """Reuse identical bytes on collision; never replace an existing audio file."""
    source = Path(source)
    source_digest = None
    dest = preferred
    suffix = 0
    while dest.exists() or dest.is_symlink():
        source_digest = source_digest or digest(source)
        if not dest.is_symlink() and dest.is_file() and dest.stat().st_size == source.stat().st_size and digest(dest) == source_digest:
            return dest
        suffix += 1
        tag = source_digest[:10] + (f'-{suffix}' if suffix > 1 else '')
        dest = preferred.with_name(f'{preferred.stem} · {tag}{preferred.suffix}')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix='.', suffix='.tmp', delete=False) as target:
            temporary = Path(target.name)
            with source.open('rb') as original:
                shutil.copyfileobj(original, target)
            target.flush()
            os.fsync(target.fileno())
        # Linking publishes a complete file and fails if somebody created the name.
        os.link(temporary, dest)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return dest


def synchronize(base, role):
    """Discover new legacy files while retaining user-added canonical files directly."""
    role_name(role)
    base = Path(base).resolve()
    catalog = base/'assets/audio/catalog.json'
    mapping = json.loads(catalog.read_text()).get('sources', {}) if catalog.exists() else {}
    with library_lock(base) as root:
        for item in ROLES:
            directory(root, item)
        manifest_path = root/'.manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'sources': {}}
        records = manifest['sources']
        changed = not manifest_path.exists()
        for relative, fallback_role in SOURCES:
            for source in audio_files(base/relative):
                key = source.relative_to(base).as_posix()
                entry = mapping.get(key, {})
                folder = directory(root, entry.get('role', fallback_role), entry.get('folder', ''))
                preferred = folder/(clean_name(entry.get('name', source.stem)) + source.suffix.lower())
                stat = source.stat()
                target = preferred.relative_to(root).as_posix()
                record = records.get(key, {})
                saved = root/record.get('dest', '')
                if (record.get('size'), record.get('mtime_ns'), record.get('target')) == (stat.st_size, stat.st_mtime_ns, target) and saved.is_file() and not saved.is_symlink():
                    continue
                dest = copy_unique(source, preferred)
                records[key] = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                                'target': target, 'dest': dest.relative_to(root).as_posix()}
                changed = True
        if changed:
            project.atomic_json(manifest_path, manifest)
        result = root/role_name(role)
        return {'directory': str(result), 'count': sum(1 for _ in audio_files(result))}


def retain(base, source, role):
    """Copy an explicitly imported, already validated audio into its permanent role."""
    role_name(role)
    source = Path(source).resolve()
    with library_lock(base) as root:
        folder = directory(root, role)
        if source.is_relative_to(root.resolve()):
            return source
        source_digest = digest(source)
        size = source.stat().st_size
        for candidate in audio_files(folder):
            if candidate.stat().st_size == size and digest(candidate) == source_digest:
                return candidate
        return copy_unique(source, folder/(clean_name(source.stem) + source.suffix.lower()))
