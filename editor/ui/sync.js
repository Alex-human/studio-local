'use strict';
// Revision polling never takes focus from a field or interrupts a running review.
function syncBlocked(){return busy||state.duplicating||state.folderBusy||state.creatingProject||$('folderDialog').open||state.feedbackOpening||$('feedbackDialog').open||state.booting||state.updating||state.conflict||state.saveError||['dirty','saving'].includes(state.saveStatus)||rulerDrag||edgeDrag||imageDrag||cropDrag||$('cropDialog').open||($('newDialog').open||$('duplicateDialog').open)||['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);}
function sourceAnchor(model,frame){
 let start=0;for(const c of model?.clips||[]){if(frame<start+c.length)return {id:c.id,asset:c.asset,source:c.in+(frame-start)*(c.speed||1)};start+=c.length;}return null;
}
function anchorFrame(model,anchor,fallback){
 if(!anchor)return fallback;let start=0,candidates=[];
 for(const c of model.clips){if(c.asset===anchor.asset&&anchor.source>=c.in&&anchor.source<c.in+c.length*(c.speed||1))candidates.push({id:c.id,frame:start+Math.round((anchor.source-c.in)/(c.speed||1))});start+=c.length;}
 return (candidates.find(c=>c.id===anchor.id)||candidates.sort((a,b)=>Math.abs(a.frame-fallback)-Math.abs(b.frame-fallback))[0])?.frame??Math.min(fallback,Math.max(0,start-1));
}
function sessionView(){return {project:homeVisible?null:path,homeFolder,revision:p?.revision,cursor,anchor:sourceAnchor(p,cursor),zoom,scroll:$('timelineScroll').scrollLeft,selection,cutStart,cutEnd,playing:playbackPlaying,playbackRate,feedbackId:typeof feedbackSessionId==='function'?feedbackSessionId():null};}
let sessionTail=Promise.resolve();
function saveSession(){if(state.booting)return Promise.resolve();const session=sessionView();const task=sessionTail.catch(()=>{}).then(()=>api({action:'sessionSave',session}));sessionTail=task;return task;}
function restoreView(view){
 cursor=Math.max(0,Math.min(anchorFrame(p,view.anchor,view.cursor||0),Math.max(0,frames()-1)));zoom=Math.max(1,Math.min(64,view.zoom||1));selection=view.selection;
 if(selection&&!selected())selection=null;
 if(p.revision===view.revision){cutStart=view.cutStart??null;cutEnd=view.cutEnd??null;}
 draw();$('timelineScroll').scrollLeft=view.scroll||0;
}
async function restoreSession(){
 state.booting=true;
 try{
  const view=await api({action:'sessionRead'});
  homeFolder=view?.homeFolder||null;
  await playbackRateReady;
  playbackRate=parsePlaybackRate(view?.playbackRate??1)??1;drawPlaybackRate();
  if(view?.project){await refreshProjects();if(await openProject(view.project)){restoreView(view);await seek(cursor);if(view.feedbackId&&typeof openFeedback==='function')await openFeedback(view.feedbackId);else if(view.playing)await togglePlay();}return;}
  await showProjects();
 }catch(e){toast('No se pudo recuperar la sesión: '+e.message,true);await showProjects();}
 finally{state.booting=false;}
}

function audioShape(model){return JSON.stringify(model,(key,value)=>['revision','mixer','volumeDb','muted','soundDb'].includes(key)?undefined:value);}
async function acceptExternal(data){
 const view=sessionView(),keep=liveAudioReady()&&audioShape(p)===audioShape(data.project);
 if(keep)void api({action:'playback',command:'levels',key:playbackKey,levels:audioLevels(data.project)}).catch(e=>toast(e.message,true));
 receive(data,keep);restoreView(view);setSaveState('saved');
 if(!keep)await seek(cursor);
 $('syncMessage').hidden=true;
}
async function syncExternal(){
 if(homeVisible||!p||syncBlocked()||state.polling)return;
 const target=path,revision=p.revision,serial=state.mutationSerial;state.polling=true;
 try{
  const data=await api({action:'poll',project:target,revision});
  if(path!==target||p.revision!==revision||state.mutationSerial!==serial||syncBlocked()||!data.changed)return;
  if((playbackPlaying||state.continuingPlayback)&&(!liveAudioReady()||audioShape(p)!==audioShape(data.project))){
   $('syncMessage').textContent='Cambios recibidos · se incorporan al pausar';$('syncMessage').hidden=false;return;
  }
  await acceptExternal(data);
 }catch(e){$('syncMessage').textContent='Sincronización pendiente · '+e.message;$('syncMessage').hidden=false;}
 finally{state.polling=false;}
}
function showSyncConflict(error){$('syncConflict').hidden=false;$('syncConflictText').textContent=error.message;}
$('resolveSync').onclick=safe(async()=>{
 // Explicitly discards only the rejected local attempt, never a saved revision.
 await mutationTail;const data=await api({action:'open',project:path});
 state.conflict=null;state.saveError=null;$('syncConflict').hidden=true;await acceptExternal(data);
 toast('Versión guardada cargada. Puedes repetir el ajuste sobre esta versión.');
});
window.studioUpdateCancelled=()=>{state.updating=false;};
window.studioRequestUpdate=kind=>{state.updateAvailable=kind;$('updateEditor').hidden=false;return true;};
async function applyEditorUpdate(){
 if(syncBlocked()||playbackPlaying||state.continuingPlayback||state.preparingPlayback||state.polling)return false;
 state.updating=true;
 try{await flushEdits();await saveSession();await api({action:'applyUpdate',kind:state.updateAvailable});return true;}
 catch(e){state.updating=false;toast('Actualización pendiente: '+e.message,true);return false;}
}
$('updateEditor').onclick=safe(applyEditorUpdate);
let lastInteraction=Date.now();
for(const event of ['pointerdown','keydown','input'])document.addEventListener(event,()=>{lastInteraction=Date.now();});
if(typeof setInterval==='function')setInterval(async()=>{
 if(state.updating)return;
 await syncExternal();
 if(typeof refreshFeedback==='function')await refreshFeedback();
 if(!syncBlocked()&&!state.polling){
  const view=JSON.stringify(sessionView());if(view!==state.lastSession){try{await saveSession();state.lastSession=view;}catch(e){/* Quit/update still requires a successful save. */}}
  if(state.updateAvailable&&!playbackPlaying&&Date.now()-lastInteraction>4000)await applyEditorUpdate();
 }
},1200);
