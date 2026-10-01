"""Opt-in, own-process final-output speed regression; no microphone or raw recordings.

Builds actual engine playback plans with video voice, music and SFX. Distinct
pitched pulse trains let the final captured output prove tempo and pitch for
each track independently, including free tracks and the baked ducking route.
"""
import argparse
import copy
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'engine'))
import project
import preview
import render

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, default=root.parent / 'tmp/speed-free-audio-20260922')
parser.add_argument('--report', type=Path, default=root / 'evidence/speed-free-audio-20260922.json')
parser.add_argument('--analyze-only', action='store_true')
args = parser.parse_args()
work = args.work.resolve()
work.mkdir(parents=True, exist_ok=True)
frequencies = {'voice': 317, 'music': 997, 'sfx': 2399}
periods = {'voice': .8, 'music': 1, 'sfx': 1.2}


def run(command, timeout=120, **kwargs):
    return subprocess.run([str(arg) for arg in command], check=True, timeout=timeout, **kwargs)


if not args.analyze_only:
    binary = work / 'native_speed_output'
    run(['xcrun', 'swiftc', '-swift-version', '5', '-O', '-suppress-warnings', '-module-cache-path', root / '.build/module-cache',
         root / 'native/Playback.swift', root / 'native/VideoCompositor.swift', root / 'tests/native_speed_output.swift', '-o', binary,
         '-framework', 'AppKit', '-framework', 'AVFoundation', '-framework', 'MediaToolbox', '-framework', 'CoreImage',
         '-framework', 'ScreenCaptureKit', '-framework', 'Accelerate'])
    # Preflight never requests permission; exit 77 is an explicit unsupported check.
    preflight = subprocess.run([str(binary), '--preflight'], check=False)
    if preflight.returncode:
        raise SystemExit(preflight.returncode)
    rate = 48000
    time = np.arange(36 * rate) / rate
    for role, frequency in frequencies.items():
        position = np.mod(time-.15, periods[role])
        envelope = .02 + .98 * np.minimum(np.clip(position/.01, 0, 1), np.clip((.18-position)/.01, 0, 1))
        pcm = (np.sin(2*np.pi*frequency*time) * envelope * .07 * 32767).astype('<i2')
        with wave.open(str(work / f'{role}.wav'), 'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate); output.writeframes(pcm.tobytes())
    run([root / 'runtime/ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=blue:s=64x64:r=30:d=32',
         '-i', work / 'voice.wav', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-t', '32', work / 'video.mp4'])
    p = project.new('Synthetic free audio speed check', width=64, height=64, fps=30)
    for role, path in [('video', work / 'video.mp4'), ('music', work / 'music.wav'), ('sfx', work / 'sfx.wav')]:
        asset = render.probe(path); asset['id'] = role; p['assets'].append(asset)
    p['clips'] = [dict(id='main-video', asset='video', length=960, **{'in': 0})]
    p['audio'] = [dict(id=role, asset=role, role=role, start=0, length=960, **{'in': offset})
                  for role, offset in [('music', 9), ('sfx', 18)]]
    linked = preview.prepare(p, work / 'project', native_images=True)
    free = project.apply(p, [dict(op='linkTrack', track=role, linked=False) for role in ('music', 'sfx')]
                         + [dict(op='set', kind='audio', id=role, values={'linked': False}) for role in ('music', 'sfx')])
    free_plan = preview.prepare(free, work / 'project', native_images=True)
    for key in ('clips', 'audioSources', 'audioCues', 'mediaKey', 'key'):
        assert linked[key] == free_plan[key], f'Free track changed playback {key}'
    assert all(not project.linked(free, 'audio', item) for item in free['audio'])
    project.save(work / 'synthetic-free.studio', free)
    ducking = copy.deepcopy(free); ducking['ducking'] = True
    ducking_plan = preview.prepare(ducking, work / 'project', native_images=True)
    assert ducking_plan['audio'] and not ducking_plan['audioSources']
    bundle = dict(plans=dict(linked=linked, free=free_plan, ducking=ducking_plan))
    (work / 'plans.json').write_text(json.dumps(bundle))
    run([binary, work / 'plans.json', work / 'spectral-envelopes.json'], timeout=120)


def pulse_times(time, envelope):
    smooth = np.convolve(envelope, np.ones(3)/3, mode='same')
    threshold = np.percentile(smooth, 95)*.20
    active = np.flatnonzero(smooth > threshold)
    assert len(active), 'No audible pulses'
    groups = np.split(active, np.flatnonzero(np.diff(active) > 7)+1)
    peaks = []
    for group in groups:
        if len(group) < 3:
            continue
        # Center of energy avoids choosing arbitrary maxima on a pulse plateau.
        weights = np.maximum(0, smooth[group]-threshold)
        peaks.append(float(np.sum(time[group]*weights)/np.sum(weights)))
    return np.array(peaks)


captured = json.loads((work / 'spectral-envelopes.json').read_text())
assert captured['captureScope'] == 'own-process-only' and not captured['pcmPersisted']
results = []
for phase in captured['phases']:
    assert not phase['formatError'] and phase['gaps'] == 0, (phase['name'], 'capture format or gaps')
    rows = np.array(phase['rows'])
    assert len(rows) > 100 and phase['samples'] > 48000, 'Insufficient final-output samples'
    usable = rows[(rows[:, 0] > .8) & (rows[:, 0] < rows[-1, 0]-.25)]
    if phase['paused']:
        peak = float(np.max(usable[:, -1]))
        assert peak < 1e-7, ('Paused output is not silent', peak)
        results.append(dict(phase=phase['name'], digital_silence=True, max_rms=peak))
        print('PASS paused final output is digitally silent')
        continue
    result = dict(phase=phase['name'], requested_rate=phase['rate'], tracks={})
    for index, role in enumerate(frequencies):
        envelope = usable[:, 1+index*2]
        assert float(np.max(envelope)) > 1e-5, (phase['name'], role, 'No audible track')
        peaks = pulse_times(usable[:, 0], envelope)
        assert len(peaks) >= 3, (phase['name'], role, 'Too few measured pulses', peaks.tolist())
        intervals = np.diff(peaks)
        period = float(np.median(intervals))
        measured = periods[role]/period
        assert abs(measured-phase['rate']) < .12, (phase['name'], role, 'Wrong audible tempo', measured, peaks.tolist())
        expected = periods[role]/phase['rate']
        assert np.count_nonzero(abs(intervals-expected) < .075) >= max(2, len(intervals)-1), (phase['name'], role, 'Irregular pulse timing', intervals.tolist())
        peak_frequencies = usable[envelope > np.percentile(envelope, 95)*.40, 2+index*2]
        pitch = float(np.median(peak_frequencies))
        assert abs(pitch-frequencies[role]) < max(18, frequencies[role]*.025), (phase['name'], role, 'Pitch changed', pitch)
        result['tracks'][role] = dict(measured_speed=round(measured, 5), pulse_interval_seconds=round(period, 5),
                                     expected_interval_seconds=round(expected, 5), pulses=len(peaks),
                                     pitch_hz=pitch, source_pitch_hz=frequencies[role])
    speeds = [value['measured_speed'] for value in result['tracks'].values()]
    assert max(speeds)-min(speeds) < .12, (phase['name'], 'Tracks disagree on tempo', speeds)
    results.append(result)
    print('PASS final-output', phase['name'], json.dumps(result['tracks'], sort_keys=True))

report = dict(result='passed', method='ScreenCaptureKit final output, filter restricted to own synthetic test process',
              microphone=False, other_apps=False, source_footage=False, raw_recordings_persisted=False,
              project_engine_plans=True, linked_and_free_playback_plans_identical=True,
              independent_tracks=['music', 'sfx'], source_pulse_period_seconds=periods, phases=results,
              limitations=['Synthetic tones and pulse trains verify tempo/pitch numerically; real music listening quality is not rated.',
                           'Spectral pitch resolution is 11.72 Hz; tempo uses 10 ms envelope steps.',
                           'Image-triggered AVAudioPlayer cues are covered by native_speed.swift, not this track-output test.'])
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2)+'\n')
print('PASS linked/free music and SFX final audio tempo, pitch, live change, pause/seek and baked ducking')
