// Production desktop timeline behavior with a controlled clock and browser scroll limits.
// No media, user projects or native application writes.
const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const elements=new Map();let now=0;
function element(id){
 if(!elements.has(id))elements.set(id,{style:{},dataset:{},clientWidth:1200,scrollTop:95,addEventListener(){},setAttribute(){},getBoundingClientRect(){return {left:0,top:0,width:1200,height:675};}});
 return elements.get(id);
}
const context={console,Map,Set,Promise,Number,Math,Date,Error,performance:{now:()=>now},state:{},p:{revision:1,fps:30},path:'test.studio',cursor:3000,zoom:100,
 homeVisible:false,busy:false,previewRevision:-1,mutationTail:Promise.resolve(),$:element,frames:()=>6000,tc:String,
 safe:fn=>fn,drawImageSelection(){},flushEdits:async()=>{},syncExternal:async()=>{},toast(){},document:{addEventListener(){}},
 api:async request=>request.action==='capabilities'?{playbackRate:true}:request.action==='preparePlayback'?{key:'plan',seconds:0}:{}
};
context.window=context;vm.createContext(context);
for(const file of ['timeline.js','playback.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui',file),'utf8'),context);
vm.runInContext('async function seek(frame){await pausePlayback();cursor=frame;}',context);
const get=s=>vm.runInContext(s,context),scroller=element('timelineScroll');let scroll=0;
Object.defineProperty(scroller,'scrollLeft',{get:()=>scroll,set:value=>{scroll=Math.max(0,Math.min(value,160+get('timelineWidth()')-scroller.clientWidth));}});
const half=()=>(scroller.clientWidth-160)/2,head=()=>get('cursor/frames()*timelineWidth()')-scroll;
const near=(actual,expected,message)=>assert.ok(Math.abs(actual-expected)<.01,`${message}: ${actual} vs ${expected}`);
function tick(frame,elapsed){now+=elapsed;get(`studioPlaybackEvent({key:playbackKey,frame:${frame},playing:true})`);assert.equal(scroller.scrollTop,95);}
async function position(at){await get('pausePlayback();');get('cursor=3000');scroller.scrollLeft=get('cursor/frames()*timelineWidth()')-at;}
(async()=>{
 await get('playbackRateReady');
 // A left-side click stays put on Play; the head travels naturally to the center.
 await position(half()*.4);const leftScroll=scroll,leftHead=head();await get('togglePlay()');
 near(scroll,leftScroll,'Play must not recenter a left-side position');
 tick(3005,100);near(scroll,leftScroll,'tracks remain stationary before the center');assert.ok(head()>leftHead&&head()<half());
 tick(3018,300);near(head(),half(),'the head reaches the center naturally');
 for(const frame of [3020,3030,3100]){tick(frame,100);near(head(),half(),'following keeps the head centered');}
 const followingScroll=scroll;await get('pausePlayback()');near(scroll,followingScroll,'pause retains the viewport');
 // Pausing before reaching the center must not finish or snap the approach.
 await position(half()*.3);await get('togglePlay()');tick(3005,100);const earlyScroll=scroll,earlyHead=head();
 await get('pausePlayback()');near(scroll,earlyScroll,'early pause keeps tracks');near(head(),earlyHead,'early pause keeps head');
 scroller.scrollLeft=250;await get('seek(2000)');assert.equal(scroll,250,'paused seek preserves manual scroll');
 // A right-side position eases left to the center without an initial jump.
 await position(half()*1.6);const rightScroll=scroll,rightHead=head();await get('togglePlay()');
 near(scroll,rightScroll,'right-side Play starts in place');
 let previous=rightHead;
 for(let elapsed=16;elapsed<=656;elapsed+=16){tick(3000+Math.floor(elapsed*30/1000),16);const current=head();assert.ok(current<=previous+.01&&current>=half()-.01,'head approaches center monotonically');assert.ok(previous-current<20,'no sudden recentering jump');previous=current;}
 near(head(),half(),'right-side approach finishes at center');
 // A pause or manual ruler/edge gesture cancels the approach immediately.
 await position(half()*1.8);await get('togglePlay()');tick(3002,100);const interrupted=scroll;
 await get('pausePlayback()');now+=1000;get('studioPlaybackEvent({key:playbackKey,frame:3003,playing:true})');near(scroll,interrupted,'late native events cannot resume scrolling');
 const resumeHead=head();await get('togglePlay()');near(head(),resumeHead,'resume begins at its current position');
 for(const drag of ['rulerDrag','edgeDrag']){
  get(`${drag}={}`);const gestureScroll=scroll;tick(3010,200);near(scroll,gestureScroll,'active gesture owns the viewport');
  await get('pausePlayback()');near(scroll,gestureScroll,'gesture pause does not center');get(`${drag}=null`);
  await get('togglePlay()');
 }
 // Obsolete/hidden-project events do not control this view.
 const before=scroll;get('studioPlaybackEvent({key:"obsolete",frame:100,playing:true})');assert.equal(scroll,before);
 get('homeVisible=true;studioPlaybackEvent({key:playbackKey,frame:100,playing:true});homeVisible=false');assert.equal(scroll,before);
 // Starting off screen also recovers smoothly rather than waiting indefinitely.
 await position(-400);const offscreenScroll=scroll;await get('togglePlay()');near(scroll,offscreenScroll,'offscreen start does not jump');tick(3001,700);near(head(),half(),'offscreen head is recovered');
 // The scroll never exceeds real content; Fit keeps the complete timeline visible.
 await get('pausePlayback()');get('cursor=0');scroll=0;await get('togglePlay()');tick(0,700);assert.equal(scroll,0);
 tick(5999,1000);assert.equal(scroll,160+get('timelineWidth()')-scroller.clientWidth);
 await get('pausePlayback()');get('zoom=1;cursor=3000');scroll=0;await get('togglePlay()');tick(4000,700);assert.equal(scroll,0);
 // Natural end also stops where it is, without completing an unfinished approach.
 await get('pausePlayback()');get('zoom=100;cursor=5990');scroller.scrollLeft=get('cursor/frames()*timelineWidth()')-half()*.3;
 await get('togglePlay()');const endScroll=scroll;get('studioPlaybackEvent({key:playbackKey,frame:5991,ended:true})');await Promise.resolve();
 assert.equal(get('playbackPlaying'),false);near(scroll,endScroll,'end does not force centering');
 console.log('PASS desktop timeline: left-side travel, smooth right-side capture, pause/resume, gestures, late/stale events, offscreen recovery, bounds, Fit and end');
})().catch(error=>{console.error(error);process.exitCode=1;});
