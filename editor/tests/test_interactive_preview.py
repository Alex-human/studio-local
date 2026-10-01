import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import graphics,preview,project,render


class InteractivePreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'video.mp4';self.source.write_bytes(b'video fixture')
        self.png=self.root/'motion.png';Image.new('RGBA',(100,80),'blue').save(self.png)
        self.p=project.new(width=1080,height=1920,fps=30)
        self.p['assets']=[dict(id='v',kind='video',path=str(self.source),name='Video',fps=30,duration=120,width=1080,height=1920,audio=True),
                          dict(id='i',kind='image',path=str(self.png),name='Motion',width=100,height=80,audio=False)]
        self.p['clips']=[dict(id='c',asset='v',length=3000,**{'in':0})]
    def tearDown(self):self.temp.cleanup()
    def prepare(self,frame=0):return preview.prepare(self.p,self.root,True,True,True,True,True,frame)
    def fake_render(self,p,folder,**kwargs):
        path=Path(folder)/'video.mp4';path.write_bytes(b'render fixture');return {'path':str(path)}
    def fake_audio(self,p,folder,**kwargs):
        path=Path(folder)/'mix.wav';path.write_bytes(b'audio fixture');return path
    def motion(self,id='g'):
        return dict(id=id,type='image',start=0,length=3000,props=dict(asset='i',animation='none'),
                    keyframes={k:[dict(frame=0,value=a),dict(frame=3000,value=b)] for k,a,b in
                               [('x',700,1200),('y',500,1600),('width',400,800),('rotation',-25,25),('opacity',0,1),('cropRight',0,.8)]})

    def test_motion_stack_never_renders_video_or_audio_and_edits_reuse_media(self):
        self.p['graphics']=[self.motion(str(i)) for i in range(24)]
        self.p['graphics'].insert(1,dict(id='title',type='title',start=0,length=3000,props=dict(text='Palabra')))
        self.p['captions']=[dict(id='word',start=0,length=3000,text='Subtítulo')]
        original=copy.deepcopy(self.p)
        with patch.object(render,'render',side_effect=AssertionError('whole video render')),patch.object(render,'render_audio',side_effect=AssertionError('whole audio render')):
            first=self.prepare();self.p['graphics'][0]['keyframes']['cropRight'][1]['value']=.5;second=self.prepare()
        self.assertEqual(first['renderedFrames'],0);self.assertEqual(first['directFrames'],3000)
        self.assertEqual(first['mediaKey'],second['mediaKey']);self.assertNotEqual(first['key'],second['key'])
        self.assertEqual([x.get('kind','image') for x in first['images']][:3],['image','text','image'])
        self.assertEqual(first['images'][-1]['kind'],'text')
        self.assertEqual(first['images'][0]['keyframes'],original['graphics'][0]['keyframes'])
        self.assertEqual(self.source.read_bytes(),b'video fixture')

    def test_every_non_native_template_renders_only_half_second_with_full_stack(self):
        for typ in ('lower_third','stat','cards','progress','channel_intro','title'):
            with self.subTest(template=typ):
                special=dict(id='special',type=typ,start=60,length=2940,props=dict(text='Prueba'))
                if typ=='title':special['keyframes']={'x':[dict(frame=0,value=1000)]}
                self.p['graphics']=[self.motion(),special]
                self.p['captions']=[dict(id='word',start=0,length=3000,text='Encima')]
                with patch.object(render,'render',side_effect=self.fake_render) as baked,patch.object(render,'render_audio',side_effect=AssertionError('visual effect forced full mix')):
                    plan=self.prepare(1000)
                self.assertEqual((plan['windowStart'],plan['windowEnd'],plan['frames']),(1000,1015,15))
                self.assertEqual(plan['images'],[]);self.assertEqual(plan['videoOverlays'],[])
                self.assertEqual(sum(project.duration(call.args[0]) for call in baked.call_args_list),15)
                portion=baked.call_args.args[0]
                self.assertEqual([g['id'] for g in portion['graphics']],['g','special'])
                self.assertEqual(portion['graphics'][0]['offset'],1000)
                self.assertEqual(portion['graphics'][1]['offset'],940)
                self.assertEqual(portion['captions'][0]['text'],'Encima')
                self.assertEqual(plan['audioSources'][0]['source'],1000/30)

    def test_direct_stretch_before_and_after_effect_is_not_baked(self):
        self.p['graphics']=[dict(id='special',type='cards',start=90,length=60,props={})]
        with patch.object(render,'render',side_effect=AssertionError('unexpected render')):
            before=self.prepare();after=self.prepare(150)
        self.assertEqual((before['windowStart'],before['windowEnd']),(0,90))
        self.assertEqual((after['windowStart'],after['windowEnd']),(150,3000))
        self.assertEqual(after['clips'][0]['sourceIn'],150)

    def test_window_preserves_source_motion_audio_fades_and_revision(self):
        self.p['graphics']=[self.motion()]
        self.p['clips'][0].update(fadeIn=120,fadeOut=60)
        self.p['audio']=[dict(id='a',asset='v',role='music',start=10,length=1000,**{'in':20},speed=1.5,fadeIn=60,fadeOut=120)]
        original=copy.deepcopy(self.p);part=preview.playback_window(self.p,80,100)
        self.assertEqual(part['graphics'][0]['offset'],80)
        self.assertEqual(part['graphics'][0]['motionLength'],3000)
        self.assertEqual(part['audio'][0]['in'],125)
        self.assertEqual((part['audio'][0]['fadeOffset'],part['audio'][0]['fadeLength']),(70,1000))
        self.assertEqual(part['revision'],self.p['revision']);self.assertEqual(self.p,original)
        voice=preview.audio_layers(part)[0]
        self.assertEqual((voice['fadeIn'],voice['fadeOut'],voice['fadeOffset'],voice['fadeLength']),(4,2,80/30,100))
        self.assertEqual((voice['deClickOffset'],voice['deClickLength']),(80/30,100))

    def test_ducking_uses_original_continuous_mix_and_seeks_to_window(self):
        self.p['ducking']=True
        self.p['graphics']=[dict(id='special',type='stat',start=0,length=3000,props={})]
        with patch.object(render,'render',side_effect=self.fake_render),patch.object(render,'render_audio',side_effect=self.fake_audio) as mix:
            first=self.prepare(150);second=self.prepare(165)
        self.assertEqual(project.duration(mix.call_args.args[0]),3000);self.assertEqual(mix.call_count,1)
        self.assertEqual(first['audio'],second['audio']);self.assertEqual(first['audioSourceIn'],5)

    def test_overlay_audio_changes_invalidate_mix_but_not_picture(self):
        self.p['graphics']=[dict(id='overlay',type='video',asset='v',start=0,length=30,**{'in':12},props=dict(animation='none',style='clean'))]
        first=preview.audible_key(self.p,True);visual=preview.visual_key(self.p)
        self.p['graphics'][0]['volumeDb']=-12
        self.assertNotEqual(preview.audible_key(self.p,True),first);self.assertEqual(preview.visual_key(self.p),visual)

    def test_native_base_gates_retiming_and_frame_rate_but_accepts_geometry(self):
        c=self.p['clips'][0];a=self.p['assets'][0]
        c.update(zoom=1.2,zoomEnd=1.5,x=.3,color=dict(exposure=.2))
        self.assertTrue(preview.direct(c,a,self.p,True))
        for changes in ({'speed':1.5},{'in':5.25}):
            self.assertFalse(preview.direct({**c,**changes},a,self.p,True))
        self.assertFalse(preview.direct(c,{**a,'fps':24},self.p,True))

    def test_unknown_video_codec_fallback_is_bounded_and_preserves_every_layer(self):
        self.p['graphics']=[self.motion()]
        with patch.object(render,'render',side_effect=self.fake_render) as baked:
            plan=preview.prepare(self.p,self.root,True,True,True,True,True,60,False,True)
        self.assertTrue(plan['rasterFallback']);self.assertEqual(plan['frames'],15)
        self.assertEqual(plan['images'],[]);self.assertEqual(plan['renderedFrames'],15)
        self.assertEqual(baked.call_args.args[0]['graphics'][0]['id'],'g')

    def test_overlay_tail_does_not_extend_native_composition(self):
        self.p['graphics']=[dict(id='g',type='video',asset='v',start=2990,length=30,props={}),dict(id='after',type='video',asset='v',start=3000,length=30,props={})]
        layers=preview.video_layers(self.p)
        self.assertEqual(len(layers),1);self.assertEqual(layers[0]['length'],10)


if __name__=='__main__':unittest.main()
