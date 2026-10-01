import copy
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import editor, graphics, project, render, sync


class JoinTracks(unittest.TestCase):
    def setUp(self):
        self.p = project.new(fps=30, width=128, height=128)
        self.p['assets'] = [dict(id='source', name='Source', path='/source.mp4', duration=60, audio=False)]
        self.p['clips'] = [dict(id='video', asset='source', length=300, **{'in':0}, muted=True, zoom=1, zoomEnd=1.4)]
        self.p['audio'] = [dict(id=r, asset='source', role=r, start=0, length=300, **{'in':0}, fadeIn=60, fadeOut=60) for r in project.ROLES]
        self.p['graphics'] = [dict(id='title', type='title', start=0, length=300, props={'text':'Título'})]
        self.p['captions'] = [dict(id='caption', text='Palabra', start=0, length=300)]

    def join(self, p, track):
        return project.apply(p, [dict(op='joinTrack', track=track)])

    def clock(self, p, kind, role=None):
        frames = [];cursor = 0
        for item in p[kind]:
            start = cursor if kind == 'clips' else item['start']
            if kind == 'clips':cursor += item['length']
            if role is not None and item.get('role') != role:continue
            frames.extend((start + f, item.get('in', 0) + f * item.get('speed', 1)) for f in range(item['length']))
        return sorted(frames)

    def title_pixels(self, p):
        return [graphics.composite(Image.new('RGB', (128, 128)), p, f).tobytes() for f in range(project.duration(p))]

    def flat_hook(self):
        p = copy.deepcopy(self.p);p['audio'] = [];p['captions'] = []
        p['clips'][0]['length'] = 90
        base = dict(type='title', motionLength=300, props={'text':'Un solo gancho', 'enter':.01, 'style':'instagram', 'size':100})
        p['graphics'] = [dict(copy.deepcopy(base), id=f'hook{i}', start=i*30, length=30, offset=offset) for i,offset in enumerate((8, 80, 160))]
        return p

    def test_split_then_join_preserves_clocks_motion_fades_and_other_tracks(self):
        split = project.apply(self.p, [dict(op='splitAt', frame=120)])
        self.assertEqual(project.join_counts(split), {**dict.fromkeys(project.JOIN_TRACKS, 1), 'overlays':0})
        before = copy.deepcopy(split)
        for target,kind,role in [('video','clips',None), ('voice','audio','voice'), ('music','audio','music'), ('sfx','audio','sfx')]:
            joined = self.join(split, target)
            self.assertEqual(self.clock(split,kind,role), self.clock(joined,kind,role))
            self.assertEqual(project.duration(joined), 300)
            for other in ('clips','audio','graphics','captions'):
                if other != kind:self.assertEqual(joined[other], split[other])
            item = joined[kind][0] if kind == 'clips' else next(a for a in joined[kind] if a['role'] == role)
            self.assertEqual(item['length'],300)
            self.assertEqual(item['motionLength' if kind == 'clips' else 'fadeLength'],300)
        joined = self.join(split, 'graphics')
        self.assertEqual(self.title_pixels(joined), self.title_pixels(split))
        self.assertEqual(len(self.join(split,'captions')['captions']),1)
        self.assertEqual(split,before)

    def test_cut_source_gap_is_never_restored_and_mismatched_effects_do_not_join(self):
        cut = project.apply(self.p,[dict(op='cutRange',start=90,end=120)])
        for target in ('video',*project.ROLES):
            self.assertEqual(project.join_counts(cut)[target],0)
            with self.assertRaisesRegex(ValueError,'No hay tramos compatibles'):self.join(cut,target)
        split = project.apply(self.p,[dict(op='splitAt',frame=120)])
        for key,value in [('speed',1.5),('volumeDb',-12),('zoomEnd',1.8),('color',{'exposure':.2})]:
            changed = copy.deepcopy(split);changed['clips'][1][key] = value
            self.assertEqual(project.join_counts(changed)['video'],0)
        split['clips'][1]['motionOffset'] += 1
        self.assertEqual(project.join_counts(split)['video'],0)
        split['audio'][1]['fadeOffset'] += 1
        self.assertEqual(project.join_counts(split)['voice'],0)

    def test_static_hook_with_removed_phase_gaps_joins_without_pixel_change(self):
        p = self.flat_hook();before = copy.deepcopy(p)
        self.assertEqual(project.join_counts(p)['graphics'],2)
        joined = self.join(p,'graphics')
        self.assertEqual(len(joined['graphics']),1)
        hook = joined['graphics'][0]
        self.assertEqual((hook['id'],hook['start'],hook['length'],hook['offset'],hook['motionLength']),('hook0',0,90,8,300))
        self.assertTrue(hook['keepTogether'])
        self.assertEqual(self.title_pixels(p), self.title_pixels(joined))
        self.assertEqual(p,before)

    def test_hook_remains_one_piece_through_linked_cuts_but_explicit_split_works(self):
        joined = self.join(self.flat_hook(),'graphics')
        split = project.apply(joined,[dict(op='splitAt',frame=45)])
        self.assertEqual(split['graphics'],joined['graphics'])
        for start,end in [(0,10),(20,30),(80,90)]:
            cut = project.apply(joined,[dict(op='cutRange',start=start,end=end)])
            self.assertEqual(len(cut['graphics']),1)
            self.assertEqual(cut['graphics'][0]['length'],80)
            original = self.title_pixels(joined)
            self.assertEqual(self.title_pixels(cut),original[:start]+original[end:])
        split = project.apply(joined,[dict(op='split',kind='graphics',id='hook0',at=45)])
        self.assertEqual(len(split['graphics']),2)
        self.assertTrue(all('keepTogether' not in g for g in split['graphics']))

    def test_flat_title_exception_rejects_keyframes_fades_repeated_words_or_changed_text(self):
        p = self.flat_hook();p['graphics'] = p['graphics'][:2]
        for change in [dict(offset=0),dict(offset=290),dict(motionLength=301),dict(keyframes={'opacity':[dict(frame=0,value=.5)]})]:
            changed = copy.deepcopy(p);changed['graphics'][1].update(change)
            self.assertEqual(project.join_counts(changed)['graphics'],0)
        changed = copy.deepcopy(p);changed['graphics'][1]['props']['text'] = 'Otro'
        self.assertEqual(project.join_counts(changed)['graphics'],0)
        changed = copy.deepcopy(p);changed['graphics'][1]['offset'] = 8
        self.assertEqual(project.join_counts(changed)['graphics'],0)
        changed = copy.deepcopy(p);changed['graphics'][1]['linked'] = False
        self.assertEqual(project.join_counts(changed)['graphics'],0)

    def test_graphics_and_captions_do_not_cross_painter_order(self):
        p = self.flat_hook();p['graphics'] = p['graphics'][:2]
        overlay = dict(id='overlay',type='title',start=35,length=10,props={'text':'Arriba'})
        p['graphics'].insert(1,overlay)
        self.assertEqual(project.join_counts(p)['graphics'],0)
        p = project.apply(self.p,[dict(op='splitAt',frame=120)])
        p['captions'].insert(1,dict(id='upper',text='Arriba',start=140,length=30))
        self.assertEqual(project.join_counts(p)['captions'],0)

    def test_captions_require_split_lineage_and_preserve_repeated_words(self):
        self.p['captions'] = [dict(id='one',text='no',start=0,length=30),dict(id='two',text='no',start=30,length=30)]
        self.assertEqual(project.join_counts(self.p)['captions'],0)
        split = project.apply(self.p,[dict(op='split',kind='captions',id='one',at=15)])
        self.assertEqual(project.join_counts(split)['captions'],1)
        joined = self.join(split,'captions')
        self.assertEqual([(c['id'],c['length']) for c in joined['captions']],[('one',30),('two',30)])

    def test_audio_role_sorting_preserves_parallel_clips(self):
        split = project.apply(self.p,[dict(op='splitAt',frame=120)])
        split['audio'].reverse()
        joined = self.join(split,'music')
        self.assertEqual(self.clock(split,'audio','music'),self.clock(joined,'audio','music'))
        self.assertEqual(len([a for a in joined['audio'] if a['role']=='music']),1)
        split['audio'].append(dict(id='parallel',asset='source',role='music',start=60,length=180,**{'in':30}))
        self.assertEqual(project.join_counts(split)['music'],0)

    def test_join_keeps_authored_audio_fade_waveform(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);tone = root/'tone.wav'
            samples = (np.sin(np.arange(480000)*2*np.pi*720/48000)*8000).astype('<i2')
            with wave.open(str(tone),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(48000);out.writeframes(samples.tobytes())
            p = copy.deepcopy(self.p);p['assets'][0]['path'] = str(tone)
            p['audio'] = [p['audio'][1]];p['graphics'] = [];p['captions'] = []
            split = project.apply(p,[dict(op='splitAt',frame=120)])
            joined = self.join(split,'music')
            def pcm(value,name):
                work = root/name;work.mkdir()
                path = render.render_audio(value,work)
                return np.frombuffer(render.run(['-v','error','-i',path,'-ac','1','-f','f32le','-']),np.float32)
            np.testing.assert_allclose(pcm(split,'split'),pcm(joined,'joined'),atol=2e-5)

    def test_join_undo_redo_and_failed_join_do_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'p.studio';p = self.flat_hook();project.save(path,p)
            joined = editor.dispatch(dict(action='ops',project=str(path),revision=0,ops=[dict(op='joinTrack',track='graphics')]))['project']
            self.assertEqual(joined['revision'],1)
            self.assertEqual(len(joined['graphics']),1)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError,'No hay tramos compatibles'):
                editor.dispatch(dict(action='ops',project=str(path),revision=1,ops=[dict(op='joinTrack',track='graphics')]))
            self.assertEqual(path.read_bytes(),before)
            undone = editor.dispatch(dict(action='undo',project=str(path),revision=1))['project']
            self.assertEqual(undone['graphics'],p['graphics'])
            redone = editor.dispatch(dict(action='redo',project=str(path),revision=2))['project']
            self.assertEqual(redone['graphics'],joined['graphics'])

    def test_keep_together_validation_and_independent_hook(self):
        for kind in ('clips','audio','captions'):
            invalid = copy.deepcopy(self.p);invalid[kind][0]['keepTogether'] = True
            with self.assertRaisesRegex(ValueError,'Mantener de una pieza'):project.validate(invalid)
        animated = copy.deepcopy(self.p);animated['graphics'][0].update(keepTogether=True,keyframes={'opacity':[dict(frame=0,value=.5)]})
        with self.assertRaisesRegex(ValueError,'Mantener de una pieza'):project.validate(animated)
        animated['graphics'][0]['keepTogether'] = False
        project.validate(animated)
        p = self.join(self.flat_hook(),'graphics');p['graphics'][0]['linked'] = False
        cut = project.apply(p,[dict(op='cutRange',start=20,end=30)])
        self.assertEqual(cut['graphics'],p['graphics'])

    def test_stale_join_or_enabling_continuity_never_extends_concurrent_text_change(self):
        for action in ('join','keep'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'p.studio';p = self.flat_hook();project.save(path,p)
                values = copy.deepcopy(p['graphics'][0]['props']);values['text'] = 'Cambio concurrente'
                editor.dispatch(dict(action='ops',project=str(path),revision=0,ops=[dict(op='set',kind='graphics',id='hook0',values={'props':values})]))
                before = path.read_bytes()
                ops = [dict(op='joinTrack',track='graphics')] if action == 'join' else [dict(op='set',kind='graphics',id=g['id'],values={'keepTogether':True}) for g in p['graphics']]
                with self.assertRaises(sync.Conflict):
                    editor.dispatch(dict(action='ops',project=str(path),revision=0,ops=ops))
                self.assertEqual(path.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
