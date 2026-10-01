import concurrent.futures,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import editor,project,render,sync
class FeedbackTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.shared=tempfile.TemporaryDirectory();cls.video=Path(cls.shared.name)/'source.mp4'
  render.run(['-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-y',str(cls.video)])
 @classmethod
 def tearDownClass(cls):cls.shared.cleanup()
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'p.studio'
  self.p=project.new(width=320,height=180,fps=30);self.p['assets']=[dict(id='a',kind='video',path=str(self.video),name='source',duration=3,audio=False)]
  self.p['clips']=[dict(id='c',asset='a',length=90,**{'in':0})];project.save(self.path,self.p)
 def call(self,command,**kwargs):return editor.dispatch(dict(action='feedback',project=str(self.path),command=command,**kwargs))
 def create(self,id='f1',frame=45,revision=0):return self.call('create',id=id,frame=frame,revision=revision)
 def update(self,n,values):return self.call('update',id=n['id'],version=n['version'],values=values)
 def test_read_empty_has_no_db_side_effect(self):
  self.assertEqual(self.call('list'),dict(version=0,projectRevision=0,notes=[]));self.assertFalse((self.path.parent/'feedback').exists())
 def test_exact_immutable_frame_and_note_outside_render(self):
  before=self.path.read_bytes();n=self.create();self.assertEqual(before,self.path.read_bytes());self.assertEqual((n['frame'],n['seconds'],n['revision']),(45,1.5,0))
  original=render.frame(self.p,45,self.path.parent/'comparison',width=320)
  editor.dispatch(dict(action='ops',project=str(self.path),revision=0,ops=[dict(op='set',kind='clips',id='c',values={'zoom':1.5})]))
  n=self.call('capture',id=n['id']);self.assertEqual(n['capture'],'ready')
  with Image.open(n['files']['image']) as actual,Image.open(original['path']) as expected:self.assertIsNone(ImageChops.difference(actual,expected).getbbox())
  self.assertEqual(project.load(n['files']['project'])['revision'],0)
 def test_drawings_persist_raster_and_are_not_video_layers(self):
  n=self.call('capture',id=self.create()['id']);before=self.path.read_bytes();stroke=dict(tool='ellipse',color='#ffad5c',width=.01,points=[[.1,.1],[.7,.7]])
  n=self.update(n,dict(text='Mover aquí',strokes=[stroke],status='open'));self.assertEqual(self.path.read_bytes(),before)
  with Image.open(n['files']['image']) as a,Image.open(n['files']['annotated']) as b:self.assertIsNotNone(ImageChops.difference(a,b).getbbox())
  self.assertEqual(self.call('get',id=n['id'])['strokes'],[stroke])
 def test_capture_failure_keeps_text_and_retries(self):
  n=self.update(self.create(),{'text':'No perder esto'})
  with patch.object(render,'frame',side_effect=ValueError('test capture')):
   with self.assertRaises(ValueError):self.call('capture',id=n['id'])
  n=self.call('get',id=n['id']);self.assertEqual(n['text'],'No perder esto');self.assertEqual(n['capture'],'error')
  with self.assertRaises(ValueError):self.update(n,{'status':'open'})
  n=self.call('capture',id=n['id']);self.assertEqual(n['capture'],'ready');self.assertEqual(n['version'],2)
 def test_anchor_moves_after_ripple_and_removed_note_survives(self):
  n=self.create();editor.dispatch(dict(action='ops',project=str(self.path),revision=0,ops=[dict(op='cutRange',start=5,end=15)]))
  self.assertEqual(self.call('get',id=n['id'])['currentFrame'],35)
  editor.dispatch(dict(action='ops',project=str(self.path),revision=1,ops=[dict(op='cutRange',start=30,end=40)]))
  n=self.call('get',id=n['id']);self.assertIsNone(n['currentFrame']);self.assertEqual(n['position'],'removed');self.assertTrue(Path(n['files']['project']).exists())
 def test_review_revision_is_kept_even_if_project_advanced(self):
  editor.dispatch(dict(action='ops',project=str(self.path),revision=0,ops=[dict(op='cutRange',start=5,end=15)]))
  n=self.create();self.assertEqual(n['revision'],0);self.assertEqual(self.call('get',id=n['id'])['currentFrame'],35)
  self.assertEqual(self.call('list',revision=0)['notes'][0]['currentFrame'],45)
 def test_create_idempotent_and_two_concurrent_notes(self):
  self.create();self.create();self.assertEqual(len(self.call('list')['notes']),1)
  with concurrent.futures.ThreadPoolExecutor(4) as pool:list(pool.map(lambda i:self.create('f'+str(i),i+10),range(2,8)))
  self.assertEqual(len(self.call('list')['notes']),7)
 def test_optimistic_conflict_does_not_lose_newer_comment(self):
  n=self.create();updated=self.update(n,{'text':'nuevo'})
  with self.assertRaises(sync.Conflict):self.update(n,{'text':'viejo'})
  self.assertEqual(self.call('get',id=n['id'])['text'],'nuevo');self.assertEqual(updated['version'],2)
 def test_statuses_and_filter_and_soft_delete(self):
  n=self.call('capture',id=self.create()['id']);n=self.update(n,{'text':'Cambio','status':'open'})
  n=self.update(n,{'status':'resolved','resolution':'Título corregido','appliedRevision':0});self.assertEqual(self.call('list',status='open')['notes'],[])
  self.assertEqual(len(self.call('list',status='resolved')['notes']),1);n=self.update(n,{'status':'open'});n=self.update(n,{'status':'deleted'});self.assertEqual(self.call('list')['notes'],[]);self.assertEqual(self.call('get',id=n['id'])['text'],'Cambio')
 def test_invalid_payload_and_empty_publish(self):
  n=self.create()
  for points in ([[float('nan'),.1]],[[2,.1]]):
   with self.assertRaises(ValueError):self.update(n,{'strokes':[dict(tool='pen',points=points,width=.005,color='#ffffff')]})
  with self.assertRaises(ValueError):self.create('../outside')
  with self.assertRaises(ValueError):self.create(frame=4.5)
  n=self.call('capture',id=n['id'])
  with self.assertRaises(ValueError):self.update(n,{'status':'open'})
 def test_poll_separates_project_revision_and_feedback_version(self):
  self.create();a=self.call('list');self.assertTrue(self.call('list',since=a['version'],projectRevision=0)['unchanged'])
  editor.dispatch(dict(action='ops',project=str(self.path),revision=0,ops=[dict(op='cutRange',start=5,end=15)]));b=self.call('list',since=a['version'],projectRevision=0);self.assertEqual(b['notes'][0]['currentFrame'],35)
