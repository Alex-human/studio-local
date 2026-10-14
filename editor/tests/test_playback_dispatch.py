import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import editor, project, render


class PlaybackDispatchTests(unittest.TestCase):
    def test_native_playback_action_preserves_video_audio_and_project(self):
        with tempfile.TemporaryDirectory(prefix='studio-dispatch-') as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'
            render.run(['-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=30:duration=1',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', source])
            p = project.new(width=64, height=64, fps=30)
            p['assets'] = [dict(id='video', path=str(source), name='Source', kind='video',
                                duration=1, width=64, height=64, fps=30, audio=True)]
            p['clips'] = [dict(id='clip', asset='video', length=30, **{'in': 0})]
            path = root / 'Project.studio'
            project.save(path, p)
            before = path.read_bytes()
            plan = editor.dispatch(dict(action='preparePlayback', project=str(path),
                                        nativeImages=True, nativeText=True, nativeMotion=True,
                                        nativeVideo=True, interactive=True, frame=0))
            self.assertEqual(plan['totalFrames'], 30)
            self.assertEqual(plan['renderedFrames'], 0)
            self.assertEqual(plan['clips'][0]['path'], str(source))
            self.assertEqual(plan['audioSources'][0]['path'], str(source))
            self.assertEqual(path.read_bytes(), before)

    def test_file_at_another_frame_rate_plays_directly_only_on_a_host_that_retimes(self):
        with tempfile.TemporaryDirectory(prefix='studio-dispatch-') as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'
            render.run(['-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=30:duration=1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', source])
            p = project.new(width=64, height=64, fps=50)
            p['assets'] = [dict(id='video', path=str(source), name='Source', kind='video',
                                duration=1, width=64, height=64, fps=30, audio=False)]
            p['clips'] = [dict(id='clip', asset='video', length=40, **{'in': 5})]
            path = root / 'Project.studio'
            project.save(path, p)
            request = dict(action='preparePlayback', project=str(path), nativeImages=True, nativeText=True,
                           nativeMotion=True, nativeVideo=True, interactive=True, frame=0)
            plan = editor.dispatch(dict(request, nativeRetime=True))
            self.assertEqual((plan['directFrames'], plan['progressive'], plan['clips'][0].get('retime')), (40, False, True))
            self.assertTrue(editor.dispatch(request)['progressive'])


if __name__ == '__main__':
    unittest.main()
