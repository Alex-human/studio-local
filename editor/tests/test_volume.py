import copy,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import project,render,preview
from PIL import Image

class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.tone=self.root/'tone.wav'
        render.run(['-v','error','-f','lavfi','-i','sine=frequency=660:duration=1',self.tone])
        self.p=project.new(width=64,height=64,fps=30)
        self.p['assets']=[dict(id='tone',name='Tone',path=str(self.tone),audio=True,kind='video',duration=1,fps=30)]
        self.p['clips']=[dict(id='video',asset='tone',length=30,**{'in':0},muted=True)]
    def tearDown(self):self.temp.cleanup()
    def mix(self,p):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            result=render.render_audio(p,Path(folder))
            return np.frombuffer(render.run(['-v','error','-i',result,'-f','f32le','-']),np.float32)
    def test_percent_levels_match_native_and_export_for_every_role(self):
        for kind,role in [('clips','voice'),('audio','voice'),('audio','music'),('audio','sfx')]:
            p=copy.deepcopy(self.p)
            if kind=='clips':c=p['clips'][0];c['muted']=False
            else:
                c=dict(id='sound',asset='tone',role=role,start=0,length=30,**{'in':0});p['audio']=[c]
            baseline=None
            for percent in [100,50,25,0]:
                c['volumeDb']=20*np.log10(percent/100) if percent else -60
                actual=self.mix(p);sources=preview.audio_layers(p)
                source=next(s for s in sources if s['id']==c['id']);self.assertAlmostEqual(source['volume'],percent/100)
                if percent==100:baseline=actual
                np.testing.assert_allclose(actual,baseline*percent/100,atol=3e-7)
                if percent==0:self.assertEqual(np.count_nonzero(actual),0)
            # Zero at either stage remains silent even with positive legacy gain at the other.
            c['volumeDb']=-60;p['mixer'][role]=18;self.assertEqual(np.count_nonzero(self.mix(p)),0)
            c['volumeDb']=18;p['mixer'][role]=-60;self.assertEqual(np.count_nonzero(self.mix(p)),0)
            self.assertEqual(next(s for s in preview.audio_layers(p) if s['id']==c['id'])['volume'],0)
    def test_muted_sources_remain_available_for_live_unmute(self):
        p=copy.deepcopy(self.p)
        p['assets'][0]['audio']=True
        p['clips'][0].update(muted=True,volumeDb=0)
        p['audio']=[dict(id='mutedMusic',asset=p['assets'][0]['id'],role='music',start=0,length=30,**{'in':0},volumeDb=0,muted=True)]
        muted={s['id']:s for s in preview.audio_layers(p)}
        self.assertIn(p['clips'][0]['id'],muted)
        self.assertEqual(muted['mutedMusic']['volume'],0)
        self.assertEqual(muted[p['clips'][0]['id']]['volume'],0)
        p['clips'][0]['muted']=False;p['audio'][0]['muted']=False
        audible={s['id']:s for s in preview.audio_layers(p)}
        self.assertEqual(muted.keys(),audible.keys())
        self.assertEqual(audible['mutedMusic']['volume'],1)

    def test_image_sound_zero_and_effects_bus_zero_are_silent(self):
        image=self.root/'image.png';Image.new('RGB',(64,64),'blue').save(image)
        self.p['assets'].append(dict(id='image',path=str(image),name='Image',kind='image',audio=False,width=64,height=64))
        self.p['graphics']=[dict(id='imageSound',type='image',start=0,length=30,props={'asset':'image','sound':True,'soundDb':-60})]
        self.p['mixer']['sfx']=6
        cache=self.root/'cache';cache.mkdir()
        self.assertEqual(preview.image_cues(self.p,cache)[0]['volume'],0)
        self.assertEqual(np.count_nonzero(self.mix(self.p)),0)
        self.p['graphics'][0]['props']['soundDb']=0;self.p['mixer']['sfx']=-60
        self.assertEqual(preview.image_cues(self.p,cache)[0]['volume'],0)
        self.assertEqual(np.count_nonzero(self.mix(self.p)),0)

if __name__=='__main__':unittest.main()
