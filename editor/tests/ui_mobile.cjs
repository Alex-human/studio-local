// Behavioral regressions of the actual mobile module. Browser layout/media is checked separately.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict'), path = require('node:path');
const nodes = new Map(), memory = new Map();
function node(id='') {
  if (id && nodes.has(id)) return nodes.get(id);
  const n = {disabled:false,hidden:false,open:false,value:'',style:{},children:[],events:{},currentTime:0,
    clientWidth:393,classList:{toggle(){}},setAttribute(){},append(...items){this.children.push(...items)},after(){},
    replaceChildren(){this.children=[]},querySelectorAll(){const out=[];(function walk(n){for(const c of n.children){if(c.row)out.push(c);walk(c);}})(this);return out},getBoundingClientRect(){return {width:100,height:100,left:0,top:0}},
    getContext(){return {beginPath(){},moveTo(){},lineTo(){},stroke(){},ellipse(){},rect(){}}},focus(){},scrollIntoView(options){this.scrolled=options;},pause(){},
    removeAttribute(){this.removed=(this.removed||0)+1},load(){},play(){return Promise.resolve()},canPlayType(){return 'probably'},readyState:4,
    showModal(){this.open=true},close(){this.open=false;queueMicrotask(()=>this.events.close?.())},
    addEventListener(type,fn){this.events[type]=fn}};
  Object.defineProperty(n,'id',{set(value){nodes.set(value,n)},get(){return id}});
  if(id) nodes.set(id,n);
  return n;
}
const context = {assert,console,structuredClone,crypto:require('node:crypto').webcrypto,setInterval(){},setTimeout(){},clearTimeout(){},setImmediate,queueMicrotask,
  performance,AbortController,DirectPlayer:class {constructor(...args){this.args=args} release(){this.released=(this.released||0)+1} load(){return Promise.resolve(true)} seek(){} stop(){}},devicePixelRatio:1,navigator:{userAgent:'test'},document:{hidden:false,getElementById:node,createElement:()=>node(),
    querySelector(){return null},querySelectorAll(selector){return selector.includes('dialog textarea') ? [node('noteText'),node('hookText')] : []},addEventListener(){}},
  window:{events:{},addEventListener(type,fn){(this.events[type]??=[]).push(fn)},removeEventListener(type,fn){this.events[type]=(this.events[type]||[]).filter(x=>x!==fn)}},localStorage:{setItem:(k,v)=>memory.set(k,v),getItem:k=>memory.get(k),removeItem:k=>memory.delete(k)}};
vm.createContext(context);
const fixture = {id:'P',name:'fixture',revision:1,fps:30,clips:[{id:'clip',asset:'asset',in:0,length:300}],
  graphics:[{id:'hook',type:'title',start:0,length:300,props:{text:'Hook'}}],captions:[],audio:[],assets:[]};
