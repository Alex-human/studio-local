import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import graphics, project, preview, render


class TextPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='studio-text-preview-');self.root=Path(self.temp.name)
        self.source=self.root/'source.mp4';self.source.write_bytes(b'immutable media fixture')
        self.p=project.new(width=1080,height=1920,fps=30)
        self.p['assets']=[dict(id='v',path=str(self.source),name='Video',fps=30,audio=False,duration=40)]
        self.p['clips']=[dict(id='c',asset='v',length=1009)]
    def tearDown(self):self.temp.cleanup()
    def title(self,id='g',**props):
        return dict(id=id,type='title',start=0,length=120,props={'text':'Una palabra','x':960,'y':1500,'size':92,**props})
    def image(self,id='image'):
        path=self.root/f'{id}.png';Image.new('RGB',(100,80),'blue').save(path)
        self.p['assets'].append(dict(id=id,path=str(path),name=id,width=100,height=80))
        return dict(id=f'g-{id}',type='image',start=0,length=120,props={'asset':id,'animation':'none'})
    def prepare(self):return preview.prepare(self.p,self.root,native_images=True,native_text=True)
    def fake_render(self,p,folder,**kwargs):
        path=folder/'rendered.mp4';path.write_bytes(b'render fixture');return {'path':str(path)}
    def fake_audio(self,p,folder,**kwargs):
        path=folder/'audio.wav';path.write_bytes(b'audio fixture');return path

    def test_93_titles_prepare_without_video_or_audio_render_and_leave_sources_unchanged(self):
        self.p['graphics']=[self.title(str(i),text=f'Palabra {i}') for i in range(93)]
        self.p['graphics'][0]['props'].update(style='instagram',text='Escribe aquí\ntu gancho')
        for g in self.p['graphics'][1:]:g['keyframes']={'opacity':[{'frame':0,'value':0},{'frame':8,'value':1}]}
        before=copy.deepcopy(self.p)
        with patch.object(render,'render',side_effect=AssertionError('unexpected video render')),patch.object(render,'render_audio',side_effect=AssertionError('unexpected mix')):
            cold=self.prepare();warm=self.prepare()
        self.assertEqual(cold['renderedFrames'],0);self.assertEqual(cold['directFrames'],1009)
        self.assertEqual(len(cold['images']),93);self.assertEqual(cold['mediaKey'],warm['mediaKey'])
        self.assertEqual(self.p,before);self.assertEqual(self.source.read_bytes(),b'immutable media fixture')
        self.assertTrue(all(Path(g['path']).stat().st_size<200_000 for g in cold['images']))

    def test_text_edit_hide_delete_and_captions_keep_base_media(self):
        self.p['graphics']=[self.title()];self.p['captions']=[dict(id='caption',start=0,length=120,text='Subtítulo')]
        first=self.prepare();base_key=preview.visual_key(self.p,True,True)
        self.p['graphics'][0]['props']['text']='Corregido';edited=self.prepare()
        self.p['graphics'][0]['hidden']=True;hidden=self.prepare()
        self.p['graphics']=[];self.p['captions'][0]['text']='Otra palabra';deleted=self.prepare()
        self.assertEqual({p['mediaKey'] for p in (first,edited,hidden,deleted)},{first['mediaKey']})
        self.assertEqual(len({p['key'] for p in (first,edited,hidden,deleted)}),4)
        self.assertEqual(preview.visual_key(self.p,True,True),base_key)
        cut=preview.window(self.p,0,60,True,True)
        self.assertEqual(cut['graphics'],[]);self.assertEqual(cut['captions'],[])

    def test_timing_and_opacity_remain_in_plan_not_baked_into_sprite(self):
        g=self.title();g.update(offset=41,motionLength=300,start=20)
        g['keyframes']={'opacity':[{'frame':0,'value':0},{'frame':90,'value':1}]};self.p['graphics']=[g]
        initial=self.prepare()['images'][0]
        self.assertEqual((initial['start'],initial['offset'],initial['motionLength']),(20,41,300))
        self.assertEqual(initial['keyframes'],g['keyframes'])
        self.assertEqual(initial['props'],dict(enter=.45,opacity=1))
        g['props'].update(opacity=.2,enter=1.8);g['keyframes']['opacity'][1]['value']=.7
        edited=self.prepare()['images'][0]
        self.assertEqual(initial['path'],edited['path']);self.assertNotEqual(initial['props'],edited['props'])
        self.assertNotEqual(initial['keyframes'],edited['keyframes'])
        g['keyframes']['opacity'].reverse()
        self.assertEqual(self.prepare()['images'][0]['keyframes'],edited['keyframes'])
        with patch.object(graphics,'text_sprite',side_effect=AssertionError('warm cache rerasterized')):self.prepare()

    def test_all_graphics_keep_order_and_captions_follow_them(self):
        a=self.image('a');b=self.image('b');self.p['graphics']=[self.title('first'),a,self.title('second',text='Segunda'),b]
        self.p['captions']=[dict(id='caption',start=0,length=60,text='Al final')]
        layers=self.prepare()['images']
        self.assertEqual([g.get('kind','image') for g in layers],['text','image','text','image','text'])
        self.assertEqual(layers[1]['path'],self.p['assets'][1]['path'])
        self.assertEqual(layers[3]['path'],self.p['assets'][2]['path'])
        self.assertEqual(layers[-1]['props'],{'animation':'none'})

    def test_unsupported_graphics_keep_complete_canonical_stack(self):
        for unsupported in [dict(type='lower_third',props={'text':'Lower third'}),
                            dict(type='title',keyframes={'x':[{'frame':0,'value':100}]},props={'text':'Moving'}),
                            dict(type='image',keyframes={'opacity':[{'frame':0,'value':1}]},props={'asset':'image'})]:
            with self.subTest(type=unsupported['type']):
                self.p['graphics']=[self.image() if not any(a['id']=='image' for a in self.p['assets']) else dict(id='image-g',type='image',start=0,length=120,props={'asset':'image'}),self.title()]
                self.p['graphics'].append(dict(id='unsupported',start=0,length=120,**unsupported))
                self.assertEqual(preview.native_modes(self.p,True,True),(False,False))
                self.assertEqual(len(preview.window(self.p,0,30,True,True)['graphics']),3)
                with patch.object(render,'render',side_effect=self.fake_render),patch.object(render,'render_audio',side_effect=self.fake_audio):plan=self.prepare()
                self.assertEqual(plan['images'],[]);self.assertGreater(plan['renderedFrames']+plan['cachedFrames'],0)

    def test_old_host_retains_rendered_titles_and_legacy_image_mode(self):
        self.p['graphics']=[self.title(),self.image()]
        self.assertTrue(any(r['cached'] for r in preview.regions(self.p,True)))
        self.assertEqual(len(preview.window(self.p,0,30,True)['graphics']),1)
        with patch.object(render,'render',side_effect=self.fake_render):plan=preview.prepare(self.p,self.root,native_images=True)
        self.assertEqual(len(plan['images']),1);self.assertNotIn('kind',plan['images'][0])
        self.assertGreater(plan['renderedFrames'],0)

    def test_static_title_sprite_matches_prior_canonical_rgba_pixels(self):
        size=(960,1706);w,h=size;sc=w/1920
        for props in [dict(text='Esta palabra',x=960.3,y=2600.7,size=92.8,weight=620),
                      dict(text='Título\nmúltiple',subtitle='Subtítulo morado',color='#eedddd',accent='#aa33ff'),
                      dict(text='Escribe aquí\ntu gancho',style='instagram',x=960,y=1000,size=108)]:
            with self.subTest(props=props):
                expected=Image.new('RGBA',size);d=ImageDraw.Draw(expected)
                x=float(props.get('x',960))*sc;y=float(props.get('y',540))*sc
                content=props['text'];font_size=float(props.get('size',72))*sc;color=props.get('color','#ffffff');accent=props.get('accent','#75b8ff')
                if props.get('style')=='instagram':graphics.instagram_hook(d,content,x,y,font_size,w*.86,color,accent)
                else:
                    weight=props.get('weight',580);font_size=graphics.fit_text(content,w*.86,font_size,weight)
                    shadow=Image.new('RGBA',size);graphics.text(ImageDraw.Draw(shadow),(x,y+3*sc),content,font_size,(0,0,0,220),weight=weight)
                    expected=Image.alpha_composite(expected,shadow.filter(ImageFilter.GaussianBlur(6*sc)));d=ImageDraw.Draw(expected)
                    graphics.text(d,(x,y),content,font_size,color,weight=weight)
                    if props.get('subtitle'):graphics.text(d,(x,y+font_size*.9),props['subtitle'],font_size*.43,accent)
                sprite,rect=graphics.text_sprite(size,props);actual=Image.new('RGBA',size);actual.alpha_composite(sprite,tuple(rect[:2]))
                np.testing.assert_array_equal(np.array(expected),np.array(actual))
                np.testing.assert_array_equal(np.array(expected),np.array(graphics.title_layer(size,props)))

    def test_caption_rgba_pixels_match_original_pass(self):
        size=(960,1706);w,h=size;sc=w/1920;content='Primera línea\nSegunda línea\nÚltima'
        expected=Image.new('RGBA',size);d=ImageDraw.Draw(expected);lines=content.split('\n')[:3]
        for i,line in enumerate(lines):
            font_size=graphics.fit_text(line,w*.85,48*sc);y=h*.88+(i-(len(lines)-1))*font_size*1.3
            d.text((w/2,y),line,font=graphics.font(font_size),fill='white',anchor='mm',stroke_width=max(1,int(2*sc)),stroke_fill=(0,0,0,190))
        sprite,rect=graphics.text_sprite(size,caption=content);actual=Image.new('RGBA',size);actual.alpha_composite(sprite,tuple(rect[:2]))
        np.testing.assert_array_equal(np.array(expected),np.array(actual))
        np.testing.assert_array_equal(np.array(expected),np.array(graphics.caption_layer(size,content)))

    def test_title_rest_outside_canvas_keeps_glyphs_for_entrance(self):
        props=dict(text='Visible al entrar',style='instagram',x=960,y=-20,size=48)
        sprite,rect=graphics.text_sprite((960,1706),props)
        self.assertLess(rect[1],0);self.assertIsNotNone(sprite.getbbox())
        actual=Image.new('RGBA',(960,1706));actual.alpha_composite(sprite,(rect[0],rect[1]+17))
        self.assertIsNotNone(actual.getbbox())


if __name__=='__main__':unittest.main()
