import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import project, render

def luma(path,width=320,height=180):
    raw=render.run(['-v','error','-i',path,'-f','rawvideo','-pix_fmt','gray','-'])
    return np.frombuffer(raw,np.uint8).reshape(-1,height,width).astype(np.int32)

class GpuExport(unittest.TestCase):
    """The GPU exporter covers only what the playback compositor and the sprites reproduce, and matches paint()."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='studio-gpu-');root=cls.root=Path(cls.temp.name)
        render.run(['-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=4','-c:v','libx264','-pix_fmt','yuv420p',root/'cam.mp4'])
        render.run(['-v','error','-f','lavfi','-i','testsrc=size=320x180:rate=30:duration=2','-c:v','libx264','-pix_fmt','yuv420p',root/'scene.mp4'])
        Image.new('RGB',(160,90),(200,40,40)).save(root/'card.png')
        p=project.new(width=320,height=180,fps=30)
        video=lambda i,f,d:dict(id=i,kind='video',path=str(root/f),name=f,duration=d,width=320,height=180,fps=30,audio=False)
        p['assets']=[video('cam','cam.mp4',4),video('scene','scene.mp4',2),dict(id='card',kind='image',path=str(root/'card.png'),name='card.png',width=160,height=90)]
        p['clips']=[dict(id='a',asset='cam',length=60,zoom=1.1,zoomEnd=1.25,**{'in':0}),dict(id='b',asset='cam',length=30,**{'in':70})]
        fade={'opacity':[{'frame':0,'value':0},{'frame':6,'value':1},{'frame':24,'value':1},{'frame':30,'value':0}]}
        p['graphics']=[dict(id='o',type='video',asset='scene',start=20,length=30,muted=True,keyframes=fade,
                            props={'width':1920,'x':960,'y':540,'style':'clean','animation':'none','opacity':1},**{'in':0}),
                       dict(id='t',type='title',start=0,length=90,props={'text':'Encima','enter':.3}),
                       dict(id='i',type='image',start=50,length=40,props={'asset':'card','width':500,'x':1400,'y':300,'animation':'pop','enter':.3,'style':'photo'})]
        p['captions']=[dict(id='c',text='Subtítulo',start=10,length=60)]
        cls.p=project.validate(p)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_plan_covers_native_layers_only(self):
        with tempfile.TemporaryDirectory() as folder:
            plan=render.export_plan(self.p,Path(folder))
            self.assertEqual((plan['frames'],len(plan['placements']),sum(c['length'] for c in plan['clips'])),(90,90,90))
            self.assertEqual([o['id'] for o in plan['videoOverlays']],['o'])
            self.assertEqual(len(plan['placements'][55])//4,3)   # title, image and caption
            lower=dict(id='l',type='lower_third',start=0,length=10,props={})
            fast=[dict(self.p['clips'][0],speed=2,length=30),self.p['clips'][1]]
            for change in ({'graphics':[*self.p['graphics'],lower]},{'clips':fast}):
                self.assertIsNone(render.export_plan(project.validate({**self.p,**change}),Path(folder)))
    def test_export_matches_painter(self):
        if not render.EXPORTER.is_file():self.skipTest('Exportador GPU sin compilar')
        gpu=render.render(self.p,self.root/'gpu',with_audio=False,gpu=True)
        if gpu['engine']!='gpu':self.skipTest('VideoToolbox no está disponible en este entorno')
        with patch.dict(render.ENCODER,{'master':['-c:v','libx264','-preset','ultrafast','-qp','0']}):
            ref=render.render(self.p,self.root/'ref',with_audio=False)
        a,b=luma(gpu['path']),luma(ref['path'])
        self.assertEqual(len(a),len(b))
        psnr=[10*np.log10(255**2/max(1e-9,((x-y)**2).mean())) for x,y in zip(a,b)]
        self.assertGreater(min(psnr),30,f'peor fotograma {int(np.argmin(psnr))}')
    def test_only_4k_previews_go_through_the_gpu(self):
        self.assertEqual(render.render(self.p,self.root/'preview-small',preview=True,with_audio=False,gpu=True)['engine'],'cpu')
    def test_4k_preview_goes_through_the_gpu_at_preview_size_and_matches_painter(self):
        if not render.EXPORTER.is_file():self.skipTest('Exportador GPU sin compilar')
        p=project.validate({**self.p,'width':3840,'height':2160})
        gpu=render.render(p,self.root/'preview-gpu',preview=True,with_audio=False,gpu=True)
        if gpu['engine']!='gpu':self.skipTest('VideoToolbox no está disponible en este entorno')
        self.assertEqual((gpu['width'],gpu['height'],gpu['preview']),(960,540,True))
        with patch.dict(render.ENCODER,{'preview':['-c:v','libx264','-preset','ultrafast','-qp','0']}):
            ref=render.render(p,self.root/'preview-ref',preview=True,with_audio=False)
        self.assertEqual(ref['engine'],'cpu')
        a,b=luma(gpu['path'],960,540),luma(ref['path'],960,540)
        self.assertEqual(len(a),len(b))
        psnr=[10*np.log10(255**2/max(1e-9,((x-y)**2).mean())) for x,y in zip(a,b)]
        self.assertGreater(min(psnr),30,f'peor fotograma {int(np.argmin(psnr))}')
    def test_failed_exporter_falls_back_to_painter(self):
        script=self.root/'falla.sh';script.write_text('#!/bin/sh\nexit 3\n');script.chmod(0o755)
        with patch.object(render,'EXPORTER',script):out=render.render(self.p,self.root/'fallback',with_audio=False,gpu=True)
        self.assertEqual((out['engine'],out['frames']),('cpu',90))

if __name__=='__main__':unittest.main()
