import copy
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import editor, graphics, project, render, sync

class OverlayModel(unittest.TestCase):
    def setUp(self):
        self.p=project.new(width=160,height=90,fps=30)
        self.p['assets']=[dict(id='base',kind='video',duration=30,audio=False,path='/base.mp4',name='Base'),dict(id='over',kind='video',duration=8,audio=True,path='/over.mp4',name='Over')]
        self.p['clips']=[dict(id='first',asset='base',length=60,**{'in':0}),dict(id='second',asset='base',length=90,**{'in':90}),dict(id='third',asset='base',length=150,**{'in':300})]
        self.p['graphics']=[dict(id='title',type='title',start=0,length=300,props={'text':'Title'})]
        self.p['captions']=[dict(id='word',text='Word',start=100,length=10)]
    def add(self,start=30):
        out=project.apply(self.p,[dict(op='addOverlay',asset='over',start=start)])
        item=out['graphics'][-1];item['id']='overlay'
        return out,item
    def clock(self,p):
        result=[]
        for g in p['graphics']:
            if g['type']=='video':result.extend((g['start']+f,g.get('in',0)+f*g.get('speed',1),g.get('offset',0)+f,g.get('fadeOffset',0)+f) for f in range(g['length']))
        return result
    def test_add_defaults_duration_and_separate_link_track(self):
        out,item=self.add(250)
        self.assertEqual(item['length'],50);self.assertTrue(item['muted']);self.assertEqual(item['props']['animation'],'none')
        linked=project.apply(out,[dict(op='linkTrack',track='overlays',linked=False)])
        self.assertFalse(project.linked(linked,'graphics',linked['graphics'][-1]));self.assertTrue(project.linked(linked,'graphics',linked['graphics'][0]))
        self.assertEqual(project.duration(out),300);self.assertEqual(out['clips'],self.p['clips'])
        with self.assertRaises(ValueError):project.apply(self.p,[dict(op='addOverlay',asset='over',start=300)])
        empty=copy.deepcopy(self.p);empty['clips']=[]
        with self.assertRaises(ValueError):project.apply(empty,[dict(op='addOverlay',asset='over',start=0)])
    def test_duration_frames_survive_ntsc_float_rounding(self):
        # 2100 fotogramas a 60000/1001 duran 35.035 s; 35.035*59.94… = 2099.9999…, que int() dejaba en 2099
        p=project.new(width=160,height=90,fps=60000/1001);p['assets']=[dict(id='base',kind='video',duration=60,audio=False,path='/b.mp4',name='B'),dict(id='over',kind='video',duration=35.035,audio=False,path='/o.mp4',name='O'),dict(id='new',kind='video',duration=35.035,audio=False,path='/n.mp4',name='N')]
        p['clips']=[dict(id='c',asset='base',length=3000,**{'in':0})]
        out=project.apply(p,[dict(op='addOverlay',asset='over',start=0)]);self.assertEqual(out['graphics'][-1]['length'],2100)
        project.replace_overlay(out,out['graphics'][-1]['id'],'new');self.assertEqual(out['graphics'][-1]['length'],2100)
    def test_prune_assets_keeps_every_referenced_medium(self):
        out,_=self.add()
        out['assets']+=[dict(id='img',kind='image',path='/i.png',name='I',width=10,height=10),dict(id='music',kind='audio',duration=30,audio=True,path='/m.wav',name='M'),dict(id='old',kind='video',duration=8,audio=False,path='/gone.mp4',name='Old')]
        out['graphics'].append(dict(id='pic',type='image',start=0,length=30,props={'asset':'img'}))
        out['audio']=[dict(id='song',asset='music',role='music',start=0,length=90,**{'in':0})]
        pruned=project.apply(out,[dict(op='pruneAssets')])
        self.assertEqual(sorted(a['id'] for a in pruned['assets']),['base','img','music','over'])
    def test_split_join_and_cut_keep_source_motion_and_fade_clocks(self):
        out,item=self.add();item.update(length=100,**{'in':20},speed=1.5,fadeIn=40,fadeOut=30,fadeOffset=7,fadeLength=200,offset=11,motionLength=220)
        split=project.apply(out,[dict(op='splitAt',frame=80)])
        self.assertEqual(self.clock(out),self.clock(split));self.assertEqual(project.join_counts(split)['overlays'],1)
        joined=project.apply(split,[dict(op='joinTrack',track='overlays')]);self.assertEqual(self.clock(out),self.clock(joined))
        cut=project.apply(out,[dict(op='cutRange',start=65,end=85)])
        expected=[(f if f<65 else f-20,*rest) for f,*rest in self.clock(out) if not 65<=f<85]
        self.assertEqual(self.clock(cut),expected)
        self.assertEqual(project.join_counts(cut)['overlays'],0)
    def test_trim_duplicate_and_handles_never_exceed_media(self):
        out,item=self.add();item.update(length=100,**{'in':20},speed=2)
        trimmed=project.apply(out,[dict(op='trim',kind='graphics',id='overlay',head=5,tail=10)])
        g=trimmed['graphics'][-1];self.assertEqual((g['start'],g['in'],g['length'],g['offset'],g['fadeOffset']),(35,30,85,5,5))
        duplicated=project.apply(trimmed,[dict(op='duplicate',kind='graphics',id='overlay',newId='copy')]);self.assertEqual(duplicated['graphics'][-1]['in'],30)
        with self.assertRaises(ValueError):project.apply(out,[dict(op='duration',kind='graphics',id='overlay',length=120)])
        with self.assertRaises(ValueError):project.apply(out,[dict(op='resizeEdge',kind='graphics',id='overlay',edge='start',delta=-11)])
        with self.assertRaises(ValueError):project.apply(out,[dict(op='source',id='overlay',**{'in':80})])
        changed=project.apply(out,[dict(op='source',id='overlay',**{'in':10})]);self.assertEqual(changed['graphics'][-1]['in'],10)
        with self.assertRaises(ValueError):project.apply(out,[dict(op='set',kind='graphics',id='overlay',values={'keepTogether':True})])
    def test_extending_primary_cannot_stretch_overlay_past_source(self):
        out,item=self.add(30);item.update(length=30,**{'in':210})
        restored=project.apply(out,[dict(op='resizeEdge',kind='clips',id='first',edge='end',delta=20)])
        self.assertEqual(restored['graphics'][-1]['length'],30)
        # An overlay crossing the inserted boundary has a finite source and stays finite.
        item.update(length=100,**{'in':0})
        restored=project.apply(out,[dict(op='resizeEdge',kind='clips',id='first',edge='end',delta=20)])
        self.assertEqual(restored['graphics'][-1]['length'],100)
    def test_promote_replaces_only_interval_preserves_duration_and_source(self):
        out,item=self.add(30);item.update(length=150,**{'in':20},speed=1.2,muted=False,volumeDb=-12)
        before=copy.deepcopy(out);promoted=project.apply(out,[dict(op='promoteOverlay',id='overlay')])
        self.assertEqual(project.duration(promoted),300)
        self.assertEqual([c['length'] for c in promoted['clips']],[30,150,120])
        self.assertEqual(promoted['clips'][2]['in'],330)
        moved=promoted['clips'][1];self.assertEqual((moved['id'],moved['asset'],moved['in'],moved['speed'],moved['volumeDb'],moved['muted']),('overlay','over',20,1.2,-12,False))
        self.assertEqual(promoted['graphics'],before['graphics'][:-1]);self.assertEqual(promoted['captions'],before['captions']);self.assertEqual(out,before)
        # Inside one main clip, both surviving pieces have unique IDs.
        out,item=self.add(170);item['length']=30
        promoted=project.apply(out,[dict(op='promoteOverlay',id='overlay')]);self.assertEqual(len({c['id'] for c in promoted['clips']}),len(promoted['clips']))
    def test_replacement_and_concurrent_history_are_atomic(self):
        out,item=self.add();out['assets'].append(dict(id='short',kind='video',duration=1,audio=False,path='/short.mp4',name='Short'))
        item.update(offset=9,**{'in':90},speed=2);item['props']['rotation']=17
        project.replace_overlay(out,'overlay','short');item=out['graphics'][-1]
        self.assertEqual((item['id'],item['start'],item['length'],item['in'],item['offset'],item['props']['rotation']),('overlay',30,15,0,9,17))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'Test.studio';project.save(path,out)
            current=editor.dispatch(dict(action='ops',project=str(path),revision=out['revision'],ops=[dict(op='mixer',values={'music':-3})]))['project']
            for op in [dict(op='promoteOverlay',id='overlay'),dict(op='addOverlay',asset='over',start=0),dict(op='source',id='overlay',**{'in':0})]:
                with self.assertRaises(sync.Conflict):editor.dispatch(dict(action='ops',project=str(path),revision=out['revision'],ops=[op]))
            self.assertEqual(project.load(path),current)
            promoted=editor.dispatch(dict(action='ops',project=str(path),revision=current['revision'],ops=[dict(op='promoteOverlay',id='overlay')]))['project']
            undone=editor.dispatch(dict(action='undo',project=str(path),revision=promoted['revision']))['project']
            undone['revision']=current['revision'];self.assertEqual(undone,current)

class OverlayRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='studio-overlays-');cls.root=Path(cls.temp.name)
        cls.base=cls.root/'base.mp4';cls.overlay=cls.root/'overlay.mp4'
        render.run(['-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=2','-an','-c:v','libx264','-pix_fmt','yuv420p',cls.base])
        render.run(['-v','error','-f','lavfi','-i','testsrc2=s=80x40:r=24:d=2','-f','lavfi','-i','sine=frequency=750:sample_rate=48000:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',cls.overlay])
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.p=project.new(width=160,height=90,fps=30)
        self.p['assets']=[render.probe(self.base),render.probe(self.overlay)]
        self.p['clips']=[dict(id='base',asset=self.p['assets'][0]['id'],length=60,**{'in':0},muted=True)]
        self.p=project.apply(self.p,[dict(op='addOverlay',asset=self.p['assets'][1]['id'],start=10)])
        self.g=self.p['graphics'][-1];self.g.update(length=30,**{'in':5},speed=1.5);self.g['props'].update(width=960,x=960,y=540)
    def test_frame_cache_streaming_and_export_match_source_clocks(self):
        work=self.root/project.uid();work.mkdir()
        decoder=render.OverlayDecoders(self.p,work)
        try:
            for frame in range(60):
                streams=decoder.frames(frame)
                if not 10<=frame<40:self.assertFalse(streams);continue
                exact=render.overlay_frame(self.p,self.g,frame,work)
                np.testing.assert_array_equal(np.asarray(streams[self.g['id']]),np.asarray(exact))
        finally:decoder.close()
        self.assertFalse(decoder.active)
        result=render.frame(self.p,20,work,width=160)
        with Image.open(result['path']) as still:self.assertGreater(np.asarray(still)[30:60,50:110,0].mean(),40)
        with patch.object(render,'run',side_effect=AssertionError('decode should be cached')):
            self.g['props']['x']=900;render.frame(self.p,20,work,width=160)
        exported=render.render(self.p,work,with_audio=False)
        self.assertEqual(exported['frames'],60)
    def test_video_painter_order_and_hard_cut_geometry(self):
        solid=Image.new('RGBA',(80,40),'red');self.g['props'].update(width=1920,opacity=1,animation='none')
        for frame in (10,39):
            image=graphics.composite(Image.new('RGB',(160,90),'blue'),self.p,frame,{self.g['id']:solid})
            self.assertEqual(image.getpixel((80,45)),(255,0,0))
            # Rectangle has no rounded clean-image border or shadow.
            self.assertEqual(image.getpixel((0,5)),(255,0,0));self.assertEqual(image.getpixel((0,4)),(0,0,255))
        self.p['graphics'].insert(0,dict(id='label',type='title',start=0,length=60,props={'text':'A','size':500,'x':960,'y':540,'enter':.01}))
        image=graphics.composite(Image.new('RGB',(160,90),'blue'),self.p,20,{self.g['id']:solid})
        self.assertGreater(np.asarray(image)[20:65,60:100,1].max(),200)
        with self.assertRaises(ValueError):graphics.composite(Image.new('RGB',(160,90)),self.p,20)
    def test_audio_hidden_muted_speed_and_source_specs(self):
        work=self.root/project.uid();work.mkdir()
        self.assertEqual(render.audio_specs(self.p,work),[])
        self.g.update(muted=False,volumeDb=-8,fadeIn=6,fadeOut=9,fadeOffset=3,fadeLength=45)
        specs=render.audio_specs(self.p,work);self.assertEqual(len(specs),1)
        self.assertEqual((specs[0]['source'],specs[0]['speed'],specs[0]['role'],specs[0]['db']),(5/30,1.5,'voice',-8))
        wav=render.render_audio(self.p,work)
        samples=np.frombuffer(render.run(['-v','error','-i',wav,'-f','f32le','-ac','2','-']),np.float32)
        self.assertGreater(np.abs(samples).max(),.01)
        self.g['hidden']=True;self.assertEqual(render.audio_specs(self.p,work),[])
    def test_import_and_replace_keep_originals_and_undo(self):
        work=self.root/project.uid();work.mkdir();path=work/'Test.studio';project.save(path,self.p)
        original=self.overlay.read_bytes();before=len(self.p['clips'])
        out=editor.dispatch(dict(action='import',overlay=True,project=str(path),revision=self.p['revision'],path=str(self.overlay),start=50))['project']
        self.assertEqual(len(out['clips']),before);self.assertEqual(out['graphics'][-1]['length'],10)
        id=out['graphics'][-1]['id']
        replaced=editor.dispatch(dict(action='import',overlay=True,replaceOverlay=id,project=str(path),revision=out['revision'],path=str(self.base)))['project']
        self.assertEqual(replaced['graphics'][-1]['id'],id);self.assertEqual(replaced['graphics'][-1]['asset'],self.p['assets'][0]['id'])
        self.assertEqual(self.overlay.read_bytes(),original)
        editor.dispatch(dict(action='undo',project=str(path),revision=replaced['revision']))
        self.assertEqual(project.load(path)['graphics'],out['graphics'])
        with self.assertRaises(sync.Conflict):editor.dispatch(dict(action='import',overlay=True,replaceOverlay=id,project=str(path),revision=0,path=str(self.base)))

class OverlayTimestampParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='studio-overlay-time-');cls.root=Path(cls.temp.name);cls.assets={}
        for fps in (24,30):
            file=cls.root/f'source-{fps}.mp4'
            encoder=subprocess.Popen([str(render.FF),'-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','240x160','-r',str(fps),'-i','-','-an','-c:v','libx264','-crf','0','-pix_fmt','yuv420p',str(file)],stdin=subprocess.PIPE)
            try:
                for frame in range(fps*10):
                    pixels=np.empty((160,240,3),np.uint8)
                    for bit in range(7):pixels[:,round(bit*240/7):round((bit+1)*240/7)]=235 if frame&(1<<bit) else 16
                    encoder.stdin.write(pixels.tobytes())
                encoder.stdin.close()
                if encoder.wait():raise ValueError('Cannot generate frame identity fixture')
            finally:render.stop(encoder)
            cls.assets[fps]=render.probe(file)
        variable=cls.root/'variable.mp4'
        render.run(['-v','error','-i',cls.assets[30]['path'],'-vf',"select='not(mod(n,3))+not(mod(n,5))'",'-fps_mode','vfr','-c:v','libx264','-crf','0',variable])
        cls.assets['vfr']=render.probe(variable)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def identity(self,image):
        pixels=np.asarray(image);height,width=pixels.shape[:2]
        return sum(1<<bit for bit in range(7) if pixels[height//2,round((bit+.5)*width/7),:3].mean()>128)
    def test_exact_source_frame_identity_across_rates_speeds_and_vfr(self):
        for source_fps,project_fps in ((30,30),(24,30),(30,60),('vfr',30)):
            asset=self.assets[source_fps];p=project.new(width=240,height=160,fps=project_fps);p['assets']=[asset]
            for speed in (.25,.5,.75,1,1.25,1.5,2,4):
                item=dict(id='overlay',type='video',asset=asset['id'],start=0,length=60,**{'in':5.25},speed=speed,props={'animation':'none','style':'clean'})
                p['graphics']=[item];work=self.root/f'{source_fps}-{project_fps}-{speed}';work.mkdir();decoder=render.OverlayDecoders(p,work)
                try:
                    for frame in range(60):
                        time=(5.25+frame*speed)/project_fps
                        source_index=math.floor(time*(30 if source_fps=='vfr' else source_fps)+1e-7)
                        if source_fps=='vfr':source_index=max(i for i in range(source_index+1) if i%3==0 or i%5==0)
                        expected=source_index%128
                        with self.subTest(source_fps=source_fps,project_fps=project_fps,speed=speed,frame=frame):
                            self.assertEqual(self.identity(decoder.frames(frame)['overlay']),expected)
                            if frame in (0,1,5,14,20,50):self.assertEqual(self.identity(render.overlay_frame(p,item,frame,work)),expected)
                finally:decoder.close()
    def test_empty_edit_at_file_start_holds_first_picture(self):
        # Some encoders open the file with an empty edit: the first picture starts 20 ms late.
        delayed=self.root/'delayed.mp4'
        render.run(['-v','error','-y','-i',self.assets[30]['path'],'-c','copy','-output_ts_offset','0.02',delayed])
        asset=render.probe(delayed);p=project.new(width=240,height=160,fps=30);p['assets']=[asset]
        item=dict(id='overlay',type='video',asset=asset['id'],start=10,length=20,**{'in':0},speed=1,props={'animation':'none','style':'clean'})
        p['graphics']=[item];work=self.root/'delayed';work.mkdir();decoder=render.OverlayDecoders(p,work)
        try:
            for frame in range(10,30):
                # Frame n is shown from n/30 + 20 ms: output frame k still shows k-1; frame 0 holds the first.
                expected=max(0,frame-11)
                with self.subTest(frame=frame):
                    self.assertEqual(self.identity(decoder.frames(frame)['overlay']),expected)
                    if frame in (10,11,12,20):self.assertEqual(self.identity(render.overlay_frame(p,item,frame,work)),expected)
        finally:decoder.close()

if __name__=='__main__':unittest.main()
