import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import graphics, project, render

class HiddenBaseShortcut(unittest.TestCase):
    """Frames under an opaque full-canvas overlay skip the camera decode and the painting below it, with identical pixels."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='studio-cover-');root=cls.root=Path(cls.temp.name)
        render.run(['-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=6','-c:v','libx264','-pix_fmt','yuv420p',root/'base.mp4'])
        render.run(['-v','error','-f','lavfi','-i','testsrc=size=160x90:rate=30:duration=4','-c:v','libx264','-pix_fmt','yuv420p',root/'over.mp4'])
        render.run(['-v','error','-f','lavfi','-i','testsrc=size=160x90:rate=30:duration=4,format=rgba,colorchannelmixer=aa=.5','-c:v','png',root/'alpha.mov'])
        p=project.new(width=160,height=90,fps=30)
        p['assets']=[dict(id='base',kind='video',path=str(root/'base.mp4'),name='Base',duration=6,width=160,height=90,fps=30,audio=False),
                     dict(id='over',kind='video',path=str(root/'over.mp4'),name='Over',duration=4,width=160,height=90,fps=30,audio=False)]
        p['clips']=[dict(id='a',asset='base',length=80,zoom=1.2,zoomEnd=1.3,**{'in':0}),dict(id='b',asset='base',length=40,**{'in':100})]
        props={'width':1920,'x':960,'y':540,'style':'clean','animation':'none','opacity':1}
        fade={'opacity':[{'frame':0,'value':0},{'frame':6,'value':1},{'frame':34,'value':1},{'frame':40,'value':0}]}
        p['graphics']=[dict(id='o',type='video',asset='over',start=30,length=40,muted=True,props=props,keyframes=fade,**{'in':0}),
                       dict(id='o2',type='video',asset='over',start=75,length=20,muted=True,props=props,**{'in':30}),
                       dict(id='t',type='title',start=40,length=20,props={'text':'Encima'})]
        p['captions']=[dict(id='c',text='Subtítulo',start=50,length=6)]
        cls.p=project.validate(p)
    def test_cover_follows_the_painter(self):
        size=(160,90)
        g=self.p['graphics'][0];opaque=[f for f in range(30,70) if float(graphics.keyframed(g['props'],g['keyframes'],f-30)['opacity'])>=1]
        self.assertEqual([f for f in range(30,70) if graphics.covers(g,self.p,f,size)],opaque)
        self.assertTrue(opaque and opaque[0]>30 and opaque[-1]<69)   # los fundidos no tapan
        self.assertTrue(graphics.covers(self.p['graphics'][1],self.p,80,size))
        for change in ({'style':'photo'},{'rotation':3},{'cropLeft':.1},{'width':1800},{'x':900},{'opacity':.99},{'animation':'pop'}):
            g={**self.p['graphics'][1],'props':{**self.p['graphics'][1]['props'],**change}}
            self.assertFalse(graphics.covers(g,self.p,76,size),change)
        entering={**self.p['graphics'][1],'props':{**self.p['graphics'][1]['props'],'animation':'pop','enter':.2}}
        self.assertTrue(graphics.covers(entering,self.p,94,size))
    def frames(self,name,shortcut):
        folder=self.root/name
        with patch.dict(render.ENCODER,{'master':['-c:v','libx264','-preset','ultrafast','-qp','0']}):
            if shortcut:out=render.render(self.p,folder,with_audio=False)
            else:
                with patch.object(graphics,'covers',return_value=False),patch.object(graphics,'bare',return_value=False):
                    out=render.render(self.p,folder,with_audio=False)
        raw=render.run(['-v','error','-i',out['path'],'-f','rawvideo','-pix_fmt','rgb24','-'])
        return np.frombuffer(raw,np.uint8).reshape(-1,90,160,3)
    def test_export_is_identical(self):
        fast,slow=self.frames('fast',True),self.frames('slow',False)
        self.assertEqual(len(fast),120);np.testing.assert_array_equal(fast,slow)
    def test_bare_frames_skip_the_painter(self):
        with patch.object(graphics,'composite',wraps=graphics.composite) as painter:self.frames('spy',True)
        painted=[f for f in range(120) if not graphics.bare(self.p,f)]
        self.assertTrue(0<len(painted)<120);self.assertEqual(painter.call_count,len(painted))
    def test_single_frame_is_identical(self):
        for n in (45,52,80):
            a=render.frame(self.p,n,self.root/'fa',width=160)
            with patch.object(graphics,'covers',return_value=False):b=render.frame(self.p,n,self.root/'fb',width=160)
            with Image.open(a['path']) as x,Image.open(b['path']) as y:np.testing.assert_array_equal(np.asarray(x),np.asarray(y))
    def test_transparent_overlay_does_not_cover(self):
        p={**self.p,'assets':[{**a,'path':str(self.root/'alpha.mov')} if a['id']=='over' else a for a in self.p['assets']]}
        a=render.frame(p,80,self.root/'ta',width=160)
        with patch.object(graphics,'covers',return_value=False):b=render.frame(p,80,self.root/'tb',width=160)
        with Image.open(a['path']) as x,Image.open(b['path']) as y:np.testing.assert_array_equal(np.asarray(x),np.asarray(y))

class TextTextures(unittest.TestCase):
    def test_textures_match_full_canvas_layers(self):
        styles=[{'text':'Hola\nmundo','subtitle':'Sub'},{'style':'instagram','text':'Escribe aquí\ntu gancho','box':True},
                {'style':'sticker','text':'Uno dos\ntres'},{'text':'Borde','x':-40,'y':10},{'text':'Centro','align':'center','x':1900,'y':1070}]
        p=project.new(width=320,height=180,fps=30)
        p['graphics']=[dict(id=f't{i}',type='title',start=0,length=60,motionLength=50,props=dict(enter=.3,**style)) for i,style in enumerate(styles)]
        p['captions']=[dict(id='c',text='Dos líneas\nde subtítulo',start=5,length=40)]
        p=project.validate(p)
        self.assertEqual([graphics.sprite((320,180),json.dumps(g['props'],sort_keys=True)) is not None for g in p['graphics']],[True,True,True,False,False])   # the last two cross the edge
        rng=np.random.default_rng(3)
        for f in (5,12,47,55):
            base=Image.fromarray(rng.integers(0,255,(180,320,3),dtype=np.uint8))
            fast=graphics.composite(base,p,f)
            with patch.object(graphics,'sprite',lambda *_:None):slow=graphics.composite(base,p,f)
            np.testing.assert_array_equal(np.asarray(fast),np.asarray(slow),err_msg=f'frame {f}')

if __name__=='__main__':unittest.main()
