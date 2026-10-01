'use strict';
let playbackKey=null,playbackPlaying=false,playbackTicket=0;
let playbackRate=1;
const playbackRateReady=api({action:'capabilities'}).then(c=>{
 state.playbackRateSupported=!!c.playbackRate;
 state.interactivePlayback=!!c.interactivePlayback;
 $('playbackSpeedControls').hidden=!state.playbackRateSupported;
 return state.playbackRateSupported;
}).catch(()=>false);
function parsePlaybackRate(value){
 const text=String(value).trim().replace(',','.');
 if(!/^\d+(?:\.\d+)?$/.test(text))return null;
 const rate=Number(text);return rate>=1&&rate<=2?Math.round(rate*100)/100:null;
}
function drawPlaybackRate(){
 $('playbackSpeed').value=String(playbackRate);
 $('playbackSpeed').setAttribute('aria-valuetext',String(playbackRate).replace('.',',')+' veces');
 $('playbackRate').value=String(playbackRate).replace('.',',');
 for(const [id,rate] of [['speed1',1],['speed15',1.5],['speed2',2]])$(id).setAttribute('aria-pressed',String(playbackRate===rate));
}
function setPlaybackRate(value){
 const rate=parsePlaybackRate(value);
 if(rate===null){drawPlaybackRate();toast('Escribe una velocidad entre 1 y 2; por ejemplo, 1,25.',true);return Promise.resolve(false);}
 playbackRate=rate;drawPlaybackRate();
 // Review preference only: never mutate the timeline or invalidate its cache.
 if(playbackKey&&state.playbackRateSupported)return api({action:'playback',command:'rate',rate}).then(()=>true);
 return Promise.resolve(true);
}
$('playbackSpeed').oninput=safe(()=>setPlaybackRate($('playbackSpeed').value));
$('playbackRate').onchange=safe(()=>setPlaybackRate($('playbackRate').value));
$('playbackRate').onkeydown=event=>{
 if(event.key==='Enter'){event.preventDefault();$('playbackRate').blur();}
 if(event.key==='Escape'){event.preventDefault();event.stopPropagation();drawPlaybackRate();$('playbackRate').blur();}
};
for(const [id,rate] of [['speed1',1],['speed15',1.5],['speed2',2]])$(id).onclick=safe(()=>setPlaybackRate(rate));
drawPlaybackRate();
function playbackRect(){const r=$('viewer').getBoundingClientRect();return {x:r.left,y:r.top,width:r.width,height:r.height};}
function updatePlaybackControls(){ $('play').textContent=playbackPlaying||state.continuingPlayback?'Ⅱ':'▶';drawImageSelection(); }
function playbackStatus(label,stateName=''){$('previewBadge').textContent=label;$('previewBadge').dataset.state=stateName;}
function cancelPreparation(job){if(state.interactivePlayback&&job?.token)void api({action:'cancelPreparation',preparation:job.token}).catch(()=>{});}
function playbackContains(frame){return !state.playbackPlan||(frame>=(state.playbackPlan.windowStart||0)&&frame<(state.playbackPlan.windowEnd??frames()));}
function invalidatePlayback(){
 cancelPreparation(state.preparingPlayback);cancelPreparation(state.nextPlayback);
 state.nextPlayback=null;state.playbackPlan=null;state.queuedPlayback=null;state.continuingPlayback=false;
 playbackTicket++;state.nativeAudio=false;state.audioIds=null;state.preparingPlayback=null;playbackKey=null;playbackPlaying=false;previewRevision=-1;
 // Keep the native composition warm. Image-only plans can then replace their
 // lightweight overlays without rebuilding the 20-minute video timeline.
 void api({action:'playback',command:state.interactivePlayback?'invalidate':'pause'}).catch(()=>{});updatePlaybackControls();
}
async function pausePlayback(){
 state.continuingPlayback=false;
 if(!playbackPlaying)return;
 playbackPlaying=false;await api({action:'playback',command:'pause'});updatePlaybackControls();
}
window.studioPlaybackEvent=event=>{
 if(event.advanced&&state.queuedPlayback?.plan.key===event.key&&!homeVisible&&p){
  const plan=state.queuedPlayback.plan;state.queuedPlayback=null;state.nextPlayback=null;
  adoptPlaybackPlan(plan);cursor=event.frame;playbackPlaying=!!event.playing;state.continuingPlayback=false;updatePlaybackControls();prefetchPlayback(plan);
 }
 if(homeVisible||!p||event.key!==playbackKey)return;
 if(event.queueFailed){state.queuedPlayback=null;return;}
 if(event.error){
  const retry=state.interactivePlayback&&!state.playbackPlan?.rasterFallback&&playbackPlaying;
  if(Number.isInteger(event.frame))cursor=Math.min(frames()-1,event.frame);
  invalidatePlayback();
  if(retry){state.rasterProject=path;state.continuingPlayback=true;void safe(()=>continuePlayback(cursor))();}
  else{playbackStatus('No se pudo reproducir este tramo','error');toast(event.error,true);void safe(()=>seek(cursor))();}
  return;
 }
 if(event.playing||event.ended){cursor=Math.min(frames()-1,Math.max(0,event.frame));$('cursorTime').textContent=tc(cursor);$('playhead').style.left=cursor/Math.max(1,frames())*100+'%';}
 if(event.ended){
  const end=state.playbackPlan?.windowEnd??frames();
  if(playbackPlaying&&end<frames()){playbackPlaying=false;state.continuingPlayback=true;updatePlaybackControls();void safe(()=>continuePlayback(end))();}
  else{playbackPlaying=false;updatePlaybackControls();void safe(()=>seek(cursor))();}
 }
};
function prefetchPlayback(plan){
 if(!state.interactivePlayback||!plan.progressive||plan.windowEnd>=frames())return;
 const from=plan.windowEnd,projectPath=path,revision=p.revision,ticket=playbackTicket,token='next-'+(state.preparationSerial=(state.preparationSerial||0)+1);
 cancelPreparation(state.nextPlayback);
 // Cache one following interval only. Edits cancel this exact engine job.
 const promise=api({action:'preparePlayback',project:projectPath,revision,frame:from,lookAhead:true,forceRaster:!!plan.rasterFallback,preparation:token}).then(async next=>{
  if(ticket===playbackTicket&&path===projectPath&&p.revision===revision&&playbackKey===plan.key){
   const queued={plan:next,afterKey:plan.key};state.queuedPlayback=queued;
   try{await api({action:'queuePlayback',plan:next,afterKey:plan.key});}
   catch(_){if(state.queuedPlayback===queued)state.queuedPlayback=null;}
  }
  return {plan:next};
 },error=>({error}));
 state.nextPlayback={path:projectPath,revision,from,token,promise};
}
function adoptPlaybackPlan(plan){
 state.nativeAudio=!plan.audio;state.audioIds=new Set([...(plan.audioSources||[]),...(plan.audioCues||[])].map(x=>x.id));
 state.playbackPlan=plan;playbackKey=plan.key;previewRevision=p.revision;
 playbackStatus('Reproducción lista','ready');$('renderState').textContent=plan.progressive?'Efectos preparados por tramos · vista de edición':plan.renderedFrames?'Caché actualizada · '+plan.seconds+' s':'Capas en tiempo real';
}
async function continuePlayback(from){
 const ticket=playbackTicket,projectPath=path,revision=p.revision;
 playbackStatus('Preparando este tramo…','preparing');
 try{
  if(!await preparePlayback(from))return;
  if(!state.continuingPlayback||ticket!==playbackTicket-1||path!==projectPath||p.revision!==revision)return;
  cursor=from;
  await api({action:'playback',command:'play',rect:playbackRect(),...(state.playbackRateSupported?{rate:playbackRate}:{})});
  if(!state.continuingPlayback){await api({action:'playback',command:'pause'});return;}
  playbackPlaying=true;state.continuingPlayback=false;$('still').hidden=true;updatePlaybackControls();
 }catch(error){state.continuingPlayback=false;playbackPlaying=false;updatePlaybackControls();throw error;}
}
async function preparePlayback(from=cursor){
 await mutationTail;if(!frames())return;
 const projectPath=path,revision=p.revision;
 if(state.preparingPlayback?.path===projectPath&&state.preparingPlayback.revision===revision&&state.preparingPlayback.from===from)return state.preparingPlayback.promise;
 cancelPreparation(state.preparingPlayback);
 const ticket=++playbackTicket;
 const token='play-'+ticket;
 playbackStatus('Preparando reproducción…','preparing');$('renderState').textContent='Puedes seguir editando mientras se prepara';
 const promise=(async()=>{
  try{
   const next=state.nextPlayback;
   let plan;
   if(next&&next.path===projectPath&&next.revision===revision&&next.from===from){
    const result=await next.promise;if(result.error)throw result.error;plan=result.plan;
    if(state.nextPlayback===next)state.nextPlayback=null;
   }else{
    cancelPreparation(next);state.nextPlayback=null;
    plan=await api({action:'preparePlayback',project:projectPath,revision,frame:from,forceRaster:state.rasterProject===projectPath,...(state.interactivePlayback?{preparation:token}:{})});
   }
   if(ticket!==playbackTicket||path!==projectPath||p.revision!==revision||homeVisible)return false;
   try{await api({action:'loadPlayback',plan,frame:from});}
   catch(error){
    if(!state.interactivePlayback||plan.rasterFallback||ticket!==playbackTicket||path!==projectPath||p.revision!==revision)throw error;
    // An unsupported camera codec still gets every layer, through a bounded
    // canonical proxy. Keep this choice for this project during this session.
    state.rasterProject=projectPath;
    plan=await api({action:'preparePlayback',project:projectPath,revision,frame:from,forceRaster:true,preparation:token});
    if(ticket!==playbackTicket||path!==projectPath||p.revision!==revision||homeVisible)return false;
    await api({action:'loadPlayback',plan,frame:from});
   }
   if(ticket!==playbackTicket||path!==projectPath||p.revision!==revision||homeVisible)return false;
   state.queuedPlayback=null;adoptPlaybackPlan(plan);prefetchPlayback(plan);return true;
  }catch(error){
   if(ticket!==playbackTicket||error.cancelled)return false;
   playbackStatus('Reproducción pendiente','error');$('renderState').textContent='Pulsa reproducir para reintentar';
   throw error;
  }finally{if(state.preparingPlayback?.ticket===ticket)state.preparingPlayback=null;}
 })();
 state.preparingPlayback={ticket,path:projectPath,revision,from,token,promise};return promise;
}
async function togglePlay(){
 if(!frames()||busy||state.feedbackOpening||$('feedbackDialog').open||state.duplicating||$('duplicateDialog').open)return;
 await flushEdits();
 if(playbackPlaying||state.continuingPlayback){await pausePlayback();await syncExternal();await seek(cursor);return;}
 if(cursor>=frames()-1)cursor=0;
 if(previewRevision!==p.revision||!playbackKey||!playbackContains(cursor)){if(!await preparePlayback())return;}
 if(state.feedbackOpening||$('feedbackDialog').open||state.duplicating||$('duplicateDialog').open)return;
 await api({action:'playback',command:'seek',frame:cursor});
 if(state.feedbackOpening||$('feedbackDialog').open||state.duplicating||$('duplicateDialog').open)return;
 await api({action:'playback',command:'play',rect:playbackRect(),...(state.playbackRateSupported?{rate:playbackRate}:{})});
 if(state.feedbackOpening||$('feedbackDialog').open||state.duplicating||$('duplicateDialog').open){await api({action:'playback',command:'pause'});return;}
 playbackPlaying=true;$('still').hidden=true;updatePlaybackControls();
}
if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>{if(playbackKey)void api({action:'playback',rect:playbackRect()}).catch(()=>{});}).observe($('viewer'));
