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


class DuplicateElements(unittest.TestCase):
    def setUp(self):
        self.p = project.new(fps=30, width=128, height=128)
        self.p['assets'] = [dict(id='source', name='Source', path='/source.mp4', duration=60, audio=True)]
        self.p['clips'] = [dict(id='first', asset='source', length=30, **{'in':0}, muted=True),
                           dict(id='selected', asset='source', length=60, **{'in':90}, speed=1.5,
                                muted=True, volumeDb=-8, zoom=1.2, zoomEnd=1.7, motionOffset=20,
                                motionLength=180, color={'exposure':.2}),
                           dict(id='last', asset='source', length=210, **{'in':240}, muted=True)]
        self.p['audio'] = [dict(id='music', asset='source', role='music', start=20, length=70,
                               **{'in':45}, speed=1.5, volumeDb=-14, fadeIn=30, fadeOut=40,
                               fadeOffset=15, fadeLength=180, linked=False)]
        self.p['graphics'] = [dict(id='title', type='title', start=10, length=130, offset=8,
                                  motionLength=180, props={'text':'Título', 'size':100, 'x':850, 'y':520})]
        self.p['captions'] = [dict(id='caption', text='Palabra', start=30, length=60, splitFrom='old-word')]

    def duplicate(self, kind, id, **fields):
        return project.apply(self.p, [dict(op='duplicate', kind=kind, id=id, **fields)])

    def samples(self, p, kind, frame):
        values = [];position = 0
        for item in p[kind]:
            start = position if kind == 'clips' else item['start']
            if kind == 'clips':position += item['length']
            if not start <= frame < start + item['length']:continue
            local = frame-start
            if kind in ('clips', 'audio'):
                values.append((item['asset'], item.get('in', 0)+local*item.get('speed', 1),
                               item.get('volumeDb', 0), item.get('muted', False),
                               (item.get('motionOffset', 0)+local, item.get('motionLength', item['length'])) if kind == 'clips'
                               else (item.get('fadeOffset', 0)+local, item.get('fadeLength', item['length']))))
            elif kind == 'graphics':
                values.append((item['type'], item.get('props'), item.get('offset', 0)+local,
                               item.get('motionLength', item['length']), item.get('hidden', False)))
            else:values.append((item['text'], item.get('hidden', False)))
        return values

    def pixels(self, p, frame):
        return graphics.composite(Image.new('RGB', (128, 128), '#213141'), p, frame).tobytes()

    def test_nonvideo_copies_all_properties_without_changing_source_or_other_tracks(self):
        for kind, id in [('audio', 'music'), ('graphics', 'title'), ('captions', 'caption')]:
            with self.subTest(kind=kind):
                before = copy.deepcopy(self.p);source = project.find(self.p, kind, id)
                out = self.duplicate(kind, id, newId='copy')
                expected = copy.deepcopy(source);expected.update(id='copy', start=source['start']+source['length'])
                if kind == 'captions':expected['splitFrom'] = 'copy'
                self.assertEqual(project.find(out, kind, 'copy'), expected)
                self.assertEqual(project.find(out, kind, id), source)
                self.assertEqual(self.p, before)
                for other in ('clips', 'audio', 'graphics', 'captions', 'assets'):
                    if other != kind:self.assertEqual(out[other], before[other])
                self.assertEqual(out['revision'], before['revision']+1)
        image = dict(id='image', type='image', start=0, length=20,
                     props={'asset':'source', 'animation':'from-left', 'sound':True, 'soundDb':-24,
                            'cropLeft':.1, 'rotation':12}, keyframes={'x':[dict(frame=0, value=400)]})
        self.p['graphics'] = [image]
        out = self.duplicate('graphics', 'image', newId='image-copy')
        self.assertEqual(out['graphics'][1], {**image, 'id':'image-copy', 'start':20})
        out['graphics'][1]['props']['rotation'] = 20
        self.assertEqual(out['graphics'][0]['props']['rotation'], 12)

    def test_explicit_position_and_shorter_copy_preserve_authored_phase(self):
        out = self.duplicate('audio', 'music', start=260, length=40, newId='copy')
        duplicate = project.find(out, 'audio', 'copy')
        self.assertEqual((duplicate['start'], duplicate['length'], duplicate['in'], duplicate['fadeOffset'], duplicate['fadeLength']), (260, 40, 45, 15, 180))
        self.assertEqual(project.duration(out), 300)
        for f in range(40):self.assertEqual(self.samples(out, 'audio', 260+f), self.samples(self.p, 'audio', 20+f))
        self.p['graphics'][0].pop('motionLength');self.p['graphics'][0].pop('offset')
        out = self.duplicate('graphics', 'title', start=270, length=30)
        duplicate = out['graphics'][1]
        self.assertEqual((duplicate['offset'], duplicate['motionLength']), (0, 130))
        self.assertEqual(duplicate['props'], self.p['graphics'][0]['props'])

    def test_video_replays_linked_interval_and_preserves_all_clocks_and_painter_order(self):
        self.p['audio'][0]['linked'] = True
        self.p['audio'][0]['length'] = 130
        self.p['audio'] += [dict(id='later-audio', asset='source', role='voice', start=90, length=50, **{'in':400}),
                            dict(id='free-audio', asset='source', role='sfx', start=40, length=100, **{'in':30}, linked=False)]
        self.p['graphics'] += [dict(id='upper', type='title', start=40, length=100, props={'text':'Arriba', 'color':'#00ff00'}),
                               dict(id='later', type='title', start=90, length=80, props={'text':'Después'})]
        self.p['captions'] += [dict(id='cross-caption', text='Cruza', start=70, length=60)]
        before = copy.deepcopy(self.p);out = self.duplicate('clips', 'selected', newId='copy')
        self.assertEqual(self.p, before)
        self.assertEqual([c['id'] for c in out['clips']], ['first', 'selected', 'copy', 'last'])
        self.assertEqual(out['clips'][2], {**self.p['clips'][1], 'id':'copy'})
        self.assertEqual(project.find(out, 'audio', 'free-audio'), self.p['audio'][-1])
        self.assertEqual(project.duration(out), 360)
        # Remove independent media from the replay comparison: it keeps wall-clock time.
        reference = copy.deepcopy(self.p);reference['audio'] = reference['audio'][:-1]
        compared = copy.deepcopy(out);compared['audio'] = [a for a in compared['audio'] if a['id'] != 'free-audio']
        for frame in range(360):
            original = frame if frame < 90 else frame-60
            for kind in ('clips', 'audio', 'graphics', 'captions'):
                self.assertEqual(self.samples(compared, kind, frame), self.samples(reference, kind, original), (kind, frame))
            self.assertEqual(self.pixels(out, frame), self.pixels(self.p, original), frame)
        ids = [item['id'] for kind in ('clips', 'audio', 'graphics', 'captions') for item in out[kind]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_video_keeps_independent_tracks_and_overrides_exactly_unchanged(self):
        self.p['syncTracks'] = dict(music=False, graphics=False, captions=False)
        self.p['audio'][0].pop('linked')
        out = self.duplicate('clips', 'selected')
        for kind in ('audio', 'graphics', 'captions'):self.assertEqual(out[kind], self.p[kind])
        self.p['graphics'][0]['linked'] = True
        out = self.duplicate('clips', 'selected')
        self.assertNotEqual(out['graphics'], self.p['graphics'])
        self.assertEqual(out['audio'], self.p['audio'])

    def test_flat_kept_hook_remains_one_piece_with_identical_pixels(self):
        hook = self.p['graphics'][0]
        hook.update(start=0, length=250, offset=20, motionLength=300, keepTogether=True)
        self.p['captions'] = []
        out = self.duplicate('clips', 'selected')
        self.assertEqual(len(out['graphics']), 1)
        copied = out['graphics'][0]
        self.assertEqual((copied['id'], copied['length'], copied['motionLength'], copied['offset']), ('title', 310, 360, 20))
        for frame in range(360):
            original = frame if frame < 90 else frame-60
            self.assertEqual(self.pixels(out, frame), self.pixels(self.p, original), frame)
        out = self.duplicate('graphics', 'title', start=0, length=30, newId='copy')
        self.assertEqual(len(out['graphics']), 2)
        self.assertTrue(project.find(out, 'graphics', 'copy')['keepTogether'])
        # Adjacent explicit repetitions must remain separate selected elements.
        hook['length'] = 90
        out = self.duplicate('graphics', 'title', newId='copy')
        self.assertEqual([g['id'] for g in out['graphics']], ['title', 'copy'])

    def test_animated_kept_hook_uses_exact_phase_fragments(self):
        hook = self.p['graphics'][0]
        hook.update(start=0, offset=0, length=130, motionLength=130, keepTogether=True)
        self.p['captions'] = []
        out = self.duplicate('clips', 'selected')
        self.assertGreater(len(out['graphics']), 1)
        for frame in range(360):
            original = frame if frame < 90 else frame-60
            self.assertEqual(self.pixels(out, frame), self.pixels(self.p, original), frame)

    def test_duplicated_caption_has_independent_lineage_and_can_be_split_then_joined(self):
        out = self.duplicate('captions', 'caption', newId='copy')
        self.assertEqual(project.join_counts(out)['captions'], 0)
        split = project.apply(out, [dict(op='split', kind='captions', id='copy', at=20)])
        joined = project.apply(split, [dict(op='joinTrack', track='captions')])
        self.assertEqual(joined['captions'], out['captions'])

    def test_repeated_music_has_no_overlap_or_gain_change_in_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);tone = root/'tone.wav'
            samples = (np.sin(np.arange(144000)*2*np.pi*720/48000)*8000).astype('<i2')
            with wave.open(str(tone), 'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(48000);audio.writeframes(samples.tobytes())
            p = copy.deepcopy(self.p);p['assets'][0]['path'] = str(tone)
            p['graphics'] = [];p['captions'] = []
            p['audio'] = [dict(id='music', asset='source', role='music', start=0, length=30,
                               **{'in':30}, fadeIn=20, fadeOut=20, fadeOffset=15, fadeLength=60, volumeDb=-10)]
            def pcm(value, name):
                work = root/name;work.mkdir()
                return np.frombuffer(render.run(['-v','error','-i',render.render_audio(value, work),'-ac','1','-f','f32le','-']), np.float32)
            original = pcm(p, 'original')
            out = project.apply(p, [dict(op='duplicate', kind='audio', id='music')])
            repeated = pcm(out, 'repeated')
            np.testing.assert_allclose(repeated[:48000], original[:48000], atol=2e-5)
            np.testing.assert_allclose(repeated[48000:96000], original[:48000], atol=2e-5)
            np.testing.assert_allclose(repeated[96000:], original[96000:], atol=2e-5)

    def test_invalid_arguments_and_tail_overflow_never_mutate_or_write(self):
        cases = [dict(kind='audio', id='missing'), dict(kind='wrong', id='music'),
                 dict(kind='audio', id='music', start=280), dict(kind='audio', id='music', start=-1),
                 dict(kind='audio', id='music', start=.5), dict(kind='audio', id='music', start=True),
                 dict(kind='audio', id='music', length=0), dict(kind='audio', id='music', length=71),
                 dict(kind='audio', id='music', length=1.5), dict(kind='audio', id='music', length=True),
                 dict(kind='audio', id='music', newId='title'), dict(kind='audio', id='music', newId='bad/id'),
                 dict(kind='audio', id='music', newId=None), dict(kind='clips', id='selected', start=90),
                 dict(kind='clips', id='selected', length=30), dict(kind='clips', id='selected', newId='caption')]
        before = copy.deepcopy(self.p)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'p.studio';project.save(path, self.p);saved = path.read_bytes()
            for fields in cases:
                with self.subTest(fields=fields), self.assertRaises(ValueError):
                    editor.dispatch(dict(action='ops', project=str(path), revision=0, ops=[dict(op='duplicate', **fields)]))
                self.assertEqual(path.read_bytes(), saved)
                self.assertEqual(self.p, before)
        self.p['audio'][0].update(start=230, length=70)
        with self.assertRaisesRegex(ValueError, 'no cabe'):self.duplicate('audio', 'music')

    def test_duplicate_and_undo_redo_are_one_atomic_history_step(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'p.studio';project.save(path, self.p)
            out = editor.dispatch(dict(action='ops', project=str(path), revision=0,
                                       ops=[dict(op='duplicate', kind='clips', id='selected', newId='copy')]))['project']
            self.assertEqual(out['revision'], 1)
            undone = editor.dispatch(dict(action='undo', project=str(path), revision=1))['project']
            for key in ('clips', 'audio', 'graphics', 'captions', 'assets'):self.assertEqual(undone[key], self.p[key])
            redone = editor.dispatch(dict(action='redo', project=str(path), revision=2))['project']
            for key in ('clips', 'audio', 'graphics', 'captions', 'assets'):self.assertEqual(redone[key], out[key])
            self.assertEqual(project.load(path), redone)

    def test_stale_duplicate_does_not_copy_old_source_settings_or_write(self):
        for kind, id in [('clips', 'selected'), ('audio', 'music')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'p.studio';project.save(path, self.p)
                editor.dispatch(dict(action='ops', project=str(path), revision=0,
                                     ops=[dict(op='set', kind=kind, id=id, values={'volumeDb':-30})]))
                before = path.read_bytes()
                with self.assertRaises(sync.Conflict):
                    editor.dispatch(dict(action='ops', project=str(path), revision=0,
                                         ops=[dict(op='duplicate', kind=kind, id=id)]))
                self.assertEqual(path.read_bytes(), before)

    def test_id_collision_cannot_be_hidden_by_automatic_hook_join(self):
        base = dict(type='title', length=30, keepTogether=True, motionLength=300, props={'text':'Gancho'})
        self.p['graphics'] = [dict(base, id='title', start=0, offset=30),
                              dict(base, id='later', start=120, offset=60)]
        before = copy.deepcopy(self.p)
        with self.assertRaisesRegex(ValueError, 'ID de elemento duplicado'):
            self.duplicate('graphics', 'title', start=90, newId='later')
        self.assertEqual(self.p, before)


if __name__ == '__main__':
    unittest.main()
