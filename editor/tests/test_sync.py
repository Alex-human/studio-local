import sys,tempfile,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import editor,project,sync
class SyncTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'p.studio'
  p=project.new(fps=30);p['assets']=[dict(id='v',path='/video.mp4',name='video',duration=60,audio=True)]
  p['clips']=[dict(id='c',asset='v',length=600,**{'in':0})];p['audio']=[dict(id='music',asset='v',start=0,length=300,role='music',volumeDb=-12,**{'in':0})]
  p['graphics']=[dict(id='g',type='title',start=80,length=90,props={'text':'Título','x':200})];project.save(self.path,p)
 def ops(self,rev,ops):return editor.dispatch(dict(action='ops',project=str(self.path),revision=rev,ops=ops))['project']
 def test_disjoint_fields_same_item(self):
  self.ops(0,[dict(op='set',kind='audio',id='music',values={'fadeOut':60})])
  p=self.ops(0,[dict(op='set',kind='audio',id='music',values={'volumeDb':-20})]);self.assertEqual((p['audio'][0]['fadeOut'],p['audio'][0]['volumeDb']),(60,-20))
 def test_media_replacement_merges_volume_but_conflicts_with_other_replacement(self):
  p=project.load(self.path);p['assets'] += [dict(id=id,path='/'+id+'.mp4',name=id,duration=60,audio=True) for id in ('v2','v3')];project.save(self.path,p)
  self.ops(0,[dict(op='set',kind='clips',id='c',values={'volumeDb':-9})])
  p=self.ops(0,[dict(op='set',kind='clips',id='c',values={'asset':'v2'})]);self.assertEqual((p['clips'][0]['asset'],p['clips'][0]['volumeDb']),('v2',-9))
  before=self.path.read_bytes()
  with self.assertRaises(sync.Conflict):self.ops(0,[dict(op='set',kind='clips',id='c',values={'asset':'v3'})])
  self.assertEqual(self.path.read_bytes(),before)
 def test_nested_properties_and_two_additions(self):
  self.ops(0,[dict(op='set',kind='graphics',id='g',values={'props':{'text':'Nuevo','x':200}}),dict(op='add',kind='graphics',item=dict(id='a',type='title',start=0,length=20,props={}))])
  p=self.ops(0,[dict(op='set',kind='graphics',id='g',values={'props':{'text':'Título','x':400}}),dict(op='add',kind='graphics',item=dict(id='b',type='title',start=300,length=20,props={}))]);self.assertEqual(p['graphics'][0]['props'],{'text':'Nuevo','x':400});self.assertEqual({g['id'] for g in p['graphics']},{'g','a','b'})
 def test_same_property_conflict_does_not_write(self):
  self.ops(0,[dict(op='set',kind='audio',id='music',values={'volumeDb':-20})]);before=self.path.read_bytes()
  with self.assertRaises(sync.Conflict):self.ops(0,[dict(op='set',kind='audio',id='music',values={'volumeDb':-30})])
  self.assertEqual(self.path.read_bytes(),before)
 def test_delete_vs_edit_conflicts(self):
  self.ops(0,[dict(op='delete',kind='graphics',id='g')])
  with self.assertRaises(sync.Conflict):self.ops(0,[dict(op='set',kind='graphics',id='g',values={'hidden':True})])
 def test_cut_and_unrelated_volume_preserve_ripple(self):
  self.ops(0,[dict(op='cutRange',start=10,end=40)])
  p=self.ops(0,[dict(op='set',kind='graphics',id='g',values={'props':{'text':'Otro','x':200}})])
  self.assertEqual(project.duration(p),570);self.assertEqual(p['graphics'][0]['start'],50);self.assertEqual(p['graphics'][0]['props']['text'],'Otro')
 def test_two_structural_edits_refuse_ambiguous_frames(self):
  self.ops(0,[dict(op='cutRange',start=10,end=40)]);before=self.path.read_bytes()
  with self.assertRaises(sync.Conflict):self.ops(0,[dict(op='cutRange',start=100,end=130)])
  self.assertEqual(self.path.read_bytes(),before)
 def test_undo_after_merge_keeps_remote_change(self):
  self.ops(0,[dict(op='mixer',values={'music':-18})]);self.ops(0,[dict(op='mixer',values={'voice':-3})])
  p=editor.dispatch(dict(action='undo',project=str(self.path)))['project'];self.assertEqual(p['mixer'],dict(voice=0,music=-18,sfx=0))
 def test_poll_readonly(self):
  self.assertFalse(editor.dispatch(dict(action='poll',project=str(self.path),revision=0))['changed']);self.ops(0,[dict(op='mixer',values={'music':-15})]);before=self.path.read_bytes()
  self.assertTrue(editor.dispatch(dict(action='poll',project=str(self.path),revision=0))['changed']);self.assertEqual(before,self.path.read_bytes())
 def test_rename_preserves_remote_edit_and_rejects_competing_name(self):
  original=project.load(self.path)
  self.ops(0,[dict(op='mixer',values={'music':-18})])
  p=self.ops(0,[dict(op='settings',values={'name':'Nombre nuevo'})])
  self.assertEqual(p['name'],'Nombre nuevo');self.assertEqual(p['mixer']['music'],-18)
  for key in ('id','assets','clips','audio','graphics','captions'):self.assertEqual(p[key],original[key])
  before=self.path.read_bytes()
  with self.assertRaises(sync.Conflict):self.ops(0,[dict(op='settings',values={'name':'Otro nombre'})])
  self.assertEqual(self.path.read_bytes(),before)
  p=editor.dispatch(dict(action='undo',project=str(self.path)))['project']
  self.assertEqual(p['name'],original['name']);self.assertEqual(p['mixer']['music'],-18)
