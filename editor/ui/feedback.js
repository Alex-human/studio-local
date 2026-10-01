'use strict';
const feedback={enabled:false,notes:[],path:null,version:-1,revision:-1,filter:'open',note:null,strokes:[],stroke:null,tool:'pen',generation:0,saved:0,error:null,tail:Promise.resolve(),creating:null,capturing:null};
const feedbackReady=api({action:'capabilities'}).then(c=>feedback.enabled=!!c.feedback).catch(()=>false);
function feedbackRequest(command,extra={},target=path){return api({action:'feedback',command,project:target,revision:p?.revision,...extra});}
function feedbackTime(frame,fps=p?.fps||60){const sec=Math.floor(frame/fps),f=Math.floor(frame-sec*fps);return [Math.floor(sec/3600),Math.floor(sec/60)%60,sec%60,f].map(n=>String(n).padStart(2,'0')).join(':');}
function feedbackSessionId(){return $('feedbackDialog').open?feedback.note?.id:null;}
function feedbackFailure(error){feedback.error=error;$('feedbackError').textContent=error.message;$('feedbackError').hidden=false;$('feedbackRetrySave').hidden=!!error.conflict;$('feedbackReload').hidden=!error.conflict;$('feedbackSaveState').textContent='No guardado · tu texto sigue aquí';}
function feedbackSaved(){feedback.error=null;$('feedbackError').hidden=true;$('feedbackRetrySave').hidden=true;$('feedbackReload').hidden=true;$('feedbackSaveState').textContent=feedback.generation===feedback.saved?(feedback.note?.status==='draft'?'Borrador guardado en este Mac':'Guardado en este Mac'):'Guardando…';}
function drawFeedbackMarkers(){
 const row=$('feedbackTrack');row.replaceChildren();if(!p||feedback.path!==path)return;
 const width=timelineWidth(),groups=new Map();
 for(const note of feedback.notes){if(note.currentFrame===null||note.status==='deleted')continue;const bucket=Math.floor(note.currentFrame/Math.max(1,frames())*width/25);if(!groups.has(bucket))groups.set(bucket,[]);groups.get(bucket).push(note);}
 for(const notes of groups.values()){
  const note=notes.find(n=>n.status==='open')||notes[0],b=elem('button','feedback-marker '+note.status,'F');
  if(notes.length>1)b.append(elem('small',null,notes.length));
  b.style.left=Math.max(13,Math.min(width-13,note.currentFrame/Math.max(1,frames())*width))+'px';
  b.title=notes.length>1?notes.length+' comentarios aquí':feedbackTime(note.currentFrame)+' · '+(note.text||'Indicación dibujada');b.setAttribute('aria-label','Feedback '+feedbackTime(note.currentFrame)+' · '+(note.text||'Dibujo'));
  b.onclick=safe(async e=>{e.stopPropagation();showFeedbackPanel(true);await openFeedback(note.id);});row.append(b);
 }
}
function showFeedbackPanel(show=true){$('feedbackPanel').hidden=!show;$('feedbackPanel').parentElement.classList.toggle('feedback-mode',show);if(show)void refreshFeedback(true);}
function drawFeedbackList(){
 $('feedbackCount').textContent=feedback.notes.filter(n=>n.status==='open').length;const list=$('feedbackList');list.replaceChildren();
 const notes=feedback.notes.filter(n=>feedback.filter==='all'||(feedback.filter==='open'?['open','draft'].includes(n.status):n.status==='resolved'));
 $('feedbackListStatus').textContent=feedback.notes.length?feedback.notes.filter(n=>n.status==='open').length+' pendientes · guardados en este Mac':'';
 for(const note of notes){
  const button=elem('button','feedback-note');const head=elem('div','feedback-note-heading');head.append(elem('strong',null,note.currentFrame===null?'Tramo no disponible':feedbackTime(note.currentFrame)),elem('span',null,{open:'Pendiente',draft:'Borrador',resolved:'Resuelto'}[note.status]));
  button.append(head,elem('p',null,note.text|| (note.strokes.length?'Indicación dibujada':'Borrador sin comentario')));if(note.strokes.length)button.append(elem('small',null,'✎ Incluye dibujo'));button.onclick=safe(()=>openFeedback(note.id));list.append(button);
 }
 if(!notes.length)list.append(elem('p','feedback-empty',feedback.filter==='resolved'?'Los comentarios resueltos aparecerán aquí.':'Pulsa ⌘F en cualquier momento del vídeo. Escribe qué cambiar y, si quieres, dibuja sobre el fotograma.'));
 drawFeedbackMarkers();
}
async function refreshFeedback(force=false){
 if(!feedback.enabled||homeVisible||!p||feedback.polling)return;
 const target=path,revision=p.revision;if(feedback.path!==target){feedback.path=target;feedback.notes=[];feedback.version=feedback.revision=-1;drawFeedbackList();}feedback.polling=true;
 try{
  const data=await feedbackRequest('list',{since:force?-1:feedback.version,projectRevision:feedback.revision});
  if(path!==target||p.revision!==revision)return;
  if(!data.unchanged){feedback.path=target;feedback.notes=data.notes;feedback.version=data.version;feedback.revision=data.projectRevision;drawFeedbackList();}
 }catch(e){$('feedbackListStatus').textContent='No se pudo leer el feedback: '+e.message;}
 finally{feedback.polling=false;}
}
function updateFeedbackTools(){
 const ready=feedback.note?.capture==='ready';
 for(const name of ['Pen','Ellipse','Rect','Arrow','Color','Undo','Clear'])$('feedback'+name).disabled=!ready;
 $('feedbackPublish').disabled=!ready||(!$('feedbackText').value.trim()&&!feedback.strokes.length);
 $('feedbackResolve').hidden=!feedback.note||feedback.note.status==='draft';$('feedbackResolve').textContent=feedback.note?.status==='resolved'?'↶ Reabrir comentario':'✓ Marcar resuelto';
 $('feedbackDelete').textContent=feedback.note?.status==='draft'?'Descartar borrador':'Eliminar comentario';
 for(const [id,tool] of [['Pen','pen'],['Ellipse','ellipse'],['Rect','rect'],['Arrow','arrow']]){const selected=feedback.tool===tool;$('feedback'+id).classList.toggle('active',selected);$('feedback'+id).setAttribute('aria-pressed',String(selected));}
}
function strokeSVG(s){
 const W=feedback.canvasWidth||1920,H=feedback.canvasHeight||1080,unit=Math.min(W,H),points=s.points.map(([x,y])=>[x*W,y*H]),style=`fill="none" stroke="${s.color}" stroke-width="${s.width*unit}" stroke-linecap="round" stroke-linejoin="round"`;
 if(s.tool==='pen')return points.length===1?`<circle cx="${points[0][0]}" cy="${points[0][1]}" r="${s.width*unit/2}" fill="${s.color}"/>`:`<polyline points="${points.map(p=>p.join(',')).join(' ')}" ${style}/>`;
 const [[x1,y1],[x2,y2]]=points,x=Math.min(x1,x2),y=Math.min(y1,y2),w=Math.abs(x2-x1),h=Math.abs(y2-y1);
 if(s.tool==='ellipse')return `<ellipse cx="${x+w/2}" cy="${y+h/2}" rx="${w/2}" ry="${h/2}" ${style}/>`;
 if(s.tool==='rect')return `<rect x="${x}" y="${y}" width="${w}" height="${h}" ${style}/>`;
 const angle=Math.atan2(y2-y1,x2-x1),size=.035*unit;return `<path d="M${x1} ${y1}L${x2} ${y2}M${x2-size*Math.cos(angle-.5)} ${y2-size*Math.sin(angle-.5)}L${x2} ${y2}L${x2-size*Math.cos(angle+.5)} ${y2-size*Math.sin(angle+.5)}" ${style}/>`;
}
function drawFeedbackStrokes(){$('feedbackDrawing').innerHTML=[...feedback.strokes,...(feedback.stroke?[feedback.stroke]:[])].map(strokeSVG).join('');updateFeedbackTools();}
function feedbackPoint(event){const rect=$('feedbackDrawing').getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];}
function changedFeedback(){feedback.generation++;$('feedbackSaveState').textContent='Guardando borrador…';clearTimeout(feedback.timer);feedback.timer=setTimeout(()=>void saveFeedbackDraft().catch(feedbackFailure),350);updateFeedbackTools();}
function finishFeedbackStroke(){if(!feedback.stroke)return;feedback.strokes.push(feedback.stroke);feedback.stroke=null;drawFeedbackStrokes();changedFeedback();}
$('feedbackDrawing').onpointerdown=event=>{if(event.button!==0||feedback.note?.capture!=='ready')return;if(feedback.strokes.length>=100)return toast('Máximo 100 trazos. Puedes borrar alguno antes de seguir.');event.preventDefault();const point=feedbackPoint(event);feedback.stroke={tool:feedback.tool,color:$('feedbackColor').value,width:.005,points:feedback.tool==='pen'?[point]:[point,point]};$('feedbackDrawing').setPointerCapture(event.pointerId);drawFeedbackStrokes();};
$('feedbackDrawing').onpointermove=event=>{const stroke=feedback.stroke;if(!stroke)return;const point=feedbackPoint(event);if(stroke.tool==='pen'){const last=stroke.points.at(-1);if(stroke.points.length<2000&&Math.hypot(point[0]-last[0],point[1]-last[1])>.001)stroke.points.push(point);}else stroke.points[1]=point;drawFeedbackStrokes();};
$('feedbackDrawing').onpointerup=finishFeedbackStroke;$('feedbackDrawing').onpointercancel=finishFeedbackStroke;
for(const [id,tool] of [['Pen','pen'],['Ellipse','ellipse'],['Rect','rect'],['Arrow','arrow']])$('feedback'+id).onclick=()=>{feedback.tool=tool;updateFeedbackTools();};
$('feedbackUndo').onclick=()=>{if(feedback.strokes.length){feedback.strokes.pop();drawFeedbackStrokes();changedFeedback();}};
$('feedbackClear').onclick=()=>{feedback.strokes=[];drawFeedbackStrokes();changedFeedback();};$('feedbackText').oninput=changedFeedback;
function saveFeedbackDraft(){
 clearTimeout(feedback.timer);
 const generation=feedback.generation,text=$('feedbackText').value,strokes=JSON.parse(JSON.stringify(feedback.strokes)),target=feedback.target;
 const task=feedback.tail.catch(()=>{}).then(async()=>{
  if(feedback.creating)await feedback.creating;
  if(!feedback.note){if(feedback.error)throw feedback.error;return;}if(generation===feedback.saved)return;
  const result=await feedbackRequest('update',{id:feedback.note.id,version:feedback.note.version,values:{text,strokes,...(feedback.note.status==='resolved'?{status:'open'}:{})}},target);
  feedback.note={...result,capture:feedback.note.capture==='ready'?'ready':result.capture,files:{...result.files,...feedback.note.files}};feedback.saved=generation;feedbackSaved();return result;
 });feedback.tail=task;return task;
}
async function flushFeedback(){if(!$('feedbackDialog').open)return;try{finishFeedbackStroke();await saveFeedbackDraft();if(feedback.error)throw feedback.error;}catch(e){feedbackFailure(e);throw e;}}
function showFeedbackCapture(note){
 const ready=note.capture==='ready'&&note.files.image;$('feedbackCaptureStatus').hidden=!!ready;
 $('feedbackCaptureStatus').textContent=note.capture==='error'?'No se pudo preparar este fotograma. Tu comentario está guardado.':'Preparando fotograma…';$('feedbackRetryCapture').hidden=note.capture!=='error';
 if(ready){$('feedbackImage').src=fileURL(note.files.image);$('feedbackImage').onload=()=>{if($('feedbackImage').naturalWidth)$('feedbackCanvas').style.aspectRatio=$('feedbackImage').naturalWidth+'/'+$('feedbackImage').naturalHeight;};}
 updateFeedbackTools();
}
async function captureFeedback(){
 const note=feedback.note,target=feedback.target;if(!note)return;
 try{const result=await feedbackRequest('capture',{id:note.id},target);if(feedback.note?.id!==note.id)return;feedback.note.capture=result.capture;feedback.note.files=result.files;showFeedbackCapture(feedback.note);}
 catch(e){if(feedback.note?.id===note.id){feedback.note.capture='error';showFeedbackCapture(feedback.note);$('feedbackError').textContent=e.message;$('feedbackError').hidden=false;}}
}
async function createFeedbackNote(){
 const req=feedback.createRequest;
 feedback.creating=feedbackRequest(req.command,req.values,feedback.target).then(note=>{

   feedback.note=note;$('feedbackText').disabled=false;feedback.canvasWidth=note.width;feedback.canvasHeight=note.height;$('feedbackDrawing').setAttribute('viewBox','0 0 '+note.width+' '+note.height);if(feedback.createRequest.command==='get'){$('feedbackText').value=note.text;feedback.strokes=note.strokes;$('feedbackText').focus();}
   $('feedbackTime').textContent=feedbackTime(note.frame,note.fps);$('feedbackPosition').textContent=note.currentFrame===null?'El fragmento original ya no está en el montaje. Conservamos su captura.':'Captura de la revisión '+note.revision+' · fotograma '+note.frame;
   $('feedbackGoTo').disabled=note.currentFrame===null;showFeedbackCapture(note);drawFeedbackStrokes();feedbackSaved();
   if(note.capture!=='ready')feedback.capturing=captureFeedback();return note;

 });
 try{return await feedback.creating;}finally{feedback.creating=null;}
}
async function openFeedback(id=null){
 if(!await feedbackReady)return toast('El feedback estará disponible cuando termine la actualización del editor.');
 if(homeVisible||!p||!frames()||busy)return;
 if($('cropDialog').open||($('newDialog').open||$('duplicateDialog').open))return toast('Cierra el diálogo actual antes de añadir feedback.');
 if($('feedbackDialog').open){if(!id||id===feedback.note?.id){$('feedbackText').focus();return;}await closeFeedback();}
 if(state.feedbackOpening)return;state.feedbackOpening=true;
 try{
  await flushEdits();
  if(state.preparingPlayback){invalidatePlayback();playbackStatus('Reproducción pendiente');$('renderState').textContent='';}
  if(playbackPlaying){const frozen=await api({action:'playback',command:'freeze'});if(!Number.isInteger(frozen.frame))throw new Error('No se pudo fijar el fotograma. Pausa el vídeo y vuelve a pulsar ⌘F.');playbackPlaying=false;cursor=frozen.frame;updatePlaybackControls();}
  await pausePlayback();clearTimeout(frameTimer);
  feedback.target=path;feedback.canvasWidth=p.width;feedback.canvasHeight=p.height;$('feedbackDrawing').setAttribute('viewBox','0 0 '+p.width+' '+p.height);feedback.note=null;feedback.generation=feedback.saved=0;feedback.error=null;feedback.strokes=[];feedback.stroke=null;feedback.tail=Promise.resolve();
  $('feedbackText').value='';$('feedbackText').disabled=!!id;$('feedbackError').hidden=true;$('feedbackRetrySave').hidden=true;$('feedbackReload').hidden=true;$('feedbackRetryCapture').hidden=true;$('feedbackImage').removeAttribute('src');$('feedbackCanvas').style.aspectRatio=p.width+'/'+p.height;$('feedbackCaptureStatus').hidden=false;$('feedbackCaptureStatus').textContent='Preparando fotograma…';$('feedbackSaveState').textContent='Borrador';$('feedbackTime').textContent=feedbackTime(cursor);drawFeedbackStrokes();$('feedbackDialog').showModal();$('feedbackText').focus();
  const requestId=id||('f'+Date.now().toString(36)+Math.random().toString(36).slice(2,10));
  feedback.createRequest={command:id?'get':'create',values:{id:requestId,frame:cursor,revision:p.revision}};
  await createFeedbackNote();
 }catch(e){feedbackFailure(e);}
 finally{state.feedbackOpening=false;}
}
window.studioFeedback=()=>{if(homeVisible||busy)return false;void openFeedback();return true;};
async function closeFeedback(){
 await flushFeedback();
 if(feedback.note?.status==='draft'&&!$('feedbackText').value.trim()&&!feedback.strokes.length)await feedbackRequest('update',{id:feedback.note.id,version:feedback.note.version,values:{status:'deleted'}},feedback.target);
 $('feedbackDialog').close();feedback.note=null;feedback.error=null;void refreshFeedback(true);await seek(cursor);
}
$('feedbackPublish').onclick=safe(async()=>{await flushFeedback();feedback.note=await feedbackRequest('update',{id:feedback.note.id,version:feedback.note.version,values:{status:'open'}},feedback.target);await closeFeedback();toast('Feedback guardado · texto, dibujo y fotograma asociados.');});
$('feedbackClose').onclick=safe(closeFeedback);$('feedbackDialog').oncancel=event=>{event.preventDefault();void closeFeedback().catch(feedbackFailure);};
$('feedbackReload').onclick=safe(async()=>{clearTimeout(feedback.timer);await feedback.tail.catch(()=>{});feedback.generation=feedback.saved=0;feedback.createRequest={command:'get',values:{id:feedback.note.id}};await createFeedbackNote();});
$('feedbackRetrySave').onclick=()=>void (async()=>{if(!feedback.note)await createFeedbackNote();await saveFeedbackDraft();})().catch(feedbackFailure);$('feedbackRetryCapture').onclick=()=>{feedback.note.capture='pending';showFeedbackCapture(feedback.note);feedback.capturing=captureFeedback();};
$('feedbackResolve').onclick=safe(async()=>{await flushFeedback();feedback.note=await feedbackRequest('update',{id:feedback.note.id,version:feedback.note.version,values:{status:feedback.note.status==='resolved'?'open':'resolved'}},feedback.target);await closeFeedback();});
$('feedbackDelete').onclick=safe(async()=>{clearTimeout(feedback.timer);await feedback.tail.catch(()=>{});if(feedback.creating)await feedback.creating.catch(()=>{});if(feedback.note)await feedbackRequest('update',{id:feedback.note.id,version:feedback.note.version,values:{status:'deleted'}},feedback.target);feedback.error=null;feedback.generation=feedback.saved;$('feedbackDialog').close();feedback.note=null;void refreshFeedback(true);});
$('feedbackGoTo').onclick=safe(async()=>{const frame=feedback.note?.currentFrame;if(frame===null||frame===undefined)return;await closeFeedback();await seek(frame);});
$('feedbackToggle').onclick=()=>showFeedbackPanel($('feedbackPanel').hidden);$('feedbackNew').onclick=()=>void openFeedback();$('feedbackPanelClose').onclick=()=>showFeedbackPanel(false);
for(const [id,filter] of [['Open','open'],['All','all'],['Resolved','resolved']])$('feedback'+id+'Filter').onclick=()=>{feedback.filter=filter;for(const name of ['Open','All','Resolved'])$('feedback'+name+'Filter').classList.toggle('active',id===name);drawFeedbackList();};
document.addEventListener('keydown',event=>{
 if(event.metaKey&&event.key.toLowerCase()==='f'){event.preventDefault();window.studioFeedback();return;}
 if(!$('feedbackDialog').open)return;
 if(event.metaKey&&event.key==='Enter'){event.preventDefault();if(!$('feedbackPublish').disabled)void $('feedbackPublish').onclick();}
 if(event.metaKey&&event.key.toLowerCase()==='z'&&!['INPUT','TEXTAREA'].includes(event.target.tagName)){event.preventDefault();$('feedbackUndo').onclick();}
});
