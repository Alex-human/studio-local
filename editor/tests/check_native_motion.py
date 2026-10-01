"""Compare native image motion against canonical Pillow output, using disposable fixtures."""
import copy,json,subprocess,sys,tempfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'engine'))
import graphics

def run(args):subprocess.run([str(a) for a in args],check=True,timeout=120)

with tempfile.TemporaryDirectory(prefix='studio-native-motion-') as directory:
    work=Path(directory);w,h=640,360;sw,sh=160,100;sc=w/1920
    pixels=np.zeros((sh,sw,4),dtype=np.uint8)
    pixels[:,:,0]=np.arange(sw)[None,:]*1.5;pixels[:,:,1]=np.arange(sh)[:,None]*2.5
    pixels[:,:,2]=140;pixels[:,:,3]=255
    source=Image.fromarray(pixels);ImageDraw.Draw(source).rectangle((45,30,90,65),fill=(0,0,0,0));source.save(work/'source.png')
    base=dict(kind='image',path=str(work/'source.png'),sourceWidth=sw,sourceHeight=sh,start=5,length=80,offset=0,motionLength=80,
              props=dict(asset='fixture',x=960,y=540,width=650,rotation=0,opacity=1,enter=.48,style='clean',animation='none'),keyframes={})
    cases=[]
    def add(name,spec,frame):
        local=frame-spec['start']+spec['offset'];p=graphics.keyframed(spec['props'],spec['keyframes'],local)
        dx,dy,scale,alpha=graphics.image_motion(p,local/30)
        left=min(sw-1,max(0,round(sw*p.get('cropLeft',0))));top=min(sh-1,max(0,round(sh*p.get('cropTop',0))))
        right=max(left+1,round(sw*(1-p.get('cropRight',0))));bottom=max(top+1,round(sh*(1-p.get('cropBottom',0))))
        iw=max(2,round(p['width']*sc*scale));ih=max(2,round(iw*(bottom-top)/(right-left)))
        pad=max(2,round(12*sc)) if p['style']=='photo' else 0
        panel=Image.new('RGBA',(iw+2*pad,ih+2*pad))
        if p.get('rotation'):panel=panel.rotate(-p['rotation'],Image.Resampling.BICUBIC,expand=True)
        pw,ph=panel.size;x=round((p['x']+dx)*sc-pw/2);y=round((p['y']+dy)*sc-ph/2)
        alpha*=graphics.smooth((spec['motionLength']-local)/30/.2)*p['opacity']
        expected=dict(props={k:v for k,v in p.items() if isinstance(v,(int,float))},width=pw,height=ph,x=x+pw/2,y=h-(y+ph/2),opacity=max(0,min(1,alpha)),
                      cropX=left/sw,cropY=(sh-bottom)/sh,cropWidth=(right-left)/sw,cropHeight=(bottom-top)/sh)
        cases.append(dict(name=name,spec=spec,frame=frame,expected=expected))
        g=dict(id='g',type='image',start=spec['start'],length=spec['length'],offset=spec['offset'],motionLength=spec['motionLength'],props=spec['props'],keyframes=spec['keyframes'])
        project=dict(fps=30,assets=[dict(id='fixture',path=str(work/'source.png'))],graphics=[g],captions=[])
        graphics.composite(Image.new('RGB',(w,h),(40,50,60)),project,frame).save(work/(name+'-canonical.png'))
    for style,rotation in [('clean',0),('clean',27),('photo',0),('photo',-23),('photo',90)]:
        spec=copy.deepcopy(base);spec['props'].update(style=style,rotation=rotation,cropLeft=.13,cropRight=.17,cropTop=.11,cropBottom=.22)
        add(style+str(rotation),spec,20)
    moving=copy.deepcopy(base);moving['offset']=7;moving['motionLength']=100;moving['props']['animation']='from-left'
    moving['keyframes']={key:[dict(frame=20,value=b),dict(frame=0,value=a),dict(frame=20,value=c),dict(frame=40,value=d)] for key,a,b,c,d in
                        [('x',600,1000,900,1200),('y',400,500,550,600),('width',400,650,700,450),('rotation',-20,10,0,15),
                         ('opacity',.2,1,.9,.4),('enter',.2,.7,.4,.5),('cropLeft',0,.15,.2,.3),('cropRight',.1,.2,.1,0),
                         ('cropTop',0,.15,.05,.1),('cropBottom',.2,0,.1,.15)]}
    early=copy.deepcopy(moving);early['offset']=0
    for points in early['keyframes'].values():
        for point in points:point['frame']+=10
    add('before-first-point',early,8)
    for local in [7,10,19,20,21,30,40,79,97,99]:
        spec=copy.deepcopy(moving)
        if local>=80:spec['offset']=local;spec['motionLength']=100
        add('animated'+str(local),spec,spec['start']+local-spec['offset'])
    for animation in ['pop','from-left','from-right','from-top','from-bottom','none']:
        spec=copy.deepcopy(base);spec['props']['animation']=animation
        add('entrance-'+animation,spec,8)
        if animation=='pop':add('entrance-zero',copy.deepcopy(spec),5)
    for crop in [('cropLeft','cropRight'),('cropTop','cropBottom')]:
        spec=copy.deepcopy(base);spec['keyframes']={key:[dict(frame=0,value=.8),dict(frame=20,value=.9)] for key in crop}
        if crop[0]=='cropLeft':spec['props']['width']=6
        add('crossed-'+crop[0],spec,15)
    path=work/'fixture.json';path.write_text(json.dumps(dict(width=w,height=h,cases=cases)))
    run(['xcrun','swiftc','-swift-version','5','-Onone','-suppress-warnings','-module-cache-path',root/'.build/module-cache',root/'native/Playback.swift',root/'native/VideoCompositor.swift',root/'tests/native_motion.swift','-o',work/'native-motion','-framework','AppKit','-framework','AVFoundation','-framework','MediaToolbox','-framework','CoreImage'])
    run([work/'native-motion',path])
    for case in cases:
        name=case['name'];native=np.asarray(Image.open(work/(name+'-native.png')).convert('RGB'),dtype=float)
        canonical=np.asarray(Image.open(work/(name+'-canonical.png')).convert('RGB'),dtype=float)
        delta=np.abs(native-canonical);mean=float(delta.mean());p99=float(np.percentile(delta,99))
        assert mean<.65 and p99<12,(name,mean,p99)
        print('PASS raster',name,'mean',round(mean,3),'p99',round(p99,1))
