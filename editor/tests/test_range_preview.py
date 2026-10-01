import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import editor, project, render

class RangePreview(unittest.TestCase):
    """A rendered range equals the same stretch of the whole timeline, without rendering the whole video."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='studio-range-');root=cls.root=Path(cls.temp.name)
        render.run(['-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=6','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=6',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',root/'base.mp4'])
        render.run(['-v','error','-f','lavfi','-i','testsrc=size=160x90:rate=30:duration=4','-c:v','libx264','-pix_fmt','yuv420p',root/'over.mp4'])
        render.run(['-v','error','-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=6',root/'music.wav'])
        p=project.new(width=160,height=90,fps=30)
        p['assets']=[dict(id='base',kind='video',path=str(root/'base.mp4'),name='Base',duration=6,width=160,height=90,fps=30,audio=True),
                     dict(id='over',kind='video',path=str(root/'over.mp4'),name='Over',duration=4,width=160,height=90,fps=30,audio=False),
                     dict(id='song',kind='audio',path=str(root/'music.wav'),name='Song',duration=6,audio=True)]
        p['clips']=[dict(id='a',asset='base',length=60,zoom=1.2,zoomEnd=1.5,**{'in':0}),dict(id='b',asset='base',length=60,**{'in':90})]
        p['graphics']=[dict(id='t',type='title',start=0,length=120,props={'text':'Title'}),
                       dict(id='o',type='video',asset='over',start=30,length=60,muted=True,props={'width':1920,'x':960,'y':540,'style':'clean','animation':'none','opacity':1},
                            keyframes={'opacity':[{'frame':0,'value':0},{'frame':9,'value':1},{'frame':51,'value':1},{'frame':60,'value':0}]},**{'in':0})]
        p['audio']=[dict(id='m',asset='song',role='music',start=10,length=100,volumeDb=-12,fadeIn=20,fadeOut=30,**{'in':0})]
        cls.p=project.validate(p);cls.path=root/'test.studio';project.save(cls.path,cls.p)
        cls.part=project.excerpt(cls.p,45,75)
    def test_excerpt_keeps_every_layer_in_sync_and_the_revision(self):
        self.assertEqual(project.duration(self.part),30);self.assertEqual(self.part['revision'],self.p['revision'])
        self.assertEqual([c['in'] for c in self.part['clips']],[45,90])
        with self.assertRaises(ValueError):project.excerpt(self.p,75,45)
        with self.assertRaises(ValueError):project.excerpt(self.p,0,121)
    def test_frames_match_the_whole_timeline(self):
        for i in (0,5,14,15,29):
            a=render.frame(self.part,i,self.root/'part',width=160);b=render.frame(self.p,45+i,self.root/'full',width=160)
            with Image.open(a['path']) as x,Image.open(b['path']) as y:np.testing.assert_array_equal(np.asarray(x),np.asarray(y))
    def test_mix_matches_the_whole_timeline(self):
        (self.root/'mixpart').mkdir(exist_ok=True);(self.root/'mixfull').mkdir(exist_ok=True)
        pcm=lambda wav:np.frombuffer(render.run(['-v','error','-i',wav,'-f','f32le','-ac','2','-']),np.float32).reshape(-1,2)
        part,full=pcm(render.render_audio(self.part,self.root/'mixpart')),pcm(render.render_audio(self.p,self.root/'mixfull'))
        a=48000*45//30;n=len(part);edge=480   # 10 ms: the cut edges get the usual 3 ms anti-click fades
        self.assertEqual(n,48000*30//30)
        self.assertLess(np.abs(part[edge:n-edge]-full[a+edge:a+n-edge]).max(),2e-3)
        self.assertGreater(np.abs(part).max(),.01)
    def test_render_action_writes_only_the_range_as_a_preview(self):
        result=editor.dispatch({'action':'render','project':str(self.path),'range':[45,75]})
        self.assertEqual(result['frames'],30);self.assertTrue(result['preview']);self.assertIn('-45-75-',Path(result['path']).name)
        self.assertEqual(Path(result['path']).parent,(self.root/'previews').resolve())
        self.assertEqual(len(render.run(['-v','error','-i',result['path'],'-f','rawvideo','-pix_fmt','gray','-']))//(160*90),30)
        for bad in ([45],[45,'75'],[75,45]):
            with self.assertRaises(ValueError):editor.dispatch({'action':'render','project':str(self.path),'range':bad})

if __name__=='__main__':unittest.main()
