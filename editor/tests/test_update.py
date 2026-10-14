import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import install_update as update
import editor
class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);(self.root/'.build').mkdir();(self.root/'runtime').mkdir()
  self.stage=self.root/'.build/app-test';self.stage.mkdir();(self.stage/'Studio Local.app').mkdir();(self.stage/'Studio Local.app/new').write_text('new');(self.stage/'probe').write_text('probe')
  (self.root/'Studio Local.app').mkdir();(self.root/'Studio Local.app/old').write_text('old')
 def test_no_replace_running_bundle(self):
  with patch.object(update,'ROOT',self.root),patch.object(update,'running',return_value=True):
   with self.assertRaises(RuntimeError):update.promote(self.stage)
  self.assertTrue((self.root/'Studio Local.app/old').exists());self.assertTrue(self.stage.exists())
 def test_fresh_install_does_not_require_process_visibility(self):
  import shutil
  shutil.rmtree(self.root/'Studio Local.app')
  with patch.object(update,'ROOT',self.root),patch.object(update.subprocess,'run') as processes:
   update.promote(self.stage);processes.assert_not_called()
  self.assertTrue((self.root/'Studio Local.app/new').exists())
 def test_existing_install_keeps_process_check(self):
  from types import SimpleNamespace
  with patch.object(update,'ROOT',self.root),patch.object(update.subprocess,'run',return_value=SimpleNamespace(returncode=2)):
   with self.assertRaises(RuntimeError):update.running()
 def test_closed_bundle_promotes(self):
  with patch.object(update,'ROOT',self.root),patch.object(update,'running',return_value=False):update.promote(self.stage)
  self.assertTrue((self.root/'Studio Local.app/new').exists());self.assertEqual((self.root/'runtime/probe').read_text(),'probe');self.assertFalse(self.stage.exists())
 def test_failure_restores_old_bundle(self):
  with patch.object(update,'ROOT',self.root),patch.object(update,'running',return_value=False),patch.object(update.os,'replace',side_effect=OSError('test')):
   with self.assertRaises(OSError):update.promote(self.stage)
  self.assertTrue((self.root/'Studio Local.app/old').exists());self.assertTrue((self.stage/'Studio Local.app/new').exists())
 def test_session_roundtrip_no_project_writes(self):
  session=dict(project='/test.studio',revision=3,cursor=140,zoom=8,scroll=900,selection={'kind':'audio','id':'music'},playing=False)
  with patch.object(editor,'ROOT',self.root):
   self.assertIsNone(editor.dispatch({'action':'sessionRead'}));editor.dispatch({'action':'sessionSave','session':session});self.assertEqual(editor.dispatch({'action':'sessionRead'}),session)
 def test_stage_must_be_local_build(self):
  with patch.object(update,'ROOT',self.root):
   with self.assertRaises(ValueError):update.verified_stage('/private/tmp/foreign')
