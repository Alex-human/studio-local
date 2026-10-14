// The actual player against a real proxy, with a decoder and a connection the test controls. Browser timing is checked separately.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path'),os=require('node:os'),{execFileSync}=require('node:child_process');
// A proxy as direct.py writes it: ten seconds, a key frame every half second, no reordering, the index first.
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'studio-direct-'));
execFileSync(path.join(__dirname,'../runtime/ffmpeg'),['-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=10','-c:v','libx264','-b:v','400k',
  '-g','15','-bf','0','-x264-params','scenecut=0','-pix_fmt','yuv420p','-movflags','+faststart',path.join(folder,'v.mp4')]);
const proxy=new Uint8Array(fs.readFileSync(path.join(folder,'v.mp4')));fs.rmSync(folder,{recursive:true});
// The connection: what was asked for, and how much of a file it lets through.
const files=new Map(),requests=[],limit=new Map();let latency=0;
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),until=async test=>{for(let n=0;n<400&&!test();n++)await sleep(5);assert.ok(test(),'timed out: '+test);};
async function fetch(url,{signal,headers={}}={}) {
  requests.push(url+(headers.Range?' '+headers.Range:''));
  await sleep(latency);
  if(!files.has(url))return {ok:false};
  const from=headers.Range?Number(/bytes=(\d+)-/.exec(headers.Range)[1]):0,data=files.get(url).subarray(from);let at=0;
  const aborted=()=>{if(signal?.aborted)throw Object.assign(new Error('aborted'),{name:'AbortError'});};
  return {ok:true,headers:{get:name=>name==='Content-Length'?String(data.length):null},arrayBuffer:async()=>new ArrayBuffer(8),
    body:{getReader:()=>({async read(){
      while(from+at>=(limit.get(url)??Infinity)){aborted();await sleep(2);}
      aborted();return at<data.length?{done:false,value:data.subarray(at,at=Math.min(at+16384,(limit.get(url)??Infinity)-from))}:{done:true};
    }})}};
}
// The decoder: keeps `hold` frames back like WebKit's, can stay silent, and can refuse the video.
const decoders=[],fed=[];let hold=3,silent=false,refuse=false,open=0;
class VideoDecoder {
  constructor(init){Object.assign(this,{init,state:'unconfigured',decodeQueueSize:0,queue:[]});decoders.push(this);}
  configure(){if(refuse)return queueMicrotask(()=>{this.state='closed';this.init.error(Error('unsupported'));});this.state='configured';}
  decode(chunk){this.queue.push(chunk);fed.push(chunk.timestamp);queueMicrotask(()=>this.emit());}
  emit(all){
    while(this.state==='configured'&&!silent&&this.queue.length>(all?0:hold)) {
      const frame={timestamp:this.queue.shift().timestamp,displayWidth:160,displayHeight:90,close(){open--;}};open++;this.init.output(frame);
    }
  }
  flush(){this.emit(true);return Promise.resolve();}
  close(){this.state='closed';}
}
let offset=0,nodraw=false;const drawn=[],cropped=[];
// Sound: every node records what it is asked; a device starts in the state the test chooses.
const node=()=>{const n={asked:[],playbackRate:{},offset:{},connect(){},disconnect(){},start(...x){n.asked.push(['start',...x]);},stop(...x){n.asked.push(['stop',...x]);}};
  n.gain={value:1,cancelScheduledValues(){},setValueAtTime(...x){n.asked.push(['set',...x]);},linearRampToValueAtTime(...x){n.asked.push(['ramp',...x]);}};return n;};
const devices=[],processors=[];let starts='running',suspended=0,closed=0;
class AudioContext{constructor(){Object.assign(this,{state:starts,currentTime:0,destination:{},audioWorklet:{addModule:async()=>{}},resume:async()=>{},suspend(){suspended++;},close:async()=>{closed++;},
  createGain:node,createBufferSource:node,createConstantSource:node});devices.push(this);}}
