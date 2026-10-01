'use strict';
const timelineTracks=[['video','Vídeo','clips'],['overlays','Superposición','graphics'],['graphics','Gráficos','graphics'],['captions','Texto','captions'],['voice','Voz','audio'],['music','Música','audio'],['sfx','Efectos','audio']];
let cutStart=null,cutEnd=null,rulerDrag=null,edgeDrag=null,timelineFocused=false;
function isLinked(kind,item){return kind==='clips'||(item.linked??p.syncTracks?.[kind==='audio'?item.role:kind==='graphics'&&item.type==='video'?'overlays':kind]??true);}
function trackItems(track,kind){return p[kind].filter(item=>kind==='audio'?item.role===track:kind==='graphics'?(item.type==='video')===(track==='overlays'):true);}
function validRange(){return cutStart!==null&&cutEnd!==null&&cutEnd>cutStart&&cutEnd<=frames();}
function clearCutRange(){cutStart=cutEnd=null;}
function timelineShape(project){return JSON.stringify(project?.clips.map(c=>[c.id,c.in,c.length,c.speed]));}
function timelineWidth(){return Math.max(600,$('timelineScroll').clientWidth-160)*zoom;}
function videoRanges(){let start=0;return p.clips.map(item=>{const range={item,start,end:start+item.length};start=range.end;return range;});}
function mediaHandle(item,edge){const a=asset(item.asset),speed=item.speed||1;if(!a?.duration)return 0;return edge==='start'?Math.max(0,Math.floor(((item.in||0)+1e-7)/speed)):Math.max(0,Math.floor((a.duration*p.fps-(item.in||0)-item.length*speed+1e-7)/speed));}
function edgeLimits(range,edge){
 const item=range.item;if(range.kind!=='clips'){let available=Math.max(0,edge==='start'?range.start:frames()-range.end);if(range.kind==='audio'||range.kind==='graphics'&&item.type==='video')available=Math.min(available,mediaHandle(item,edge));return edge==='start'?{min:-available,max:item.length-1}:{min:-(item.length-1),max:available};}
 const ranges=videoRanges(),index=ranges.findIndex(x=>x.item.id===item.id);let available=mediaHandle(item,edge),neighbour=edge==='start'?ranges[index-1]?.item:ranges[index+1]?.item;
 if(neighbour?.asset===item.asset){const itemStart=item.in||0,itemEnd=itemStart+item.length*(item.speed||1),otherStart=neighbour.in||0,otherEnd=otherStart+neighbour.length*(neighbour.speed||1);available=Math.min(available,Math.max(0,Math.floor(((edge==='start'?itemStart-otherEnd:otherStart-itemEnd)+1e-7)/(item.speed||1))));}
 return edge==='start'?{min:-available,max:item.length-1}:{min:-(item.length-1),max:available};
}
function selectedCutGroup(){
 if(!selection||!p)return null;
 if(selection.kind==='graphics'&&selected()?.type==='video')return null;
 if(selection.kind==='clips')return videoRanges().find(range=>range.item.id===selection.id)||null;
 const item=selected();if(!item||!isLinked(selection.kind,item)||item.start===undefined)return null;
 return videoRanges().find(range=>range.start===item.start&&range.end===item.start+item.length)||null;
}
function drawDuplicateButton(){
 const item=selected(),button=$('duplicate');button.disabled=!item||!!state.duplicating;
 button.title=!item?'Selecciona un elemento para duplicarlo':selection.kind==='clips'?'Duplicar este tramo y sus capas vinculadas a continuación':'Duplicar solo este elemento a continuación';
}
function duplicatePosition(){
 const raw=$('duplicateStart').value.trim().replace(',','.');
 if(!/^\d+(?:\.\d*)?$/.test(raw))return null;
 const start=Math.round(Number(raw)*p.fps),length=Math.min(state.duplicateSource?.length||0,frames()-start);
 return Number.isSafeInteger(start)&&start>=0&&length>0?{start,length}:null;
}
function drawDuplicatePosition(){
 const position=duplicatePosition(),source=state.duplicateSource;
 $('duplicateApply').disabled=!position||!!state.duplicating;
 $('duplicateCancel').disabled=!!state.duplicating;
 if(!position){$('duplicateSummary').textContent='Elige un inicio dentro del vídeo.';return;}
 const {start,length}=position,seconds=n=>(n/p.fps).toFixed(2).replace('.',',')+' s';
 const overlaps=source.kind==='audio'&&p.audio.some(a=>a.role===source.role&&a.start<start+length&&a.start+a.length>start);
 $('duplicateSummary').textContent=(length<source.length?'Se copiarán '+seconds(length)+' de los '+seconds(source.length)+' del original para encajar.':'Copia completa · '+seconds(length)+'.')+' Termina en '+tc(start+length)+'.'+(overlaps?' Se superpone con audio de esta pista.':'');
}
async function commitDuplicate(source,position={}){
 const id='copy-'+Date.now().toString(36)+Math.random().toString(36).slice(2,10);
 await ops(()=>{if(path!==source.project||p.revision!==source.revision)throw new Error('El proyecto cambió. Selecciona de nuevo el elemento que quieres duplicar.');return [{op:'duplicate',kind:source.kind,id:source.id,newId:id,...position}];});
 if(path!==source.project||!p[source.kind].some(item=>item.id===id))return;
 selection={kind:source.kind,id};clearCutRange();draw();
 const start=source.kind==='clips'?videoRanges().find(r=>r.item.id===id).start:selected().start;
 await seek(start);$('timelineScroll').scrollLeft=Math.max(0,start/Math.max(1,frames())*timelineWidth()-80);
 toast('Copia creada y seleccionada. Puedes deshacer con ⌘Z.');
}
async function duplicateSelected(){
 if(!selected()||state.duplicating)return;
 state.duplicating=true;drawDuplicateButton();
 try{
  await flushEdits();const item=selected();if(!item)return;
  const source={...selection,project:path,revision:p.revision,length:item.length,role:item.role};
  if(source.kind==='clips'||item.start+2*item.length<=frames())return await commitDuplicate(source);
  await pausePlayback();state.duplicateSource=source;
  $('duplicateStart').value=((item.start+item.length<frames()?item.start+item.length:cursor)/p.fps).toFixed(3);
  $('duplicateAfter').disabled=item.start+item.length>=frames();$('duplicateError').hidden=true;
  $('duplicateDialog').showModal();
 }finally{state.duplicating=false;drawDuplicateButton();if($('duplicateDialog').open)drawDuplicatePosition();}
}
$('duplicate').onclick=safe(duplicateSelected);
$('duplicateStart').oninput=drawDuplicatePosition;
$('duplicateAtCursor').onclick=()=>{$('duplicateStart').value=(cursor/p.fps).toFixed(3);drawDuplicatePosition();};
$('duplicateAfter').onclick=()=>{const source=state.duplicateSource,item=p[source.kind].find(x=>x.id===source.id);$('duplicateStart').value=((item.start+item.length)/p.fps).toFixed(3);drawDuplicatePosition();};
$('duplicateCancel').onclick=()=>$('duplicateDialog').close();
$('duplicateDialog').onclose=()=>{state.duplicateSource=null;};
$('duplicateDialog').oncancel=e=>{if(state.duplicating)e.preventDefault();};
$('duplicateForm').onsubmit=async e=>{
 e.preventDefault();if(state.duplicating)return;const position=duplicatePosition();if(!position)return;
 state.duplicating=true;drawDuplicatePosition();drawDuplicateButton();$('duplicateError').hidden=true;
 try{await commitDuplicate(state.duplicateSource,position);$('duplicateDialog').close();}
 catch(error){$('duplicateError').textContent=error.message;$('duplicateError').hidden=false;if(error.conflict)$('duplicateDialog').close();}
 finally{state.duplicating=false;drawDuplicateButton();if($('duplicateDialog').open)drawDuplicatePosition();}
};
function drawTimeline(){
 drawDuplicateButton();
 const total=frames()||600,width=timelineWidth(),content=$('timelineContent');content.style.width=content.style.minWidth=width+'px';
 $('timelineZoom').value=Math.log2(zoom);$('timelineScale').textContent=zoom.toFixed(1)+'×';
 const ruler=$('ruler');ruler.replaceChildren();const seconds=total/(p?.fps||60);
 const step=[1/(p?.fps||60),.1,.25,.5,1,2,5,10,30,60,120,300,600,1800,3600].find(s=>s/seconds*width>=70)||3600;
 for(let i=0;i<=Math.ceil(seconds/step);i++){const t=i*step;if(t>seconds)break;const tick=elem('span',null,step<1?tc(Math.round(t*p.fps)).slice(3):Math.floor(t/60)+':'+String(Math.round(t%60)).padStart(2,'0'));tick.style.left=t/seconds*100+'%';ruler.append(tick);}
 const labels=$('trackLabels');labels.replaceChildren(elem('div','ruler-label','PISTAS · VÍNCULOS'));
 const feedbackHead=elem('div','feedback-track-label');const addFeedback=elem('button',null,'F');addFeedback.title='Añadir feedback · ⌘F';addFeedback.onclick=()=>window.studioFeedback();feedbackHead.append(addFeedback,elem('span',null,'Feedback'));labels.append(feedbackHead);if(typeof drawFeedbackMarkers==='function')drawFeedbackMarkers();
 for(const [track,title,kind] of timelineTracks){
  const row=document.querySelector('[data-track="'+track+'"]');row.replaceChildren();const items=trackItems(track,kind);
  const head=elem('div','track-heading'),main=elem('div','track-heading-main');head.append(main);main.append(elem('span','track-name',title));
  if(track==='video')main.append(elem('span','track-base','BASE'));
  else{
   const count=items.filter(item=>isLinked(kind,item)).length,united=items.length?count===items.length:(p.syncTracks?.[track]??true),mixed=count>0&&count<items.length;
   const button=elem('button','track-link'+(united?' linked':mixed?' mixed':''),mixed?'Mixta':united?'Unida':'Libre');
   button.setAttribute('aria-label',(united?'Separar ':'Vincular ')+title+' '+(united?'de los cortes':'al vídeo'));button.setAttribute('aria-pressed',mixed?'mixed':String(united));
   button.title=united?'Se corta y se desplaza con el vídeo. Pulsa para separar.':'Conserva sus tiempos al cortar el vídeo. Pulsa para vincular toda la pista.';
   button.onclick=safe(()=>ops([{op:'linkTrack',track,linked:!united}]));main.append(button);
  }
  const join=elem('button','track-join','Unir tramos');join.id='join-'+track;join.disabled=!(state.joinable?.[track]>0);
  join.setAttribute('aria-label','Unir tramos de '+title);
  join.title=join.disabled?'No hay fragmentos contiguos del mismo elemento que se puedan unir.':'Reúne fragmentos del mismo elemento en un bloque editable. Conserva los cortes de contenido y permite deshacer.';
  join.onclick=safe(async()=>{await flushEdits();await timelineEdit({op:'joinTrack',track});toast('Tramos unidos. Puedes deshacer con ⌘Z.');});head.append(join);
  const lanes=[],layout=[];let offset=0;
  const positioned=items.map(item=>{const start=kind==='clips'?offset:item.start;offset+=kind==='clips'?item.length:0;return {item,start};}).sort((a,b)=>a.start-b.start);
  for(const {item,start} of positioned){
   if(start>=total)continue;let lane=lanes.findIndex(end=>end<=start);if(lane<0)lane=lanes.length;lanes[lane]=start+item.length;layout.push({item,start,end:start+item.length,lane});
  }
  for(const {item,start,end,lane} of layout){
   const label=kind==='clips'||kind==='audio'||item.type==='video'?asset(item.asset)?.name||'Medio':kind==='captions'?item.text:item.props?.text||item.props?.title||templateName(item.type);
   const linked=isLinked(kind,item),affected=validRange()&&linked&&start<cutEnd&&start+item.length>cutStart;
   const joinedLeft=layout.some(other=>other.lane===lane&&other.end===start),joinedRight=layout.some(other=>other.lane===lane&&other.start===end);
   const b=elem('button','clip '+track+(kind==='audio'?' audio':'')+(item.hidden||item.muted?' hidden':'')+(selection?.id===item.id?' selected':'')+(!linked?' unlinked':'')+(affected?' cut-affected':'')+(joinedLeft?' joins-left':'')+(joinedRight?' joins-right':''),label);
   b.style.left=start/total*100+'%';b.style.width=Math.min(item.length,total-start)/total*100+'%';b.style.top=4+lane*30+'px';
   b.title=label+' · '+tc(start)+' → '+tc(start+item.length)+(linked?' · Vinculado':' · Independiente');b.setAttribute('aria-label',label+(linked?'':' · Independiente'));
   b.onclick=safe(async e=>{e.stopPropagation();timelineFocused=true;selection={kind,id:item.id};drawTimeline();drawInspector();await seek(item.type==='image'?imageRestFrame(item):start);});
   for(const edge of ['start','end']){const handle=elem('span','clip-edge '+edge),hint=kind==='clips'?'recortar o alargar vídeo':kind==='audio'?'recortar o alargar audio':'cambiar la duración';handle.title=(edge==='start'?'Ajustar inicio':'Ajustar final')+' · arrastra para '+hint;handle.setAttribute('role','separator');handle.onpointerdown=e=>beginEdgeDrag(e,{item,start,end,kind},edge,handle);handle.onclick=e=>e.stopPropagation();b.append(handle);}
   row.append(b);if(kind==='audio')drawWaveform(item,b);
  }
  const height=Math.max(62,lanes.length*30+8);row.style.height=head.style.height=height+'px';labels.append(head);
  if(validRange()&&(track==='video'||items.some(item=>isLinked(kind,item)))){const shade=elem('div','cut-range-shade');shade.style.left=cutStart/total*100+'%';shade.style.width=(cutEnd-cutStart)/total*100+'%';row.append(shade);}
 }
 const group=selectedCutGroup(),groupShade=$('groupSelection');groupShade.hidden=!group;
 if(group){groupShade.style.left=group.start/total*100+'%';groupShade.style.width=(group.end-group.start)/total*100+'%';}
 $('delete').textContent=group?'Quitar tramo unido':'Quitar clip';$('delete').title=group?'Quita este tramo de vídeo, voz y todas las capas vinculadas.':'Quita solo el elemento seleccionado.';
 $('playhead').style.left=cursor/total*100+'%';drawRangeControls();
}
function drawWaveform(item,button){
 const a=asset(item.asset);if(!a?.waveform?.length||!a.duration)return;const points=[];
 for(let i=0;i<128;i++){const second=((item.in||0)+item.length*(item.speed||1)*i/127)/p.fps;const index=Math.min(a.waveform.length-1,Math.max(0,Math.floor(second/a.duration*a.waveform.length)));const amp=Math.min(1,a.waveform[index]*2);points.push(`${i},${10-amp*9} ${i},${10+amp*9}`);}
 const img=elem('img','waveform');img.alt='';img.src='data:image/svg+xml,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 20" preserveAspectRatio="none"><polyline points="${points.join(' ')}" fill="none" stroke="white" stroke-width="0.6"/></svg>`);button.append(img);
}
function drawRangeControls(){
 const ready=validRange(),some=cutStart!==null||cutEnd!==null;
 $('cutRange').disabled=!ready||cutEnd-cutStart===frames();$('clearRange').disabled=!some;$('markIn').disabled=$('markOut').disabled=!frames();
 $('rangeSummary').textContent=ready?tc(cutStart)+' → '+tc(cutEnd)+' · '+((cutEnd-cutStart)/p.fps).toFixed(2)+' s':some?'Primer corte '+(cutStart===null?'—':tc(cutStart))+' · mueve el cabezal y pulsa ⌘C otra vez':'⌘C en el inicio y ⌘C en el final · también puedes arrastrar la regla o usar I / O.';
 $('cutRange').title='Quita este intervalo del vídeo y de las capas vinculadas; cierra el hueco.';
 $('linkStatus').textContent=timelineTracks.slice(1).filter(([t,,kind])=>trackItems(t,kind).some(item=>!isLinked(kind,item))).map(([,name])=>name).join(', ')||'Todo vinculado';
 if($('linkStatus').textContent!=='Todo vinculado')$('linkStatus').textContent+=': elementos independientes';
 for(const [id,value] of [['rangeIn',cutStart],['rangeOut',cutEnd]]){const marker=$(id);marker.hidden=value===null;marker.style.left=(value||0)/Math.max(1,frames())*100+'%';}
}
function markRange(end){if(!frames())return;if(end)cutEnd=cursor+1;else cutStart=cursor;drawTimeline();}
function markShortcut(){
 if(!frames())return false;
 if(cutStart===null||validRange()){cutStart=cursor;cutEnd=null;toast('Primer corte marcado. Mueve el cabezal y pulsa ⌘C otra vez.');}
 else{const anchor=cutStart;cutStart=Math.min(anchor,cursor);cutEnd=Math.max(anchor,cursor)+1;toast('Tramo seleccionado. Pulsa Supr o “Eliminar selección”.');}
 drawTimeline();return true;
}
function timelineEdit(operation){
 const revision=p.revision,target=path;
 return ops(()=>{if(path!==target||p.revision!==revision)throw new Error('El proyecto cambió. Marca el corte de nuevo.');return [operation];});
}
async function removeRange(){
 if(!validRange())return toast('Marca el inicio y el fin del tramo con I y O.');
 const start=cutStart,end=cutEnd;
 await timelineEdit({op:'cutRange',start,end});
 await seek(Math.min(start,frames()-1));toast('Tramo quitado. Las capas vinculadas siguen sincronizadas.');
}
async function splitTimeline(){
 if(!frames())return;const item=selected();
 if(item&&selection.kind!=='clips'&&!isLinked(selection.kind,item))return timelineEdit({op:'split',...selection,at:cursor-item.start});
 await timelineEdit({op:'splitAt',frame:cursor});
 const left=videoRanges().find(range=>range.end===cursor);
 if(left){selection={kind:'clips',id:left.item.id};drawTimeline();drawInspector();toast('Corte creado. El tramo de la izquierda queda listo para quitar.');}
}
async function linkAll(){if(!p)return;await ops([{op:'linkTrack',track:'all',linked:true}]);toast('Todo vinculado al vídeo para los próximos cortes.');}
window.studioLinkAll=()=>{if(homeVisible||editingText()||busy||($('newDialog').open||$('duplicateDialog').open)||($('cropDialog').open||$('feedbackDialog').open)||!p)return false;safe(linkAll)();return true;};
window.studioMarkRange=()=>{if(homeVisible||editingText()||busy||($('newDialog').open||$('duplicateDialog').open)||($('cropDialog').open||$('feedbackDialog').open)||!p||!timelineFocused)return false;return markShortcut();};
function drawLinkInspector(box,item,kind){
 if(kind==='clips'){box.append(elem('p','link-description','Los cortes del vídeo arrastran sus capas vinculadas. Las pistas libres conservan sus tiempos.'));return;}
 const linked=isLinked(kind,item),button=elem('button','secondary full link-item',linked?'Separar del vídeo':'Vincular al vídeo');button.setAttribute('aria-pressed',String(linked));
 const selectedRef={...selection};button.onclick=safe(()=>ops([{op:'set',...selectedRef,values:{linked:!linked}}]));box.append(button,elem('p','link-description',linked?'Este elemento se corta y se desplaza con el vídeo.':'Independiente: los cortes del vídeo no lo recortan ni desplazan.'));
}
function setTimelineZoom(next,clientX){
 if(!p)return;const scroller=$('timelineScroll'),old=timelineWidth(),visible=Math.max(1,scroller.clientWidth-160),head=cursor/Math.max(1,frames())*old;
 const anchor=clientX===undefined?(head>=scroller.scrollLeft&&head<=scroller.scrollLeft+visible?head-scroller.scrollLeft:visible/2):Math.max(0,Math.min(visible,clientX-scroller.getBoundingClientRect().left-160));
 const fraction=(scroller.scrollLeft+anchor)/old;zoom=Math.max(1,Math.min(64,next));drawTimeline();scroller.scrollLeft=Math.max(0,fraction*timelineWidth()-anchor);
}
function rulerFrame(event){const r=$('ruler').getBoundingClientRect();return Math.max(0,Math.min(frames()-1,Math.floor((event.clientX-r.left)/r.width*frames())));}
$('ruler').onpointerdown=e=>{if(e.button!==0||!frames())return;e.preventDefault();timelineFocused=true;void pausePlayback();rulerDrag={frame:rulerFrame(e),x:e.clientX};$('ruler').setPointerCapture(e.pointerId);};
$('ruler').onpointermove=e=>{if(!rulerDrag||Math.abs(e.clientX-rulerDrag.x)<3&&!rulerDrag.moved)return;rulerDrag.moved=true;const end=rulerFrame(e);cutStart=Math.min(rulerDrag.frame,end);cutEnd=Math.max(rulerDrag.frame,end)+1;drawTimeline();};
$('ruler').onpointerup=safe(async e=>{if(!rulerDrag)return;const frame=rulerDrag.moved?cutStart:rulerDrag.frame;rulerDrag=null;await seek(frame);});
$('ruler').onpointercancel=()=>rulerDrag=null;
function beginEdgeDrag(event,range,edge,handle){
 if(event.button!==0||!p)return;event.preventDefault();event.stopPropagation();timelineFocused=true;void pausePlayback();selection={kind:range.kind,id:range.item.id};drawInspector();
 edgeDrag={kind:range.kind,id:range.item.id,edge,startX:event.clientX,boundary:edge==='start'?range.start:range.end,delta:0,limits:edgeLimits(range,edge)};handle.setPointerCapture(event.pointerId);handle.onpointermove=moveEdgeDrag;handle.onpointerup=safe(finishEdgeDrag);handle.onpointercancel=cancelEdgeDrag;
}
function moveEdgeDrag(event){
 if(!edgeDrag)return;const raw=Math.round((event.clientX-edgeDrag.startX)*frames()/timelineWidth()),delta=Math.max(edgeDrag.limits.min,Math.min(edgeDrag.limits.max,raw));edgeDrag.delta=delta;
 const marker=$('edgePreview');marker.hidden=false;marker.style.left=(edgeDrag.boundary+delta)/frames()*100+'%';
 const extending=edgeDrag.edge==='start'?delta<0:delta>0,verb=extending?'Recuperar':'Recortar';$('rangeSummary').textContent=verb+' '+(edgeDrag.edge==='start'?'inicio':'final')+' · '+Math.abs(delta)+' fotogramas · '+(Math.abs(delta)/p.fps).toFixed(3)+' s';
}
function cancelEdgeDrag(){edgeDrag=null;$('edgePreview').hidden=true;drawRangeControls();}
async function finishEdgeDrag(){
 if(!edgeDrag)return;const drag=edgeDrag;edgeDrag=null;$('edgePreview').hidden=true;if(!drag.delta){drawRangeControls();return;}
 await timelineEdit({op:'resizeEdge',kind:drag.kind,id:drag.id,edge:drag.edge,delta:drag.delta});const item=selected(),range=drag.kind==='clips'?videoRanges().find(x=>x.item.id===drag.id):item&&{start:item.start,end:item.start+item.length};if(range)await seek(Math.max(0,Math.min(frames()-1,drag.edge==='start'?range.start:range.end-1)));toast(drag.kind==='clips'?(drag.edge==='start'?'Inicio':'Final')+' ajustado. Las capas unidas siguen sincronizadas.':'Duración del elemento ajustada.');
}
$('markIn').onclick=()=>markRange(false);$('markOut').onclick=()=>markRange(true);$('clearRange').onclick=()=>{clearCutRange();drawTimeline();};$('cutRange').onclick=safe(removeRange);$('linkAll').onclick=safe(linkAll);
$('timelineZoom').oninput=e=>setTimelineZoom(2**Number(e.target.value));$('zoomIn').onclick=()=>setTimelineZoom(zoom*1.5);$('zoomOut').onclick=()=>setTimelineZoom(zoom/1.5);$('zoomFit').onclick=()=>{setTimelineZoom(1);$('timelineScroll').scrollLeft=0;};
$('timelineScroll').addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();setTimelineZoom(zoom*Math.exp(-e.deltaY*.006),e.clientX);}}, {passive:false});
$('timelineScroll').addEventListener('pointerdown',()=>{timelineFocused=true;});
document.addEventListener('pointerdown',e=>{if(e.target&&!$('timelineScroll').contains(e.target))timelineFocused=false;},true);
if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>{if(p&&!homeVisible)drawTimeline();}).observe($('timelineScroll'));
document.addEventListener('keydown',safe(async e=>{
 if(homeVisible||editingText()||busy||($('newDialog').open||$('duplicateDialog').open)||($('cropDialog').open||$('feedbackDialog').open))return;const key=e.key.toLowerCase();
 if(!e.metaKey&&!e.ctrlKey&&!e.altKey){
  if(key==='i'||key==='o'){e.preventDefault();markRange(key==='o');}
  else if(key==='b'){e.preventDefault();await splitTimeline();}
  else if(key==='escape'){clearCutRange();drawTimeline();}
  else if(key==='+'||key==='='||key==='-'){e.preventDefault();setTimelineZoom(zoom*(key==='-'?1/1.5:1.5));}
 }
}));
