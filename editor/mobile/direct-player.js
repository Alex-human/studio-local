// The montage is an edit list, not a newly encoded movie. One audio clock drives everything.
const clamp = (x, lo=0, hi=1) => Math.max(lo,Math.min(hi,x));
const smooth = x => {x=clamp(x);return x*x*(3-2*x);};
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
export function animated(item, local) {
  const props={...item.props};
  for(const [key,points] of Object.entries(item.keyframes||{})) {
    const sorted=[...points].sort((a,b)=>a.frame-b.frame);
    if(!sorted.length)continue;
    let a=sorted[0],b=sorted.at(-1);
    for(let i=1;i<sorted.length;i++)if(local<sorted[i].frame){a=sorted[i-1];b=sorted[i];break;}
    props[key]=local<=a.frame?a.value:local>=b.frame?b.value:a.value+(b.value-a.value)*smooth((local-a.frame)/(b.frame-a.frame));
  }
  return props;
}
export function audioLevel(item, local) {
  const t=local+(item.fadeOffset||0), duration=item.fadeLength??item.length;
  const fadeIn=Math.min(duration,item.fadeIn||0),fadeOut=Math.min(duration,item.fadeOut||0);
  let gain=(item.volume??1)*(fadeIn?clamp(t/fadeIn):1)*(fadeOut?clamp((duration-t)/fadeOut):1);
  if(item.deClickLength) {
    const at=local+(item.deClickOffset||0),length=item.deClickLength??item.length;
    gain*=Math.min(clamp(at/.003),clamp((length-at)/.003));
  }
  return gain;
}
export function envelopePoints(item,from,end) {
  const points=new Set([from,end]);
  for(const x of [item.fadeIn||0,(item.fadeLength??item.length)-(item.fadeOut||0)])points.add(clamp(item.start+x-(item.fadeOffset||0),from,end));
  if(item.deClickLength)for(const x of [.003,item.deClickLength-.003])points.add(clamp(item.start+x-(item.deClickOffset||0),from,end));
  const edges=[...points].sort((a,b)=>a-b),result=[from];
  for(let i=1;i<edges.length;i++) {
    const a=edges[i-1],b=edges[i],mid=audioLevel(item,(a+b)/2-item.start);
    const curved=Math.abs(mid-(audioLevel(item,a-item.start)+audioLevel(item,b-item.start))/2)>1e-6;
    const steps=curved?32:1;
    for(let n=1;n<=steps;n++)result.push(a+(b-a)*n/steps);
  }
  return result;
}
function mediaReady(media,time) {
  return media.readyState>=2 && !media.seeking && Math.abs(media.currentTime-time)<.12;
}
async function waitMedia(media,test,current=()=>true) {
  const deadline=performance.now()+20000;
  while(!test()) {
    if(!current())return false;
    if(media.error)throw new Error('No se pudo leer un medio del proyecto.');
    if(performance.now()>deadline)throw new Error('La conexión no ha entregado el vídeo. Vuelve a pulsar reproducir.');
    await sleep(20);
  }
  return current();
}
export class DirectPlayer {
  constructor(viewer,query,onFrame,onState,onError) {
    Object.assign(this,{viewer,query,onFrame,onState,onError,frame:0,rate:1,generation:0,playing:false});
    this.videos=new Map();this.images=new Map();this.audio=new Map();this.pending=new Map();this.ready=new Set();this.sources=new Map();
    this.canvas=document.createElement('canvas');this.canvas.id='composition';this.canvas.hidden=true;viewer.append(this.canvas);
    this.ctx=this.canvas.getContext('2d',{alpha:false});
  }
  // Called directly by the click handler, before any network/promise boundary (iOS).
  unlock() {
    if(!this.audioContext) {
      this.audioContext=new AudioContext({latencyHint:'interactive'});
      this.worklet=this.audioContext.audioWorklet.addModule('/vendor/soundtouch-processor.js');
      this.worklet.catch(()=>{});
    }
    return this.audioContext.resume();
  }
  async load(project,frame) {
    this.stop();this.plan=null;this.frame=frame;
    const generation=this.generation;
    const plan=await this.query({action:'directPlan',project:project.id,revision:project.revision});
    if(generation!==this.generation)return;
    this.plan=plan;
    if(!plan){this.canvas.hidden=true;return false;}
    this.canvas.width=plan.width;this.canvas.height=plan.height;this.canvas.hidden=false;
    this.canvas.style.aspectRatio=`${plan.width}/${plan.height}`;
    this.draw();return true;
  }
  visual(frame=this.frame,ahead=0) {
    const end=frame+ahead*this.plan.fps;
    return [...this.plan.clips.map(c=>({...c,base:true})),...this.plan.layers].filter(x=>x.start<=end&&x.start+x.length>frame);
  }
  audible(t=this.frame/this.plan.fps,ahead=0) {
    return this.plan.audio.filter(x=>x.start<=t+ahead&&x.start+x.length>t);
  }
  async ensure(urls,generation) {
    const missing=[...new Set(urls)].filter(url=>!this.ready.has(url));
    if(!missing.length)return;
    const deadline=performance.now()+180000;
    while(missing.some(url=>!this.ready.has(url))) {
      if(generation!==this.generation)return;
      const result=await this.query({action:'directStatus',urls:missing});
      for(const url of result.ready)this.ready.add(url);
      if(result.failed.length)throw new Error('No se pudo preparar un medio ligero. Revisa la fuente en el Mac.');
      if(performance.now()>deadline)throw new Error('El Mac sigue preparando los medios iniciales. Vuelve a abrir el proyecto en unos minutos.');
      if(missing.some(url=>!this.ready.has(url)))await sleep(500);
    }
  }
  key(item) {return `${item.base?'base':'layer'}:${item.id}`;}
  sourceTime(item,frame) {return Math.max(0,((item.in||0)+(frame-item.start)*(item.speed||1))/this.plan.fps);}
  async picture(item,frame,generation=this.generation) {
    if(generation!==this.generation||!this.plan)return null;
    if(!item.base&&item.type!=='video') {
      if(!this.images.has(item.url)) {
        const image=new Image();image.src=item.url;
        const promise=image.decode().then(()=>image).catch(e=>{this.images.delete(item.url);throw e;});this.images.set(item.url,{image,promise});
      }
      return this.images.get(item.url).promise;
    }
    const key=this.key(item);let slot=this.videos.get(key);
    if(slot&&(slot.url!==item.url||slot.media.error)){slot.media.pause();slot.media.remove();this.videos.delete(key);slot=null;}
    if(!slot) {
      const media=document.createElement('video');media.muted=true;media.playsInline=true;media.preload='auto';
      media.className='source-video';media.src=item.url;this.viewer.append(media);
      slot={media,url:item.url};this.videos.set(key,slot);
    }
    const media=slot.media;
    if(!await waitMedia(media,()=>media.readyState>=1,()=>generation===this.generation))return null;
    const time=Math.min(this.sourceTime(item,frame),Math.max(0,media.duration-1/this.plan.fps));
    if(Math.abs(media.currentTime-time)>.2/this.plan.fps)media.currentTime=time;
    if(!await waitMedia(media,()=>mediaReady(media,time),()=>generation===this.generation))return null;return media;
  }
  async buffer(url) {
    if(this.audio.has(url)){const value=this.audio.get(url);this.audio.delete(url);this.audio.set(url,value);return value;}
    if(!this.pending.has(url)) {
      const promise=(async()=>{
        const response=await fetch(url);if(!response.ok){this.ready.delete(url);throw new Error('No se pudo cargar el audio.');}
        const value=await this.audioContext.decodeAudioData(await response.arrayBuffer());
        this.audio.set(url,value);this.pruneAudio();return value;
      })().finally(()=>this.pending.delete(url));this.pending.set(url,promise);
    }
    return this.pending.get(url);
  }
  pruneAudio() {
    const keep=new Set(this.plan?this.audible(undefined,16).map(x=>x.url):[]);
    let bytes=[...this.audio.values()].reduce((n,b)=>n+b.length*b.numberOfChannels*4,0);
    for(const [url,b] of this.audio)if(bytes>160*1024*1024&&!keep.has(url)) {bytes-=b.length*b.numberOfChannels*4;this.audio.delete(url);}
  }
  async prepare(frame,generation,audio=true) {
    const visual=this.visual(frame),audible=audio?this.audible(frame/this.plan.fps):[];
    await this.ensure([...visual,...audible].map(x=>x.url),generation);
    if(generation!==this.generation)return;
    await Promise.all(visual.map(item=>this.picture(item,frame,generation)));
    if(audio)await Promise.all(audible.map(x=>this.buffer(x.url)));
    if(generation!==this.generation)return;
    this.frame=frame;this.draw();
  }
  async seek(frame) {
    this.stop();this.frame=frame;if(!this.plan)return;
    const generation=this.generation;this.onState(false,true);
    try {await this.prepare(frame,generation,false);if(generation===this.generation){this.onState(false,false);this.prefetch();}}
    catch(e){if(generation===this.generation){this.onState(false,false);this.onError(e);}}
  }
  clock() {
    return this.playing ? Math.min(this.plan.frames-1,this.anchorFrame+Math.max(0,this.audioContext.currentTime-this.anchorTime)*this.rate*this.plan.fps) : this.frame;
  }
  stop() {
    this.frame=this.clock();this.generation++;this.playing=false;cancelAnimationFrame(this.raf);
    for(const node of this.sources.values()){try{node.stop();}catch{}node.disconnect();}this.sources.clear();
    if(this.bus){this.bus.disconnect();this.bus.port?.close();this.bus=null;}
    for(const {media} of this.videos.values())media.pause();
    this.audioContext?.suspend();
    this.onState(false,false);
  }
  async play(frame=this.frame,rate=this.rate) {
    this.stop();this.frame=frame;this.rate=rate;if(!this.plan)return;
    const generation=this.generation;this.onState(true,true);
    try {
      await this.unlock();if(rate!==1)await this.worklet;
      await this.prepare(frame,generation);
      if(generation!==this.generation)return;
      // A new bus for every seek discards old buffered DSP samples.
      this.bus=rate===1?this.audioContext.createGain():new AudioWorkletNode(this.audioContext,'soundtouch-processor',{outputChannelCount:[2],parameterData:{playbackRate:rate}});
      if(rate!==1)this.bus.port.postMessage({type:'set-stretch-parameters',params:{sequenceMs:30,seekWindowMs:10,overlapMs:8}});
      this.bus.connect(this.audioContext.destination);
      await Promise.all(this.visual(frame).filter(x=>x.base||x.type==='video').map(x=>{
        const media=this.videos.get(this.key(x)).media;media.playbackRate=rate;return media.play();
      }));
      if(generation!==this.generation)return;
      this.anchorFrame=frame;this.anchorTime=this.audioContext.currentTime+.025;this.playing=true;
      this.schedule();this.onState(true,false);this.tick();this.prefetch();
    } catch(e) {if(generation===this.generation){for(const {media,url} of this.videos.values())if(media.error)this.ready.delete(url);this.stop();this.onError(e);}}
  }
  schedule() {
    const t=this.clock()/this.plan.fps;
    for(const item of this.audible(t,12)) {
      const key=`${item.id}:${item.start}:${item.url}`;
      if(this.sources.has(key)||!this.audio.has(item.url))continue;
      const from=Math.max(t,item.start),end=item.start+item.length;
      if(end-from<.002)continue;
      const when=Math.max(this.audioContext.currentTime,this.anchorTime+(from-this.anchorFrame/this.plan.fps)/this.rate);
      const source=this.audioContext.createBufferSource(),gain=this.audioContext.createGain();
      source.buffer=this.audio.get(item.url);source.playbackRate.value=this.rate;
      source.connect(gain);gain.connect(this.bus);
      const points=envelopePoints(item,from,end);
      for(const [i,at] of points.entries()) {
        const time=when+(at-from)/this.rate,value=audioLevel(item,at-item.start);
        if(i===0)gain.gain.setValueAtTime(value,time);else gain.gain.linearRampToValueAtTime(value,time);
      }
      source.start(when,item.source+from-item.start,(end-from));
      source.onended=()=>{source.disconnect();gain.disconnect();source.buffer=null;if(this.sources.get(key)===source)this.sources.delete(key);};this.sources.set(key,source);
    }
  }
  prefetch() {
    if(!this.plan||this.prefetching)return;
    const generation=this.generation,frame=this.frame;
    const visual=this.visual(frame,4),audible=this.audioContext?this.audible(frame/this.plan.fps,16):[];
    const keys=new Set(visual.map(x=>this.key(x)));
    for(const [key,{media}] of this.videos)if(!keys.has(key)){media.pause();media.removeAttribute('src');media.load();media.remove();this.videos.delete(key);}
    const imageURLs=new Set(visual.map(x=>x.url));
    for(const url of this.images.keys())if(this.images.size>48&&!imageURLs.has(url))this.images.delete(url);
    this.prefetching=true;
    (async()=>{
      await this.ensure([...visual,...audible].map(x=>x.url),generation);
      if(generation!==this.generation)return;
      await Promise.all([...visual.filter(x=>x.start>frame).map(x=>this.picture(x,x.start,generation)),...audible.map(x=>this.buffer(x.url))]);
    })().catch(()=>{/* A current-media miss is reported by play/seek; speculative misses do not interrupt it. */}).finally(()=>{this.prefetching=false;});
  }
  tick() {
    if(!this.playing)return;
    this.frame=this.clock();const visible=this.visual();
    const missing=visible.some(x=>!this.ready.has(x.url)||(!x.base&&x.type!=='video'&&!this.images.get(x.url)?.image.naturalWidth)||((x.base||x.type==='video')&&(!this.videos.has(this.key(x))||!mediaReady(this.videos.get(this.key(x)).media,this.sourceTime(x,this.frame))))) || this.audible().some(x=>!this.audio.has(x.url));
    if(missing){this.play(this.frame,this.rate);return;}
    for(const item of visible)if(item.base||item.type==='video') {
      const media=this.videos.get(this.key(item)).media;
      if(media.paused){media.playbackRate=this.rate;media.play().catch(e=>{this.stop();this.onError(e);});}
    }
    for(const [key,{media}] of this.videos)if(!visible.some(x=>this.key(x)===key))media.pause();
    this.draw();this.onFrame(Math.round(this.frame));this.schedule();
    if(this.frame>=this.plan.frames-1){this.stop();return;}
    if(!this.lastPrefetch||performance.now()-this.lastPrefetch>1000){this.lastPrefetch=performance.now();this.prefetch();}
    this.raf=requestAnimationFrame(()=>this.tick());
  }
  draw() {
    if(!this.plan)return;
    const ctx=this.ctx,{width:w,height:h,fps}=this.plan;ctx.fillStyle='#000';ctx.fillRect(0,0,w,h);
    for(const item of this.visual()) {
      const source=(item.base||item.type==='video')?this.videos.get(this.key(item))?.media:this.images.get(item.url)?.image;
      if(!source||(!source.videoWidth&&!source.naturalWidth)||(source.readyState!==undefined&&source.readyState<2))continue;
      const local=this.frame-item.start+(item.offset||0),props=animated(item,local),s=w/1920;
      ctx.save();
      if(item.base) {
        const iw=source.videoWidth,ih=source.videoHeight;
        const z0=item.zoom||1,z=z0+((item.zoomEnd??z0)-z0)*smooth((this.frame-item.start+(item.motionOffset||0))/Math.max(1,(item.motionLength??item.length)-1));
        const cover=Math.max(w/iw,h/ih)*z,sw=w/cover,sh=h/cover;
        ctx.drawImage(source,(iw-sw)*(item.x??.5),(ih-sh)*(item.y??.5),sw,sh,0,0,w,h);
      } else if(item.kind==='text'||item.type==='text'||item.type==='title') {
        const [x,y,sw,sh]=item.rect;
        const enter=props.animation==='none'?1:smooth(local/fps/(props.enter||.45));
        const exit=props.animation==='none'?1:smooth(((item.motionLength??item.length)-local)/fps/.2);
        ctx.globalAlpha=clamp(enter*exit*(props.opacity??1));
        ctx.drawImage(source,x,y+(1-enter)*35*s,sw,sh);
      } else {
        const sw=item.sourceWidth,sh=item.sourceHeight;
        const l=props.cropLeft||0,r=props.cropRight||0,t=props.cropTop||0,b=props.cropBottom||0;
        const u=clamp(local/fps/Math.max(.01,props.enter??.48)),ease=1-(1-u)**4,animation=props.animation||'pop';
        const motion=animation==='pop'?.88+.12*ease:1;
        const dx=animation==='from-left'?-180*(1-ease):animation==='from-right'?180*(1-ease):0;
        const dy=animation==='from-top'?-150*(1-ease):animation==='from-bottom'?150*(1-ease):0;
        const width=(props.width??760)*s*motion,height=width*(sh*(1-t-b))/(sw*(1-l-r));
        ctx.globalAlpha=clamp((props.opacity??1)*(animation==='none'?1:Math.min(1,u*4))*(item.type==='image'?smooth(((item.motionLength??item.length)-local)/fps/.2):1));
        ctx.translate(((props.x??960)+dx)*s,((props.y??540)+dy)*s);ctx.rotate((props.rotation||0)*Math.PI/180);
        const photo=(props.style??'photo')==='photo',pad=photo?Math.max(2,Math.round(12*s)):0;
        if(photo){ctx.fillStyle='#f6f7fa';ctx.shadowColor='#0005';ctx.shadowBlur=18*s;ctx.shadowOffsetY=12*s;ctx.fillRect(-width/2-pad,-height/2-pad,width+2*pad,height+2*pad);ctx.shadowColor='transparent';}
        ctx.beginPath();ctx.roundRect(-width/2,-height/2,width,height,photo?8*s:0);ctx.clip();
        // Proxy dimensions differ from the originals, but crop fractions do not.
        const iw=source.videoWidth||source.naturalWidth,ih=source.videoHeight||source.naturalHeight;
        ctx.drawImage(source,iw*l,ih*t,iw*(1-l-r),ih*(1-t-b),-width/2,-height/2,width,height);
      }
      ctx.restore();
    }
  }
  release() {
    this.stop();for(const {media} of this.videos.values()){media.removeAttribute('src');media.load();media.remove();}this.videos.clear();
  }
}
