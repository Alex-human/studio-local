"""Verify review speed using the real macOS players and disposable media."""
import json
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def run(args, timeout=60):
    subprocess.run([str(arg) for arg in args], check=True, timeout=timeout)


with tempfile.TemporaryDirectory(prefix='studio-speed-regression-') as directory:
    work = Path(directory)
    ffmpeg = root / 'runtime/ffmpeg'
    run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:r=30:d=20',
         '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', work / 'video.mp4'])
    run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=20',
         '-ac', '2', '-c:a', 'pcm_s16le', work / 'audio.wav'])
    plan = dict(frames=600, fps=30, fpsNum=30, fpsDen=1, width=64, height=64,
                clips=[dict(path=str(work / 'video.mp4'), start=0, sourceIn=0, length=600)],
                audio=None, audioSources=[dict(id='voice', path=str(work / 'audio.wav'), start=0,
                                              length=20, source=0, speed=1, volume=1, fadeIn=0, fadeOut=0)],
                images=[], audioCues=[dict(id='short', path=str(work / 'audio.wav'), start=.6,
                                          length=1.2, source=1, volume=0),
                                     dict(id='long', path=str(work / 'audio.wav'), start=3,
                                          length=4, source=.25, volume=0)],
                mediaKey='speed', key='speed')
    plan_path = work / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    binary = work / 'native_speed'
    run(['xcrun', 'swiftc', '-swift-version', '5', '-Onone', '-suppress-warnings', '-module-cache-path', root / '.build/module-cache',
         root / 'native/Playback.swift', root / 'native/VideoCompositor.swift', root / 'tests/native_speed.swift', '-o', binary,
         '-framework', 'AppKit', '-framework', 'AVFoundation', '-framework', 'MediaToolbox', '-framework', 'CoreImage'], timeout=120)
    run([binary, plan_path])
