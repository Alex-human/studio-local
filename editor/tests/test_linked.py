import copy
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import project, editor, render

class LinkedTimeline(unittest.TestCase):
    def setUp(self):
        self.p=project.new(fps=30,width=64,height=64)
        self.p['assets']=[dict(id='source',name='Source',path='/source.mp4',duration=60,audio=False)]
        self.p['clips']=[dict(id='video',asset='source',length=300,**{'in':0},muted=True)]
        self.p['audio']=[dict(id=r,asset='source',role=r,start=0,length=300,**{'in':0},fadeIn=60,fadeOut=60) for r in project.ROLES]
        self.p['graphics']=[dict(id='g',type='image',start=60,length=180,props={'asset':'source','animation':'pop','sound':True})]
        self.p['captions']=[dict(id='c',text='Texto',start=120,length=90)]
    def source_map(self,p,kind,identity):
        out={};offset=0
        for item in p[kind]:
            start=offset if kind=='clips' else item['start']
            if kind=='clips':offset+=item['length']
            if identity and item.get('role',item.get('type'))!=identity:continue
            source=item.get('in',0) if kind in ('clips','audio') else item.get('offset',0)
            for f in range(item['length']):out[start+f]=source+f*item.get('speed',1)
        return out
    def test_split_linked_then_remove_keeps_all_clocks_and_independent_music(self):
        p=project.apply(self.p,[dict(op='linkTrack',track='music',linked=False),dict(op='splitAt',frame=150)])
        self.assertEqual([len([a for a in p['audio'] if a['role']==r]) for r in project.ROLES],[2,1,2])
        music=copy.deepcopy([a for a in p['audio'] if a['role']=='music'])
        before=self.p
        for start,end in [(120,180),(0,10),(270,300),(59,62),(149,151)]:
            cut=project.apply(p,[dict(op='cutRange',start=start,end=end)])
            self.assertEqual([a for a in cut['audio'] if a['role']=='music'],music)
            for kind,identity in [('clips',None),('audio','voice'),('audio','sfx'),('graphics','image')]:
                old=self.source_map(before,kind,identity)
                expected={t if t<start else t-(end-start):v for t,v in old.items() if not start<=t<end}
                self.assertEqual(self.source_map(cut,kind,identity),expected)
        self.assertEqual(self.p['revision'],0)
    def test_independent_item_survives_video_trim_and_delete(self):
        self.p['audio'][2]['linked']=False
        self.p['audio'][2]['start']=180;self.p['audio'][2]['length']=30
        self.p['graphics'][0]['linked']=False
        p=project.apply(self.p,[dict(op='splitAt',frame=90)])
        for operation in [dict(op='delete',kind='clips',id=p['clips'][0]['id']),dict(op='trim',kind='clips',id=p['clips'][1]['id'],head=10,tail=20)]:
            out=project.apply(p,[operation]);self.assertEqual(out['graphics'],self.p['graphics'])
            self.assertEqual(next(a for a in out['audio'] if a['id']=='sfx'),self.p['audio'][2])

    def test_dragging_video_edges_restores_real_source_and_linked_layers(self):
        cut=project.apply(self.p,[dict(op='linkTrack',track='music',linked=False),dict(op='cutRange',start=120,end=180)])
        music=copy.deepcopy([a for a in cut['audio'] if a['role']=='music'])
        left,right=cut['clips']
        restored_left=project.apply(cut,[dict(op='resizeEdge',kind='clips',id=left['id'],edge='end',delta=20)])
        self.assertEqual(project.duration(restored_left),260)
        self.assertEqual([(c['in'],c['length']) for c in restored_left['clips']],[(0,140),(180,120)])
        self.assertEqual([(a['start'],a['in'],a['length']) for a in restored_left['audio'] if a['role']=='voice'],[(0,0,140),(140,180,120)])
        self.assertEqual([a for a in restored_left['audio'] if a['role']=='music'],music)

        right=cut['clips'][1]
        restored_right=project.apply(cut,[dict(op='resizeEdge',kind='clips',id=right['id'],edge='start',delta=-15)])
        self.assertEqual(project.duration(restored_right),255)
        self.assertEqual([(c['in'],c['length']) for c in restored_right['clips']],[(0,120),(165,135)])
        self.assertEqual([(a['start'],a['in'],a['length']) for a in restored_right['audio'] if a['role']=='sfx'],[(0,0,120),(120,165,135)])
        self.assertEqual([a for a in restored_right['audio'] if a['role']=='music'],music)

    def test_dragging_edges_shrinks_with_ripple_and_stops_at_source_gap(self):
        cut=project.apply(self.p,[dict(op='cutRange',start=120,end=180)])
        left,right=cut['clips']
        shorter=project.apply(cut,[dict(op='resizeEdge',kind='clips',id=left['id'],edge='end',delta=-10)])
        self.assertEqual(project.duration(shorter),230)
        self.assertEqual([(c['in'],c['length']) for c in shorter['clips']],[(0,110),(180,120)])
        self.assertEqual([(a['start'],a['in'],a['length']) for a in shorter['audio'] if a['role']=='voice'],[(0,0,110),(110,180,120)])
        with self.assertRaisesRegex(ValueError,'No queda más material'):
            project.apply(cut,[dict(op='resizeEdge',kind='clips',id=left['id'],edge='end',delta=61)])

    def test_dragging_nonvideo_edges_changes_only_the_selected_element(self):
        original_audio=copy.deepcopy(self.p['audio'])
        image=project.apply(self.p,[dict(op='resizeEdge',kind='graphics',id='g',edge='start',delta=-30)])
        self.assertEqual((image['graphics'][0]['start'],image['graphics'][0]['length']),(30,210))
        self.assertEqual(image['graphics'][0]['motionLength'],210)
        self.assertEqual(project.duration(image),300)
        self.assertEqual(image['audio'],original_audio)
        image=project.apply(image,[dict(op='resizeEdge',kind='graphics',id='g',edge='end',delta=30)])
        self.assertEqual((image['graphics'][0]['start'],image['graphics'][0]['length']),(30,240))
        trimmed=project.apply(self.p,[dict(op='resizeEdge',kind='graphics',id='g',edge='start',delta=20)])
        restored=project.apply(trimmed,[dict(op='resizeEdge',kind='graphics',id='g',edge='start',delta=-10)])
        self.assertEqual((restored['graphics'][0]['start'],restored['graphics'][0]['length'],restored['graphics'][0]['offset'],restored['graphics'][0]['motionLength']),(70,170,10,180))

        caption=project.apply(self.p,[dict(op='resizeEdge',kind='captions',id='c',edge='start',delta=10)])
        self.assertEqual((caption['captions'][0]['start'],caption['captions'][0]['length']),(130,80))

        self.p['audio'][2].update(start=60,**{'in':90},length=120)
        audio=project.apply(self.p,[dict(op='resizeEdge',kind='audio',id='sfx',edge='start',delta=-30)])
        selected=next(a for a in audio['audio'] if a['id']=='sfx')
        self.assertEqual((selected['start'],selected['in'],selected['length']),(30,60,150))
        audio=project.apply(audio,[dict(op='resizeEdge',kind='audio',id='sfx',edge='end',delta=20)])
        selected=next(a for a in audio['audio'] if a['id']=='sfx')
        self.assertEqual((selected['start'],selected['in'],selected['length']),(30,60,170))
        self.assertEqual(project.duration(audio),300)
        with self.assertRaisesRegex(ValueError,'No queda más espacio'):
            project.apply(self.p,[dict(op='resizeEdge',kind='graphics',id='g',edge='start',delta=-61)])
    def test_track_defaults_inherit_and_relink_overrides_without_retiming(self):
        p=project.apply(self.p,[dict(op='linkTrack',track='music',linked=False)])
        extra=dict(id='m2',asset='source',role='music',start=150,length=60,**{'in':0})
        p=project.apply(p,[dict(op='add',kind='audio',item=extra),dict(op='set',kind='graphics',id='g',values={'linked':False})])
        self.assertFalse(project.linked(p,'audio',p['audio'][-1]))
        out=project.apply(p,[dict(op='linkTrack',track='all',linked=True)])
        self.assertTrue(all(project.linked(out,k,x) for k in ('clips','audio','graphics','captions') for x in out[k]))
        self.assertEqual(out['audio'],p['audio']);self.assertNotIn('linked',out['graphics'][0])
    def test_group_undo_redo_and_reopen_are_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.studio';project.save(path,self.p)
            p=editor.dispatch(dict(action='ops',project=str(path),revision=0,ops=[dict(op='linkTrack',track='music',linked=False)]))['project']
            previous=copy.deepcopy(p)
            p=editor.dispatch(dict(action='ops',project=str(path),revision=p['revision'],ops=[dict(op='splitAt',frame=90)]))['project']
            self.assertEqual(p['revision'],2)
            undone=editor.dispatch(dict(action='undo',project=str(path),revision=p['revision']))['project']
            for key in ('clips','audio','graphics','captions','syncTracks'):self.assertEqual(undone[key],previous[key])
            redone=editor.dispatch(dict(action='redo',project=str(path),revision=undone['revision']))['project']
            self.assertEqual(project.load(path),redone);self.assertEqual(redone['audio'],p['audio'])
    def test_speed_phase_and_invalid_link_are_validated(self):
        self.p['audio'][0]['speed']=2
        p=project.apply(self.p,[dict(op='cutRange',start=30,end=60)])
        right=[a for a in p['audio'] if a['role']=='voice'][1]
        self.assertEqual(right['in'],120);self.assertEqual(right['fadeOffset'],60)
        for op in [dict(op='linkTrack',track='wrong',linked=False),dict(op='linkTrack',track='music',linked=1),dict(op='set',kind='clips',id='video',values={'linked':False}),dict(op='splitAt',frame=30.2)]:
            with self.assertRaises(ValueError):project.apply(self.p,[op])
    def test_split_and_cut_keep_audio_fades_and_continuous_music(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);tone=root/'tone.wav'
            render.run(['-v','error','-f','lavfi','-i','sine=frequency=720:sample_rate=48000:duration=10',tone])
            self.p['assets'][0]['path']=str(tone);self.p['audio']=[self.p['audio'][1]]
            self.p['graphics']=[];self.p['captions']=[]
            def samples(p,name):
                work=root/name;work.mkdir();wav=render.render_audio(p,work)
                return np.frombuffer(render.run(['-v','error','-i',wav,'-ac','1','-f','f32le','-']),np.float32)
            original=samples(self.p,'original')
            split=project.apply(self.p,[dict(op='splitAt',frame=30)])
            np.testing.assert_allclose(samples(split,'split'),original,atol=2e-5)
            cut=project.apply(self.p,[dict(op='cutRange',start=30,end=60)])
            expected=np.concatenate([original[:48000],original[96000:]])
            np.testing.assert_allclose(samples(cut,'cut'),expected,atol=2e-5)
            free=project.apply(self.p,[dict(op='linkTrack',track='music',linked=False),dict(op='cutRange',start=30,end=60)])
            np.testing.assert_allclose(samples(free,'free'),original[:432000],atol=2e-5)

if __name__=='__main__':unittest.main()