class AudioWorkletNode{constructor(context,name,options){this.rate=options.parameterData.playbackRate;this.port={postMessage(){}};processors.push(this);}connect(){}}
class OfflineAudioContext{decodeAudioData(){return Promise.resolve({length:1,numberOfChannels:1});}}
const sandbox={console,setTimeout,clearTimeout,queueMicrotask,AbortController,fetch,VideoDecoder,AudioContext,AudioWorkletNode,OfflineAudioContext,EncodedVideoChunk:class{constructor(x){Object.assign(this,x);}},
  performance:{now:()=>performance.now()+offset},requestAnimationFrame(){},cancelAnimationFrame(){},
  document:{createElement:()=>({style:{},hidden:true,getContext:()=>({fillRect(){},save(){},restore(){},drawImage:(source,...at)=>{if(nodraw)throw TypeError('not drawable');drawn.push(source);if(at.length===8&&source.displayWidth)cropped.push(source);}})})}};
vm.createContext(sandbox);
const code=fs.readFileSync(path.join(__dirname,'../mobile/direct-player.js'),'utf8').replace(/export /g,'');
vm.runInContext(code+'\nObject.assign(this,{DirectPlayer,Media,Reader,sampleTable,audioLevel,envelopePoints});',sandbox);
(async()=>{
 // The index of a real proxy.
 const table=sandbox.sampleTable(proxy),{samples}=table;
 assert.equal(samples.length,300);assert.ok(samples.every((s,i)=>s.key===(i%15===0)),'a key frame every half second');
 assert.ok(Math.abs(samples[45].time-1.5)<1e-9);assert.equal(samples.at(-1).at+samples.at(-1).size,proxy.length,'the samples end where the file does');
 assert.match(table.codec,/^avc1\.[0-9a-f]{6}$/);assert.deepEqual([table.width,table.height],[160,90]);
 assert.equal(sandbox.sampleTable(proxy.subarray(0,300)),null,'no index until all of it has arrived');
 // A proxy downloads from the first sample wanted, and again from an earlier one when that is asked for.
 for(let i=0;i<6;i++){files.set(`/v${i}.mp4`,proxy);files.set(`/a${i}.m4a`,new Uint8Array(8));}
 const net={bytes:0,ms:0,skips:0,start(){},end(){}};let gone=0;
 let media=new sandbox.Media('/v0.mp4',0,net,()=>gone++);await until(()=>media.done);
 assert.deepEqual(requests,['/v0.mp4']);assert.ok(media.have(0)&&media.have(299));assert.equal(net.bytes,proxy.length);
 requests.length=0;const middle=new sandbox.Media('/v0.mp4',7.2,net,()=>gone++);await until(()=>middle.done);
 assert.deepEqual(requests,['/v0.mp4',`/v0.mp4 bytes=${samples[210].at}-`],'wanted from its middle, what lies before is not downloaded');
 assert.ok(!middle.have(209)&&middle.have(210)&&middle.have(299));
 requests.length=0;latency=40;middle.reach(3);const asking=setInterval(()=>middle.reach(3),5);await until(()=>middle.done);clearInterval(asking);latency=0;
 assert.deepEqual(requests,[`/v0.mp4 bytes=${samples[90].at}-`],'asked again while the answer is on its way, it is one download');assert.ok(middle.have(90)&&middle.have(299));
 const missing=new sandbox.Media('/none.mp4',0,net,()=>gone++);await until(()=>missing.error);assert.equal(gone,1,'a proxy the Mac no longer has is asked of it again');
 // Decoding: the exact frame although the decoder keeps some back; forwards it goes on, backwards it starts at the key frame.
 const reader=new sandbox.Reader(media,net),show=async time=>{for(let n=0;n<200;n++){reader.at(time,0);if(!reader.late)return reader.frames[0].i;await sleep(1);}assert.fail('never shown');};
 assert.equal(await show(1.2),36);assert.equal(fed[0],1e6,'decoding starts at the key frame before');
 assert.equal(await show(1.3),39);assert.equal(decoders.length,1,'a later frame of the same group goes on with the same decoder');
 fed.length=0;assert.equal(await show(.7),21);assert.equal(decoders.length,2);assert.equal(fed[0],.5e6,'an earlier frame starts again from its key frame');
 fed.length=0;assert.equal(await show(5.1),153);assert.equal(decoders.length,2);assert.equal(fed[0],5e6);assert.equal(net.skips,1,'far ahead, it goes straight to that key frame');
 assert.equal(await show(99),299,'past the end of its proxy an item holds the last frame');
 reader.close();assert.equal(open,0,'every decoded frame is closed');
 // The player.
 const states=[],errors=[],logs=[],asked=[];
 const plan=size=>({fps:30,frames:1800,width:size,height:size*9/16,layers:[],pending:['/v5.mp4'],clips:[0,1,2,3,4,5].map(i=>({id:'c:'+i,base:true,start:i*300,length:300,in:0,url:`/v${i}.mp4`})),
   audio:[0,1,2,3,4,5].map(i=>({id:'a:'+i,start:i*10,length:10,source:0,volume:1,url:`/a${i}.m4a`}))});
 const query=async req=>{asked.push(req);return req.action==='directPlan'?plan(req.size):{ready:req.urls,failed:[]};};
 const p=new sandbox.DirectPlayer({append(){}},query,()=>{},(...x)=>states.push(x),e=>errors.push(e),(event,data)=>logs.push({event,...data}));
 assert.equal(await p.load({id:'P',revision:1},0.4),true);assert.equal(asked[0].frame,0,'the plan request carries the playhead as a whole frame');
 assert.equal(asked[0].size,1280,'a phone asks for the picture its screen shows');assert.equal(asked[0].player,2);
 sandbox.matchMedia=query=>({matches:query==='(min-width: 900px) and (pointer: fine)'});
 await p.load({id:'P',revision:1},0.4);assert.equal(asked.at(-1).size,1920,'desktop requests HD without changing the project');
 sandbox.matchMedia=()=>({matches:false});
 assert.ok(p.ready.has('/v0.mp4')&&!p.ready.has('/v5.mp4'),'the plan says what the Mac already has, without another round trip');
 asked.length=0;await p.ensure(['/v0.mp4'],p.generation,['/v0.mp4','/v5.mp4']);
 assert.equal(asked.map(x=>x.urls.join()).join('|'),'/v5.mp4','ready media does not wait while the Mac is told what comes next');
 await sleep(1);assert.ok(p.ready.has('/v5.mp4'));asked.length=0;await p.ensure(['/v0.mp4'],p.generation,['/v5.mp4']);assert.equal(asked.length,0);
 // Seeking: a cancelled seek ends without a word; one frame further is one sample further; the picture is the decoded frame.
 const cancelled=p.seek(0);await p.seek(450);await cancelled;
 const second=p.readers.get('base:c:1');assert.equal(second.frames[0].i,150);assert.equal(logs.filter(x=>x.event==='seek').length,1);
 assert.equal(drawn.at(-1),second.frames[0].frame);
 await p.seek(451);assert.equal(second.frames[0].i,151);assert.equal(p.readers.get('base:c:1'),second);
 const pictures=drawn.length;p.frame=700;p.draw();assert.equal(drawn.length,pictures,'while a video is on its way the last picture stays');
 // An edit keeps what is loaded; a montage that stops being playable here drops it.
 await p.load({id:'P',revision:2},451);assert.equal(p.readers.get('base:c:1'),second);
 // Playing: what comes after a cut is decoded before it, so the cut is not a wait.
 await p.unlock();const audio=p.audioContext;
 const clock=frame=>{audio.currentTime=p.anchorTime+(frame-p.anchorFrame)/30;p.tick();};
 await p.play(240,1);assert.equal(p.playing,true);assert.equal(p.readers.get('base:c:0').frames[0].i,240);
 clock(270);await sleep(30);clock(271);await sleep(10);
 assert.equal(p.readers.get('base:c:1').frames[0].i,0,'the first frame after a cut is ready before the cut');
 clock(303);await sleep(10);clock(304);assert.equal(drawn.at(-1),p.readers.get('base:c:1').frames[0].frame);
 assert.equal(logs.filter(x=>x.event==='wait').length,0);assert.equal(p.playing,true);
 // Only a picture that is late and not moving stops the clock, and the log says whether the link or the decoder owed it.
 // It then plays on by itself, once four seconds of watching are on the phone; a link that does not carry the sharp picture gets the light one.
 const waits=()=>logs.filter(x=>x.event==='wait').map(x=>x.why);
 p.media.get('/v2.mp4').abort();p.media.delete('/v2.mp4');limit.set('/v2.mp4',samples[30].at);clock(590);await sleep(30);clock(645);offset+=300;clock(645);
 assert.deepEqual({...logs.at(-2)},{event:'wait',why:'download',frame:645});assert.equal(logs.at(-1).event,'played');
 await sleep(60);assert.equal(p.playing,false);assert.equal(asked.filter(x=>x.action==='directPlan').at(-1).size,640);limit.delete('/v2.mp4');await sleep(80);assert.equal(p.playing,true);
 p.audio.set('/a3.m4a',{});silent=true;clock(890);await sleep(30);clock(905);offset+=300;clock(905);assert.deepEqual(waits(),['download','decode']);
 silent=false;await sleep(60);assert.equal(p.playing,true);silent=true;
 const slow=p.readers.get('base:c:3');for(const {frame} of slow.frames.splice(0))frame.close();
 for(const i of [20,21,22]){slow.frames=[{i,frame:{displayWidth:160,displayHeight:90,close(){}}}];offset+=300;clock(930);}
 assert.equal(waits().length,2,'late but moving, it catches up by itself');silent=false;
 p.stop();assert.equal(logs.at(-1).event,'played');assert.equal(logs.at(-1).late,10,'how far the picture trailed is in the log');
 // Read-ahead: what twenty seconds of watching use downloads one at a time, the sound first, then the pictures from the one on screen.
 p.release();assert.equal(closed,1,'leaving the montage ends its sound device');requests.length=0;p.frame=240;p.prefetch();await sleep(80);
 assert.deepEqual(requests.filter(x=>!x.includes(' ')),['/a0.m4a','/a1.m4a','/a2.m4a','/v0.mp4','/v1.mp4','/v2.mp4']);
 // A first start does not wait for what comes next: it plays with the picture on screen.
 p.release();limit.set('/v1.mp4',0);p.play(240,1);await sleep(80);assert.equal(p.playing,true);limit.delete('/v1.mp4');
 assert.equal(devices.length,2,'and the next play gets a new one');
 // Moving elsewhere gives up what the new place does not use.
 p.stop();const left=p.media.get('/v0.mp4');p.forget(1700);assert.equal(p.media.has('/v0.mp4')||p.media.has('/v1.mp4'),false);assert.equal(left.control,null);
 // Sound: overlapping fades, sources that free their audio, an audio context that counts as unlocked by its state.
 const fade={start:0,length:1,fadeLength:1,fadeIn:1,fadeOut:1,volume:1};
 assert.ok(sandbox.envelopePoints(fade,0,1).includes(.5));assert.equal(sandbox.audioLevel(fade,.5),.25,'overlapping fades retain the canonical product');
 let source;const device=p.audioContext;device.createBufferSource=()=>source=node();
 p.audio.clear();p.audio.set('/a0.m4a',{});p.frame=0;p.anchorFrame=0;p.anchorTime=0;p.bus={};p.schedule();
 assert.equal(p.sources.size,1);source.onended();assert.equal(p.sources.size,0);assert.equal(source.buffer,null,'finished sources release their decoded audio');
 // A pause leaves the sound device running and fades the sound; nothing is cut in mid-swing.
 p.bus=null;device.currentTime=10;await p.play(0,1);const bus=p.bus;
 assert.equal(bus.gain.value,0,'silent until its fade');assert.deepEqual(bus.asked,[['set',0,p.anchorTime],['ramp',1,p.anchorTime+.02]],'the sound fades in');
 assert.deepEqual(source.asked[0].slice(0,2),['start',p.anchorTime]);
 device.currentTime=12;p.stop();
 assert.deepEqual(bus.asked.at(-1),['ramp',0,12.015],'and fades out');assert.deepEqual(source.asked.at(-1),['stop',12.02],'before its sources end');
 assert.equal(suspended,0,'a pause does not suspend the sound device');
 // At another speed one processor serves every play at that speed, and the clock waits for what it holds back: sound and picture start together.
 await p.play(0,1.5);const first=p.anchorTime;
 assert.ok(first>=12.2,'a new processor is filled with silence before it is heard');
 assert.ok(Math.abs(source.asked[0][1]-(first-.037))<1e-9,'the sound goes in ahead of the clock by the processor delay');
 assert.ok(Math.abs(p.bus.asked[0][2]-(first-.037))<1e-9,'and fades in as it goes in');
 device.currentTime=first;assert.equal(p.clock(),0);device.currentTime=first+1;assert.ok(Math.abs(p.clock()-45)<1e-6);
 await p.play(p.clock(),1.5);assert.equal(processors.length,1,'the next play at that speed reuses it');
 assert.ok(Math.abs(p.anchorTime-(first+1.02+.037+.037))<1e-9,'and is heard once the tail of the last has left the processor');
 p.stop();await p.play(0,2);assert.deepEqual(processors.map(x=>x.rate),[1.5,2]);p.stop();
 // A sound device that is not running is not woken up: the play gets a new one.
 device.state='interrupted';starts='suspended';await assert.rejects(p.unlock(),/sonido/);assert.equal(devices.length,3);
 starts='running';await p.unlock();assert.equal(devices.length,4);assert.equal(closed,3);await p.unlock();assert.equal(devices.length,4,'a running one is kept');
 // A browser that cannot decode the video leaves this player for the composed preview, and says so once.
 p.release();errors.length=0;refuse=true;await p.seek(0);
 assert.equal(errors.length,1);assert.equal(p.broken,true);assert.equal(logs.at(-1).where,'seek');assert.equal(await p.load({id:'P',revision:2},0),false);
 // So does one that decodes nothing for five seconds with the samples there, or that cannot draw what it decoded.
 for(const fault of [()=>{silent=true;},()=>{nodraw=true;}]) {
  refuse=false;p.broken=false;await p.load({id:'P',revision:2},0);errors.length=0;fault();
  const seeking=p.seek(0);await sleep(60);offset+=6000;await seeking;silent=nodraw=false;
  assert.equal(p.broken,true);assert.equal(errors.length,1);
 }
 p.broken=false;asked.length=0;sandbox.VideoDecoder=undefined;
 assert.equal(await p.load({id:'P',revision:2},0),false);assert.equal(asked.length,0,'without a video decoder the Mac is not asked for a plan');
 sandbox.VideoDecoder=VideoDecoder;await p.load({id:'P',revision:2},0);await p.seek(0);assert.equal(p.readers.size,1);
 p.query=async()=>null;assert.equal(await p.load({id:'P',revision:3},0),false);assert.equal(p.readers.size+p.media.size,0);assert.equal(open,0);
 // A tap on the picture finds the text drawn there: the picture is letterboxed in its box and the text drawn last is on top.
 p.plan={fps:30,width:160,height:320,clips:[{id:'c',start:0,length:90}],layers:[{id:'under',start:0,length:90,rect:[0,0,160,320]},{id:'hook',start:0,length:30,rect:[20,40,120,60]}]};
 p.canvas.getBoundingClientRect=()=>({left:10,top:20,width:400,height:640});
 const tap=(x,y)=>p.textAt({clientX:10+40+x*2,clientY:20+y*2});
 assert.equal(tap(25,45),'hook');assert.equal(tap(5,45),'under');assert.equal(tap(-10,45),undefined,'the bars beside the picture are not it');
 p.frame=45;assert.equal(tap(25,45),'under','a text that is no longer on screen is not tapped');
 assert.equal(cropped.length,0,'a video frame is drawn whole and placed: WebKit ignores its source rectangle, so a zoomed clip showed with no zoom');
 console.log('PASS · direct player: proxy index, a tap on a text, download from the middle, decoding, seeks, cuts, waits, read-ahead, sound, fallback');
})().catch(e=>{console.error(e);process.exitCode=1});
