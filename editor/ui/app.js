'use strict';
const $=id=>document.getElementById(id);
const pending=new Map();
let p=null,path=null,selection=null,cursor=0,zoom=1,previewRevision=-1,frameTimer=null,requestSerial=0,busy=false;
const state={};
let mutationTail=Promise.resolve();
window.studioReply=(id,response)=>{const pair=pending.get(id);if(!pair)return;pending.delete(id);response.ok?pair.resolve(response.result):pair.reject(Object.assign(new Error(response.error||'Error'),{cancelled:response.cancelled,conflict:response.conflict}));};
function api(request){return new Promise((resolve,reject)=>{const id=String(++requestSerial);pending.set(id,{resolve,reject});if(window.webkit?.messageHandlers?.studio)window.webkit.messageHandlers.studio.postMessage({id,request});else{pending.delete(id);reject(new Error('Abre Studio Local.app para utilizar el editor.'));}});}
function toast(msg,error=false){$('toast').textContent=msg;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(state.toast);state.toast=setTimeout(()=>$('toast').hidden=true,6500);}
function safe(fn){return async(...args)=>{try{return await fn(...args);}catch(e){if(!e.cancelled)toast(e.message,true);}};}
function setSaveState(status){
 state.saveStatus=status;const el=$('saveState');if(!el)return;el.dataset.state=status;
 el.textContent=status==='dirty'?'Cambios pendientes':status==='saving'?'Guardando…':status==='error'?'No se pudo guardar':'Guardado automáticamente'+(p?' · revisión '+p.revision:'');
}
function commitActiveControl(){const active=document.activeElement;if(active&&['INPUT','TEXTAREA','SELECT'].includes(active.tagName)&&typeof active.blur==='function')active.blur();}
async function flushEdits(){commitActiveControl();await Promise.resolve();await mutationTail;if(state.saveError)throw state.saveError;if(typeof flushFeedback==='function')await flushFeedback();return true;}
window.studioPrepareToQuit=()=>{
 void flushEdits().then(()=>saveSession()).then(()=>api({action:'quitReady',allow:true})).catch(async e=>{setSaveState('error');toast('No se pudo guardar. Studio Local sigue abierto para que puedas reintentarlo.',true);try{await api({action:'quitReady',allow:false});}catch(_){}});
 return true;
};
function fileURL(p){return 'file://'+p.split('/').map(encodeURIComponent).join('/');}
function frames(){return p?p.clips.reduce((n,c)=>n+c.length,0):0;}
function tc(n){const fps=Math.round(p?.fps||60),sec=Math.floor(n/(p?.fps||60));return [Math.floor(sec/3600),Math.floor(sec/60)%60,sec%60,Math.floor(n-sec*(p?.fps||60))%fps].map(x=>String(x).padStart(2,'0')).join(':');}
function asset(id){return p.assets.find(x=>x.id===id);}
function selected(){return selection&&p?.[selection.kind]?.find(x=>x.id===selection.id);}
function elem(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function setBusy(value,title='Preparando vídeo…'){busy=value;$('busy').hidden=!value;$('busyTitle').textContent=title;}
async function refreshProjects(){const list=await api({action:'list'});state.projectFolders=list.folders||[];state.folderRevision=list.folderRevision??0;const select=$('projects');select.replaceChildren();for(const item of list.projects){const o=elem('option',null,item.name);o.value=item.path;select.append(o);}if(path)select.value=path;return list.projects;}
async function openProject(next){const ticket=state.openRequest=(state.openRequest||0)+1;await flushEdits();const data=await api({action:'open',project:next});if(ticket!==state.openRequest)return false;showEditor();receive(data);setSaveState('saved');await seek(0);return true;}
function receive(data,keepPlayback=false){if(!keepPlayback&&(path!==data.path||p?.revision!==data.project.revision))invalidatePlayback();if(path!==data.path||timelineShape(p)!==timelineShape(data.project))clearCutRange();p=data.project;path=data.path;state.joinable=data.joinable||{};if(keepPlayback)previewRevision=p.revision;cursor=Math.min(cursor,Math.max(0,frames()-1));if(selection&&!selected())selection=null;$('analysis').hidden=true;draw();}
function edit(request,{audioOnly=false}={}){
 if(state.conflict)return Promise.reject(new Error('Resuelve primero el cambio pendiente en el aviso de sincronización.'));
 const target=path,serial=state.mutationSerial=(state.mutationSerial||0)+1,userDraft=state.saveStatus==='dirty';state.saveError=null;setSaveState('saving');
 const task=mutationTail.then(async()=>{
  if(state.conflict)throw state.conflict;
  if(path!==target)throw new Error('El proyecto activo cambió. Repite la modificación en el proyecto correcto.');
  let keepPlayback=audioOnly&&liveAudioReady();
  if(!keepPlayback)await pausePlayback();
  const fields=typeof request==='function'?request():request;
  const baseRevision=p.revision,view=sessionView();
  const data=await api({...fields,project:target,revision:baseRevision});
  if(keepPlayback&&audioShape(p)!==audioShape(data.project)){await pausePlayback();keepPlayback=false;}
  // Saving and drawing the edited frame are immediate. Rebuild playback only
  // when the user presses play; routine edits must never trigger a render.
  if(path===target){if(keepPlayback)await api({action:'playback',command:'levels',key:playbackKey,levels:audioLevels(data.project)});receive(data,keepPlayback);if(data.project.revision>baseRevision+1)restoreView(view);if(!keepPlayback)await seek(cursor);}return data;
 });
 task.then(()=>{if(state.mutationSerial===serial){state.saveError=null;setSaveState('saved');}},error=>{if(error.conflict){state.conflict=error;void pausePlayback();showSyncConflict(error);}if(state.mutationSerial===serial){state.saveError=userDraft||error.conflict?error:null;setSaveState(state.saveError?'error':'saved');}});
 mutationTail=task.catch(()=>{});return task;
}
async function ops(operations,options){if(!p)return;return edit(()=>({action:'ops',ops:typeof operations==='function'?operations():operations}),options);}
function draw(){
 $('projectTitle').textContent=p.name;$('projects').value=path;
 $('formatBadge').textContent=p.height+'p · '+p.fps.toFixed(2).replace('.',',');$('resolution').textContent=p.width+' × '+p.height;
 $('durationTime').textContent=tc(frames());$('emptyViewer').hidden=frames()>0;$('viewerLabel').hidden=frames()===0;
 const previewCurrent=previewRevision===p.revision;$('previewBadge').textContent=previewCurrent?'Reproducción lista':'Vista previa pendiente';$('previewBadge').dataset.state=previewCurrent?'ready':'';
 $('projectStats').textContent=p.clips.length+' clips · '+p.graphics.filter(g=>g.type!=='video').length+' gráficos · '+p.graphics.filter(g=>g.type==='video').length+' superposiciones · '+p.audio.length+' pistas de audio';
 $('outputSize').value=p.width+'x'+p.height;$('ducking').checked=!!p.ducking;
 drawMixer();
 const media=$('mediaList');media.replaceChildren();for(const a of p.assets){const el=elem('div','media');const icon=elem('span','media-icon',a.kind==='audio'?'♫':a.kind==='image'?'▧':'▻');const body=elem('div');body.append(elem('strong',null,a.name),elem('small',null,a.kind==='video'?a.width+' × '+a.height+' · '+a.duration.toFixed(1)+' s':a.kind==='audio'?a.duration.toFixed(1)+' s':'Imagen'));el.append(icon,body);if(a.kind==='video'){el.classList.add('has-overlay');const overlay=elem('button','media-overlay','Superponer');overlay.disabled=!frames();overlay.title='Añadir este vídeo encima del principal en el cabezal';overlay.onclick=safe(async()=>{const ids=new Set(p.graphics.map(g=>g.id));await ops([{op:'addOverlay',asset:a.id,start:cursor}]);const added=p.graphics.find(g=>!ids.has(g.id));if(added){selection={kind:'graphics',id:added.id};draw();}});el.append(overlay);}media.append(el);}
 const captions=$('captionList');captions.replaceChildren();for(const c of p.captions){const b=elem('button',null,c.text);b.onclick=safe(async()=>{selection={kind:'captions',id:c.id};draw();await seek(c.start);});captions.append(b);}
 drawTimeline();drawInspector();drawImageSelection();
}
function drawInspector(){
 const box=$('selectionFields');box.replaceChildren();const item=selected();$('selectedBadge').textContent=selection?{clips:'Vídeo',audio:'Audio',graphics:'Motion',captions:'Texto'}[selection.kind]:'Proyecto';
 if(!item){box.append(elem('p','muted','Selecciona un clip, gráfico o sonido en la línea de tiempo.'));return;}
 const kind=selection.kind;if(kind==='graphics'&&item.type==='video')$('selectedBadge').textContent='Superposición';drawLinkInspector(box,item,kind);
 const set=values=>ops(()=>[{op:'set',kind,id:item.id,values:typeof values==='function'?values(p[kind].find(x=>x.id===item.id)):values}]);
 const input=(label,value,opts,onchange)=>{const l=elem('label',opts?.stacked?'stacked':'',label);let e=elem(opts?.area?'textarea':'input');e.value=value??'';if(!opts?.area)e.type=opts?.type||'number';for(const k of ['min','max','step'])if(opts?.[k]!==undefined)e[k]=opts[k];l.append(e);e.oninput=()=>setSaveState('dirty');e.onchange=safe(()=>onchange(e.type==='number'?Number(e.value):e.value));box.append(l);return e;};
 const check=(label,value,onchange)=>{const l=elem('label','check');const c=elem('input');c.type='checkbox';c.checked=!!value;c.onchange=safe(()=>onchange(c.checked));l.append(c,document.createTextNode(label));box.append(l);};
 if(kind==='clips'||kind==='audio'){
  box.append(elem('p','muted',asset(item.asset)?.name));
  volumeControl(box,'Volumen del clip',{kind,id:item.id},item.volumeDb??0,item.muted,kind==='clips'&&!asset(item.asset)?.audio);
  box.append(elem('h3',null,'Recorte por fotogramas'));
  const head=input('Quitar al inicio',0,{min:0,max:item.length-1,step:1},()=>{});
  const tail=input('Quitar al final',0,{min:0,max:item.length-1,step:1},()=>{});
  const trim=elem('button','secondary full','Aplicar recorte');trim.onclick=safe(()=>ops([{op:'trim',kind,id:item.id,head:Number(head.value),tail:Number(tail.value)}]));box.append(trim);
  box.append(elem('p','muted tiny',item.length+' fotogramas · '+(item.length/p.fps).toFixed(3)+' s'));
 }
 if(kind==='clips'){
  box.append(elem('h3',null,'Encuadre y movimiento'));
  input('Zoom inicial',item.zoom||1,{min:1,max:3,step:.01},v=>set({zoom:v}));input('Zoom final',item.zoomEnd||item.zoom||1,{min:1,max:3,step:.01},v=>set({zoomEnd:v}));
  input('Centro horizontal',item.x??.5,{min:0,max:1,step:.01},v=>set({x:v}));input('Centro vertical',item.y??.5,{min:0,max:1,step:.01},v=>set({y:v}));
  box.append(elem('h3',null,'Color'));
  for(const [k,label,def,min,max,step] of [['exposure','Luminosidad',0,-2,2,.05],['contrast','Contraste',1,.5,1.5,.01],['saturation','Saturación',1,0,2,.05],['temperature','Temperatura',0,-1,1,.05]])input(label,item.color?.[k]??def,{min,max,step},v=>set(current=>({color:{...current.color,[k]:v}})));
 }
 if(kind==='audio'){
  const l=elem('label',null,'Pista');const s=elem('select');for(const [v,n]of [['voice','Voz'],['music','Música'],['sfx','Efectos']]){const o=elem('option',null,n);o.value=v;s.append(o);}s.value=item.role;s.onchange=safe(()=>set({role:s.value}));l.append(s);box.append(l);
  input('Inicio · fotograma',item.start,{min:0,step:1},v=>ops([{op:'move',kind,id:item.id,start:v}]));
  input('Entrada suave · frames',item.fadeIn||0,{min:0,step:1},v=>set({fadeIn:v}));input('Salida suave · frames',item.fadeOut||0,{min:0,step:1},v=>set({fadeOut:v}));
 }
 if(kind==='graphics'){
  if(item.type==='video'){drawVideoInspector(box,item,{input,check,set});return;}
  if(item.type==='image'){drawImageInspector(box,item,{input,check,set});return;}
  const props=item.props||{};const prop=(key,value)=>set(current=>({props:{...current.props,[key]:value}}));
  check('Ocultar gráfico',item.hidden,v=>set({hidden:v}));
  input(item.type==='channel_intro'?'Título de tarjeta':'Texto',props[item.type==='channel_intro'?'title':'text']||'',{type:'text',stacked:true,area:true},v=>prop(item.type==='channel_intro'?'title':'text',v));
  if(item.type==='title')check('Gancho editorial de Instagram',props.style==='instagram',v=>prop('style',v?'instagram':'plain'));
  if(item.type==='title'&&props.style==='instagram')check('Caja negra detrás del gancho',props.box,v=>prop('box',v));
  if(item.type==='title'&&!Object.keys(item.keyframes||{}).length){
   check('Mantener de una pieza al cortar',item.keepTogether,v=>set({keepTogether:v}));
   box.append(elem('p','muted tiny','Reúne sus fragmentos al cortar el vídeo siempre que la animación se conserve. Dividir este elemento directamente desactiva la opción.'));
  }
  if(['title','lower_third'].includes(item.type)&&props.style!=='instagram')input('Texto secundario',props.subtitle||'',{type:'text',stacked:true},v=>prop('subtitle',v));
  input('Color de acento',props.accent||'#75b8ff',{type:'color'},v=>prop('accent',v));
  if(item.type==='title'){input('Tamaño',props.size||72,{min:20,max:200,step:1},v=>prop('size',v));input('Color de texto',props.color||'#ffffff',{type:'color'},v=>prop('color',v));}
  if(item.type!=='channel_intro'){const a=graphicAnchor(item);box.append(elem('p','muted tiny','Arrastra el gráfico en el visor para moverlo.'));input('Posición X',a.x,{min:0,max:1920},v=>prop('x',v));input('Posición Y',a.y,{min:0,max:Math.min(3840,Math.round(1920*p.height/p.width))},v=>prop('y',v));}
  if(item.type==='stat'){input('Valor',props.value||100,{min:-100000,max:100000},v=>prop('value',v));input('Sufijo',props.suffix||'%',{type:'text'},v=>prop('suffix',v));}
  if(item.type==='cards')input('Tarjetas · una por línea',(props.labels||['Idea','Proceso','Resultado']).join('\n'),{area:true,stacked:true},v=>prop('labels',v.split('\n').filter(Boolean).slice(0,5)));
  input('Inicio · fotograma',item.start,{min:0,step:1},v=>ops([{op:'move',kind,id:item.id,start:v}]));
 }
 if(kind==='captions')input('Texto',item.text,{area:true,stacked:true},v=>set({text:v}));
 if(kind==='graphics'||kind==='captions')box.append(elem('p','muted tiny',item.length+' fotogramas · '+(item.length/p.fps).toFixed(2)+' s'));
}
async function seek(frame){
 await pausePlayback();
 cursor=Math.max(0,Math.min(Math.round(frame),frames()-1));$('cursorTime').textContent=tc(cursor);$('playhead').style.left=cursor/Math.max(1,frames())*100+'%';
 drawImageSelection();if(!frames())return;
 clearTimeout(frameTimer);const rev=p.revision;const sought=cursor;const projectPath=path;const ticket=state.frameRequest=(state.frameRequest||0)+1;
 frameTimer=setTimeout(safe(async()=>{const data=await api({action:'frame',project:projectPath,frame:sought});if(homeVisible||playbackPlaying||path!==projectPath||p.revision!==rev||cursor!==sought||state.frameRequest!==ticket)return;$('still').src=fileURL(data.path);$('still').hidden=false;}),120);
}
async function doRender(){
 await flushEdits();await pausePlayback();
 if(!frames())return toast('Añade un vídeo antes de renderizar.');
 setBusy(true,'Exportando tu vídeo…');
 try{const result=await api({action:'render',project:path,preview:false});
  toast('Exportado · '+(result.bytes/1024/1024).toFixed(1)+' MB · '+result.frames+' fotogramas');await api({action:'reveal',path:result.path});
  $('renderState').textContent='Exportación · '+result.seconds+' s';return result;
 }finally{setBusy(false);}
}
function templateName(type){return {title:'Título editorial',lower_third:'Nombre y contexto',stat:'Cifra animada',cards:'Tarjetas de proceso',progress:'Progreso visual',image:'Imagen',video:'Vídeo superpuesto',channel_intro:'Canal → explicación'}[type]||type;}
async function addGraphic(type){if(!frames())return toast('Añade primero un vídeo.');const props={title:'Tu canal',text:type==='stat'?'Una cifra que importa':'Tu idea, con claridad',accent:'#75b8ff'};const item={type,start:cursor,length:Math.min(frames()-cursor,Math.round(p.fps*(type==='channel_intro'?8.5:4))),props};await ops([{op:'add',kind:'graphics',item}]);selection={kind:'graphics',id:p.graphics[p.graphics.length-1].id};draw();}
async function importMedia(action='chooseImport',extra={}){if(!p)return;const before=new Set([...p.graphics,...p.audio].map(x=>x.id));const data=await edit({action,start:cursor,...extra});if(data?.path===path){const added=p.graphics.find(x=>!before.has(x.id))||p.audio.find(x=>!before.has(x.id));if(added){selection={kind:p.graphics.includes(added)?'graphics':'audio',id:added.id};draw();if(added.type==='image')await seek(imageRestFrame(added));}}}
async function undo(redo=false){return edit({action:redo?'redo':'undo'});}
async function split(){return splitTimeline();}
async function remove(){
 const group=selectedCutGroup();
 if(group){const start=group.start;await timelineEdit({op:'cutRange',start,end:group.end});await seek(Math.min(start,frames()-1));toast('Tramo unido quitado de vídeo, voz y capas vinculadas.');return;}
 if(!selected())return;await ops([{op:'delete',...selection}]);
}
async function analyze(){if(!frames())return;setBusy(true,'Buscando silencios…');try{const analyzedPath=path;const analyzedRevision=p.revision;const result=await api({action:'analyze',project:path});if(path!==analyzedPath||p.revision!==analyzedRevision||result.revision!==p.revision)return;$('analysis').hidden=false;const box=$('analysisItems');box.replaceChildren();if(!result.candidates.length)box.append(elem('p','muted','No se encontraron pausas largas con estos márgenes.'));for(const c of result.candidates){const row=elem('div','analysis-row');row.append(elem('span',null,tc(c.start)+' · '+((c.end-c.start)/p.fps).toFixed(2)+' s'));const hear=elem('button',null,'Ver');hear.onclick=safe(()=>seek(Math.max(0,c.start-15)));const cut=elem('button',null,'Quitar');cut.onclick=safe(async()=>{await ops(()=>{if(path!==analyzedPath||p.revision!==analyzedRevision){$('analysis').hidden=true;throw new Error('El proyecto cambió. Analiza los silencios de nuevo.');}return [{op:'cutRange',start:c.start,end:c.end}];});$('analysis').hidden=true;});row.append(hear,cut);box.append(row);}}finally{setBusy(false);}}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));for(const t of ['media','motion','text'])$(t+'Panel').hidden=t!==b.dataset.tab;});
for(const [type,glyph,desc]of [['channel_intro','▱ →','Tarjeta, revelado y fichas'],['cards','▢ ▢ ▢','Jerarquía y entrada escalonada'],['stat','100','Contador con aceleración suave'],['progress','━','Una relación que se entiende']]){const b=elem('button','template');b.append(elem('span','template-glyph',glyph),elem('strong',null,templateName(type)),elem('small',null,desc));b.onclick=safe(()=>addGraphic(type));$('templates').append(b);}
$('projects').onchange=safe(e=>openProject(e.target.value));
for(const id of ['import','importMore','emptyImport'])$(id).onclick=safe(()=>importMedia());
$('importOverlay').onclick=safe(()=>frames()?importMedia('chooseOverlay'):toast('Añade primero el vídeo principal.'));
$('importSfx').onclick=safe(()=>importMedia('chooseSfx'));
$('importMusic').onclick=safe(()=>importMedia('chooseMusic'));
$('newProject').onclick=()=>{if(state.folderBusy)return;state.newProjectFolder=homeVisible?homeFolder:null;$('newDialog').showModal();};
$('createProject').onclick=safe(async e=>{e.preventDefault();if(state.creatingProject)return;state.creatingProject=true;$('createProject').disabled=true;try{await flushEdits();const data=await api({action:'create',name:$('newName').value,fps:Number($('newFps').value),...(state.newProjectFolder?{folder:state.newProjectFolder}:{})});$('newDialog').close();showEditor();receive(data);setSaveState('saved');await refreshProjects();}finally{state.creatingProject=false;$('createProject').disabled=false;}});
$('openProject').onclick=safe(async()=>{const data=await api({action:'chooseProject'});await openProject(data.path);});
$('addTitle').onclick=safe(()=>addGraphic('title'));$('addLower').onclick=safe(()=>addGraphic('lower_third'));
$('captions').onclick=safe(()=>edit({action:'chooseCaptions'}));
$('undo').onclick=safe(()=>undo());$('redo').onclick=safe(()=>undo(true));$('split').onclick=safe(split);$('delete').onclick=safe(remove);
$('preview').onclick=safe(()=>togglePlay());$('export').onclick=safe(()=>doRender());$('play').onclick=safe(()=>togglePlay());
$('backFrame').onclick=safe(()=>seek(cursor-1));$('nextFrame').onclick=safe(()=>seek(cursor+1));
$('ducking').onchange=safe(e=>ops([{op:'settings',values:{ducking:e.target.checked}}]));
$('outputSize').onchange=safe(e=>{const [width,height]=e.target.value.split('x').map(Number);return ops([{op:'settings',values:{width,height}}]);});
$('silence').onclick=safe(analyze);$('closeAnalysis').onclick=()=>$('analysis').hidden=true;
$('cancelRender').onclick=safe(async()=>{invalidatePlayback();await api({action:'cancel'});setBusy(false);});
document.addEventListener('keydown',safe(async e=>{if(homeVisible||($('newDialog').open||$('duplicateDialog').open)||$('cropDialog').open||$('feedbackDialog').open||['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||busy)return;if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();await undo(e.shiftKey);}else if(e.code==='Space'){e.preventDefault();await togglePlay();}else if(e.key==='ArrowLeft'){e.preventDefault();await seek(cursor-1);}else if(e.key==='ArrowRight'){e.preventDefault();await seek(cursor+1);}else if(e.key==='Backspace'||e.key==='Delete'){e.preventDefault();if(validRange())await removeRange();else await remove();}}));
