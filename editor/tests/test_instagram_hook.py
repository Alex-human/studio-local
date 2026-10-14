import copy, sys, unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import graphics, project

class InstagramHookTests(unittest.TestCase):
    def setUp(self):
        self.p=project.new(width=1080,height=1920,fps=30)
        self.p['assets']=[dict(id='v',path='/example.mp4',name='Example',duration=4,audio=False)]
        self.p['clips']=[dict(id='c',asset='v',length=120,**{'in':0})]
        self.p['graphics']=[dict(id='hook',type='title',start=0,length=120,offset=15,motionLength=150,props=dict(text='Diego, pero ¿no es malo\ndepender de anuncios?',style='instagram',x=960,y=1000,size=108,color='white',accent='#B28CFF'))]
    def pixels(self,p,frame):return np.asarray(graphics.composite(Image.new('RGB',(540,960)),p,frame))
    def test_hook_is_visible_at_both_ends_and_absent_after_shortening(self):
        first=self.pixels(self.p,0)
        self.assertTrue(np.array_equal(first,self.pixels(self.p,119)))
        self.assertGreater(np.count_nonzero(first),1000)
        shortened=project.apply(self.p,[dict(op='duration',kind='graphics',id='hook',length=60)])
        self.assertEqual(np.count_nonzero(self.pixels(shortened,61)),0)
    def test_native_text_edit_changes_text_and_underline_together(self):
        before=self.pixels(self.p,30)
        props={**self.p['graphics'][0]['props'],'text':'Ahora\nmenos'}
        changed=project.apply(self.p,[dict(op='set',kind='graphics',id='hook',values={'props':props})])
        after=self.pixels(changed,30)
        def purple_width(a):
            y,x=np.where((a[:,:,0]>80)&(a[:,:,2]>a[:,:,0]+20)&(a[:,:,0]>a[:,:,1]+10))
            return x.max()-x.min()
        self.assertLess(purple_width(after),purple_width(before))
        self.assertEqual(self.p['graphics'][0]['props']['text'],'Diego, pero ¿no es malo\ndepender de anuncios?')
    def test_multiline_and_automatic_wrap_preserve_words_and_fit(self):
        for content in ['Diego, pero ¿no es malo depender de anuncios?','Escribe aquí\ntu gancho','Una explicación más larga con suficientes palabras para comprobar que se adapta al ancho disponible']:
            lines,size=graphics.instagram_hook_layout(content,880,65)
            self.assertEqual(' '.join(lines),' '.join(content.split()))
            for i,line in enumerate(lines):self.assertLessEqual(graphics.font(size,600 if i==len(lines)-1 else 400,i==len(lines)-1).getlength(line),880)
    def test_plain_title_remains_unchanged(self):
        p=copy.deepcopy(self.p);p['graphics'][0]['props']={'text':'Normal','x':960,'y':540}
        implicit=self.pixels(p,30);p['graphics'][0]['props']['style']='plain'
        self.assertTrue(np.array_equal(implicit,self.pixels(p,30)))
    def test_black_card_wraps_both_lines_and_matches_native_sprite(self):
        size=(1080,1920);props={**self.p['graphics'][0]['props'],'text':'El vago método de duplicar tu negocio según Hormozi:','box':True,'y':590}
        layer=np.asarray(graphics.title_layer(size,props))
        card=np.argwhere((layer[:,:,3]==255)&(layer[:,:,:3].max(2)==0))
        white=np.argwhere((layer[:,:,3]==255)&(layer[:,:,:3].min(2)>200))
        self.assertGreater(len(card),20000)
        for axis in (0,1):
            self.assertLess(card[:,axis].min(),white[:,axis].min());self.assertGreater(card[:,axis].max(),white[:,axis].max())
        rows,_,_,_,_=graphics.instagram_hook_parts(graphics.ImageDraw.Draw(Image.new('L',(1,1))),props['text'],540,332,61,1080*.86,True)
        self.assertEqual(len(rows),2)
        sprite,rect=graphics.text_sprite(size,props);actual=Image.new('RGBA',size);actual.alpha_composite(sprite,tuple(rect[:2]))
        np.testing.assert_array_equal(layer,np.asarray(actual))
    def test_sticker_hook_cards_each_line_and_matches_native_sprite(self):
        size=(1080,1920);sc=1080/1920;props=dict(text='La pregunta que más cierres en llamada me ha dado',style='sticker',x=960,y=590,size=141,color='#ffffff')
        p=copy.deepcopy(self.p);p['graphics'][0]['props']=props;project.validate(p)
        _,rows,bands,_=graphics.sticker_hook_parts(props['text'],960*sc,590*sc,141*sc,1080*.86)
        self.assertEqual(' '.join(line for line,_ in rows),props['text'])
        self.assertEqual(len(bands),2)
        layer=np.asarray(graphics.title_layer(size,props))
        card=(layer[:,:,3]==255)&(layer[:,:,:3].max(2)==0);white=np.argwhere((layer[:,:,3]==255)&(layer[:,:,:3].min(2)>200))
        for (left,top,right,bottom),(_,base) in zip(bands,rows):  # every line sits inside its own card
            ink=white[(white[:,0]>base-40)&(white[:,0]<=base)]
            self.assertTrue(card[round(base)-20,round(left)+12] and card[round(base)-20,round(right)-12])
            self.assertGreater(ink[:,1].min(),left);self.assertLess(ink[:,1].max(),right)
        self.assertFalse(card[round(bands[1][3])-20,round(bands[0][0])+12])  # the shorter line's card is narrower
        for props in (props,{**props,'size':160,'y':1000}):  # the second lands outline vertices on subsample boundaries
            sprite,rect=graphics.text_sprite(size,props);actual=Image.new('RGBA',size);actual.alpha_composite(sprite,tuple(rect[:2]))
            np.testing.assert_array_equal(np.asarray(graphics.title_layer(size,props)),np.asarray(actual))
    def test_weight_and_style_validation(self):
        for values in [{'weight':999},{'style':'unknown'},{'box':'sí'}]:
            p=copy.deepcopy(self.p);p['graphics'][0]['props'].update(values)
            with self.assertRaises(ValueError):project.validate(p)

if __name__=='__main__':unittest.main()
