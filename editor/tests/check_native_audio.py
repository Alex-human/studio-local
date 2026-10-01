"""Run the real macOS player regressions with disposable, generated media."""
import json
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def run(args, timeout=60):
    subprocess.run([str(a) for a in args], check=True, timeout=timeout)


with tempfile.TemporaryDirectory(prefix='studio-audio-regression-') as directory:
    work = Path(directory)
    ffmpeg = root / 'runtime/ffmpeg'
    run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=30:d=30',
         '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', work / 'video.mp4'])
    for name, rate, channels, codec in [('stereo.wav', 44100, 2, 'pcm_s16le'), ('mono.m4a', 48000, 1, 'aac')]:
        run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', f'sine=frequency=660:sample_rate={rate}:duration=30',
             '-ac', channels, '-c:a', codec, work / name])

    def source(id, name, start, length, offset=0, volume=1):
        return dict(id=id, path=str(work / name), start=start, length=length, source=offset,
                    speed=1, volume=volume, fadeIn=0, fadeOut=0)

    plan = dict(revision=1, frames=900, fps=30, fpsNum=30, fpsDen=1, width=64, height=64,
                clips=[dict(path=str(work / 'video.mp4'), start=0, sourceIn=0, length=900)],
                audio=None, audioSources=[source('tone', 'stereo.wav', 0, 30)],
                images=[], audioCues=[], ducking=False, mediaKey='regression', key='regression')
    steady = work / 'steady.json'
    steady.write_text(json.dumps(plan))
    plan['frames'] = plan['clips'][0]['length'] = 480
    plan['audioSources'] = [source('c0', 'stereo.wav', 0, 4, 16), source('c1', 'stereo.wav', 4, 4, 2, .25),
                            source('c2', 'mono.m4a', 8, 4, 19), source('c3', 'mono.m4a', 12, 4, 3, .5)]
    adjacent = work / 'adjacent.json'
    adjacent.write_text(json.dumps(plan))
    # Twenty camera takes with one AAC format, one distinct tone each, cut back to back at
    # 59.94 fps: a frame is 800.8 samples, so most cuts fall between two samples.
    run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=60000/1001:d=62',
         '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', work / 'video60.mp4'])
    for i in range(20):
        run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', f'sine=frequency={300 + 37 * i}:sample_rate=48000:duration=8',
             '-ac', 2, '-c:a', 'aac', work / f'take{i:02d}.m4a'])
    frame = 1001 / 60000
    plan.update(fps=60000 / 1001, fpsNum=60000, fpsDen=1001, frames=20 * 181, mediaKey='takes', key='takes')
    plan['clips'] = [dict(path=str(work / 'video60.mp4'), start=0, sourceIn=0, length=20 * 181)]
    plan['audioSources'] = [source(f't{i:02d}', f'take{i:02d}.m4a', 181 * i * frame, 181 * frame, (90 + 7 * i) * frame)
                            for i in range(20)]
    takes = work / 'takes.json'
    takes.write_text(json.dumps(plan))

    for test, arguments in [('native_gain', []), ('native_live_volume', [steady]),
                            ('native_independent_audio', [adjacent]), ('native_audio_start', [takes])]:
        binary = work / test
        run(['xcrun', 'swiftc', '-swift-version', '5', '-O', '-D', 'STUDIO_AUDIO_TESTS',
             '-module-cache-path', root / '.build/module-cache', root / 'native/Playback.swift', root / 'native/VideoCompositor.swift',
             root / f'tests/{test}.swift', '-o', binary, '-framework', 'AppKit',
             '-framework', 'AVFoundation', '-framework', 'MediaToolbox', '-framework', 'CoreImage'])
        run([binary, *arguments])
    print('PASS native gain formats, live faders, adjacent clips, AAC/WAV transitions, seek and restore, '
          'same-format takes on one track with an on-time audio start')
