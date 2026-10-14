import {DirectPlayer} from '/direct-player.js';
const $ = id => document.getElementById(id);
const video = $('video');
const names = {clips:'Vídeo',overlays:'Superposición',graphics:'Gráficos',captions:'Subtítulos',voice:'Voz',music:'Música',sfx:'Efectos'};
let library, folder = '', p = null, frame = 0, selection = null, notes = [], busy = false;
let scale = 16, playing = false, playbackOffset = 0, mediaGeneration = 0, noteDraft = null, textDraft = null;
let pollBusy = false, drawing = false, stroke = null, navigation = 0, dragging = false;
let mediaSource = null, speed = 1, warmTimer = null, positioning = false;
let directSupported=null, directLoad=null, directRequest=0, timelineHold=0, timelineTouch=false, timelineTap=null;
const direct=new DirectPlayer($('viewer'),query,n=>{frame=n;updatePosition();},(active,loading)=>{
  playing=active;$('play').textContent=active?'Ⅱ':'▶';$('play').setAttribute('aria-label',active?'Pausar':'Reproducir');
  $('preparing').textContent='Cargando medios…';$('preparing').hidden=!loading;
},e=>{notice(e.message);if(direct.broken&&directSupported){directSupported=false;showFrame();}},report);
const pendingKey = 'studio-mobile-pending';
const draftKey = pid => 'studio-mobile-note-' + pid;
const textKey = draft => 'studio-mobile-text-' + draft.project + '-' + draft.id;

