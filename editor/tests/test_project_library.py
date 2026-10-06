import concurrent.futures
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import editor
import project
import project_library
import sync


class ProjectFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'projects'
        self.patch = patch.object(editor, 'PROJECTS', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def command(self, command, **fields):
        return editor.dispatch({'action': 'projectFolders', 'command': command, **fields})

    def new_folder(self, name='Clips'):
        return self.command('create', name=name)['folders'][-1]['id']

    def test_empty_list_and_create_in_folder(self):
        self.assertEqual(editor.dispatch({'action': 'list'})['folders'], [])
        id = self.new_folder('  Clientes   · Clips  ')
        item = editor.dispatch({'action': 'create', 'name': 'Prueba', 'folder': id})
        listing = editor.dispatch({'action': 'list'})
        self.assertEqual(listing['folders'][0]['name'], 'Clientes · Clips')
        self.assertEqual(listing['projects'][0]['folder'], id)
        self.assertEqual(listing['projects'][0]['id'], item['project']['id'])
        self.assertTrue(Path(item['path']).parent.parent == self.root)

    def test_assign_rename_unassign_preserves_project_bytes(self):
        result = editor.dispatch({'action': 'create', 'name': 'Original'})
        path = Path(result['path'])
        before = path.read_bytes()
        id = self.new_folder()
        self.command('assign', project=str(path), folder=id)
        self.command('rename', id=id, name='Clientes')
        listing = editor.dispatch({'action': 'list'})
        self.assertEqual(listing['projects'][0]['folder'], id)
        self.assertEqual(listing['folders'][0]['name'], 'Clientes')
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent/'.history').exists())
        self.command('assign', project=str(path), folder=None)
        self.assertIsNone(editor.dispatch({'action': 'list'})['projects'][0]['folder'])
        self.assertEqual(path.read_bytes(), before)

    def test_delete_nonempty_rejected_and_empty_allowed(self):
        id = self.new_folder()
        result = editor.dispatch({'action': 'create', 'folder': id})
        before = (self.root/'.folders.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Mueve los proyectos'):
            self.command('delete', id=id)
        self.assertEqual((self.root/'.folders.json').read_bytes(), before)
        self.command('assign', project=result['path'], folder=None)
        self.assertEqual(self.command('delete', id=id)['folders'], [])
        self.assertTrue(Path(result['path']).exists())

    def test_trash_moves_project_dir_and_release_unassigns(self):
        trash = Path(self.tmp.name)/'trash'
        with patch.object(project_library, 'TRASH', trash):
            id = self.new_folder()
            a = editor.dispatch({'action': 'create', 'name': 'A', 'folder': id})
            b = editor.dispatch({'action': 'create', 'name': 'B', 'folder': id})
            self.command('trash', project=a['path'])
            self.assertFalse(Path(a['path']).parent.exists())
            self.assertTrue((trash/Path(a['path']).parent.name/'Proyecto.studio').exists())
            self.command('delete', id=id, release=True)
            listing = editor.dispatch({'action': 'list'})
            self.assertEqual([x['id'] for x in listing['projects']], [b['project']['id']])
            self.assertIsNone(listing['projects'][0]['folder'])
            with self.assertRaises(ValueError):
                self.command('trash', project=str(self.root.parent/'x'/'Proyecto.studio'))

    def test_names_and_stale_revision_do_not_overwrite(self):
        id = self.new_folder('Vídeos')
        for invalid in ['', '  ', 'x'*81, None, 'VÍDEOS', 'Vídeos']:
            with self.assertRaises(ValueError):
                self.command('create', name=invalid)
        before = (self.root/'.folders.json').read_bytes()
        with self.assertRaises(sync.Conflict):
            self.command('rename', id=id, name='Otro', revision=0)
        self.assertEqual((self.root/'.folders.json').read_bytes(), before)

    def test_invalid_destination_does_not_create_project(self):
        with self.assertRaises(ValueError):
            editor.dispatch({'action': 'create', 'folder': 'missing'})
        self.assertEqual(list(self.root.glob('**/*.studio')), [])
        id = self.new_folder()
        with self.assertRaises(ValueError):
            self.command('assign', project=str(self.root.parent/'outside.studio'), folder=id)

    def test_concurrent_changes_preserve_all_folders(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda n: self.new_folder('Carpeta '+str(n)), range(12)))
        self.assertEqual(len(editor.dispatch({'action': 'list'})['folders']), 12)
        self.assertEqual(project_library.load(self.root)['revision'], 12)

    def test_history_and_feedback_snapshots_not_counted_as_projects(self):
        result = editor.dispatch({'action': 'create'})
        path, p = Path(result['path']), result['project']
        p['assets'] = [dict(id='a', kind='video', path='/fuente.mp4', name='fuente', duration=1, audio=False)]
        p['clips'] = [dict(id='c', asset='a', length=30, **{'in': 0})]
        project.save(path, p)
        project.save(path.parent/'.history/snapshot.studio', p)
        editor.dispatch({'action': 'feedback', 'project': str(path), 'command': 'create', 'id': 'nota', 'frame': 0})
        self.assertTrue((path.parent/'feedback/nota/snapshot.studio').exists())
        self.assertEqual([x['path'] for x in editor.dispatch({'action': 'list'})['projects']], [str(path)])

    def test_stale_assignments_do_not_block_removal(self):
        id = self.new_folder()
        state = project_library.load(self.root)
        state['assignments']['old-project'] = id
        project_library.save(self.root, state)
        self.command('delete', id=id)
        self.assertEqual(project_library.load(self.root)['assignments'], {})

    def test_undo_does_not_undo_folder_assignment(self):
        result = editor.dispatch({'action': 'create', 'name': 'Antes'})
        path = result['path']
        editor.dispatch({'action': 'ops', 'project': path, 'revision': 0,
                         'ops': [{'op': 'settings', 'values': {'name': 'Después'}}]})
        id = self.new_folder()
        self.command('assign', project=path, folder=id)
        editor.dispatch({'action': 'undo', 'project': path})
        self.assertEqual(editor.dispatch({'action': 'list'})['projects'][0]['folder'], id)


if __name__ == '__main__':
    unittest.main()
