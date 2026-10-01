"""Opt-in macOS final-output check. Needs Screen Recording permission.

Plays a quiet synthetic tone; captures only its own test process (no microphone,
Studio project or other apps). Verifies the signal after AVPlayer's final mix,
which an observer inside MTAudioProcessingTap cannot validate.
"""
import argparse,json,math,os,subprocess,tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--playback-source',type=Path,default=root/'native/Playback.swift',help='Optional historical source for negative control')
args=parser.parse_args()
def run(command):subprocess.run([str(x) for x in command],check=True,timeout=90)
with tempfile.TemporaryDirectory(prefix='studio-output-check-') as directory:
    work=Path(directory);ffmpeg=root/'runtime/ffmpeg'
    run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=30:d=1173','-an','-c:v','libx264','-pix_fmt','yuv420p',work/'video.mp4'])
    run([ffmpeg,'-v','error','-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=140','-ac','1','-c:a','aac','-b:a','96k',work/'tone.m4a'])
    sources=json.loads((root/'tests/audio_boundaries.json').read_text())
    for bank in {x['bank'] for x in sources}:os.link(work/'tone.m4a',work/f'bank-{bank}.m4a')
    for s in sources:s['path']=str(work/f"bank-{s.pop('bank')}.m4a")
    plan=dict(revision=1,frames=70244,fps=60000/1001,fpsNum=60000,fpsDen=1001,width=64,height=64,
              clips=[dict(path=str(work/'video.mp4'),start=0,sourceIn=0,length=70244)],
              audio=None,audioSources=sources,images=[],audioCues=[],ducking=False,key='boundaries',mediaKey='boundaries')
    (work/'plan.json').write_text(json.dumps(plan))
    run(['xcrun','swiftc','-swift-version','5','-O','-D','STUDIO_AUDIO_TESTS','-module-cache-path',root/'.build/module-cache',args.playback_source, *([root/'native/VideoCompositor.swift'] if 'PlaybackVideoBuilder' in args.playback_source.read_text() else []),
         root/'tests/native_output_volume.swift','-o',work/'probe','-framework','AppKit','-framework','AVFoundation','-framework','MediaToolbox','-framework','CoreImage','-framework','ScreenCaptureKit'])
    run([work/'probe',work/'plan.json',work/'output.json'])
    for phase in json.loads((work/'output.json-phases.json').read_text()):
        rows=phase['rows'];gain=phase['gain'];expected=0.125/math.sqrt(2)*0.1*gain
        if gain:
            first=next(t for t,v,n in rows if v>expected*0.1)
            values=sorted(v for t,v,n in rows if first+0.2<t<first+1.9)
            assert len(values)>50, 'Not enough captured output'
            lo,hi=values[len(values)//10],values[len(values)*9//10]
            assert lo>expected*.90 and hi<expected*1.10, (phase['position'],gain,lo,hi,expected)
            print('PASS output',phase['position'],'gain',gain,'p10/p90',round(lo/expected,4),round(hi/expected,4))
        else:
            values=[v for t,v,n in rows if rows[0][0]+1<t<rows[-1][0]-.3]
            assert len(values)>30 and max(values)<1e-7, 'Zero must silence the final output'
            print('PASS digital silence at final output')
    print('PASS final AVPlayer output: cut boundaries, seeks, 100%, 25%, 0%, recovery')
