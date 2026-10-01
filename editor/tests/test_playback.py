import copy
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import project,render,preview
from PIL import Image

class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='studio-playback-');self.root=Path(self.temp.name)
        self.p=project.new(width=64,height=64,fps=30)
        self.p['assets']=[dict(id='v',path=str(self.root/'v.mp4'),name='Video',kind='video',audio=False,fps=30,duration=20)]
        (self.root/'v.mp4').write_bytes(b'metadata fixture')
        self.p['clips']=[dict(id='c',asset='v',length=360,**{'in':0},muted=True)]
    def tearDown(self):self.temp.cleanup()
    def tone(self,name,freq,duration=4,rate=48000,compressed=False):
        path=self.root/(name+('.m4a' if compressed else '.wav'))
        render.run(['-v','error','-f','lavfi','-i',f'sine=frequency={freq}:sample_rate={rate}:duration={duration}',path])
        self.p['assets'].append(dict(id=name,path=str(path),name=name,kind='audio',audio=True,duration=duration))
        return path
    def mix(self,p,name):
        folder=self.root/name;folder.mkdir();path=render.render_audio(p,folder)
        return np.frombuffer(render.run(['-v','error','-i',path,'-f','f32le','-']),np.float32).reshape(-1,2)
    def test_future_clips_cannot_contaminate_prefix(self):
        self.tone('first',440);self.tone('future',607,1)
        self.p['audio']=[dict(id='first',asset='first',role='voice',start=0,length=120,**{'in':0})]
        expected=self.mix(self.p,'early')[:3*48000]
        for i in range(17):self.p['audio'].append(dict(id=f'late{i}',asset='future',role='voice',start=180+i*3,length=8,**{'in':0}))
        actual=self.mix(self.p,'full')[:3*48000]
        np.testing.assert_array_equal(expected,actual)
    def test_batched_compressed_overlap_equals_independent_decode(self):
        self.tone('aac',741,4,44100,True);self.tone('wav',330)
        for i in range(10):self.p['audio'].append(dict(id=str(i),asset='aac' if i%2 else 'wav',role='sfx',start=30+i,length=20,**{'in':7},volumeDb=-18,speed=1.25))
        actual=self.mix(self.p,'batch')
        expected=np.zeros_like(actual)
        for i,item in enumerate(self.p['audio']):
            one=copy.deepcopy(self.p);one['audio']=[item];expected+=self.mix(one,'single'+str(i))
        # PCM24 quantization happens per single file but only once for the batch.
        self.assertLess(float(np.max(np.abs(actual-expected))),2e-6)
    def test_ducking_keeps_voice_and_reduces_music(self):
        self.tone('v',440,4);self.tone('m',1000,4)
        self.p['clips'][0]['length']=120
        self.p['audio']=[dict(id='v',asset='v',role='voice',start=30,length=60,**{'in':0},volumeDb=10),dict(id='m',asset='m',role='music',start=0,length=120,**{'in':0},volumeDb=-6)]
        plain=self.mix(self.p,'plain');self.p['ducking']=True;ducked=self.mix(self.p,'ducked')
        def amplitude(samples,freq,start):
            segment=samples[int(start*48000):int((start+.25)*48000),0]
            return abs(np.sum(segment*np.exp(-2j*np.pi*freq*np.arange(len(segment))/48000)))
        self.assertAlmostEqual(amplitude(ducked,440,1.5)/amplitude(plain,440,1.5),1,places=3)
        self.assertLess(amplitude(ducked,1000,1.5)/amplitude(plain,1000,1.5),.5)
        np.testing.assert_array_equal(plain[:24000],ducked[:24000])
    def test_image_changes_only_visual_cache_without_sound(self):
        a=preview.audible_key(self.p);before=preview.visual_key(self.p)
        self.p['graphics']=[dict(id='g',type='title',start=60,length=30,props={'text':'Hola'})]
        self.assertEqual(preview.audible_key(self.p),a);self.assertNotEqual(preview.visual_key(self.p),before)
        regions=preview.regions(self.p)
        self.assertEqual([(r['start'],r['end'],r['cached']) for r in regions],[(0,60,False),(60,90,True),(90,360,False)])
        self.assertEqual(sum(r['end']-r['start'] for r in regions),360)

    def test_native_image_is_overlay_and_short_cue_not_full_mix(self):
        image=self.root/'image.png';Image.new('RGB',(120,80),'blue').save(image)
        self.p['assets'].append(dict(id='image',path=str(image),name='Image',kind='image',audio=False,width=120,height=80,duration=0,fps=0))
        base_audio=preview.audible_key(self.p,True)
        self.p['graphics']=[dict(id='g',type='image',start=60,length=120,props={
            'asset':'image','width':760,'x':960,'y':540,'animation':'pop','enter':.48,'style':'photo','sound':True,'soundDb':-12})]
        self.assertEqual(preview.audible_key(self.p,True),base_audio)
        self.assertNotEqual(preview.audible_key(self.p,False),base_audio)
        self.assertTrue(any(r['cached'] for r in preview.regions(self.p,False)))
        self.assertFalse(any(r['cached'] for r in preview.regions(self.p,True)))
        self.assertEqual(preview.image_layers(self.p)[0]['path'],str(image))
        cache=self.root/'playback';cache.mkdir()
        cues=preview.image_cues(self.p,cache)
        self.assertEqual(len(cues),1);self.assertTrue(Path(cues[0]['path']).is_file())
        self.assertLess(Path(cues[0]['path']).stat().st_size,500_000)

    def test_native_cut_plan_never_renders_or_builds_full_mix(self):
        before=preview.prepare(self.p,self.root/'before',True)
        cut=project.apply(self.p,[dict(op='cutRange',start=60,end=90)])
        after=preview.prepare(cut,self.root/'after',True)
        self.assertEqual((before['renderedFrames'],after['renderedFrames']),(0,0))
        self.assertIsNone(before['audio']);self.assertIsNone(after['audio'])
        self.assertEqual((before['frames'],after['frames']),(360,330))
    def test_visual_window_preserves_motion_phase_and_source(self):
        self.p['clips'][0].update(zoom=1,zoomEnd=1.3)
        self.p['graphics']=[dict(id='g',type='title',start=20,length=120,props={'text':'Hola'})]
        cut=preview.window(self.p,60,90)
        self.assertEqual(cut['clips'][0]['in'],60)
        self.assertEqual(cut['clips'][0]['motionOffset'],60)
        self.assertEqual(cut['clips'][0]['motionLength'],360)
        self.assertEqual(cut['graphics'][0]['offset'],40)
        self.assertEqual(cut['graphics'][0]['start'],0)
        self.assertEqual(project.duration(cut),30)
    def test_audio_tail_is_bounded_by_timeline(self):
        self.p['fps']=60000/1001;self.p['clips'][0]['length']=101
        self.tone('a',660,4,44100,True)
        self.p['audio']=[dict(id='a',asset='a',role='music',start=20,length=300,**{'in':1})]
        values=self.mix(self.p,'tail')
        self.assertEqual(len(values),round(101/self.p['fps']*48000))
        self.assertEqual(float(np.max(np.abs(values[:round(20/self.p['fps']*48000)]))),0)

if __name__=='__main__':unittest.main()
