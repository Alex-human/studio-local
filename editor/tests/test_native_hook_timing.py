"""A duration edit must not turn an Instagram hook into a dissolving card."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import graphics, preview, project, render


class NativeHookTiming(unittest.TestCase):
    def setUp(self):
        self.p = project.new(width=320, height=568, fps=30)
        self.p['assets'] = [dict(id='v', path='/fixture.mp4', duration=4, fps=30, audio=False)]
        self.p['clips'] = [dict(id='c', asset='v', length=120, **{'in': 0})]
        self.p['graphics'] = [dict(id='h', type='title', start=0, length=120, offset=8,
            motionLength=136, props=dict(style='native', text='Un gancho\nnativo',
                x=960, y=600, size=114, enter=.01, color='#000000', accent='#ffffff'))]
        self.p = project.apply(self.p, [dict(op='duration', kind='graphics', id='h', length=90)])

    def pixels(self, p, frame):
        return np.asarray(graphics.composite(Image.new('RGB', (320, 568)), p, frame))

    def test_duration_resize_and_split_end_with_a_cut(self):
        resized = project.apply(self.p, [dict(op='resizeEdge', kind='graphics', id='h', edge='end', delta=-10)])
        split = project.apply(self.p, [dict(op='split', kind='graphics', id='h', at=45)])
        for p, last in ((self.p, 89), (split, 89), (resized, 79)):
            with self.subTest(last=last, pieces=len(p['graphics'])):
                np.testing.assert_array_equal(self.pixels(p, 30), self.pixels(p, last))
                self.assertFalse(self.pixels(p, last + 1).any())
        np.testing.assert_array_equal(self.pixels(split, 44), self.pixels(split, 45))
        self.assertTrue(project.static_title(self.p['graphics'][0], 30))

    def test_gpu_placements_and_playback_keep_the_same_boundary_and_explicit_opacity(self):
        for style in ('native', 'plain'):
            p = copy.deepcopy(self.p)
            p['graphics'][0]['props']['style'] = style
            with tempfile.TemporaryDirectory() as directory:
                plan = render.export_plan(p, Path(directory))
                alpha = plan['placements'][89][-1]
                self.assertEqual(plan['placements'][90], [])
                if style == 'native':
                    self.assertEqual(alpha, 1)
                else:
                    self.assertLess(alpha, .04)
                layer = preview.text_layer(p['graphics'][0], 'graphics', (320, 568), Path(directory))
                self.assertEqual(layer['props'].get('exit'), 'cut' if style == 'native' else None)
        self.p['graphics'][0]['keyframes'] = {'opacity': [{'frame': 8, 'value': .4}, {'frame': 98, 'value': .4}]}
        with tempfile.TemporaryDirectory() as directory:
            plan = render.export_plan(self.p, Path(directory))
            self.assertEqual(plan['placements'][89][-1], .4)


if __name__ == '__main__':
    unittest.main()
