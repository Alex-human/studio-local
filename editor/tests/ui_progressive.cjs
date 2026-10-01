// Exercise playback coordination without media, filesystem or live application writes.
const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const elements=new Map(),requests=[],waiting=[];
const element=id=>{if(!elements.has(id))elements.set(id,{hidden:false,style:{},dataset:{},setAttribute(){},getBoundingClientRect(){return {left:0,top:0,width:640,height:360};}});return elements.get(id);};
const context={console,Map,Promise,Number,Math,Date,Set,Error,state:{},p:{revision:4,fps:30},path:'test.studio',cursor:0,homeVisible:false,busy:false,
 previewRevision:-1,mutationTail:Promise.resolve(),$:element,frames:()=>60,drawImageSelection(){},toast(){},tc:String,
 flushEdits:async()=>{},syncExternal:async()=>{},safe:fn=>fn,api:async request=>{
  requests.push(request);
  if(request.action==='capabilities')return {interactivePlayback:true,playbackRate:true};
  if(request.action==='preparePlayback')return new Promise(resolve=>waiting.push({request,resolve}));
  if(request.action==='loadPlayback'&&context.failNextLoad){context.failNextLoad=false;throw new Error('Invalid video composition');}
  return {};
 }};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/playback.js'),'utf8'),context);
vm.runInContext('async function seek(frame){await pausePlayback();cursor=frame;}',context);
const get=s=>vm.runInContext(s,context),settle=async()=>{for(let n=0;n<20;n++)await Promise.resolve();};
function complete(from){const index=waiting.findIndex(job=>job.request.frame===from);assert.notEqual(index,-1,'pending frame '+from);const job=waiting.splice(index,1)[0];job.resolve({key:'window-'+from,windowStart:from,windowEnd:Math.min(60,from+15),progressive:true,rasterFallback:!!job.request.forceRaster,frames:15,totalFrames:60,seconds:.1,audioSources:[]});return job;}
(async()=>{
 await get('playbackRateReady');
 const first=get('togglePlay()');await settle();complete(0);await first;await settle();
 assert.equal(get('playbackPlaying'),true);assert.equal(waiting[0].request.frame,15);
 complete(15);await settle();
 get('studioPlaybackEvent({key:playbackKey,frame:14,ended:true})');await settle();
 assert.equal(get('cursor'),15);assert.equal(get('playbackPlaying'),true);
 assert.equal(requests.filter(r=>r.action==='loadPlayback').at(-1).frame,15);
 assert.equal(waiting[0].request.frame,30);
 // Pause while the next exact interval is still rendering. It must never resume later.
 get('studioPlaybackEvent({key:playbackKey,frame:29,ended:true})');await settle();
 assert.equal(get('state.continuingPlayback'),true);await get('pausePlayback()');
 const plays=requests.filter(r=>r.command==='play').length;complete(30);await settle();
 assert.equal(get('playbackPlaying'),false);assert.equal(requests.filter(r=>r.command==='play').length,plays);
 // An edit cancels both preparation and look-ahead by their own tokens.
 const lookahead=waiting.find(j=>j.request.frame===45);assert.ok(lookahead);
 get('invalidatePlayback()');await settle();
 assert.ok(requests.some(r=>r.action==='cancelPreparation'&&r.preparation===lookahead.request.preparation));
 complete(45);await settle();assert.equal(get('playbackKey'),null);
 // A delayed obsolete response may not stop or replace a newer loaded item.
 get('cursor=0');const obsolete=get('preparePlayback()');await settle();
 get('invalidatePlayback();p.revision++;cursor=45');const current=get('preparePlayback()');await settle();
 complete(45);await current;const loads=requests.filter(r=>r.action==='loadPlayback').length;
 complete(0);assert.equal(await obsolete,false);await settle();
 assert.equal(requests.filter(r=>r.action==='loadPlayback').length,loads);
 assert.equal(requests.filter(r=>r.command==='stop').length,0);
 assert.equal(get('playbackKey'),'window-45');
 // An invalid native composition retries the same position as a full-stack proxy.
 get('invalidatePlayback();cursor=0');context.failNextLoad=true;
 const fallback=get('togglePlay()');await settle();complete(0);await settle();
 assert.equal(waiting[0].request.forceRaster,true);complete(0);await fallback;await settle();
 assert.equal(get('playbackPlaying'),true);assert.equal(get('state.playbackPlan.rasterFallback'),true);
 assert.equal(waiting[0].request.forceRaster,true);assert.equal(waiting[0].request.frame,15);
 get('invalidatePlayback()');complete(15);await settle();
 console.log('PASS progressive playback: prefetch, global seek, pause, cancellation, stale result ownership, invalid composition fallback');
})().catch(error=>{console.error(error);process.exitCode=1;});