let code=fs.readFileSync(path.join(__dirname,'../mobile/app.js'),'utf8').replace('await task(loadLibrary)();','').replace(/^import .*\n/,'');
code+=`
(async()=>{
  directSupported=false;
  p=${JSON.stringify(fixture)}; selection=null; controls();
  assert.equal($('edges').disabled,false,'edges are reachable before selecting a tiny timeline block');
  assert.equal($('hook').disabled,false,'text picker is reachable without a prior selection');
  $('edges').onclick();
  assert.equal(selected().item.id,'clip','edges select the video at the playhead');
  assert.equal($('edgeDialog').open,true);$('edgeDialog').close();
  $('hook').onclick();assert.equal($('textPicker').open,true);
  assert.equal($('textChoices').children.length,1,'picker exposes the hook as a full row');
  $('textChoices').children[0].onclick();
  assert.equal($('hookText').value,'Hook');$('textDialog').close();
  await new Promise(setImmediate);textDraft=null;
  mediaSource={project:'P',revision:1,hls:true};playbackOffset=0;frame=90;playing=true;video.currentTime=3;
  const removals=video.removed||0;pause();
  assert.equal(video.removed||0,removals,'pause retains buffered video');
  assert.equal(mediaCovers(),true);seek(150);
  assert.equal(video.currentTime,5,'seeking within the loaded HLS does not rebuild the player');
  $('speed').value='2';$('speed').onchange();
  assert.equal(video.playbackRate,2);assert.equal(video.preservesPitch,true);
  assert.equal(p.revision,1,'review speed does not edit the montage');
  releaseMedia();assert.equal(mediaCovers(),false);selection=null;
  frame=210;video.currentTime=0;video.readyState=0;await play();pause();
  assert.equal(frame,210,'pausing a cold load preserves the requested frame instead of sampling zero');
  video.readyState=1;video.onloadedmetadata();
  assert.equal(video.currentTime,1,'metadata still positions a paused cold load');
  video.readyState=4;video.onseeked();
  assert.equal(positioning,false);releaseMedia();
  p=${JSON.stringify(fixture)}; selection={kind:'graphics',id:'hook'}; controls();
  const released=direct.released;applyProject({...p,revision:2});
  assert.equal(direct.released,released,'an edit keeps the videos of the montage on screen');
  applyProject({...p,id:'Q'});assert.equal(direct.released,released+1,'another montage releases them');
  p=${JSON.stringify(fixture)}; directSupported=false; directLoad=null;
  assert.equal($('hook').disabled,false,'selected hook must be editable');
  noteDraft={project:'P',revision:1,noteId:'unsent',frame:0,text:'Do not lose this',strokes:[]};
  $('noteText').value=noteDraft.text;saveDraft();
  openNote({id:'other',revision:1,frame:0,version:2,text:'Other note',strokes:[]});
  assert.equal(stored(draftKey('P')).text,'Do not lose this','opening a note must preserve an unsent draft');
  playing=true;frame=60;playbackOffset=0;video.currentTime=2.25;pause();
  assert.equal(frame,68,'pause must sample the current playback clock');
  playing=true;frame=60;video.currentTime=2.25;$('scrub').value='150';$('scrub').oninput();
  assert.equal(frame,150,'seeking while playing keeps the requested slider value');
  playing=true;frame=60;video.currentTime=2.25;
  let sent;
  api=async req=>{sent=req;return {ok:true,result:{}}};
  await $('split').onclick();
  assert.equal(sent.op.frame,68,'split uses the paused frame rather than the last timeupdate');
  let finish;
  api=()=>new Promise(resolve=>finish=resolve);
  const sending=$('saveNote').onclick();
  await new Promise(setImmediate);
  assert.equal($('noteText').disabled,true,'typing during a write cannot be silently discarded');
  assert.equal($('hookText').disabled,true);
  finish({ok:true,result:{note:{}}});
  reload=async()=>{};
  await sending;await new Promise(setImmediate);
  assert.equal(stored(draftKey('P')),null,'successful save removes only the completed draft');
  noteDraft={project:'P',revision:1,noteId:'lost',frame:0,text:'Response lost',strokes:[]};
  $('noteText').value=noteDraft.text;saveDraft();
  persist(pendingKey,{requestId:'r',project:'P',action:'note'});
  query=async()=>({status:'done',response:{ok:true}});
  await $('checkReceipt').onclick();await new Promise(setImmediate);
  assert.equal(stored(draftKey('P')),null,'dialog close must not resurrect the acknowledged draft');
  assert.equal(stored(pendingKey),null);
  // An unknown receipt cannot be accepted without a server-side fence.
  persist(pendingKey,{requestId:'unknown',project:'P',action:'note'});
  query=async req=>{assert.equal(req.settle,true);return {status:'unknown'};};
  await $('acceptState').onclick();assert.ok(stored(pendingKey),'unknown stays blocked');
  query=async req=>({status:'processing'});await $('acceptState').onclick();assert.ok(stored(pendingKey));
  query=async req=>({status:'done',response:{ok:false,cancelled:true,error:'Cancelled before arrival'}});
  await $('acceptState').onclick();assert.equal(stored(pendingKey),null);
  noteDraft={project:'P',revision:1,noteId:'retry-capture',frame:15,text:'Retained after failure',strokes:[]};
  $('noteText').value=noteDraft.text;saveDraft();
  api=async()=>({ok:false,error:'Capture timed out'});
  query=async()=>({notes:[{id:'retry-capture',revision:1,frame:15,version:2,text:'Retained after failure',strokes:[]}]});
  await $('saveNote').onclick();assert.equal(noteDraft.version,2,'retry uses the persisted draft version without closing the dialog');
  assert.equal(noteDraft.text,'Retained after failure');
  // A matching persisted draft can be retried with its real version, without overwriting different content.
  const saved={id:'draft',revision:1,frame:15,version:2,text:'Kept',strokes:[]};
  persist(draftKey('P'),{project:'P',revision:1,noteId:'draft',frame:15,text:'Kept',strokes:[]});
  notes=[saved];openNote();assert.equal(noteDraft.version,2);assert.equal($('loadSavedNote').hidden,true);
  $('noteText').value='Unsaved changes';saveDraft();openNote({...saved,version:3,text:'Someone else'});
  assert.equal(noteDraft.text,'Unsaved changes');assert.equal(noteDraft.version,2);assert.equal($('loadSavedNote').hidden,false);
  query=async()=>({notes:[{...saved,version:3,text:'Someone else'}]});await $('loadSavedNote').onclick();
  assert.equal(noteDraft.text,'Someone else');assert.equal(noteDraft.version,3);
  noteDraft=null;localStorage.removeItem(draftKey('P'));$('noteDialog').close();
  $('hook').onclick();$('textChoices').children[0].onclick();$('hookText').value='Unsent hook';$('hookText').oninput();$('textDialog').close();
  await new Promise(setImmediate);$('hook').onclick();
  assert.equal($('textPicker').open,true,'text selection stays reachable after editing another text');
  $('textChoices').children[0].onclick();
  assert.equal($('hookText').value,'Unsent hook','closing and reopening preserves unsent hook text');
  playing=false;directSupported=null;let attempts=0;
  direct.load=async()=>{if(++attempts===1)throw Error('temporary plan failure');return false;};
  loadDirect();await directLoad;assert.equal(directLoad,null);assert.equal(directSupported,null);
  await play();assert.equal(attempts,2,'play retries a failed plan without requiring a new revision');pause();
  p.fps=30;p.clips[0].length=18000;playing=true;frame=9000;updatePosition();
  assert.ok($('timeline').scrollLeft>4500,'timeline follows playback far beyond the first screen');
  timelineTouch=true;const left=$('timeline').scrollLeft;frame+=300;updatePosition();assert.equal($('timeline').scrollLeft,left,'manual track scrolling is not fought');
  timelineTouch=false;playing=false;
  // Timeline taps seek in montage coordinates; scrolling and trim handles do not.
  const timeline=$('timeline'),tracks=$('tracks');
  const pointer=(x,y=20)=>({clientX:x,clientY:y,isPrimary:true,button:0});
  const click=(x,handle=false,detail=1)=>({...pointer(x),detail,stopPropagation(){},target:{closest:()=>handle}});
  const tap=(x,row)=>{
    timeline.events.pointerdown(pointer(x));
    if(row) { renderTimeline();const block=tracks.children.flatMap(n=>n.children).find(n=>n.title?.startsWith(names[row.track]+':'));block.onclick(click(x)); }
    else tracks.onclick(click(x));
    timelineTouch=false;
  };
  tracks.getBoundingClientRect=()=>({left:-320});scale=32;frame=0;directSupported=true;
  let seeked;direct.seek=n=>{seeked=n;};direct.clock=()=>frame;
  const beforeTimeline=JSON.stringify(p);
  tap(160,items()[0]);
  assert.equal(frame,450,'a clip tap uses the finger position after scrolling and zooming');
  assert.equal(seeked,450,'the actual player receives that frame');
  assert.equal(selection.id,'clip');
  tap(256,items()[0]);assert.equal(frame,540,'retapping the selected clip moves within it');
  tap(64);assert.equal(frame,360,'ruler and empty track taps also seek');
  timeline.events.pointerdown(pointer(64));timeline.events.pointermove(pointer(100));
  tapTimeline(click(100));assert.equal(frame,360,'a horizontal swipe does not seek');
  timeline.events.pointerdown(pointer(64));timeline.events.pointermove(pointer(64,40));
  tapTimeline(click(64));assert.equal(frame,360,'a vertical swipe does not seek');
  timeline.events.pointerdown(pointer(64));timeline.events.pointercancel();
  tapTimeline(click(64));assert.equal(frame,360,'cancelled gestures do not seek');
  timeline.events.pointerdown(pointer(64));tapTimeline(click(64,true),items()[0]);
  assert.equal(frame,360,'a trim handle cannot become a timeline tap');
  busy=true;tap(128);assert.equal(frame,360,'saving keeps the timeline locked');busy=false;
  tap(-400);assert.equal(frame,0);tap(20000);assert.equal(frame,total()-1);
  tapTimeline(click(0,false,0),items()[1]);
  assert.equal(frame,299,'keyboard selection still selects a reachable frame in the item');
  assert.equal(JSON.stringify(p),beforeTimeline,'navigation does not edit the montage');
  timelineTouch=false;timelineTap=null;
  // Zoom keeps the visible playhead fixed, including immediately after a paused touch/scroll.
  p={...p,clips:[{id:'long',asset:'asset',in:0,length:18000}]};selection=null;frame=1800;
  const beforeZoom=JSON.stringify(p);
  for (const active of [false,true]) for (const hold of [0,Infinity]) {
    playing=active;timelineHold=hold;scale=16;
    const at=active&&!hold ? $('timeline').clientWidth*.35 : 173;
    $('timeline').scrollLeft=frame/p.fps*scale-at;
    for (const id of ['zoomIn','zoomIn','zoomOut','zoomOut']) {
      $(id).onclick();
      assert.ok(Math.abs(frame/p.fps*scale-$('timeline').scrollLeft-at)<.001,'zoom must keep the playhead in place, paused or playing, even during the manual-scroll hold');
      assert.equal(frame,1800,'zoom does not seek');
      assert.equal(playing,active,'zoom does not change playback');
      assert.equal(JSON.stringify(p),beforeZoom,'zoom does not edit the montage');
    }
  }
  playing=false;timelineHold=0;
  directSupported=true;direct.broken=true;direct.args[4](Error('sin descodificador'));
  assert.equal(directSupported,false,'a browser that cannot decode the video goes on with the composed preview');
  // A text is rewritten from where it is: selected in the timeline, or tapped on the picture.
  $('textDialog').close();
  p=${JSON.stringify(fixture)};directSupported=true;selection={kind:'clips',id:'clip'};renderTimeline();
  assert.equal($('rewrite').hidden,true,'a clip has no text to rewrite');
  selection={kind:'graphics',id:'hook'};renderTimeline();assert.equal($('rewrite').hidden,false);
  $('rewrite').onclick();assert.equal($('textDialog').open,true,'the selected text opens without the list');
  $('textDialog').close();selection=null;
  direct.textAt=()=>undefined;$('viewer').onclick({});assert.equal($('textDialog').open,false,'a tap on the picture away from any text opens nothing');
  direct.textAt=()=>'hook';$('viewer').onclick({});assert.equal($('textDialog').open,true);assert.equal(selection.id,'hook','a text tapped on the picture opens');
  directSupported=false;
  // The selected element can be deleted; shortening a clip shows and leaves no gap, whatever ends the gesture.
  selection=null;controls();assert.equal($('remove').disabled,true,'nothing selected, nothing to delete');
  p={id:'P',name:'two',revision:1,fps:30,clips:[{id:'a',asset:'asset',in:0,length:300},{id:'b',asset:'asset',in:300,length:300}],graphics:[],captions:[],audio:[],assets:[]};
  selection={kind:'clips',id:'a'};scale=30;renderTimeline();controls();
  assert.equal($('remove').disabled,false);
  api=async req=>{sent=req;return {ok:true,result:{}}};
  await $('remove').onclick();
  assert.deepEqual(sent.op,{type:'delete',kind:'clips',id:'a'},'delete targets the selected element');
  const block=id=>tracks.querySelectorAll('.block').find(b=>b.row.item.id===id);
  const fire=async(type,x)=>{await Promise.all(window.events[type].map(fn=>fn({type,pointerId:7,clientX:x})));await new Promise(setImmediate);};
  const drag=()=>dragEdge({clientX:100,pointerId:7,preventDefault(){},stopPropagation(){}},block('a').row,'end',block('a'));
  drag();await fire('pointermove',70);
  assert.equal(block('a').style.width,'270px');
  assert.equal(block('b').style.transform,'translateX(-30px)','what follows closes the gap while shortening');
  sent=null;await fire('pointerup',70);
  assert.deepEqual(sent.op,{type:'resize',kind:'clips',id:'a',edge:'end',delta:-30},'lifting the finger anywhere saves the trim');
  assert.equal(dragging,false);
  drag();await fire('pointermove',70);sent=null;await fire('pointercancel',70);
  assert.equal(sent,null,'a cancelled gesture saves nothing');
  assert.equal(block('a').style.width,'300px','and the timeline shows the saved montage again');
  api=async()=>({ok:false,error:'rechazado'});
  drag();await fire('pointermove',70);await fire('pointerup',70);
  assert.equal(block('a').style.width,'300px','a rejected trim does not leave a false gap');
  // Overshooting a short source gap must recover the available context, rather than reject the entire gesture.
  p={id:'P',name:'cut',revision:4,fps:30,clips:[{id:'a',asset:'asset',in:60,length:300},{id:'b',asset:'asset',in:375,length:300}],
     graphics:[],captions:[],audio:[],assets:[{id:'asset',duration:30}]};
  selection={kind:'clips',id:'a'};scale=30;renderTimeline();
  api=async req=>{sent=req;return {ok:true,result:{}}};
  const recoverEdge=async(id,edge,x)=>{
    selection={kind:'clips',id};renderTimeline();
    dragEdge({clientX:100,pointerId:7,preventDefault(){},stopPropagation(){}},block(id).row,edge,block(id));
    await fire('pointermove',x);
  };
  await recoverEdge('a','end',200);
  assert.equal(block('a').style.width,'315px','the preview stops at the next source piece');
  assert.equal(block('b').style.transform,'translateX(15px)','later clips follow the recoverable amount');
  await fire('pointerup',200);
  assert.equal(sent.op.delta,15,'recover the half-second gap even when dragged much further');
  assert.equal(sent.revision,4,'the gesture retains its starting revision');
  await recoverEdge('b','start',0);await fire('pointerup',0);
  assert.equal(sent.op.delta,-15,'the other side recovers the same gap');
  await recoverEdge('a','start',0);await fire('pointerup',0);
  assert.equal(sent.op.delta,-60,'first clip stops at the start of its source');
  await recoverEdge('b','end',500);await fire('pointerup',500);
  assert.equal(sent.op.delta,225,'last clip stops at the end of its source');
  selection={kind:'clips',id:'a'};$('edge').value='end';$('edgeSeconds').value='5';
  await resize(true);assert.equal(sent.op.delta,15,'the Borders dialog uses the same recoverable amount');
  p.clips[1].in=360;renderTimeline();sent=null;
  await recoverEdge('a','end',200);await fire('pointerup',200);
  assert.equal(sent,null,'a contiguous source boundary creates no zero-frame write');
  await $('extend').onclick();assert.equal(sent,null);
  assert.match($('notice').textContent,/No queda más/,'a boundary with no hidden context explains why it cannot extend');
  p.clips[0].speed=2;p.clips[1].in=690;
  await recoverEdge('a','end',200);await fire('pointerup',200);
  assert.equal(sent.op.delta,15,'source gaps are converted using clip speed');
  await recoverEdge('a','end',-500);await fire('pointerup',-500);
  assert.equal(sent.op.delta,-299,'shortening always leaves at least one frame');
  // Volume: the selected element with its own sound and the three tracks of the mix, saved when the finger lifts.
  p={id:'P',name:'vol',revision:3,fps:30,mixer:{voice:0,music:-6.0206,sfx:0},clips:[{id:'a',asset:'mute',in:0,length:300}],graphics:[],captions:[],
     audio:[{id:'m',asset:'song',role:'music',start:0,length:90,volumeDb:-60}],assets:[{id:'mute',audio:false},{id:'song',audio:true}]};
  selection={kind:'clips',id:'a'};
  $('volume').onclick();assert.equal($('volumeDialog').open,true);
  assert.equal($('volumeItem').children[0].className,'hint','a clip without sound offers only the mix');
  const mix=$('volumeMix').children.map(row=>row.children[2].value);
  assert.equal(mix.join(),'100,50,100','voice, music and effects as a percentage of the original');
  $('volumeDialog').close();selection={kind:'audio',id:'m'};$('volume').onclick();
  const slider=$('volumeItem').children[0].children[2];
  assert.equal(slider.value,0,'a silenced element shows 0 %');
  api=async req=>{sent=req;return {ok:true,result:{}}};
  slider.value='80';slider.oninput();assert.equal($('volumeItem').children[0].children[1].textContent,'80 %');
  sent=null;await slider.onchange();
  assert.deepEqual(sent.op,{type:'volume',kind:'audio',id:'m',percent:80},'lifting the finger saves the element volume');
  const music=$('volumeMix').children[1].children[2];music.value='120';await music.onchange();
  assert.deepEqual(sent.op,{type:'mixer',role:'music',percent:120},'and the track volume');
  // Return to the actual opened project among 38 cards, preserving folder/search.
  const catalog=Array.from({length:38},(_,i)=>({id:'clip-'+(i+1),name:'Clip '+String(i+1).padStart(2,'0'),folder:'clips',duration:10,width:160,height:90}));
  const montage=structuredClone(p);
  query=async req=>req.action==='library'?{folders:[{id:'clips',name:'Clips'}],projects:catalog}:{project:{...montage,id:req.project},notes:[]};
  direct.load=async()=>false;folder='clips';$('search').value='Clip';lastProject=null;
  await loadLibrary();assert.equal($('projects').children.length,38);
  await $('projects').children[26].onclick();assert.equal(lastProject,'clip-27');
  catalog.reverse();await loadLibrary();
  const last=$('projects').children.find(n=>n.className.includes('last-opened'));
  assert.equal(last.children[1].children[0].textContent,'Clip 27');assert.equal(last.scrolled.block,'center');
  assert.equal($('projects').children.filter(n=>n.scrolled).length,1);assert.equal(folder,'clips');assert.equal($('search').value,'Clip');
  $('search').value='Clip 28';showLibrary();assert.equal($('projects').children.length,1);assert.equal($('projects').children[0].scrolled,undefined,'filtering does not force a scroll');
  $('search').value='Clip';catalog.splice(catalog.findIndex(x=>x.id==='clip-27'),1);await loadLibrary();
  assert.equal($('projects').children.some(n=>n.scrolled),false,'a removed project does not select its old row number');
  console.log('PASS · mobile UI: playhead-anchored zoom, timeline taps, editing, rewriting a text, delete, gap-free trim, playback reuse, speed, volume, drafts and lost acknowledgements');
})().catch(error=>{console.error(error);process.exitCode=1});`;
context.process=process;
vm.runInContext(code,context);
