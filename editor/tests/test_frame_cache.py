import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import project
import render


class FrameCacheTests(unittest.TestCase):
    def test_text_edits_reuse_source_but_source_and_framing_changes_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'video.mp4'
            source.write_bytes(b'fixture')
            p = project.new(width=960, height=540, fps=30)
            p['assets'] = [dict(id='v', path=str(source))]
            p['clips'] = [dict(id='c', asset='v', length=120, **{'in': 0})]
            p['graphics'] = [dict(id='g', type='title', start=0, length=120,
                                  props=dict(text='Antes', enter=.01))]
            raw = Image.new('RGB', (960, 540), '#19446b').tobytes()
            with patch.object(render, 'run', return_value=raw) as decode:
                first = render.frame(p, 30, folder / 'frames')
                with Image.open(first['path']) as image:before = np.array(image)
                p['revision'] += 1
                p['graphics'][0]['props']['text'] = 'Después'
                second = render.frame(p, 30, folder / 'frames')
                with Image.open(second['path']) as image:after = np.array(image)
                self.assertEqual(decode.call_count, 1)
                self.assertFalse(np.array_equal(before, after))
                p['graphics'] = []
                render.frame(p, 30, folder / 'frames')
                self.assertEqual(decode.call_count, 1)
                render.frame(p, 31, folder / 'frames')
                self.assertEqual(decode.call_count, 2)
                p['clips'][0]['zoom'] = 1.1
                render.frame(p, 30, folder / 'frames')
                self.assertEqual(decode.call_count, 3)
                source.write_bytes(b'changed source')
                render.frame(p, 30, folder / 'frames')
                self.assertEqual(decode.call_count, 4)
            self.assertEqual(len(list((folder / 'frames').glob('.source-*'))), 0)

    def test_fractional_speed_seek_preserves_full_stream_timestamp_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source=folder/'video.mp4'
            render.run(['-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=24:d=10','-c:v','libx264',source])
            asset=render.probe(source);p=project.new(width=160,height=90,fps=30);p['assets']=[asset]
            for speed in (.25,.5,.75,1,1.25,1.5,2,4):
                clip=dict(id='clip',asset=asset['id'],length=60,**{'in':5.5},speed=speed)
                p['clips']=[clip]
                raw=render.run(['-v','error',*render.video_input(clip,p,asset['path']),'-vf',render.video_filter(clip,p,160,90),'-frames:v','60','-an','-f','rawvideo','-pix_fmt','rgb24','-'])
                size=160*90*3
                for frame in (0,5,14,20,50):
                    with self.subTest(speed=speed,frame=frame):
                        cache=folder/f'{speed}-{frame}';cache.mkdir();render.frame(p,frame,cache,width=160)
                        with Image.open(next(cache.glob('source-*.png'))) as image:
                            self.assertEqual(image.tobytes(),raw[size*frame:size*(frame+1)])


if __name__ == '__main__':
    unittest.main()
