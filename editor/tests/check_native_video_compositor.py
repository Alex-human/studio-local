"""Opt-in macOS single-clock video-overlay and native transform regression."""
import copy,json,subprocess,sys,tempfile,time
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'engine'))
import project,render,preview

def run(args,**kwargs):return subprocess.run([str(x) for x in args],check=True,timeout=120,**kwargs)
with tempfile.TemporaryDirectory(prefix='studio-native-video-') as directory:
    work=Path(directory);w,h=320,180
    def source(name,fps,shift,markers=False):
        sw,sh=240,160;x=np.arange(sw)[None,:];y=np.arange(sh)[:,None]
        images=[]
        for frame in range(fps*4):
            a=np.zeros((sh,sw,3),np.uint8)
            a[:,:,0]=(x*.7+frame*1.2+shift)%256;a[:,:,1]=(y*1.1+frame*.6)%256;a[:,:,2]=(x*.3+y*.6+shift)%256
            a[15:40,20:60]=[230,40+frame,30]
            if markers:
                for bit in range(7):a[:,round(bit*sw/7):round((bit+1)*sw/7)]=235 if frame & (1<<bit) else 16
            images.append(a.tobytes())
        path=work/(name+'.mp4')
        run([root/'runtime/ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{sw}x{sh}','-r',fps,'-i','-','-an','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',path],input=b''.join(images))
        return render.probe(path)
    assets=[source('base',30,0),source('overlay',24,60)]
    p=project.new(width=w,height=h,fps=30);p['assets']=assets
    p['clips']=[dict(id='base',asset=assets[0]['id'],length=45,**{'in':3},muted=True)]
    test_frames=[0,5,14,15,20,24,25,39,40,44]
    binary=work/'native-video'
    run(['xcrun','swiftc','-swift-version','5','-Onone','-suppress-warnings','-module-cache-path',root/'.build/module-cache',root/'native/Playback.swift',root/'native/VideoCompositor.swift',root/'tests/native_video_compositor.swift','-o',binary,'-framework','AppKit','-framework','AVFoundation','-framework','MediaToolbox','-framework','CoreImage'])
    cases=[]
    cases.append(('neutral',copy.deepcopy(p)))
    q=copy.deepcopy(p);q['clips'][0].update(zoom=1.15,zoomEnd=1.7,x=.3,y=.7,motionOffset=10,motionLength=80,speed=1);cases.append(('base-motion',q))
    q=copy.deepcopy(p);q['clips'][0]['color']=dict(exposure=.2,contrast=1.2,saturation=.6,temperature=.8);cases.append(('base-color',q))
    for style in ['clean','photo']:
        q=copy.deepcopy(p)
        q['graphics']=[dict(id='a',type='video',asset=assets[1]['id'],start=5,length=20,**{'in':5.25},speed=1.4,muted=True,offset=4,motionLength=45,
                            props=dict(x=700,y=460,width=740,rotation=18,opacity=.85,animation='none',style=style,cropLeft=.1,cropTop=.1,cropRight=.05,cropBottom=.15),
                            keyframes=dict(x=[dict(frame=0,value=600),dict(frame=30,value=1000)],width=[dict(frame=0,value=500),dict(frame=30,value=850)]))]
        cases.append(('overlay-'+style,q))
    q=copy.deepcopy(cases[-2][1]);b=copy.deepcopy(q['graphics'][0]);b.update(id='b',start=15,length=25,offset=0,speed=.7);b['in']=35;b['props'].update(x=1200,y=650,width=800,rotation=-12,opacity=.7,cropLeft=0,cropRight=.15);b['keyframes']={};q['graphics'].append(b)
    q['clips']=[dict(id='one',asset=assets[0]['id'],length=20,**{'in':3},speed=1.2,muted=True),dict(id='two',asset=assets[1]['id'],length=25,**{'in':10},speed=.8,muted=True)]
    cases.append(('overlap-cuts-speed',q))
    rotated=work/'rotated.mp4'
    run([root/'runtime/ffmpeg','-v','error','-display_rotation','90','-i',assets[0]['path'],'-c','copy',rotated])
    oriented=render.probe(rotated);q=copy.deepcopy(p);q['assets'].append(oriented);q['clips'][0]['asset']=oriented['id'];cases.append(('orientation',q))
    for fps in [30,24]:
        marked=source('marked'+str(fps),fps,0,markers=True);q=copy.deepcopy(p);q['assets'].append(marked)
        q['graphics']=[dict(id='sample',type='video',asset=marked['id'],start=0,length=45,**{'in':5.25},speed=1.5,muted=True,props=dict(x=960,y=540,width=1920,opacity=1,animation='none',style='clean'))]
        for speed in [.5,1,1.5,2]:
            candidate=copy.deepcopy(q);candidate['graphics'][0]['speed']=speed;cases.append(('sampling-'+str(fps)+'-'+str(speed),candidate))
        if fps==30:
            candidate=copy.deepcopy(q);candidate['graphics'][0].update(speed=1);candidate['graphics'][0]['in']=75;cases.append(('sampling-source-end',candidate))
            # Half a frame past the file end is valid; the exporter holds the last frame there.
            candidate=copy.deepcopy(candidate);candidate['graphics'][0]['in']=75.5;cases.append(('sampling-source-end-hold',candidate))
            # An empty edit delays the file's first picture by 20 ms; both players hold it from frame 0.
            delayed=work/'delayed.mp4';run([root/'runtime/ffmpeg','-v','error','-i',marked['path'],'-c','copy','-output_ts_offset','0.02',delayed])
            late=render.probe(delayed)
            for speed in [1,1.5]:
                candidate=copy.deepcopy(q);candidate['assets'].append(late)
                candidate['graphics'][0].update(asset=late['id'],speed=speed);candidate['graphics'][0]['in']=0;cases.append(('sampling-source-start-hold-'+str(speed),candidate))
    sys.path.insert(0,str(root/'tests'));import test_lut
    graded=test_lut.lut_source(work);q=project.new(width=w,height=h,fps=30);q['assets']=[graded]
    q['clips']=[dict(id='lut',asset=graded['id'],length=30,muted=True,**{'in':0})];cases.append(('lut',q))
    for name,p in cases:
        folder=work/name;folder.mkdir()
        plan=preview.prepare(p,folder,native_images=True,native_text=True,native_motion=True,native_video=True,native_lut=True)
        frames=list(range(45)) if name.startswith('sampling') else [0,15,29] if name=='lut' else test_frames
        plan['testFrames']=frames
        plan['testOrientation']=name=='orientation'
        # Compare the same 320px preview geometry as canonical frame().
        plan['width']=w;plan['height']=h
        path=folder/'plan.json';path.write_text(json.dumps(plan));run([binary,path])
        exported=render.render(p,folder/'canonical',preview=False,with_audio=False)
        raw=render.run(['-v','error','-i',exported['path'],'-an','-f','rawvideo','-pix_fmt','rgb24','-'])
        canonical=np.frombuffer(raw,np.uint8).reshape((-1,h,w,3))
        errors=[]
        for frame in frames:
            a=np.asarray(Image.open(folder/f'native-{frame}.png').convert('RGB'),dtype=float)
            b=canonical[frame].astype(float)
            delta=np.abs(a-b);mean=float(delta.mean());p95=float(np.percentile(delta,95))
            if name.startswith('sampling'):
                def identity(image):return sum((1<<bit) if image[h//2,round((bit+.5)*w/7)].mean()>128 else 0 for bit in range(7))
                assert identity(a)==identity(b),(name,frame,'source frame mismatch',identity(a),identity(b))
            assert mean<9 and p95<28,(name,frame,mean,p95)
            if name=='lut':
                # Core Image receives 8-bit BGRA: the table must still land on the float reference.
                assert plan['clips'][0].get('lut'),'LUT clip was not played natively'
                bands=lambda image:np.array([image[k*test_lut.ROWS+4:(k+1)*test_lut.ROWS-4,4:w-4].reshape(-1,3).mean(0) for k in range(len(test_lut.BANDS))])
                reference=test_lut.expected(graded['path']);band=np.abs(bands(a)-bands(reference)).max()
                ramp=np.abs(a[160:170,4:w-4]-reference[160:170,4:w-4]).max()
                assert band<=2 and ramp<=4,(name,frame,band,ramp)
            errors.append((mean,p95))
        print('PASS',name,len(frames),'snapshots; max mean',round(max(x[0] for x in errors),2),'max p95',round(max(x[1] for x in errors),1))