function element(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
function status(message) { $('status').textContent = message; }
function seconds(n) { const s = Math.max(0, n); return `${Math.floor(s/60).toString().padStart(2,'0')}:${Math.floor(s%60).toString().padStart(2,'0')}`; }
function time(n = frame) { return `${seconds(n / p.fps)} · ${Math.round(n % p.fps).toString().padStart(2,'0')}`; }
function total() { return p?.clips.reduce((n,c) => n+c.length,0) || 0; }
function modal() { return !!document.querySelector('dialog[open]'); }
function persist(key, value) { localStorage.setItem(key, JSON.stringify(value)); }
function stored(key) { try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch { return null; } }
async function api(req) {
  const response = await fetch('/api', {method:'POST',headers:{'Content-Type':'application/json','X-Studio-Mobile':'1'},body:JSON.stringify(req)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'No se pudo conectar con el Mac.');
  return data;
}
// What the player measured on this phone, for the Mac's log: timings and failures, never content.
const reports=[];let reportTimer=null;
function report(event,data) {
  reports.push({event,project:p?.id,...data});
  reportTimer??=setTimeout(flushReports,2000);
}
function flushReports() {
  clearTimeout(reportTimer);reportTimer=null;if(!reports.length)return;
  fetch('/api',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-Studio-Mobile':'1'},body:JSON.stringify({action:'clientLog',entries:reports.splice(0)})}).catch(()=>{});
}
report('hello',{agent:navigator.userAgent,decoder:typeof VideoDecoder});
window.addEventListener('error',e=>report('error',{where:'page',message:String(e.message)}));
window.addEventListener('unhandledrejection',e=>report('error',{where:'promise',message:String(e.reason?.message||e.reason)}));
async function query(req) {
  const data = await api(req);
  if (!data.ok) throw new Error(data.error);
  return data.result;
}
function task(fn) { return (...args) => Promise.resolve().then(() => fn(...args)).catch(e => { notice(e.message); status('Revisa el aviso'); }); }
function controls() {
  const locked = busy || !!stored(pendingKey);
  for (const id of ['back','undo','redo','split','edges','hook','remove','rewrite','itemLink','linkAll','saveNote','saveText','shorten','extend']) $(id).disabled = locked;
  for (const node of document.querySelectorAll('#layerControls button, dialog textarea, dialog input, dialog select, dialog .close')) node.disabled=locked;
  for(const id of ['drawToggle','drawUndo','discardDraft','loadSavedText']) $(id).disabled=locked;
  $('edges').disabled ||= !total();
  $('remove').disabled ||= !selected();
  $('itemLink').disabled ||= selection?.kind === 'clips';
  $('hook').disabled ||= !p || !items().some(editable);
  $('play').disabled = locked || !total();
  $('comment').disabled = locked || !total();
}
async function mutate(payload) {
  if (busy || stored(pendingKey)) throw new Error('Comprueba el cambio pendiente antes de continuar.');
  pause();
  const req = {project:p.id,revision:p.revision,...payload,requestId:crypto.randomUUID()};
  persist(pendingKey, req); // A failed local save prevents the write, rather than losing its identity.
  busy = true; controls(); status('Guardando en tu Mac…'); notice();
  try {
    const response = await api(req);
    if (response.uncertain) { recover(response.error); return false; }
    localStorage.removeItem(pendingKey);
    if (!response.ok) { status(response.conflict ? 'Hay un cambio simultáneo' : 'No se ha guardado'); throw new Error(response.error); }
    if (response.result.project) applyProject(response.result.project);
    status('Guardado en tu Mac');
    return true;
  } catch (error) {
    if (stored(pendingKey)) { recover('Se perdió la respuesta. Conservamos la acción para comprobar si se guardó.'); return false; }
    throw error;
  } finally { busy = false; controls(); }
}
function recover(message) {
  $('recoverText').textContent = message;
  if (!$('recoverDialog').open) $('recoverDialog').showModal();
  status('Guardado por comprobar');
}
$('checkReceipt').onclick = task(async () => {
  const req = stored(pendingKey);
  if (!req) return $('recoverDialog').close();
  const receipt = await query({action:'receipt',requestId:req.requestId});
  if (receipt.status !== 'done') {
    $('recoverText').textContent = 'El resultado aún no está confirmado. No se ha repetido la acción. Comprueba el proyecto guardado antes de continuar.';
    return;
  }
  localStorage.removeItem(pendingKey);
  $('recoverDialog').close();
  if (receipt.response.ok) {
    if (req.action === 'note') { noteDraft=null; localStorage.removeItem(draftKey(req.project)); $('noteDialog').close(); }
    if (req.action === 'edit' && req.op.type === 'text') { localStorage.removeItem(textKey({project:req.project,id:req.op.id})); textDraft=null; $('textDialog').close(); }
    status('Guardado confirmado');
  } else notice(receipt.response.error);
  if (p) await reload();
  controls();
});
$('acceptState').onclick = task(async () => {
  const req = stored(pendingKey);
  if (!req) return $('recoverDialog').close();
  const receipt = await query({action:'receipt',requestId:req.requestId});
  if (receipt.status === 'processing') { $('recoverText').textContent='El Mac sigue procesando la acción. Espera y comprueba el guardado.'; return; }
  await openProject(req.project, true);
  localStorage.removeItem(pendingKey);
  $('recoverDialog').close();
  notice('Proyecto releído. Revisa el resultado antes de repetir el ajuste; el historial también está disponible en el Mac.');
  controls();
});
$('recoverDialog').addEventListener('cancel', event => event.preventDefault());

async function loadLibrary() {
  const token=++navigation; pause(); releaseMedia(); const result=await query({action:'library'}); if(token!==navigation)return; library=result; p = null;
  $('library').hidden = false; $('editor').hidden = true; $('back').hidden = true;
  $('title').textContent = 'Studio'; status('Conectado a tu Mac'); showLibrary();
}
function showLibrary() {
  const chips = $('folders'); chips.replaceChildren();
  for (const item of [{id:'',name:'Todos'},...library.folders]) {
    const button = element('button', item.id === folder ? 'active' : '', item.name);
    button.onclick = () => { folder = item.id; showLibrary(); }; chips.append(button);
  }
  const normalize = x => x.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const term = normalize($('search').value);
  const list = library.projects.filter(x => (!folder || x.folder === folder) && normalize(x.name).includes(term));
  $('projects').replaceChildren();
  for (const item of list) {
    const button = element('button','project');
    const info = element('div'); info.append(element('strong','',item.name),element('small','',`${seconds(item.duration)} · ${item.width} × ${item.height}`));
    button.append(element('div','aspect',item.height > item.width ? '9 : 16' : '16 : 9'),info,element('span','arrow','›'));
    button.onclick = task(() => openProject(item.id)); $('projects').append(button);
  }
  if (!list.length) $('projects').append(element('p','empty','No hay proyectos aquí.'));
}
$('search').oninput = showLibrary;
$('back').onclick = task(loadLibrary);
$('refresh').onclick = task(async () => { notice(); if (p) await reload(); else await loadLibrary(); });
async function openProject(id, recovery = false) {
  if (busy && !recovery) return;
  const token=++navigation;
  pause(); status('Abriendo proyecto…');
  const state = await query({action:'state',project:id});
  if(token!==navigation)return;
  frame = 0; selection = null; notes = state.notes;
  $('library').hidden = true; $('editor').hidden = false; $('back').hidden = false;
  applyProject(state.project); renderNotes(); status('Guardado en tu Mac');
  if (stored(draftKey(id))) notice('Tienes un comentario sin enviar. Pulsa Comentar para recuperarlo.');
}
function anchor() {
  if (!p) return null;
  let start = 0;
  for (const c of p.clips) { if (start <= frame && frame < start+c.length) return {id:c.id,asset:c.asset,source:c.in+(frame-start)*(c.speed||1)}; start += c.length; }
}
function applyProject(next) {
  const ref = p?.id === next.id ? anchor() : null;
  const changed=p?.id !== next.id || p?.revision !== next.revision;
  // An edit keeps the videos of the montage: most of them are the same after it.
  if(changed) releaseMedia(p?.id===next.id);
  p = next;
  if (ref) {
    let start = 0; const matches = [];
    for (const c of p.clips) { if (c.asset === ref.asset && c.in <= ref.source && ref.source < c.in+c.length*(c.speed||1)) matches.push({id:c.id,frame:start+Math.round((ref.source-c.in)/(c.speed||1))}); start += c.length; }
    const target = matches.find(x => x.id === ref.id) || (matches.length === 1 ? matches[0] : null);
    if (target) frame = target.frame;
  }
  frame = Math.max(0,Math.min(frame,total()-1));
  if (selection && !selected()) selection = null;
  $('title').textContent = p.name; $('scrub').max = Math.max(0,total()-1);
  renderTimeline(); renderLayers(); controls();
  if(changed)loadDirect();
  showFrame();
}
function loadDirect() {
  directSupported=null;const id=p.id,revision=p.revision,request=++directRequest;
  directLoad=direct.load(p,frame).then(supported=>{
    if(request!==directRequest||p?.id!==id||p.revision!==revision)return;
    directLoad=null;
    if(supported===undefined)return;
    directSupported=supported;
    if(!supported)notice('Este montaje se ve con la previsualización compuesta.');
    showFrame();
  }).catch(e=>{if(request!==directRequest||p?.id!==id||p.revision!==revision)return;directLoad=null;notice(e.message);$('preparing').hidden=true;});
}

async function reload() {
  if (!p || busy) return;
  const id = p.id;
  const state = await query({action:'state',project:id,revision:p.revision});
  if (p?.id !== id || busy || dragging || state.revision < p.revision) return;
  if (state.project) { pause(); applyProject(state.project); status('Cambios del Mac recibidos'); }
  if(!state.project&&directSupported===null&&!directLoad)loadDirect();
  notes = state.notes; renderNotes();
}
function mediaURL(ext, n) { return `/media/${p.id}/${p.revision}/${n}.${ext}`; }
function updatePosition(follow=false) {
  $('time').textContent = `${time()} / ${seconds(total()/p.fps)}`; $('scrub').value = frame;
  const x=frame/p.fps*scale,head=document.querySelector('.playhead');if(head)head.style.left=`${x}px`;
  const timeline=$('timeline');
  if((follow||playing)&&!timelineTouch&&performance.now()>timelineHold)timeline.scrollLeft=Math.max(0,x-timeline.clientWidth*.35); 
}
function showFrame() {
  updatePosition(true);
  if(directSupported!==false) {
    video.hidden=true;$('still').hidden=true;
    if(directSupported)direct.seek(frame);else{$('preparing').textContent='Cargando proyecto…';$('preparing').hidden=false;}
    return;
  }
  $('preparing').textContent='Preparando este tramo…';
  if (mediaCovers() && video.readyState >= 1) {
    positionVideo(); $('preparing').hidden = !positioning;
    if (video.readyState >= 2) { video.hidden=false; $('still').hidden=true; }
    warmNearby(); return;
  }
  video.hidden = true; $('still').hidden = !total();
  if (total()) $('still').src = mediaURL('jpg',frame);
  warmNearby();
}
function warmNearby() {
  clearTimeout(warmTimer);
  if (!p || !total() || document.hidden) return;
  const req={action:'warm',project:p.id,revision:p.revision,frame};
  warmTimer=setTimeout(()=>{query(req).catch(()=>{});},400);
}
function mediaCovers() {
  return !!p && !!mediaSource && mediaSource.project === p.id && mediaSource.revision === p.revision && frame >= playbackOffset &&
    frame < (mediaSource.hls ? total() : playbackOffset+Math.round(p.fps*6));
}
function releaseMedia(keepDirect=false) {
  if(!keepDirect)direct.release();
  clearTimeout(warmTimer); mediaGeneration++; mediaSource=null; positioning=false;
  video.pause(); video.removeAttribute('src'); video.load();
}
function pause() {
  if(directSupported){frame=Math.round(direct.clock());direct.stop();}
  else if(playing && !positioning && p && video.readyState>=2 && Number.isFinite(video.currentTime)) frame=Math.max(0,Math.min(total()-1,playbackOffset+Math.round(video.currentTime*p.fps)));
  playing = false; mediaGeneration++; video.pause();
  $('play').textContent = '▶'; $('play').setAttribute('aria-label','Reproducir'); $('preparing').hidden = true;
  if (p) updatePosition();
}
async function play() {
  if (!p || !total()) return;
  if (playing) return pause();
  if(directSupported===null){if(!directLoad)loadDirect();await directLoad;if(directSupported===null)return;}
  if(directSupported)return direct.play(frame,speed);
  const generation = ++mediaGeneration;
  const size = Math.round(p.fps*6), index = Math.floor(frame/size);
  playing = true;
  const hls = !!video.canPlayType('application/vnd.apple.mpegurl');
  const reuse=mediaCovers();
  if (!reuse) {
    playbackOffset=index*size;
    mediaSource={project:p.id,revision:p.revision,hls};
    positioning=true;
    video.src = mediaURL(hls ? 'm3u8' : 'mp4',index);
  }
  if (reuse && video.readyState>=1) positionVideo();
  video.playbackRate=speed; video.preservesPitch=true;
  $('preparing').hidden = false; $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label','Pausar');
  try { await video.play(); }
  catch (e) { if (generation === mediaGeneration) { pause(); notice('La reproducción no ha comenzado. Toca reproducir para reintentar.'); } }
}
function positionVideo() {
  if (!mediaCovers()) return;
  const target=(frame-playbackOffset)/p.fps;
  positioning=Math.abs(video.currentTime-target)>=1/p.fps;
  if (positioning) video.currentTime=target;
  video.playbackRate=speed;
}
video.onloadedmetadata=positionVideo;
video.onplaying = () => { if (playing && !positioning) { video.hidden = false; $('still').hidden = true; $('preparing').hidden = true; } };
video.onseeked = () => {
  if (mediaCovers() && video.readyState>=2 && !video.seeking) {
    positioning=false; video.hidden=false; $('still').hidden=true; $('preparing').hidden=true;
  }
};
video.onwaiting = () => { if (playing) $('preparing').hidden = false; };
video.ontimeupdate = () => { if (!playing || positioning || !p) return; frame = Math.min(total()-1, playbackOffset+Math.round(video.currentTime*p.fps)); updatePosition(); };
video.onended = task(async () => {
  if (!playing) return;
  const next = playbackOffset+Math.round(p.fps*6);
  if (video.canPlayType('application/vnd.apple.mpegurl') || next >= total()) return pause();
  playing = false; frame = next; await play();
});
video.onerror = () => { if (playing) { pause(); notice('No se pudo preparar el tramo. Comprueba la conexión y vuelve a reproducir.'); } };
$('still').onerror = () => { if (p && total()) notice('No se pudo cargar el fotograma. Actualiza cuando el Mac esté disponible.'); };
$('play').onclick = (...args)=>{if(directSupported!==false&&!playing)direct.unlock().catch(e=>notice(e.message));return task(play)(...args);};
$('speed').onchange=()=>{speed=Number($('speed').value);if(directSupported&&playing)direct.play(direct.clock(),speed);else{video.playbackRate=speed;video.preservesPitch=true;}};
$('prev').onclick = () => seek(frame-1);
$('next').onclick = () => seek(frame+1);
function seek(next) { pause(); frame = Math.max(0,Math.min(Math.round(next),total()-1)); showFrame(); }
$('scrub').oninput = () => { const next=Number($('scrub').value); if (playing) pause(); frame=next; updatePosition(); };
$('scrub').onchange = showFrame;
$('timeline').addEventListener('pointerdown',event=>{
  timelineTouch=true;
  timelineTap=event.isPrimary && event.button===0 ? {x:event.clientX,y:event.clientY} : null;
});
$('timeline').addEventListener('pointermove',event=>{
  if(timelineTap && Math.hypot(event.clientX-timelineTap.x,event.clientY-timelineTap.y)>8)timelineTap=null;
});
$('timeline').addEventListener('pointercancel',()=>{timelineTap=null;});
for(const event of ['pointerup','pointercancel'])window.addEventListener(event,()=>{if(timelineTouch){timelineTouch=false;timelineHold=performance.now()+1500;}});
$('timeline').addEventListener('wheel',()=>{timelineHold=performance.now()+1500;},{passive:true});
$('tracks').onclick=tapTimeline;
function tapTimeline(event,row) {
  event.stopPropagation();
  if(busy || dragging || event.target.closest('.handle'))return;
  if(!event.detail) { if(row)choose(row); return; }
  if(!timelineTap)return;
  timelineTap=null;
  const next=(event.clientX-$('tracks').getBoundingClientRect().left)/scale*p.fps;
  timelineHold=performance.now()+1500;
  if(row)choose(row,next);else seek(next);
}

function items() {
  let start = 0;
  return ['clips','graphics','captions','audio'].flatMap(kind => p[kind].map(item => {
    const at = kind === 'clips' ? start : item.start; if (kind === 'clips') start += item.length;
    const track = kind === 'audio' ? item.role : kind === 'graphics' && item.type === 'video' ? 'overlays' : kind;
    return {kind,item,start:at,track};
  }));
}
function selected() { return p && selection ? items().find(x => x.kind === selection.kind && x.item.id === selection.id) : null; }
function linked(row) { return row.kind === 'clips' || (row.item.linked ?? p.syncTracks?.[row.track] ?? true); }
function editable(item) { return !!item && (item.kind === 'captions' || item.kind === 'graphics' && item.item.type === 'title'); }
function label(row) { return row.item.props?.text || row.item.text || p.assets.find(a => a.id === row.item.asset)?.name || names[row.track]; }
function choose(row,next=frame) { selection = {kind:row.kind,id:row.item.id}; seek(Math.max(row.start, Math.min(next,row.start+row.item.length-1))); renderTimeline(); controls(); }
function renderTimeline() {
  const tracks = $('tracks'); tracks.replaceChildren();
  tracks.style.width = `${Math.max($('timeline').clientWidth-32,total()/p.fps*scale)}px`;
  const ruler = element('div','ruler'); tracks.append(ruler);
  const step = Math.max(1,Math.ceil(70/scale));
  for (let t=0; t <= total()/p.fps; t+=step) { const tick = element('span','tick',seconds(t)); tick.style.left = `${t*scale}px`; ruler.append(tick); }
  for (const track of Object.keys(names)) {
    const rows = items().filter(x => x.track === track); if (!rows.length) continue;
    const lanes = [];
    for (const row of rows.sort((a,b)=>a.start-b.start)) {
      let lane = lanes.find(x => x.end <= row.start);
      if (!lane) { lane = {node:element('div','track'),end:0}; lane.node.setAttribute('aria-label',names[track]); lanes.push(lane); tracks.append(lane.node); }
      lane.end = row.start+row.item.length;
      const sel = selection?.id === row.item.id;
      const block = element('button',`block ${row.kind}${sel?' selected':''}`);
      block.style.left = `${row.start/p.fps*scale}px`; block.style.width = `${Math.max(4,row.item.length/p.fps*scale)}px`;
      block.title = `${names[track]}: ${label(row)}`; block.setAttribute('aria-label',block.title);
      block.append(element('span','block-label',label(row)));
      block.onclick = event => tapTimeline(event,row); block.row = row;
      if (sel) for (const edge of ['start','end']) {
        const handle = element('span',`handle ${edge}`,'Ⅱ'); handle.setAttribute('aria-label',edge === 'start' ? 'Ajustar inicio' : 'Ajustar final');
        handle.onpointerdown = event => dragEdge(event,row,edge,block); block.append(handle);
      }
      lane.node.append(block);
    }
  }
  tracks.append(element('div','playhead')); updatePosition();
  const row = selected(); $('selectedLabel').textContent = row ? `${names[row.track]} · ${label(row)}` : 'Bordes ajusta el clip actual · Texto muestra los textos';
  $('itemLink').hidden = !row || row.kind === 'clips'; $('rewrite').hidden = !editable(row);
  if (row) $('itemLink').textContent = linked(row) ? '🔗 Unida' : 'Libre';
}
function dragEdge(event,row,edge,block) {
  event.preventDefault(); event.stopPropagation(); if (busy || dragging || stored(pendingKey)) return;
  pause(); const x = event.clientX, pointer = event.pointerId, revision = p.revision, id = p.id; let delta = 0;
  // Shortening a video clip closes the gap: what comes after it follows the edge while dragging, as it will once saved.
  const after = row.kind === 'clips' ? [...$('tracks').querySelectorAll('.block')].filter(b => linked(b.row) && b.row.start >= row.start+row.item.length) : [];
  dragging=true;
  const move = e => {
    if (e.pointerId !== pointer) return;
    delta = Math.round((e.clientX-x)/scale*p.fps);
    const length = row.item.length+(edge === 'end' ? delta : -delta);
    if (length > 0) { block.style.width = `${Math.max(4,length/p.fps*scale)}px`; for (const b of after) b.style.transform = `translateX(${(length-row.item.length)/p.fps*scale}px)`; }
    $('selectedLabel').textContent = `${edge === 'start'?'Inicio':'Final'}: ${delta>0?'+':''}${(delta/p.fps).toFixed(2)} s`;
  };
  // The finger is followed on the window: the gesture ends wherever it is lifted, and the timeline always shows what was saved.
  const end = task(async e => {
    if (e.pointerId !== pointer) return;
    for (const type of ['pointermove','pointerup','pointercancel']) window.removeEventListener(type,type === 'pointermove' ? move : end,true);
    dragging=false; report('edge',{edge,delta,end:e.type});
    try { if (e.type === 'pointerup' && delta) await mutate({action:'edit',project:id,revision,op:{type:'resize',kind:row.kind,id:row.item.id,edge,delta}}); }
    finally { renderTimeline(); }
  });
  window.addEventListener('pointermove',move,true); window.addEventListener('pointerup',end,true); window.addEventListener('pointercancel',end,true);
}
$('zoomIn').onclick = () => { scale = Math.min(256,scale*2); renderTimeline(); };
$('zoomOut').onclick = () => { scale = Math.max(1,scale/2); renderTimeline(); };
$('split').onclick = task(async () => {
  pause();
  const row = selected();
  const op = row && !linked(row) ? {type:'split',kind:row.kind,id:row.item.id,at:frame-row.start} : {type:'splitAt',frame};
  await mutate({action:'edit',op});
});
$('itemLink').onclick = task(async () => { const row=selected(); if (row) await mutate({action:'edit',op:{type:'linked',kind:row.kind,id:row.item.id,linked:!linked(row)}}); });
$('remove').onclick = task(async () => { const row=selected(); if (row) await mutate({action:'edit',op:{type:'delete',kind:row.kind,id:row.item.id}}); });
$('edges').onclick = () => {
  pause();
  const row=selected() || items().find(x=>x.kind==='clips' && x.start<=frame && frame<x.start+x.item.length);
  if (!row) return;
  choose(row); $('edgeLabel').textContent = `${label(row)} · ${seconds(row.start/p.fps)}–${seconds((row.start+row.item.length)/p.fps)}`;
  $('edgeDialog').showModal();
};
async function resize(extend) {
  const row = selected(), amount = Number($('edgeSeconds').value);
  if (!Number.isFinite(amount) || amount <= 0) throw new Error('Escribe una duración positiva.');
  const edge = $('edge').value;
  const delta = Math.max(1,Math.round(amount*p.fps))*(edge === 'start' ? -1 : 1)*(extend ? 1 : -1);
  if (await mutate({action:'edit',op:{type:'resize',kind:row.kind,id:row.item.id,edge,delta}})) $('edgeDialog').close();
}
$('shorten').onclick = task(() => resize(false)); $('extend').onclick = task(() => resize(true));
$('undo').onclick = task(() => mutate({action:'undo'})); $('redo').onclick = task(() => mutate({action:'redo'}));
function renderLayers() {
  $('layerControls').replaceChildren();
  for (const track of Object.keys(names).filter(x=>x !== 'clips')) {
    const list = items().filter(x=>x.track === track); const flags = new Set(list.map(linked));
    const active = flags.size === 0 ? p.syncTracks?.[track] !== false : flags.size === 1 && flags.has(true);
    const mixed = flags.size > 1;
    const row=element('div','layer'); row.append(element('span','',names[track]));
    const button=element('button',active?'united':'',mixed?'Mixta':active?'🔗 Unida':'Libre');
    button.onclick=task(()=>mutate({action:'edit',op:{type:'linkTrack',track,linked:!active}})); row.append(button); $('layerControls').append(row);
  }
}
$('linkAll').onclick = task(()=>mutate({action:'edit',op:{type:'linkTrack',track:'all',linked:true}}));
for (const [id,panel,other] of [['notesTab','notesPanel','layersPanel'],['layersTab','layersPanel','notesPanel']]) $(id).onclick=()=>{
  $(panel).hidden=false; $(other).hidden=true; $('notesTab').setAttribute('aria-selected',String(id==='notesTab')); $('layersTab').setAttribute('aria-selected',String(id==='layersTab'));
};

function openText(row) {
  if (!editable(row)) return; choose(row);
  textDraft={project:p.id,revision:p.revision,kind:row.kind,id:row.item.id};
  textDraft=stored(textKey(textDraft))||textDraft;
  $('hookText').value=textDraft.text ?? row.item.props?.text ?? row.item.text; $('textDialog').showModal(); $('hookText').focus();
}
$('hook').onclick = () => {
  pause();
  $('textSearch').value=''; renderTextChoices(); $('textPicker').showModal();
};
function renderTextChoices() {
  const term=$('textSearch').value.toLocaleLowerCase();
  const rows=items().filter(editable).filter(row=>label(row).toLocaleLowerCase().includes(term));
  rows.sort((a,b)=>Number(b.item.keepTogether===true)-Number(a.item.keepTogether===true) || a.start-b.start);
  $('textChoices').replaceChildren();
  for (const row of rows) {
    const button=element('button','text-choice');
    button.append(element('small','',`${row.item.keepTogether?'Gancho · ':''}${seconds(row.start/p.fps)}`),element('span','',label(row)));
    button.onclick=()=>{$('textPicker').close();openText(row);}; $('textChoices').append(button);
  }
  if (!rows.length) $('textChoices').append(element('p','hint','No hay textos que coincidan.'));
}
$('textSearch').oninput=renderTextChoices;
$('rewrite').onclick = () => openText(selected());
// A text is rewritten where it is seen: tapping it on the picture opens it.
$('viewer').onclick = event => { if (directSupported && !$('hook').disabled) openText(items().find(row => row.item.id === direct.textAt(event))); };
function saveTextDraft(){if(textDraft){textDraft.text=$('hookText').value;try{persist(textKey(textDraft),textDraft);}catch{notice('No se puede conservar el texto aquí. Guarda antes de cerrar.');}}}
$('hookText').oninput=saveTextDraft;
$('textDialog').addEventListener('close',saveTextDraft);
$('loadSavedText').onclick=task(async()=>{await reload();const row=selected();if(!editable(row))throw new Error('Este texto ya no existe en el montaje. Conserva tu intento.');textDraft={project:p.id,revision:p.revision,kind:row.kind,id:row.item.id};$('hookText').value=row.item.props?.text??row.item.text;saveTextDraft();});
$('saveText').onclick = task(async()=>{
  saveTextDraft();
  if (await mutate({action:'edit',project:textDraft.project,revision:textDraft.revision,op:{type:'text',kind:textDraft.kind,id:textDraft.id,text:$('hookText').value}})) {localStorage.removeItem(textKey(textDraft));textDraft=null;$('textDialog').close();}
});

function renderNotes() {
  $('notes').replaceChildren(); $('noteCount').textContent=notes.filter(n=>n.status==='open').length || '';
  for (const note of notes) {
    const button=element('button','note');
    button.append(element('b','',`${seconds((note.currentFrame??note.frame)/note.fps)} · ${note.status==='resolved'?'Resuelto':note.status==='draft'?'Borrador':'Pendiente'}`),element('p','',note.text||'Indicación dibujada'));
    if (note.position!=='current') button.append(element('small','',note.position==='removed'?'El fotograma se eliminó del montaje.':'La posición actual es ambigua.'));
    if (note.strokes.length) button.append(element('small','','Incluye dibujo'));
    button.onclick=()=>openNote(note); $('notes').append(button);
  }
  if (!notes.length) $('notes').append(element('p','empty','¿Algo que mejorar? Pausa y toca Comentar.'));
}
function saveDraft() {
  if (!noteDraft) return;
  noteDraft.text=$('noteText').value;
  try { persist(draftKey(noteDraft.project),noteDraft); $('noteStatus').textContent='Borrador conservado en este iPhone.'; }
  catch { $('noteStatus').textContent='No se puede conservar aquí. Guarda el comentario antes de cerrar.'; }
}
function openNote(note=null) {
  pause();
  const draft=stored(draftKey(p.id));
  if(note && draft && draft.noteId!==note.id && (draft.text.trim()||draft.strokes.length)) {notice('Conservamos tu borrador. Termina o descártalo antes de abrir otro comentario.');note=null;}
  noteDraft=draft && (!note||draft.noteId===note.id) ? draft : note ? {project:p.id,revision:note.revision,noteId:note.id,frame:note.frame,version:note.version,text:note.text,strokes:structuredClone(note.strokes)} : {project:p.id,revision:p.revision,noteId:crypto.randomUUID(),frame,text:'',strokes:[]};
  $('noteText').value=noteDraft.text; $('noteTime').textContent=`${seconds(noteDraft.frame/p.fps)} · FOTOGRAMA ${noteDraft.frame}`;
  $('noteImage').src=noteDraft.version ? `/note/${noteDraft.project}/${noteDraft.noteId}.png` : `/media/${noteDraft.project}/${noteDraft.revision}/${noteDraft.frame}.jpg`;
  $('noteDialog').showModal(); drawing=false; updateDrawingMode(); saveDraft(); $('noteText').focus();
}
$('comment').onclick=()=>openNote(); $('noteText').oninput=saveDraft;
const discard=element('button','','Descartar borrador local');discard.id='discardDraft';discard.type='button';$('noteStatus').after(discard);
discard.onclick=()=>{localStorage.removeItem(draftKey(noteDraft.project));noteDraft=null;$('noteDialog').close();};
$('noteDialog').addEventListener('close',saveDraft);
$('saveNote').onclick=task(async()=>{
  saveDraft();
  if (!$('noteText').value.trim() && !noteDraft.strokes.length) throw new Error('Escribe un comentario o dibuja una indicación.');
  if (await mutate({action:'note',...noteDraft,text:$('noteText').value})) {
    const pid=noteDraft.project; noteDraft=null; localStorage.removeItem(draftKey(pid)); $('noteDialog').close(); await reload();
  }
});
function updateDrawingMode() { $('drawing').classList.toggle('active',drawing); $('drawToggle').setAttribute('aria-pressed',String(drawing)); paint(); }
$('drawToggle').onclick=()=>{drawing=!drawing; updateDrawingMode();};
$('drawUndo').onclick=()=>{ noteDraft.strokes.pop(); saveDraft(); paint(); };
function paint() {
  const img=$('noteImage'), canvas=$('drawing'), box=img.getBoundingClientRect(), parent=$('annotation').getBoundingClientRect();
  if (!box.width || !box.height) return;
  canvas.style.left=`${box.left-parent.left}px`; canvas.style.top=`${box.top-parent.top}px`;
  canvas.style.width=`${box.width}px`; canvas.style.height=`${box.height}px`;
  canvas.width=Math.round(box.width*devicePixelRatio); canvas.height=Math.round(box.height*devicePixelRatio);
  const ctx=canvas.getContext('2d'); ctx.lineCap='round'; ctx.lineJoin='round';
  for (const s of noteDraft?.strokes||[]) {
    ctx.strokeStyle=s.color; ctx.lineWidth=s.width*canvas.width; ctx.beginPath();
    const pts=s.points.map(([x,y])=>[x*canvas.width,y*canvas.height]);
    if (s.tool==='pen') pts.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
    else if (pts.length===2) {
      const [[x,y],[a,b]]=pts;
      if (s.tool==='ellipse') ctx.ellipse((x+a)/2,(y+b)/2,Math.abs(a-x)/2,Math.abs(b-y)/2,0,0,Math.PI*2);
      else if(s.tool==='rect') ctx.rect(x,y,a-x,b-y);
      else { ctx.moveTo(x,y); ctx.lineTo(a,b); const angle=Math.atan2(b-y,a-x); for(const d of [-.5,.5]) {ctx.moveTo(a,b);ctx.lineTo(a-15*Math.cos(angle+d),b-15*Math.sin(angle+d));} }
    }
    ctx.stroke();
  }
}
$('noteImage').onload=paint; window.addEventListener('resize',paint);
function point(event) { const box=$('drawing').getBoundingClientRect(); return [Math.max(0,Math.min(1,(event.clientX-box.left)/box.width)),Math.max(0,Math.min(1,(event.clientY-box.top)/box.height))]; }
$('drawing').onpointerdown=event=>{
  if(!drawing || busy || stored(pendingKey) || noteDraft.strokes.length>=100) return;
  event.preventDefault(); $('drawing').setPointerCapture(event.pointerId);
  stroke={tool:'pen',color:'#ffb777',width:.006,points:[point(event)]}; noteDraft.strokes.push(stroke); paint();
};
$('drawing').onpointermove=event=>{if(stroke && stroke.points.length<2000){stroke.points.push(point(event));paint();}};
for(const evt of ['pointerup','pointercancel']) $('drawing').addEventListener(evt,()=>{if(stroke){stroke=null;saveDraft();}});

document.addEventListener('visibilitychange',()=>{if(document.hidden) {pause();releaseMedia();flushReports();} else if(p && !modal()) {showFrame();task(reload)();}});
window.addEventListener('offline',()=>{pause(); status('Sin conexión · borradores conservados');});
window.addEventListener('online',()=>{if(!stored(pendingKey)) task(p?reload:loadLibrary)();});
setInterval(async()=>{
  if(document.hidden || !p || busy || dragging || modal() || pollBusy || stored(pendingKey)) return;
  pollBusy=true;
  try {await reload();} catch {status('Sin conexión con el Mac');} finally {pollBusy=false;}
},5000);
await task(loadLibrary)();
if(stored(pendingKey)) recover('Hay una acción de la sesión anterior pendiente de comprobar.');
