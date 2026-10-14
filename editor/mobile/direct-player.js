// The montage is an edit list, not a newly encoded movie. One audio clock drives everything.
const clamp = (x, lo=0, hi=1) => Math.max(lo,Math.min(hi,x));
const smooth = x => {x=clamp(x);return x*x*(3-2*x);};
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
// Nothing the phone waits for may wait for ever.
const within = (promise,ms,message) => Promise.race([promise,sleep(ms).then(()=>{throw new Error(message);})]);
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
const video = item => item.base||item.type==='video';
// What the link carried and for how long some download was running: its real rate, however many share it.
const meter = () => ({bytes:0,ms:0,skips:0,running:0,
  start() {if(!this.running++)this.since=performance.now();},
  end() {if(!--this.running)this.ms+=performance.now()-this.since;},
  kbps() {return Math.round(this.bytes*8/(this.ms+(this.running?performance.now()-this.since:0)))||undefined;}});
// What the speed processor holds: sound comes out of it this long after going in (measured at every speed, at 44.1 and 48 kHz).
const STRETCH=.037;
const undecodable = () => Object.assign(new Error('Este navegador no ha podido descodificar el vídeo: se usa la previsualización compuesta.'),{name:'EncodingError'});
// The index of a proxy as direct.py writes it: one H.264 track without reordering, the index before the samples.
// null until all of the index has arrived.
export function sampleTable(bytes) {
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),u32=at=>view.getUint32(at);
  // The content of the first box of a type within a range, once all of it is there.
  const box=(range,type)=>{
    for(let at=range?.[0];at+8<=range?.[1]&&u32(at)>=8;at+=u32(at))
      if(String.fromCharCode(...bytes.subarray(at+4,at+8))===type)return at+u32(at)<=range[1]?[at+8,at+u32(at)]:undefined;
  };
  const moov=box([0,bytes.length],'moov');if(!moov)return null;
  const mdia=box(box(moov,'trak'),'mdia'),stbl=box(box(mdia,'minf'),'stbl'),start=type=>box(stbl,type)[0];
  const mdhd=box(mdia,'mdhd')[0],timescale=u32(mdhd+(bytes[mdhd]?20:12));
  const stsd=start('stsd'),avcC=box([stsd+94,stsd+8+u32(stsd+8)],'avcC');
  if(!avcC||box(stbl,'ctts'))throw undecodable();
  const stsz=start('stsz'),stsc=start('stsc'),stco=start('stco'),stts=start('stts'),stss=box(stbl,'stss');
  const keys=stss&&new Set(Array.from({length:u32(stss[0]+4)},(_,i)=>u32(stss[0]+8+4*i)-1)),samples=[];
  for(let i=0,chunk=0,run=0,left=0,at=0;i<u32(stsz+8);i++,left--) {
    if(!left) {
      while(run+1<u32(stsc+4)&&u32(stsc+8+12*(run+1))<=chunk+1)run++;
      left=u32(stsc+12+12*run);at=u32(stco+8+4*chunk++);
    }
    const size=u32(stsz+4)||u32(stsz+12+4*i);
    samples.push({at,size,key:!keys||keys.has(i),time:0});at+=size;
  }
  for(let entry=0,i=0,ticks=0;entry<u32(stts+4);entry++)
    for(let n=u32(stts+8+8*entry);n&&i<samples.length;n--,ticks+=u32(stts+12+8*entry))samples[i++].time=ticks/timescale;
  return {samples,codec:'avc1.'+[1,2,3].map(i=>bytes[avcC[0]+i].toString(16).padStart(2,'0')).join(''),description:bytes.slice(...avcC),
    width:view.getUint16(stsd+40),height:view.getUint16(stsd+42)};
}
// The sample on screen at a time of its proxy; past its end, the last one, as the export holds it.
const sampleAt = (samples,time) => {
  let lo=0,hi=samples.length-1;
  while(lo<hi){const mid=lo+hi+1>>1;if(samples[mid].time<=time+1e-4)lo=mid;else hi=mid-1;}
  return lo;
};
const keyBefore = (samples,i) => {while(!samples[i].key)i--;return i;};
// A proxy on its way to the phone: its index first, then its samples from the first one wanted, usable as they arrive.
class Media {
  constructor(url,time,net,gone) {Object.assign(this,{url,time,net,gone});this.read(0);}
  async read(from) {
    this.control?.abort();this.done=false;this.lo=this.hi=from;  // At once: asking again for the same place does not start it again.
    const control=this.control=new AbortController();let timer;this.net.start();
    try {
      const response=await fetch(this.url,{signal:control.signal,headers:from?{Range:`bytes=${from}-`}:{}});
      if(!response.ok){this.gone();throw new Error('No se pudo cargar un medio del proyecto.');}
      this.bytes??=new Uint8Array(Number(response.headers.get('Content-Length')));
      for(const body=response.body.getReader();;) {
        // A link that delivers nothing for twenty seconds is given up, and said.
        clearTimeout(timer);timer=setTimeout(()=>control.abort(),20000);
        const {done,value}=await body.read();
        if(control!==this.control)return;
        if(done)break;
        this.bytes.set(value,this.hi);this.hi+=value.length;this.net.bytes+=value.length;
        if(!this.table&&(this.table=sampleTable(this.bytes.subarray(0,this.hi)))) {
          // Wanted from its middle: what lies before is not downloaded.
          const first=this.table.samples[keyBefore(this.table.samples,sampleAt(this.table.samples,this.time))].at;
          if(first>this.hi+65536)return this.read(first);
        }
      }
      this.done=true;
    } catch(e) {
      if(control===this.control)this.error=e.name==='AbortError'?new Error('La conexión no ha entregado un medio a tiempo. Vuelve a pulsar reproducir.'):e;
    } finally {clearTimeout(timer);this.net.end();}
  }
  // A moment before what is arriving begins the download again from its key frame.
  reach(time) {
    if(!this.table)return void(this.time=Math.min(this.time,time));
    const first=this.table.samples[keyBefore(this.table.samples,sampleAt(this.table.samples,time))].at;
    if(first<this.lo)this.read(first);
  }
  have(i) {const sample=this.table.samples[i];return sample.at>=this.lo&&sample.at+sample.size<=this.hi;}
  abort() {this.control?.abort();this.control=null;}
}
// Decodes an item's proxy just ahead of the clock. frames holds what is decoded, in order; the first is the one on screen.
class Reader {
  constructor(media,net) {Object.assign(this,{media,net,frames:[],failures:0});}
  restart(key,time) {
    this.close();this.media.reach(time);this.next=this.from=key;this.flushed=false;
    const {table}=this.media;
    try {
      const decoder=this.decoder=new VideoDecoder({
        output:frame=>{
          if(decoder!==this.decoder)return frame.close();
          this.failures=0;this.frames.push({i:sampleAt(table.samples,frame.timestamp/1e6),frame});
        },
        error:()=>{if(decoder===this.decoder){this.decoder=null;this.failures++;}},
      });
      decoder.configure({codec:table.codec,description:table.description,codedWidth:table.width,codedHeight:table.height,optimizeForLatency:true});
    } catch {this.decoder=null;this.failures++;}
  }
  close() {
    const decoder=this.decoder;this.decoder=null;
    if(decoder&&decoder.state!=='closed')decoder.close();
    for(const {frame} of this.frames.splice(0))frame.close();
  }
  // Brings the decoding to a time of the proxy and `ahead` seconds past it. late: how many frames the one on screen trails it.
  at(time,ahead) {
    const {table}=this.media;this.late=Infinity;
    if(!table)return void this.media.reach(time);
    if(this.failures>2)throw undecodable();
    const {samples}=table,want=sampleAt(samples,time),key=keyBefore(samples,want);
    // Before what is decoded: again from its key frame. A key frame beyond what is being decoded: straight to it.
    if(this.decoder?.state!=='configured'||want<(this.frames[0]?.i??this.from))this.restart(key,time);
    else if(key>this.next){this.next=key;this.net.skips++;}
    while(this.frames.length>1&&this.frames[1].i<=want)this.frames.shift().frame.close();
    if(this.frames[0])this.late=want-this.frames[0].i;
    // As many samples go in as frames are still to come out up to `ahead`, and a few more while the one wanted
    // is not out: a decoder may keep some back.
    let feed=Math.min(sampleAt(samples,time+ahead)-(this.frames.at(-1)?.i??this.from-1)+(this.late?3:0),want+32-this.next);
    while(feed-->0&&this.decoder&&this.next<samples.length&&!(this.decoder.decodeQueueSize>=8)&&this.media.have(this.next)) {
      const sample=samples[this.next++];
      this.decoder.decode(new EncodedVideoChunk({type:sample.key?'key':'delta',timestamp:Math.round(sample.time*1e6),data:this.media.bytes.subarray(sample.at,sample.at+sample.size)}));
    }
    if(this.decoder&&this.next===samples.length&&!this.flushed){this.flushed=true;this.decoder.flush().catch(()=>{});}
  }
}
export class DirectPlayer {
  constructor(viewer,query,onFrame,onState,onError,log=()=>{}) {
    Object.assign(this,{query,onFrame,onState,onError,log,frame:0,rate:1,generation:0,playing:false,net:meter()});
    this.readers=new Map();this.media=new Map();this.images=new Map();this.audio=new Map();this.pending=new Map();this.raw=new Map();this.ready=new Set();this.sources=new Map();
    this.canvas=document.createElement('canvas');this.canvas.id='composition';this.canvas.hidden=true;viewer.append(this.canvas);
    this.ctx=this.canvas.getContext('2d',{alpha:false});
  }
  // Called directly by the click handler, before any network/promise boundary (iOS).
  // The sound device runs from the first play until the montage is left: a pause does not suspend it. One that is
  // not running is not woken up either: the play gets a new one, as reopening the page would.
  unlock() {
    if(this.audioContext?.state==='running')return Promise.resolve();
    if(!this.starting) {
      this.audioContext?.close().catch(()=>{});
      // Like a video element, it sounds with the iPhone's ringer switch off.
      try{navigator.audioSession.type='playback';}catch{}
      const context=this.audioContext=new AudioContext({latencyHint:'interactive'});
      this.stretch=new Map();this.settled=0;
      this.worklet=context.audioWorklet.addModule('/vendor/soundtouch-processor.js');
      this.worklet.catch(()=>{});
      // The state decides: on iOS the promise of resume() does not always settle.
      this.starting=Promise.race([context.resume(),sleep(3000)]).then(()=>{
        if(context.state!=='running')throw new Error('El iPhone no ha activado el sonido. Vuelve a pulsar reproducir.');
      }).finally(()=>{this.starting=null;});
    }
    return this.starting;
  }
  async load(project,frame) {
    this.stop();this.plan=null;this.frame=frame;this.project=project;
    // A browser without a video decoder of its own gets the composed preview.
    if(this.broken||typeof VideoDecoder!=='function'){this.release();this.canvas.hidden=true;return false;}
    return this.replan();
  }
  // Asks the Mac for the montage in the picture this screen shows and this link carries.
  async replan() {
    const generation=this.generation,started=performance.now();
    const size=globalThis.matchMedia?.('(min-width: 900px) and (pointer: fine)').matches?1920:this.slow?640:1280;
    const plan=await this.query({action:'directPlan',project:this.project.id,revision:this.project.revision,frame:Math.round(this.frame),size,player:2});
    if(generation!==this.generation)return;
    this.plan=plan;this.size=size;
    if(!plan){this.release();this.canvas.hidden=true;return false;}
    this.log('plan',{ms:Math.round(performance.now()-started),size});
    for(const {url} of [...plan.clips,...plan.layers,...plan.audio])plan.pending.includes(url)?this.ready.delete(url):this.ready.add(url);
    // Sizing a canvas erases it; after an edit the picture on screen stays until the new one is drawn.
    if(this.canvas.width!==plan.width||this.canvas.height!==plan.height){this.canvas.width=plan.width;this.canvas.height=plan.height;}
    this.canvas.hidden=false;this.canvas.style.aspectRatio=`${plan.width}/${plan.height}`;
    this.draw();return true;
  }
  visual(frame=this.frame,ahead=0) {
    const end=frame+ahead*this.plan.fps;
    return [...this.plan.clips,...this.plan.layers].filter(x=>x.start<=end&&x.start+x.length>frame);
  }
  // The text under a tap on the picture, the one drawn last first.
  textAt({clientX,clientY}) {
    const box=this.canvas.getBoundingClientRect(),{width:w,height:h}=this.plan,s=Math.min(box.width/w,box.height/h);
    const x=(clientX-box.left-(box.width-w*s)/2)/s,y=(clientY-box.top-(box.height-h*s)/2)/s;
    return this.visual().findLast(({rect:r})=>r&&x>=r[0]&&x<r[0]+r[2]&&y>=r[1]&&y<r[1]+r[3])?.id;
  }
  // The next minute, sound first: it is quick to prepare and playing waits for it.
  ahead(frame) {return [...this.audible(frame/this.plan.fps,60),...this.visual(frame,60)].map(x=>x.url);}
  audible(t=this.frame/this.plan.fps,ahead=0) {
    return this.plan.audio.filter(x=>x.start<=t+ahead&&x.start+x.length>t);
  }
  // Waits for urls; ahead only tells the Mac what to prepare next.
  async ensure(urls,generation,ahead=[]) {
    const pending=list=>[...new Set(list)].filter(url=>!this.ready.has(url));
    const missing=pending(urls),deadline=performance.now()+180000;
    for(;;) {
      const wanted=pending([...missing,...ahead]).slice(0,100);
      if(!wanted.length||generation!==this.generation)return;
      const request=this.query({action:'directStatus',urls:wanted}).then(result=>{for(const url of result.ready)this.ready.add(url);return result;});
      if(!pending(missing).length){request.catch(()=>{});return;}
      const result=await request;
      if(result.failed.some(url=>missing.includes(url)))throw new Error('No se pudo preparar un medio ligero. Revisa la fuente en el Mac.');
      if(performance.now()>deadline)throw new Error('El Mac sigue preparando los medios iniciales. Vuelve a abrir el proyecto en unos minutos.');
      if(!pending(missing).length)return;
      await sleep(150);
    }
  }
  key(item) {return `${item.base?'base':'layer'}:${item.id}`;}
  sourceTime(item,frame) {return Math.max(0,((item.in||0)+(frame-item.start)*(item.speed||1))/this.plan.fps);}
  // The download of an item's proxy, begun where the item first needs it. retry: one that failed is asked for again.
  fetched(item,frame,retry) {
    let media=this.media.get(item.url);
    if(media?.error&&retry){this.media.delete(item.url);media=null;}
    if(!media)this.media.set(item.url,media=new Media(item.url,this.sourceTime(item,Math.max(frame,item.start)),this.net,()=>this.ready.delete(item.url)));
    return media;
  }
  reader(item,frame,retry) {
    const key=this.key(item),media=this.fetched(item,frame,retry);let reader=this.readers.get(key);
    if(reader?.media!==media){reader?.close();this.readers.set(key,reader=new Reader(media,this.net));}
    return reader;
  }
  // The exact frame of an item, decoded.
  async picture(item,frame,generation=this.generation) {
    if(generation!==this.generation||!this.plan)return null;
    if(!video(item)) {
      if(!this.images.has(item.url)) {
        const image=new Image();image.src=item.url;
        const promise=image.decode().then(()=>image).catch(e=>{this.images.delete(item.url);throw e;});this.images.set(item.url,{image,promise});
      }
      return this.images.get(item.url).promise;
    }
    const reader=this.reader(item,frame,true),time=this.sourceTime(item,frame),deadline=performance.now()+20000;
    for(let owed;;) {
      if(reader.media.error)throw reader.media.error;
      reader.at(time,0);
      if(!reader.late)return reader;
      // Five seconds with its samples here and no frame: this browser does not decode them.
      owed=reader.media.table&&reader.media.have(sampleAt(reader.media.table.samples,time))?owed||performance.now():0;
      if(owed&&performance.now()-owed>5000)throw undecodable();
      if(performance.now()>deadline)throw new Error('La conexión no ha entregado el vídeo. Vuelve a pulsar reproducir.');
      await sleep(10);
      if(generation!==this.generation||this.readers.get(this.key(item))!==reader)return null;
    }
  }
  // What an item shows up to a frame of the montage is on the phone.
  async arrived(item,frame,until,generation) {
    const from=this.sourceTime(item,Math.max(frame,item.start)),to=this.sourceTime(item,Math.min(until,item.start+item.length-1)),media=this.fetched(item,frame,true);
    while(generation===this.generation&&this.media.get(item.url)===media) {
      if(media.error)throw media.error;
      media.reach(from);
      if(media.table&&media.have(sampleAt(media.table.samples,to)))return;
      await sleep(20);
    }
  }
  // Sound downloads as soon as its place is near; decoding waits for the audio context the first tap creates.
  bytes(url) {
    if(this.raw.has(url))return this.raw.get(url).promise;
    const control=new AbortController(),timer=setTimeout(()=>control.abort(),20000),entry={abort:()=>control.abort()};this.net.start();
    entry.promise=fetch(url,{signal:control.signal}).then(async response=>{
      if(!response.ok){this.ready.delete(url);throw new Error('No se pudo cargar un medio del proyecto.');}
      const data=await response.arrayBuffer();this.net.bytes+=data.byteLength;return data;
    }).catch(e=>{
      if(this.raw.get(url)===entry)this.raw.delete(url);
      throw e.name==='AbortError'?new Error('La conexión no ha entregado un medio a tiempo. Vuelve a pulsar reproducir.'):e;
    }).finally(()=>{clearTimeout(timer);this.net.end();});
    entry.promise.catch(()=>{});this.raw.set(url,entry);return entry.promise;
  }
  // Leaves what the place being watched will not use: downloads on their way are given up, what is here is freed.
  forget(frame) {
    const fps=this.plan.fps,reach=20*this.rate,kept=new Set([...this.visual(frame-10*fps,reach+10),...this.audible(frame/fps,reach)].map(x=>x.url));
    for(const store of [this.media,this.raw])for(const [url,entry] of store)if(!kept.has(url)){entry.abort();store.delete(url);}
  }
  async buffer(url) {
    if(this.audio.has(url)){const value=this.audio.get(url);this.audio.delete(url);this.audio.set(url,value);return value;}
    if(!this.pending.has(url)) {
      const promise=(async()=>{
        const data=await this.bytes(url);this.raw.delete(url);
        // Decoded apart from the sound device, which a visit may replace.
        const value=await within((this.decoder??=new OfflineAudioContext(2,1,48000)).decodeAudioData(data).catch(()=>{throw new Error('No se pudo leer el sonido de este tramo.');}),15000,'El sonido de este tramo no ha terminado de prepararse. Vuelve a pulsar reproducir.');
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
  // why: what interrupted the playback, if anything did. It then plays on with four seconds of watching already
  // on the phone, not with the next frame alone.
  async prepare(frame,generation,audio=true,why) {
    const fps=this.plan.fps,lead=(why?4:2)*this.rate,visual=this.visual(frame),audible=audio?this.audible(frame/fps,lead):[];
    const cushion=why?this.visual(frame,lead).filter(video):[];
    this.forget(frame);
    await this.ensure([...visual,...audible,...cushion].map(x=>x.url),generation,this.ahead(frame));
    if(generation!==this.generation)return;
    await Promise.all([...cushion.map(x=>this.arrived(x,frame,frame+lead*fps,generation)),...visual.map(item=>this.picture(item,frame,generation))]);
    if(audio)await Promise.all(audible.map(x=>this.buffer(x.url)));
    if(generation!==this.generation)return;
    this.frame=frame;this.draw();
  }
  async seek(frame) {
    this.stop();this.frame=frame;if(!this.plan)return;
    const generation=this.generation,started=performance.now();this.onState(false,true);
    try {
      await this.prepare(frame,generation,false);
      if(generation===this.generation){this.onState(false,false);this.prefetch();this.log('seek',{frame:Math.round(frame),ms:Math.round(performance.now()-started)});}
    } catch(e){if(generation===this.generation){this.onState(false,false);this.fail(e,'seek');}}
  }
  fail(e,where) {
    this.log('error',{where,frame:Math.round(this.frame),message:String(e?.message||e)});
    if(e?.name==='EncodingError'){this.broken=true;this.release();this.canvas.hidden=true;}
    this.onError(e);
  }
  clock() {
    return this.playing ? Math.min(this.plan.frames-1,this.anchorFrame+Math.max(0,this.audioContext.currentTime-this.anchorTime)*this.rate*this.plan.fps) : this.frame;
  }
  // Ends what is playing and keeps what is loaded. The sound of a play goes through one gain that fades it in and out
  // over a few milliseconds: a waveform started or cut in mid-swing is a thump.
  halt() {
    if(this.playing)this.log('played',{...this.run,skips:this.net.skips-this.run.skips,to:Math.round(this.clock()),s:+((performance.now()-this.run.at)/1000).toFixed(1),at:undefined});
    this.frame=this.clock();this.generation++;this.playing=false;cancelAnimationFrame(this.raf);
    if(this.bus) {
      const now=this.audioContext.currentTime,level=this.bus.gain;
      level.cancelScheduledValues(now);level.setValueAtTime(level.value,now);level.linearRampToValueAtTime(0,now+.015);
      for(const node of this.sources.values())try{node.stop(now+.02);}catch{}
      // What the speed processor still holds leaves it into silence, not into the next play.
      this.feed?.stop(now+.1);this.settled=now+.02+this.delay;this.bus=this.feed=null;
    }
    this.sources.clear();
  }
  stop() {this.halt();this.onState(false,false);}
  async play(frame=this.frame,rate=this.rate,why) {
    this.halt();this.frame=frame;this.rate=rate;if(!this.plan)return;
    const generation=this.generation,started=performance.now(),took=()=>Math.round(performance.now()-started);this.onState(true,true);
    try {
      await this.unlock();if(rate!==1)await within(this.worklet,10000,'No se pudo preparar el cambio de velocidad. Vuelve a pulsar reproducir.');
      const unlocked=took();
      await this.prepare(frame,generation,true,why);
      if(generation!==this.generation)return;
      // Silent until its fade: a source may start one sample before the instant the fade is set for.
      const context=this.audioContext,now=context.currentTime;this.bus=context.createGain();this.bus.gain.value=0;this.delay=0;
      let to=context.destination;
      if(rate!==1) {
        if(!this.stretch.has(rate)) {
          // One speed processor per speed for as long as the sound device lasts: one let go would keep running until
          // the page closes, and a new one, or one whose speed changes, leaves holes until silence has filled it.
          const stretch=new AudioWorkletNode(context,'soundtouch-processor',{outputChannelCount:[2],parameterData:{playbackRate:rate}});
          stretch.port.postMessage({type:'set-stretch-parameters',params:{sequenceMs:30,seekWindowMs:10,overlapMs:8}});
          stretch.connect(to);this.stretch.set(rate,stretch);this.settled=now+.2;
        }
        to=this.stretch.get(rate);this.delay=STRETCH;
        // Silence keeps it working through the play and past its end: without input it stops with sound inside.
        this.feed=context.createConstantSource();this.feed.offset.value=0;this.feed.connect(to);this.feed.start();
      }
      this.bus.connect(to);
      // The clock starts when the sound is heard: after what played before has left, and after the processor's delay.
      this.anchorFrame=frame;this.anchorTime=Math.max(now+.025,this.settled)+this.delay;this.playing=true;
      this.bus.gain.setValueAtTime(0,this.anchorTime-this.delay);this.bus.gain.linearRampToValueAtTime(1,this.anchorTime-this.delay+.02);
      this.run={from:Math.round(frame),rate,why,ms:took(),unlock:unlocked,prepare:took()-unlocked,kbps:this.net.kbps(),at:performance.now(),late:0,skips:this.net.skips,
        hz:context.sampleRate,out:Math.round(((context.baseLatency||0)+(context.outputLatency||0))*1000)};
      this.schedule();this.onState(true,false);this.tick();this.prefetch();
    } catch(e) {if(generation===this.generation){this.stop();this.fail(e,'play');}}
  }
  schedule() {
    // Sound goes into the speed processor its delay ahead of the clock.
    const start=this.anchorFrame/this.plan.fps,fed=this.anchorTime-this.delay,t=start+Math.max(0,this.audioContext.currentTime-fed)*this.rate;
    for(const item of this.audible(t,12)) {
      const key=`${item.id}:${item.start}:${item.url}`;
      if(this.sources.has(key)||!this.audio.has(item.url))continue;
      const from=Math.max(t,item.start),end=item.start+item.length;
      if(end-from<.002)continue;
      const when=Math.max(this.audioContext.currentTime,fed+(from-start)/this.rate);
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
  // Downloads what twenty seconds of watching use.
  prefetch() {
    if(!this.plan)return;
    const generation=this.generation,frame=this.frame,fps=this.plan.fps,reach=20*this.rate;
    const near=this.visual(frame,4),keys=new Set(near.map(x=>this.key(x)));
    for(const [key,reader] of this.readers)if(!keys.has(key)){reader.close();this.readers.delete(key);}
    const imageURLs=new Set(near.map(x=>x.url));
    for(const url of this.images.keys())if(this.images.size>48&&!imageURLs.has(url))this.images.delete(url);
    for(const x of near)if(x.start>frame&&!video(x))this.picture(x,x.start,generation).catch(()=>{});
    if(this.prefetching===generation)return;
    // One at a time, so that each has the whole link: the sound, which is small, then the pictures from the one on screen.
    const queue=[...this.audible(frame/fps,reach),...this.visual(frame,reach).filter(video)];
    this.forget(frame);this.prefetching=generation;
    (async()=>{
      for(const x of queue) {
        await this.ensure([x.url],generation,this.ahead(frame));
        if(generation!==this.generation)return;
        if(!video(x))await (this.audioContext?this.buffer(x.url):this.bytes(x.url));
        else await this.arrived(x,frame,x.start+x.length,generation);
      }
    })().catch(()=>{/* A current-media miss is reported by play/seek; speculative misses do not interrupt it. */}).finally(()=>{if(this.prefetching===generation)this.prefetching=null;});
  }
  tick() {
    if(!this.playing)return;
    this.frame=this.clock();const now=performance.now();
    // Sound or a picture that is not there stops the clock.
    let missing=this.audible().some(x=>!this.audio.has(x.url))&&'sound';
    try {
      // What shows is decoded a little ahead of the clock, and what the next second and a half brings waits on its
      // first frame: a cut or the end of a proxy costs nothing.
      for(const item of this.visual(this.frame,1.5*this.rate)) {
        const soon=item.start>this.frame;
        if(!this.ready.has(item.url)){if(!soon)missing||='pending';continue;}
        if(!video(item)){if(!soon&&!this.images.get(item.url)?.image.naturalWidth)missing||='image';continue;}
        const reader=this.reader(item,this.frame);
        if(reader.media.error){if(!soon)missing||='download';continue;}
        reader.at(this.sourceTime(item,Math.max(this.frame,item.start)),soon?0:.12*this.rate);
        if(soon)continue;
        // Late and not moving for a quarter of a second: nothing to show next. Late but moving, it catches up by itself.
        const head=reader.frames[0]?.i;
        if(!reader.late||head!==reader.head||!reader.moved){reader.head=head;reader.moved=now;}
        else if(now-reader.moved>250)missing||=reader.media.table&&reader.next<reader.media.table.samples.length&&!reader.media.have(reader.next)?'download':'decode';
        if(reader.late<Infinity)this.run.late=Math.max(this.run.late,reader.late);
      }
      if(!missing)this.draw();
    } catch(e){this.stop();this.fail(e,'decode');return;}
    if(missing) {
      this.log('wait',{why:missing,frame:Math.round(this.frame)});
      // A decoder that stopped giving frames is replaced.
      if(missing==='decode')for(const reader of this.readers.values())reader.close();
      // A link that does not carry the sharp picture gets the light one for the rest of the visit.
      if(missing!=='download'||this.size!==1280)return void this.play(this.frame,this.rate,missing);
      this.slow=true;this.halt();this.onState(true,true);
      this.replan().then(ok=>ok&&this.play(this.frame,this.rate,missing)).catch(e=>{this.stop();this.fail(e,'play');});
      return;
    }
    this.onFrame(Math.round(this.frame));this.schedule();
    if(this.frame>=this.plan.frames-1){this.stop();return;}
    if(!this.lastPrefetch||performance.now()-this.lastPrefetch>1000){this.lastPrefetch=performance.now();this.prefetch();}
    this.raf=requestAnimationFrame(()=>this.tick());
  }
  draw() {
    if(!this.plan)return;
    const visible=this.visual().map(item=>[item,video(item)?this.readers.get(this.key(item))?.frames[0]?.frame:this.images.get(item.url)?.image]);
    // While a video is on its way the last picture stays, as in any editor.
    if(visible.some(([item,source])=>video(item)&&!source))return;
    const ctx=this.ctx,{width:w,height:h,fps}=this.plan;ctx.fillStyle='#000';ctx.fillRect(0,0,w,h);
    // A browser that cannot draw what it decoded gets the composed preview.
    try {for(const [item,source] of visible) {
      if(!(source?.displayWidth||source?.naturalWidth))continue;
      const local=this.frame-item.start+(item.offset||0),props=animated(item,local),s=w/1920;
      ctx.save();
      if(item.base) {
        const iw=source.displayWidth,ih=source.displayHeight;
        const z0=item.zoom||1,z=z0+((item.zoomEnd??z0)-z0)*smooth((this.frame-item.start+(item.motionOffset||0))/Math.max(1,(item.motionLength??item.length)-1));
        const cover=Math.max(w/iw,h/ih)*z,sw=w/cover,sh=h/cover;
        // The whole frame, placed so that its crop fills the canvas: WebKit ignores the source rectangle of a VideoFrame.
        ctx.drawImage(source,-(iw-sw)*(item.x??.5)*cover,-(ih-sh)*(item.y??.5)*cover,iw*cover,ih*cover);
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
        const iw=source.displayWidth||source.naturalWidth,ih=source.displayHeight||source.naturalHeight;
        ctx.drawImage(source,iw*l,ih*t,iw*(1-l-r),ih*(1-t-b),-width/2,-height/2,width,height);
      }
      ctx.restore();
    }} catch {throw undecodable();}
  }
  release() {
    this.stop();for(const reader of this.readers.values())reader.close();this.readers.clear();
    for(const media of this.media.values())media.abort();this.media.clear();
    this.audioContext?.close().catch(()=>{});this.audioContext=this.starting=null;
  }
}
