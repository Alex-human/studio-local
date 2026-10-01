import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import audio_library
import editor
import project
import render
import sync


class AudioLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base/'assets/audio/Biblioteca'
        self.path = self.base/'project/Proyecto.studio'
        project.save(self.path, project.new(fps=30))
        self.root_patch = patch.object(editor, 'ROOT', self.base/'editor')
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def file(self, relative, contents=b'audio'):
        path = self.base/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def request(self, source, role='sfx', **values):
        return dict(action='import', project=str(self.path), path=str(source), libraryRole=role, **values)

    def probe(self, path):
        return dict(id=project.uid(), path=str(path), name=Path(path).name, kind='audio',
                    duration=2, width=0, height=0, fps=0, audio=True, hdr=False)

    def import_audio(self, source, role='sfx', **values):
        with patch.object(render, 'probe', side_effect=self.probe), patch.object(render, 'waveform', return_value=[.2]):
            return editor.dispatch(self.request(source, role, **values))['project']

    def test_discovery_names_mapping_and_hidden_symlinks(self):
        originals = [self.file('assets/audio/sfx/abcdef123456-Soft_Click.wav'),
                     self.file('assets/audio/music/123456abcdef-Fondo.mp3', b'music'),
                     self.file('assets/sfx/editorial/whoosh.wav', b'whoosh'),
                     self.file('editor/assets/sfx/click.wav', b'click')]
        self.file('assets/audio/sfx/.hidden.wav')
        self.file('assets/audio/sfx/.private/hidden.wav')
        self.file('assets/audio/sfx/notes.txt')
        (self.base/'assets/audio/sfx/symlink.wav').symlink_to(originals[0])
        (self.base/'assets/audio/sfx/linked').symlink_to(originals[2].parent)
        self.file('assets/audio/catalog.json', json.dumps({'sources': {
            'assets/sfx/editorial/whoosh.wav': {'role': 'music', 'name': 'Subida suave', 'folder': 'Transiciones'}
        }}).encode())
        result = editor.dispatch(dict(action='audioLibrary', role='sfx'))
        self.assertEqual(result, {'directory': str(self.root/'Efectos'), 'count': 2})
        self.assertTrue((self.root/'Efectos/Soft Click.wav').is_file())
        self.assertTrue((self.root/'Música/Fondo.mp3').is_file())
        self.assertTrue((self.root/'Música/Transiciones/Subida suave.wav').is_file())
        self.assertTrue(all(p.exists() for p in originals))
        self.assertEqual(len(list(audio_library.audio_files(self.root))), 4)

    def test_incremental_repeated_and_direct_additions(self):
        self.file('assets/audio/sfx/tick.wav')
        editor.dispatch(dict(action='audioLibrary', role='sfx'))
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()}
        with patch.object(audio_library, 'copy_unique', side_effect=AssertionError('Unchanged source recopied')):
            editor.dispatch(dict(action='audioLibrary', role='sfx'))
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()})
        self.file('assets/audio/sfx/new.wav', b'new')
        direct = self.file('assets/audio/Biblioteca/Efectos/Directo.wav', b'direct')
        result = editor.dispatch(dict(action='audioLibrary', role='sfx'))
        self.assertEqual(result['count'], 3)
        self.assertEqual(direct.read_bytes(), b'direct')

    def test_changed_source_keeps_previous_audio_and_catalog_rename_wins(self):
        source = self.file('assets/audio/sfx/sound.wav', b'first')
        editor.dispatch(dict(action='audioLibrary', role='sfx'))
        source.write_bytes(b'new audio')
        editor.dispatch(dict(action='audioLibrary', role='sfx'))
        self.assertEqual((self.root/'Efectos/sound.wav').read_bytes(), b'first')
        self.assertEqual(len(list(audio_library.audio_files(self.root))), 2)
        self.file('assets/audio/catalog.json', json.dumps({'sources': {
            'assets/audio/sfx/sound.wav': {'role': 'sfx', 'name': 'Nombre claro'}
        }}).encode())
        editor.dispatch(dict(action='audioLibrary', role='sfx'))
        self.assertEqual((self.root/'Efectos/Nombre claro.wav').read_bytes(), b'new audio')

    def test_same_name_collision_is_stable_without_overwrite(self):
        self.file('assets/audio/sfx/one/sound.wav', b'first')
        self.file('assets/audio/sfx/two/sound.wav', b'second')
        editor.dispatch(dict(action='audioLibrary', role='sfx'))
        files = {p.name: p.read_bytes() for p in audio_library.audio_files(self.root)}
        self.assertEqual(set(files.values()), {b'first', b'second'})
        self.assertEqual(len(files), 2)
        editor.dispatch(dict(action='audioLibrary', role='sfx'))
        self.assertEqual(files, {p.name: p.read_bytes() for p in audio_library.audio_files(self.root)})

    def test_external_import_deduplicates_and_inside_is_not_copied(self):
        source = self.file('external/a.wav')
        first = self.import_audio(source, start=17)
        destination = Path(first['assets'][0]['path'])
        self.assertTrue(destination.is_relative_to(self.root/'Efectos'))
        duplicate = self.file('external/renamed.wav')
        second = self.import_audio(duplicate, start=40)
        third = self.import_audio(destination, start=80)
        self.assertEqual(len(third['assets']), 1)
        self.assertEqual(len(third['audio']), 3)
        self.assertEqual(len(list(audio_library.audio_files(self.root))), 1)
        self.assertEqual(second['assets'][0]['path'], str(destination))
        self.assertEqual(source.read_bytes(), b'audio')
        source.unlink()
        self.assertEqual(destination.read_bytes(), b'audio')

    def test_external_same_name_collision(self):
        first = self.import_audio(self.file('one/sound.wav', b'one'))
        second = self.import_audio(self.file('two/sound.wav', b'two'))
        self.assertEqual(Path(first['assets'][0]['path']).read_bytes(), b'one')
        self.assertEqual(len(second['assets']), 2)
        self.assertEqual({p.read_bytes() for p in audio_library.audio_files(self.root)}, {b'one', b'two'})

    def test_concurrent_sync_and_retention_publish_one_copy(self):
        source = self.file('assets/audio/sfx/sound.wav')
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: audio_library.synchronize(self.base, 'sfx'), range(4)))
        self.assertTrue(all(result['count'] == 1 for result in results))
        duplicate = self.file('external/renamed.wav')
        with ThreadPoolExecutor(max_workers=4) as workers:
            paths = list(workers.map(lambda _: audio_library.retain(self.base, duplicate, 'sfx'), range(4)))
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(len(list(audio_library.audio_files(self.root))), 1)
        record = json.loads((self.root/'.manifest.json').read_text())['sources'][source.relative_to(self.base).as_posix()]
        self.assertEqual((self.root/record['dest']).read_bytes(), source.read_bytes())

    def test_explicit_music_and_sfx_role_gain_fades_start(self):
        source = self.file('external/track.wav')
        music = self.import_audio(source, role='music', start=93)['audio'][-1]
        self.assertEqual((music['role'], music['start'], music['volumeDb'], music['fadeIn'], music['fadeOut']), ('music', 93, -24, 15, 15))
        sfx = self.import_audio(source, role='sfx', start=117)['audio'][-1]
        self.assertEqual((sfx['role'], sfx['start'], sfx['volumeDb']), ('sfx', 117, 0))
        self.assertNotIn('fadeIn', sfx)
        with patch.object(render, 'probe', side_effect=lambda path: {**self.probe(path), 'duration': .1}), patch.object(render, 'waveform', return_value=[]):
            short = editor.dispatch(self.request(source, 'music'))['project']['audio'][-1]
        self.assertEqual((short['length'], short['fadeIn'], short['fadeOut']), (3, 3, 3))

    def test_generic_import_keeps_existing_behavior(self):
        source = self.file('external/generic.wav')
        request = self.request(source, 'music', start=43)
        del request['libraryRole']
        with patch.object(render, 'probe', side_effect=self.probe), patch.object(render, 'waveform', return_value=[]):
            result = editor.dispatch(request)['project']
        self.assertEqual(result['assets'][0]['path'], str(source))
        self.assertEqual(result['audio'][0]['volumeDb'], 0)
        self.assertEqual(result['audio'][0]['start'], 43)
        self.assertNotIn('fadeIn', result['audio'][0])
        self.assertFalse(self.root.exists())

    def test_invalid_audio_has_no_project_or_library_write(self):
        source = self.file('external/invalid.wav', b'not audio')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            editor.dispatch(self.request(source, 'music'))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.root.exists())
        self.assertFalse((self.path.parent/'.history').exists())
        with patch.object(render, 'probe', return_value={**self.probe(source), 'kind': 'video'}):
            with self.assertRaises(ValueError):
                editor.dispatch(self.request(source))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.root.exists())

    def test_stale_revision_and_invalid_start_have_no_library_write(self):
        source = self.file('external/tick.wav')
        before = self.path.read_bytes()
        with patch.object(render, 'probe', side_effect=AssertionError('Stale request probed')):
            with self.assertRaises(sync.Conflict):
                editor.dispatch(self.request(source, revision=91))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.root.exists())
        with self.assertRaises(ValueError):
            self.import_audio(source, start=-1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.root.exists())

    def test_invalid_roles_and_catalog_paths_cannot_escape(self):
        with self.assertRaises(ValueError):
            editor.dispatch(dict(action='audioLibrary', role='voice'))
        self.assertFalse(self.root.exists())
        self.file('assets/audio/sfx/tick.wav')
        self.file('assets/audio/catalog.json', json.dumps({'sources': {
            'assets/audio/sfx/tick.wav': {'role': 'sfx', 'name': 'Tick', 'folder': '../../outside'}
        }}).encode())
        with self.assertRaises(ValueError):
            editor.dispatch(dict(action='audioLibrary', role='sfx'))
        self.assertFalse((self.base/'assets/audio/outside').exists())


if __name__ == '__main__':
    unittest.main()
