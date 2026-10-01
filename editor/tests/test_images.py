import base64, copy, io, sys, tempfile, unittest, wave
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import editor, graphics, project, render, sounds

class ImageWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='studio-images-');self.root=Path(self.temp.name)
        self.p=project.new(width=320,height=180,fps=30)
        video=self.root/'source.mp4';render.run(['-v','error','-f','lavfi','-i','color=black:s=320x180:r=30:d=2','-an','-c:v','libx264',video])
        asset=render.probe(video);self.p['assets']=[asset];self.p['clips']=[dict(id='v',asset=asset['id'],length=60,**{'in':0},muted=True)]
        self.path=self.root/'Proyecto.studio';project.save(self.path,self.p)
        pixels=np.zeros((40,80,3),np.uint8);pixels[:,:40,0]=255;pixels[:,40:,2]=255
        buf=io.BytesIO();Image.fromarray(pixels).save(buf,format='PNG');self.png=base64.b64encode(buf.getvalue()).decode()
    def tearDown(self):self.temp.cleanup()
    def paste(self,start=0):
        return editor.dispatch(dict(action='importImageData',project=str(self.path),png=self.png,start=start))['project']
    def test_clipboard_is_deduplicated_and_undo_preserves_media(self):
        p=self.paste(15);g=p['graphics'][0];self.assertEqual(g['start'],15);self.assertTrue(g['props']['sound'])
        self.assertEqual(g['props']['soundDb'],-18)
        image_path=Path(p['assets'][-1]['path']);original=image_path.read_bytes()
        p=self.paste(30);self.assertEqual(len(p['assets']),2);self.assertEqual(len(p['graphics']),2)
        editor.dispatch(dict(action='undo',project=str(self.path),revision=p['revision']))
        self.assertEqual(len(project.load(self.path)['graphics']),1);self.assertEqual(image_path.read_bytes(),original)
    def test_default_photo_sound_is_a_short_subtle_click(self):
        path=self.root/'photo-click.wav';duration=sounds.motion_sound(path,'pop',.48)
        with wave.open(str(path),'rb') as source:
            samples=np.frombuffer(source.readframes(source.getnframes()),'<i2').reshape(-1,2)/32768
            self.assertEqual((source.getframerate(),source.getnchannels()),(48000,2))
        self.assertAlmostEqual(duration,.48,places=3)
        self.assertGreater(float(np.max(np.abs(samples[:4800]))),.08)
        self.assertLess(float(np.max(np.abs(samples))),.32)
        self.assertEqual(float(np.max(np.abs(samples[6240:]))),0)
        variants=[]
        for animation in set(project.IMAGE_ANIMATIONS)-{'none'}:
            candidate=self.root/(animation+'.wav');sounds.motion_sound(candidate,animation,.48)
            variants.append(candidate.read_bytes())
        self.assertTrue(all(value==variants[0] for value in variants))
    def test_crop_uses_original_pixels_and_validates_bounds(self):
        p=self.paste();g=p['graphics'][0];g['props'].update(cropLeft=.5,width=500,style='clean',animation='none')
        im=graphics.composite(Image.new('RGB',(320,180)),p,15)
        self.assertEqual(im.getpixel((160,90)),(0,0,255))
        bad=copy.deepcopy(p);bad['graphics'][0]['props']['cropRight']=.6
        with self.assertRaises(ValueError):project.validate(bad)
        p=project.apply(p,[dict(op='duration',kind='graphics',id=g['id'],length=25)])
        self.assertEqual(p['graphics'][0]['length'],25)
    def test_motion_decelerates_and_finishes_exactly(self):
        p={'animation':'from-left','enter':.48}
        self.assertAlmostEqual(graphics.image_motion(p,.24)[0],-180/16)
        self.assertEqual(graphics.image_motion(p,.48),(0,0,1,1))
        for a in project.IMAGE_ANIMATIONS:
            self.assertEqual(graphics.image_motion({'animation':a},2),(0,0,1,1))
    def audio(self,p,name):
        folder=self.root/name;folder.mkdir();wav=render.render_audio(p,folder)
        return np.frombuffer(render.run(['-v','error','-i',wav,'-f','f32le','-ac','2','-']),np.float32).reshape(-1,2)
    def test_linked_sound_moves_hides_and_does_not_restart_after_cut(self):
        p=self.paste(15);g=p['graphics'][0];g['props']['animation']='from-left'
        audio=self.audio(p,'first');self.assertLess(np.abs(audio[:24000]).max(),.00001);self.assertGreater(np.abs(audio[24000:40000]).max(),.03)
        np.testing.assert_allclose(audio[24000:40000,0],audio[24000:40000,1],atol=1e-7)
        moved=project.apply(p,[dict(op='move',kind='graphics',id=g['id'],start=30)])
        shifted=self.audio(moved,'moved');self.assertLess(np.abs(shifted[:48000]).max(),.00001)
        hidden=copy.deepcopy(p);hidden['graphics'][0]['hidden']=True
        self.assertLess(np.abs(self.audio(hidden,'hidden')).max(),.00001)
        cut=project.apply(p,[dict(op='cutRange',start=15,end=21)])
        self.assertEqual(cut['graphics'][0]['offset'],6)
        sliced=self.audio(cut,'cut');np.testing.assert_allclose(sliced[24000:33000],audio[33600:42600],atol=1e-5)
    def test_all_image_animations_render_and_invalid_paste_is_atomic(self):
        p=self.paste()
        for animation in project.IMAGE_ANIMATIONS:
            p['graphics'][0]['props']['animation']=animation
            for frame in (0,3,15):self.assertEqual(graphics.composite(Image.new('RGB',(320,180)),p,frame).size,(320,180))
        before=self.path.read_bytes()
        with self.assertRaises(Exception):editor.dispatch(dict(action='importImageData',project=str(self.path),png='not an image'))
        self.assertEqual(before,self.path.read_bytes())

if __name__=='__main__':unittest.main()
