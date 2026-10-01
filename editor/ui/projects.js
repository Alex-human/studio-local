'use strict';
let homeVisible=true,homeItems=[],homeGeneration=0,homeFolder=null;
const posters=new Map(),posterElements=new Map();
function setProjectView(home){
 homeVisible=home;$('projectHome').hidden=!home;$('homeHeader').hidden=!home;
 for(const id of ['editorWorkspace','editorTimeline','homeProjects','projects','saveState','preview','export','feedbackToggle'])$(id).hidden=home;
}
function showEditor(){
 clearCutRange();zoom=1;$('timelineScroll').scrollLeft=0;
 invalidatePlayback();selection=null;cursor=0;
 $('still').hidden=true;
 homeGeneration++;setProjectView(false);
}
function posterKey(item){return item.path+':'+item.revision+':'+item.modified;}
function projectDuration(seconds){const n=Math.round(seconds||0);return (n>=3600?Math.floor(n/3600)+':':'')+String(Math.floor(n/60)%60).padStart(2,'0')+':'+String(n%60).padStart(2,'0');}
function searchable(value){return value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es');}
function projectFolders(){return state.projectFolders||[];}
function currentFolder(){return projectFolders().find(folder=>folder.id===homeFolder);}
function folderProjects(id){return homeItems.filter(item=>(item.folder||null)===id);}
function setHomeFolder(id){if(state.folderBusy)return;homeFolder=id;$('projectSearch').value='';drawProjectGrid();}
function drawProjectGrid(){
 if(homeFolder&&!currentFolder())homeFolder=null;
 const folder=currentFolder(),folders=projectFolders(),scope=folder?folderProjects(folder.id):homeItems;
 const query=searchable($('projectSearch').value.trim());
 const items=scope.filter(item=>(folder||query||!item.folder)&&searchable(item.name).includes(query)).sort($('projectSort').value==='name'?(a,b)=>a.name.localeCompare(b.name,'es'):(a,b)=>b.modified-a.modified);
 $('homeTitleText').textContent=folder?folder.name:'Tus proyectos';$('homeCount').textContent=String(scope.length);
 $('homeSubtitle').textContent=folder?'Los proyectos de esta carpeta.':'Todo lo que estás creando, en un solo lugar.';
 $('folderBack').hidden=!folder;$('folderActions').hidden=!folder;$('newFolder').hidden=!!folder;
 $('deleteFolder').disabled=!!state.folderBusy||scope.length>0;
 $('deleteFolder').title=scope.length?'Mueve los proyectos a otra carpeta antes de eliminarla.':'Eliminar esta carpeta vacía';
 const showFolders=!folder&&!query;
 $('folderGrid').hidden=!showFolders;$('folderGrid').replaceChildren();
 if(showFolders)for(const entry of [...folders].sort((a,b)=>a.name.localeCompare(b.name,'es'))){
  const card=elem('button','folder-card');card.setAttribute('aria-label','Abrir carpeta '+entry.name);card.disabled=!!state.folderBusy;
  const icon=elem('span','folder-icon','▱');icon.setAttribute('aria-hidden','true');
  const details=elem('span','folder-details'),count=folderProjects(entry.id).length;
  details.append(elem('strong','folder-name',entry.name),elem('span','folder-count',count+' '+(count===1?'proyecto':'proyectos')));
  card.append(icon,details);card.onclick=()=>setHomeFolder(entry.id);$('folderGrid').append(card);
 }
 $('homeMessage').hidden=items.length>0||(showFolders&&folders.length>0);
 $('homeMessage').textContent=query?'No hay proyectos con ese nombre. Prueba otra búsqueda.':folder?'Esta carpeta está vacía. Crea un proyecto aquí o mueve uno desde la biblioteca.':'Aquí empieza tu próximo vídeo. Crea un proyecto o abre uno que ya tengas.';
 $('projectGrid').replaceChildren();posterElements.clear();
 for(const item of items){
  const card=elem('article','project-card');
  const open=elem('button','project-open');open.setAttribute('aria-label','Editar '+item.name);open.disabled=!!state.folderBusy;
  const cover=elem('span','project-cover');
  const fallback=elem('span','project-placeholder',item.duration?'▻':'＋');fallback.setAttribute('aria-hidden','true');
  const poster=elem('img');poster.alt='';poster.hidden=true;poster.onload=()=>poster.hidden=false;poster.onerror=()=>poster.hidden=true;
  const key=posterKey(item);posterElements.set(key,poster);if(posters.get(key))poster.src=fileURL(posters.get(key));
  cover.append(fallback,poster,elem('span','project-duration',item.duration?projectDuration(item.duration):'Sin clips'));
  const body=elem('span','project-body');body.append(elem('strong','project-name',item.name),elem('span','project-format',item.width+' × '+item.height+' · '+Number(item.fps).toFixed(2).replace('.',',')+' fps'));
  if(!folder&&query)body.append(elem('span','project-location',folders.find(entry=>entry.id===item.folder)?.name||'Sin carpeta'));
  open.append(cover,body);open.onclick=safe(()=>openProject(item.path));
  const foot=elem('div','project-card-footer');
  const modified=new Date(item.modified*1000);const date=elem('span','project-date',modified.toLocaleDateString('es-ES',{day:'numeric',month:'short',year:'numeric'}));date.title='Modificado: '+modified.toLocaleString('es-ES');
  const preview=elem('button','project-preview','▶ Vista previa');preview.setAttribute('aria-label','Vista previa de '+item.name);preview.disabled=!!state.folderBusy||!item.duration;
  preview.onclick=safe(async()=>{if(await openProject(item.path))await togglePlay();});
  const moveRow=elem('label','project-folder-control','Carpeta');
  const move=elem('select');move.setAttribute('aria-label','Mover '+item.name+' a carpeta');move.disabled=!!state.folderBusy;
  for(const destination of [{id:'',name:'Sin carpeta'},...folders]){const option=elem('option',null,destination.name);option.value=destination.id;move.append(option);}move.value=item.folder||'';
  move.onchange=safe(async()=>{const destination=move.value||null;if(destination===(item.folder||null))return;try{await mutateProjectFolders({command:'assign',project:item.path,folder:destination});}finally{move.value=item.folder||'';}});
  moveRow.append(move);foot.append(date,preview);card.append(open,foot,moveRow);$('projectGrid').append(card);
 }
}
function setFolderBusy(value){
 state.folderBusy=value;
 for(const id of ['newFolder','renameFolder','folderBack','homeNew','newProject','openProject','refreshHome','folderSave','folderCancel','folderName'])$(id).disabled=value;
 drawProjectGrid();
}
async function mutateProjectFolders(request){
 if(state.folderBusy)return false;
 setFolderBusy(true);
 // Classification shares the close barrier but never enters project history.
 const task=mutationTail.then(()=>api({action:'projectFolders',...request,revision:state.folderRevision??0}));
 mutationTail=task.catch(()=>{});
 try{
  const result=await task;state.projectFolders=result.folders;state.folderRevision=result.folderRevision;
  if(request.command==='assign'){const item=homeItems.find(item=>item.path===request.project);if(item)item.folder=request.folder;}
  if(!await showProjects())toast('El cambio de carpeta se guardó. Pulsa ↻ para actualizar la biblioteca.',true);return true;
 }catch(e){
  if(e.conflict)await showProjects();
  throw e;
 }finally{setFolderBusy(false);}
}
function openFolderDialog(rename=false){
 if(state.folderBusy||!homeVisible)return;
 const folder=rename?currentFolder():null;if(rename&&!folder)return;
 state.folderEditing=folder?.id||null;
 $('folderDialogTitle').textContent=folder?'Renombrar carpeta':'Nueva carpeta';$('folderSave').textContent=folder?'Guardar nombre':'Crear carpeta';
 $('folderName').value=folder?.name||'';$('folderError').hidden=true;$('folderDialog').showModal();$('folderName').focus();
}
async function loadPosters(generation){
 const queue=homeItems.filter(item=>item.duration&&!posters.has(posterKey(item)));
 async function worker(){
  while(queue.length&&generation===homeGeneration){
   const item=queue.shift(),key=posterKey(item);
   try{const result=await api({action:'thumbnail',project:item.path});if(generation!==homeGeneration)return;
    posters.set(key,result.path);const img=posterElements.get(key);if(img&&result.path)img.src=fileURL(result.path);
   }catch(e){if(generation!==homeGeneration)return;/* A missing poster must not block opening a project. */}
  }
 }
 await Promise.all([worker(),worker()]);
}
async function showProjects(){
 try{await flushEdits();}catch(e){setSaveState('error');toast('No se pudo guardar. Reintenta el cambio antes de salir del proyecto.',true);return false;}
 const generation=++homeGeneration;state.openRequest=(state.openRequest||0)+1;
 invalidatePlayback();$('soundPreview').pause();clearTimeout(frameTimer);state.frameRequest=(state.frameRequest||0)+1;
 setProjectView(true);$('homeMessage').hidden=false;$('homeMessage').textContent='Cargando tus proyectos…';$('projectGrid').replaceChildren();$('folderGrid').replaceChildren();$('refreshHome').disabled=true;
 try{
  const items=await refreshProjects();if(generation!==homeGeneration)return;
  homeItems=items;drawProjectGrid();void loadPosters(generation);
 }catch(e){if(generation===homeGeneration){$('homeCount').textContent='—';$('homeMessage').textContent='No se pudieron cargar los proyectos. Pulsa ↻ para volver a intentarlo.';}return false;}
 finally{if(generation===homeGeneration)$('refreshHome').disabled=!!state.folderBusy;}return true;
}
$('homeProjects').onclick=showProjects;$('refreshHome').onclick=()=>{posters.clear();return showProjects();};
$('homeNew').onclick=$('newProject').onclick;
$('folderBack').onclick=()=>setHomeFolder(null);
$('newFolder').onclick=()=>openFolderDialog();$('renameFolder').onclick=()=>openFolderDialog(true);
$('folderCancel').onclick=()=>{if(!state.folderBusy)$('folderDialog').close();};
$('folderDialog').oncancel=e=>{if(state.folderBusy)e.preventDefault();};
$('folderForm').onsubmit=async e=>{
 e.preventDefault();if(state.folderBusy)return;
 const name=$('folderName').value.trim();
 if(!name||name.length>80){$('folderError').textContent='Escribe un nombre de entre 1 y 80 caracteres.';$('folderError').hidden=false;return;}
 $('folderError').hidden=true;
 try{if(await mutateProjectFolders({command:state.folderEditing?'rename':'create',...(state.folderEditing?{id:state.folderEditing}:{}),name}))$('folderDialog').close();}
 catch(error){if(!error.cancelled){$('folderError').textContent=error.message;$('folderError').hidden=false;}}
};
$('deleteFolder').onclick=safe(async()=>{const folder=currentFolder();if(!folder||folderProjects(folder.id).length||state.folderBusy)return;await mutateProjectFolders({command:'delete',id:folder.id});});
$('projectSearch').oninput=drawProjectGrid;$('projectSort').onchange=drawProjectGrid;
void restoreSession();
