// Cancellation/clock regressions against the actual player, independent of browser timing.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const media=[];
function video(){const v={readyState:0,currentTime:0,duration:100,seeking:false,paused:true,style:{},pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()},remove(){},removeAttribute(){},load(){}};media.push(v);return v;}
const sandbox={console,performance,setTimeout,clearTimeout,requestAnimationFrame(){},cancelAnimationFrame(){},Image:class{},
 document:{createElement:type=>type==='video'?video():{style:{},getContext:()=>({}),hidden:true}},Float32Array,Map,Set};vm.createContext(sandbox);
const code=fs.readFileSync(path.join(__dirname,'../mobile/direct-player.js'),'utf8').replace(/export /g,'');
vm.runInContext(code+'\nthis.DirectPlayer=DirectPlayer;this.audioLevel=audioLevel;this.envelopePoints=envelopePoints;',sandbox);
(async()=>{
 const states=[],errors=[];const p=new sandbox.DirectPlayer({append(){}},async()=>({ready:['/v.mp4'],failed:[]}),()=>{},(...x)=>states.push(x),e=>errors.push(e));
 p.plan={fps:30,frames:3000,clips:[{id:'c',base:true,start:0,length:3000,in:0,url:'/v.mp4'}],layers:[],audio:[],width:160,height:90};p.ready.add('/v.mp4');p.draw=()=>{};p.prefetch=()=>{};
 const first=p.seek(0);await new Promise(r=>setTimeout(r,1));assert.equal(media.length,1);media[0].readyState=4;
 await p.seek(300);assert.equal(media[0].currentTime,10);await first;
 assert.equal(media[0].currentTime,10,'a cancelled seek must never reposition the winning video');
 await p.seek(301);assert.ok(Math.abs(media[0].currentTime-301/30)<1e-8,'one-frame seek changes the decoded target');
 const fade={start:0,length:1,fadeLength:1,fadeIn:1,fadeOut:1,volume:1};
 const points=sandbox.envelopePoints(fade,0,1);assert.ok(points.includes(.5));assert.equal(sandbox.audioLevel(fade,.5),.25,'overlapping fades retain the canonical product');
 p.unlock=async()=>{};p.audioContext={currentTime:0,suspend(){},createGain:()=>({connect(){},disconnect(){}})};media[0].play=()=>Promise.reject(Error('rejected play'));
 await p.play(301,1);assert.equal(p.playing,false);assert.equal(states.at(-1)[0],false);assert.equal(errors.length,1,'play rejection resets the transport and reports an actionable error');
 let source;
 p.audioContext={currentTime:0,suspend(){},createBufferSource(){return source={playbackRate:{},connect(){},disconnect(){},start(){}}},createGain(){return {gain:{setValueAtTime(){},linearRampToValueAtTime(){}},connect(){},disconnect(){}}}};
 p.plan.audio=[{id:'a',url:'/a.m4a',start:0,source:0,length:1,volume:1}];p.audio.set('/a.m4a',{});p.frame=0;p.anchorFrame=0;p.anchorTime=0;p.bus={};p.schedule();
 assert.equal(p.sources.size,1);source.onended();assert.equal(p.sources.size,0);assert.equal(source.buffer,null,'finished sources release their decoded audio');
 // Chunked proxies: a piece that starts at the first frame of its proxy, lookahead, and a proxy that reaches its end.
 const clip=p.plan.clips[0],v=media[0];let played=0;v.play=()=>{played++;v.paused=false;return Promise.resolve()};
 p.plan.audio=[];p.bus=null;p.playing=true;p.anchorFrame=301;p.anchorTime=0;p.rate=1;p.schedule=()=>{};v.currentTime=p.target(clip,301,v);
 v.paused=true;v.ended=true;p.tick();assert.equal(played,0,'a proxy that reached its end keeps its last frame instead of restarting');
 v.ended=false;p.tick();assert.equal(played,1,'a paused proxy resumes with the clock');p.stop();
 v.duration=10;assert.ok(Math.abs(p.target(clip,600,v)-(10-1/30))<1e-9,'past the end of its proxy an item holds the last frame');v.duration=100;
 const asked=[];p.query=async req=>{asked.push(req);return req.action==='directPlan'?{fps:30,frames:600,width:160,height:90,layers:[],audio:[],pending:['/b.mp4'],
   clips:[{id:'a:0',base:true,start:0,length:300,in:0,url:'/a.mp4'},{id:'a:1',base:true,start:300,length:300,in:0,url:'/b.mp4'}]}:{ready:req.urls,failed:[]};};
 p.ready.add('/b.mp4');assert.equal(await p.load({id:'P',revision:1},0.4),true);assert.equal(asked[0].frame,0,'the plan request carries the playhead as a whole frame');
 assert.ok(p.ready.has('/a.mp4')&&!p.ready.has('/b.mp4'),'the plan says what the Mac already has, without another round trip');
 asked.length=0;await p.ensure(['/a.mp4'],p.generation,['/a.mp4','/b.mp4']);
 assert.equal(asked.map(x=>x.urls.join()).join('|'),'/b.mp4','ready media does not wait while the Mac is told what comes next');
 await new Promise(r=>setTimeout(r,1));assert.ok(p.ready.has('/b.mp4'));asked.length=0;await p.ensure(['/a.mp4'],p.generation,['/b.mp4']);assert.equal(asked.length,0);
 const sets=[];media.length=0;const seeking=p.seek(0);await new Promise(r=>setTimeout(r,1));const fresh=media[0];let at=0;
 Object.defineProperty(fresh,'currentTime',{get:()=>at,set:x=>{at=x;sets.push(x)}});fresh.duration=10;fresh.readyState=4;await seeking;
 assert.deepEqual(sets,[.001],'a new element seeks even to its first frame, so iOS loads it');
 console.log('PASS · direct player: cancelled seeks, single frame, overlap fades, rejected play, audio lifetime, chunked proxies');
})().catch(e=>{console.error(e);process.exitCode=1});
