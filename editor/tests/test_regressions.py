import copy
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import project,editor,render,graphics

class Regressions(unittest.TestCase):
    def test_slow_zoom_moves_smoothly_without_pixel_jumps(self):
        with tempfile.TemporaryDirectory() as tmp:
            y,x=np.mgrid[0:360,0:640];Image.fromarray(((np.sin(x/7.0)+np.sin(y/5.0))*60+128).astype('uint8')).save(f'{tmp}/s.png')
            p=project.new(width=320,height=180,fps=30);c=dict(id='c',asset='a',length=60,zoom=1.4,zoomEnd=1.44,x=.5,y=.8,**{'in':0})
            raw=subprocess.run([str(render.FF),'-v','error','-loop','1','-t','2','-i',f'{tmp}/s.png','-vf',render.video_filter(c,p,320,180)+',format=gray','-frames:v','60','-f','rawvideo','-'],capture_output=True,check=True).stdout
        rows=np.frombuffer(raw,np.uint8).reshape(-1,180,320).astype(float).mean(axis=2)
        def paso(a,b):   # desplazamiento vertical entre dos perfiles, en cuartos de píxel
            grid=np.arange(20,160);return min((np.mean((a[grid]-np.interp(grid+s/4,np.arange(180),b))**2),s/4) for s in range(-8,9))[1]
        self.assertLess(max(abs(paso(rows[i],rows[i+1])) for i in range(len(rows)-1)),0.6)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='studio-regression-');self.root=Path(self.temp.name)
        self.p=project.new(width=64,height=64,fps=30)
    def tearDown(self):self.temp.cleanup()
    def media(self,fps=24,count=40):
        path=self.root/'frames.mkv'
        pixels=np.zeros((count,64,64,3),dtype=np.uint8)
        for i in range(count):pixels[i,:,:,0]=i*5
        subprocess.run([str(render.FF),'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','64x64','-r',str(fps),'-i','-','-c:v','ffv1',str(path)],input=pixels.tobytes(),check=True)
        a=render.probe(path);self.p['assets']=[a];self.p['clips']=[dict(id='clip',asset=a['id'],**{'in':5},length=25)]
        return path
    def samples(self,clip,path):
        raw=render.run(['-v','error',*render.video_input(clip,self.p,path),'-vf',render.video_filter(clip,self.p,64,64),'-frames:v',clip['length'],'-an','-f','rawvideo','-pix_fmt','rgb24','-'])
        return np.frombuffer(raw,np.uint8).reshape(-1,64,64,3)[:,0,0,0]
    def test_split_and_still_preserve_mixed_fps_grid(self):
        path=self.media();whole=self.samples(self.p['clips'][0],path)
        cut=project.apply(self.p,[{'op':'split','kind':'clips','id':'clip','at':7}])
        split=np.concatenate([self.samples(c,path) for c in cut['clips']])
        np.testing.assert_array_equal(whole,split)
        self.assertEqual(len(whole),25)
        for n in (0,3,4,7,8,9,24):
            out=render.frame(self.p,n,self.root/'frames')
            actual=np.asarray(Image.open(out['path']))[0,0,0]
            self.assertLessEqual(abs(int(actual)-int(whole[n])),2)
    def test_import_ten_frames(self):
        path=self.root/'ten.mp4'
        render.run(['-v','error','-f','lavfi','-i','color=red:s=64x64:r=30','-frames:v','10','-c:v','libx264',path])
        pp=self.root/'test.studio';project.save(pp,self.p)
        out=editor.dispatch({'action':'import','project':str(pp),'path':str(path)})
        self.assertEqual(out['project']['clips'][0]['length'],10)
    def test_invalid_graphics_and_ids_rejected(self):
        for change in ({'props':{'size':'bad'}},{'keyframes':{'x':[{'frame':1,'value':'bad'}]}}):
            p=copy.deepcopy(self.p);p['graphics']=[dict(id='g',type='title',start=0,length=30,**change)]
            with self.assertRaises(ValueError):project.validate(p)
        for bad in ('/tmp/out','../out','',None):
            p=copy.deepcopy(self.p);p['id']=bad
            with self.assertRaises(ValueError):project.validate(p)
        graphics.glass_panel(10,10,0)
    def test_undo_requires_current_revision(self):
        path=self.root/'test.studio';project.save(path,self.p)
        editor.dispatch({'action':'ops','project':str(path),'ops':[{'op':'mixer','values':{'music':-3}}]})
        with self.assertRaises(ValueError):editor.dispatch({'action':'undo','project':str(path),'revision':0})
        self.assertEqual(project.load(path)['mixer']['music'],-3)
    def test_project_picker_excludes_history_snapshots(self):
        path=self.root/'test.studio';project.save(path,self.p)
        editor.dispatch({'action':'ops','project':str(path),'ops':[{'op':'mixer','values':{'music':-3}}]})
        with patch.object(editor,'PROJECTS',self.root):
            items=editor.dispatch({'action':'list'})['projects']
        self.assertEqual([item['path'] for item in items],[str(path)])
        self.assertEqual((items[0]['width'],items[0]['height'],items[0]['fps']),(64,64,30))
        self.assertEqual(items[0]['modified'],path.stat().st_mtime)
    def test_home_thumbnail_uses_timeline_and_invalidates_without_revision(self):
        self.media();path=self.root/'test.studio';project.save(path,self.p)
        before=path.read_bytes();stamp=path.stat().st_mtime_ns
        result=editor.dispatch({'action':'thumbnail','project':str(path)})
        with Image.open(result['path']) as image:
            self.assertLessEqual(image.width,480);self.assertLessEqual(image.height,270)
            first=np.asarray(image).copy()
        self.assertEqual(path.read_bytes(),before);self.assertEqual(path.stat().st_mtime_ns,stamp)
        with patch.object(render,'frame',side_effect=AssertionError('Cached poster rendered again')):
            self.assertEqual(editor.dispatch({'action':'thumbnail','project':str(path)}),result)
        self.p['clips'][0]['in']=0;project.save(path,self.p)
        updated=editor.dispatch({'action':'thumbnail','project':str(path)})
        self.assertNotEqual(updated['path'],result['path'])
        with Image.open(updated['path']) as image:self.assertGreater(np.abs(np.asarray(image).astype(float)-first).mean(),1)
    def test_empty_and_missing_media_do_not_break_home_thumbnail(self):
        path=self.root/'test.studio';project.save(path,self.p)
        self.assertIsNone(editor.dispatch({'action':'thumbnail','project':str(path)})['path'])
        self.media();project.save(path,self.p)
        with patch.object(render,'frame',side_effect=ValueError('Missing source')):
            result=editor.dispatch({'action':'thumbnail','project':str(path)})
        self.assertIsNone(result['path']);self.assertIn('miniatura',result['error'])
    def test_cache_retains_imported_sources_and_history(self):
        f=self.root/'frames/frame-0-0.jpg';f.parent.mkdir();f.write_bytes(b'X'*10000)
        other=self.root/'frames/frame-0-1.jpg';other.write_bytes(b'X'*10000)
        p=copy.deepcopy(self.p);p['assets']=[{'id':'source','path':str(f),'name':'Still','kind':'image'}]
        project.save(self.root/'test.studio',p)
        render.maintain_cache(self.root,.000001)
        self.assertTrue(f.exists());self.assertFalse(other.exists())
    def test_encoder_failure_is_bounded(self):
        self.media();self.p['clips'][0]['length']=3
        tick=time.monotonic()
        with patch.object(graphics,'composite',side_effect=ValueError('synthetic drawing error')):
            with self.assertRaises(ValueError):render.render(self.p,self.root/'exports',preview=True)
        self.assertLess(time.monotonic()-tick,8)
        self.assertFalse(list((self.root/'exports').glob('.work-*')))
    def test_final_render_routes_to_exported_youtube_folder(self):
        path=self.root/'test.studio';project.save(path,self.p)
        destination=self.root/'Vídeos YouTube'/'Exportados'
        rendered={'path':str(destination/'Vídeo - r0 - test.mp4'),'bytes':1,'frames':0,'seconds':0}
        with patch.object(editor,'EXPORTS',destination),patch.object(render,'render',return_value=rendered) as call,patch.object(render,'maintain_cache',return_value={}):
            result=editor.dispatch({'action':'render','project':str(path)})
        self.assertEqual(Path(call.call_args.args[1]),destination)
        self.assertEqual(result['path'],rendered['path'])
    def test_music_gain_and_silence_candidates(self):
        music=self.root/'music.wav';voice=self.root/'voice.wav'
        render.run(['-v','error','-f','lavfi','-i','sine=frequency=600:sample_rate=48000:duration=2',music])
        render.run(['-v','error','-f','lavfi','-i','aevalsrc=if(between(t\\,0.5\\,1.2)\\,0\\,sin(2*PI*440*t)*0.2):s=48000:d=2',voice])
        self.p['assets']=[dict(id='v',path=str(voice),name='Voice',audio=True,duration=2),dict(id='m',path=str(music),name='Music',audio=True,duration=2)]
        self.p['clips']=[dict(id='c',asset='v',length=60,**{'in':0},muted=True)]
        self.p['audio']=[dict(id='a',asset='m',role='music',length=60,start=0,**{'in':0})]
        def rms(p,name):
            folder=self.root/name;folder.mkdir();out=render.render_audio(p,folder)
            raw=render.run(['-v','error','-i',out,'-ac','1','-f','f32le','-'])
            return float(np.sqrt(np.mean(np.frombuffer(raw,np.float32)**2)))
        before=rms(self.p,'before');self.p['mixer']['music']=-6
        after=rms(self.p,'after');self.assertAlmostEqual(20*np.log10(after/before),-6,places=3)
        self.p['clips'][0]['muted']=False
        pp=self.root/'test.studio';project.save(pp,self.p)
        result=editor.dispatch({'action':'analyze','project':str(pp)})
        self.assertTrue(result['candidates'])
        c=result['candidates'][0]
        self.assertGreaterEqual(c['start'],18);self.assertLessEqual(c['end'],32)

if __name__=='__main__':unittest.main()
