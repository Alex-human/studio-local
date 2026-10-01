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
 p.plan={fps:30,frames:3000,clips:[{id:'c',start:0,length:3000,in:0,url:'/v.mp4'}],layers:[],audio:[],width:160,height:90};p.ready.add('/v.mp4');p.draw=()=>{};p.prefetch=()=>{};
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
 console.log('PASS · direct player: cancelled seeks, single frame, overlap fades, rejected play, audio lifetime');
})().catch(e=>{console.error(e);process.exitCode=1});
