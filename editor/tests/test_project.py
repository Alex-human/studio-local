import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import project
import editor
import graphics
from PIL import Image

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.p=project.new(fps=30)
        self.p['assets']=[dict(id='v',path='/example.mp4',name='Example',duration=60,audio=True)]
        self.p['clips']=[dict(id='c',asset='v',length=300,**{'in':0},zoom=1,zoomEnd=1.2)]
        self.p['audio']=[dict(id='a',asset='v',role='music',start=0,length=300,**{'in':0})]
        self.p['graphics']=[dict(id='g',type='title',start=100,length=100,props={'text':'Hola'})]

    def test_cut_range_preserves_sources_and_ripples(self):
        out=project.apply(self.p,[dict(op='cutRange',start=120,end=150)])
        self.assertEqual(project.duration(out),270)
        self.assertEqual([(c['in'],c['length']) for c in out['clips']],[(0,120),(150,150)])
        self.assertEqual([(a['in'],a['start'],a['length']) for a in out['audio']],[(0,0,120),(150,120,150)])
        self.assertEqual((out['graphics'][0]['start'],out['graphics'][0]['length']),(100,20))
        self.assertEqual((out['graphics'][1]['start'],out['graphics'][1]['length'],out['graphics'][1]['offset']),(120,50,50))
        self.assertEqual(self.p['clips'][0]['length'],300)

    def test_split_retains_motion_phase(self):
        out=project.apply(self.p,[dict(op='split',kind='clips',id='c',at=99)])
        self.assertEqual(out['clips'][1]['motionOffset'],99)
        self.assertEqual(out['clips'][1]['motionLength'],300)
        self.assertEqual(out['clips'][1]['in'],99)

    def test_media_replacement_keeps_timeline_and_rejects_missing_or_short_source(self):
        self.p['assets'] += [dict(id='replacement',path='/replacement.mp4',name='Replacement',duration=60,audio=False),
                             dict(id='short',path='/short.mp4',name='Short',duration=1,audio=False)]
        op=dict(op='set',kind='clips',id='c',values={'asset':'replacement'})
        out=project.apply(self.p,[op])
        expected=copy.deepcopy(self.p);expected['clips'][0]['asset']='replacement';expected['revision']+=1
        self.assertEqual(out,expected)
        for asset in ('missing','short'):
            with self.assertRaises(ValueError):project.apply(self.p,[{**op,'values':{'asset':asset}}])
        self.assertEqual(self.p['clips'][0]['asset'],'v')

    def test_trim(self):
        out=project.apply(self.p,[dict(op='trim',kind='clips',id='c',head=30,tail=20)])
        self.assertEqual(project.duration(out),250)
        self.assertEqual(out['clips'][0]['in'],30)
        self.assertEqual(out['graphics'][0]['start'],70)

    def test_reject_invalid_range_and_no_partial_mutation(self):
        for op in [dict(op='cutRange',start=0,end=300),dict(op='split',kind='clips',id='c',at=300),dict(op='mixer',values={'music':float('nan')})]:
            with self.assertRaises(ValueError):project.apply(self.p,[op])
        self.assertEqual(self.p['revision'],0)

    def test_all_templates_and_keyframes(self):
        for template in project.TEMPLATES:
            if template in ('image','video'):continue
            p=copy.deepcopy(self.p);p['graphics']=[dict(id='g',type=template,start=0,length=300,props={'text':'Precisión y claridad'},keyframes={'x':[{'frame':0,'value':200},{'frame':90,'value':900}]})]
            result=graphics.composite(Image.new('RGB',(480,270),'#2d4450'),p,45)
            self.assertEqual(result.size,(480,270))

    def test_atomic_revision_undo_redo(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.studio';project.save(path,self.p)
            out=editor.dispatch(dict(action='ops',project=str(path),revision=0,ops=[dict(op='mixer',values={'music':-9})]))
            self.assertEqual(out['project']['mixer']['music'],-9)
            with self.assertRaises(ValueError):editor.dispatch(dict(action='ops',project=str(path),revision=0,ops=[]))
            editor.dispatch(dict(action='undo',project=str(path)))
            self.assertEqual(project.load(path)['mixer']['music'],0)
            editor.dispatch(dict(action='redo',project=str(path)))
            self.assertEqual(project.load(path)['mixer']['music'],-9)

    def test_missing_project_is_rejected_without_creating_its_folder(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ausente'/'Proyecto.studio'
            with self.assertRaises(ValueError):editor.dispatch(dict(action='open',project=str(path)))
            self.assertFalse(path.parent.exists())

    def test_mcp_real_process(self):
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        r=subprocess.run([sys.executable,str(Path(editor.__file__)),'--mcp'],input='\n'.join(map(json.dumps,messages))+'\n',capture_output=True,text=True,check=True)
        results=[json.loads(x) for x in r.stdout.splitlines()]
        self.assertEqual(results[0]['result']['serverInfo']['name'],'studio-local')
        self.assertEqual(results[1]['result']['tools'][0]['name'],'studio')

if __name__=='__main__':unittest.main()
