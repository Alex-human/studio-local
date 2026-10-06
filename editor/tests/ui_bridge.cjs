// Behavioral UI tests with a minimal DOM and the real JSON engine. Does not certify pixels or WKWebView.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert'),cp=require('child_process');
const root=path.resolve(__dirname,'..');
const python=require('path').join(__dirname,'..','.venv','bin','python3');
const engine=path.join(root,'engine/editor.py');
const work=fs.mkdtempSync('/private/tmp/studio-ui-');
// The UI contract must not depend on a user's project or its retained source media.
const original=JSON.parse(cp.execFileSync(python,['-c',`
import json,subprocess,sys
from pathlib import Path
root,work=map(Path,sys.argv[1:])
sys.path.insert(0,str(root/'engine'))
import project
ffmpeg=str(root/'runtime/ffmpeg')
def media(args):
 subprocess.run([ffmpeg,'-v','error',*args],check=True,timeout=30)
media(['-f','lavfi','-i','color=c=0x24405c:s=160x90:r=60000/1001:d=12','-an','-c:v','libx264','-pix_fmt','yuv420p',str(work/'video.mp4')])
p=project.new('Prueba UI sintética')
p['assets'].append(dict(id='video',path=str(work/'video.mp4'),name='video.mp4',kind='video',audio=False,duration=12,width=160,height=90,fps=p['fps']))
p['clips'].append(dict(id='clip',asset='video',length=510,muted=True,volumeDb=0,zoom=1,zoomEnd=1,x=.5,y=.5,**{'in':0}))
for role,hz in [('voice',440),('music',220),('sfx',880)]:
 file=work/(role+'.wav')
 media(['-f','lavfi','-i',f'sine=frequency={hz}:sample_rate=48000:duration=12','-ac','2','-c:a','pcm_s16le',str(file)])
 p['assets'].append(dict(id=role,path=str(file),name=file.name,kind='audio',audio=True,duration=12,fps=0,width=0,height=0))
 p['audio'].append(dict(id=role+'-clip',asset=role,role=role,start=0,length=510,volumeDb=0,**{'in':0}))
p['graphics'].append(dict(id='intro',type='channel_intro',start=0,length=510,props={'title':'Tu canal','accent':'#65a5ff','background':'#163768','count':3}))
project.validate(p,check_files=True)
print(json.dumps(p))
`,root,work],{encoding:'utf8',timeout:120000}));
const clipboardPng=cp.execFileSync(python,['-c','import io,base64;from PIL import Image;b=io.BytesIO();Image.new("RGB",(80,40),"blue").save(b,format="PNG");print(base64.b64encode(b.getvalue()).decode())'],{encoding:'utf8'}).trim();
const project=path.join(work,'Test.studio');fs.writeFileSync(project,JSON.stringify(original));
class El{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.style={};this.dataset={};this.value='';this.hidden=false;this.checked=false;this.clientWidth=1200;this.paused=true;this.currentTime=0;this.scrollLeft=0;this.className='';this.classList={toggle:()=>{},add:()=>{},remove:()=>{}};}
 focus(){doc.activeElement=this;}
 select(){this.focus();}
 set id(value){this._id=value;elements[value]=this;} get id(){return this._id;}
 append(...x){for(const child of x)if(child&&typeof child==='object')child.parentElement=this;this.children.push(...x);if(this.tagName==='SELECT'&&this.value===''&&x[0])this.value=x[0].value;} replaceChildren(...x){this.children=x;} setAttribute(k,v){this[k]=v;} removeAttribute(k){delete this[k];} getBoundingClientRect(){return {left:0,top:0,width:1200,height:675};} addEventListener(){} setPointerCapture(){} blur(){if(doc.activeElement===this){doc.activeElement=null;return this.onchange?.({target:this});}} pause(){this.paused=true;this.onpause?.();} async play(){this.paused=false;this.onplay?.();} showModal(){this.open=true;} close(){this.open=false;this.onclose?.();}
}
const elements={};const html=fs.readFileSync(path.join(root,'ui/index.html'),'utf8');
for(const m of html.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"[^>]*>/g)){elements[m[2]]=new El(m[1]);const v=m[0].match(/value="([^"]*)"/);if(v)elements[m[2]].value=v[1];}
const tabs=['media','motion','text'].map(t=>{const e=new El('button');e.dataset.tab=t;return e;});const tracks=Object.fromEntries(['video','overlays','graphics','captions','voice','music','sfx'].map(t=>[t,new El()]));
const listeners={};
const doc={getElementById:id=>elements[id],createElement:tag=>new El(tag),createTextNode:t=>({textContent:t}),addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn),querySelectorAll:s=>s==='[data-tab]'?tabs:s==='.track'?Object.values(tracks):[],querySelector:s=>tracks[s.match(/data-track="([^"]+)/)?.[1]]};
elements.feedbackPanel.parentElement=new El('aside');
let calls=0,failures=[],actions=[],bridgeRequests=[];const percent25=20*Math.log10(.25);
const catalog=[{path:project,name:'Zeta',revision:0,duration:8.5085,width:1920,height:1080,fps:60,modified:200},{path:project+'.album',name:'Álbum',revision:0,duration:8.5085,width:1920,height:1080,fps:60,modified:100}];
let listedProjects=catalog,listError=false,testSession=null,cancelAudio=false;
let listedFolders=[],folderRevision=0,folderSequence=0,folderFixture=false,folderFailure=null;
function folderResponse(request){
 if(folderFailure){const failure=folderFailure;folderFailure=null;return {ok:false,...failure};}
 if(request.revision!==folderRevision)return {ok:false,error:'La biblioteca cambió. Actualiza e inténtalo de nuevo.',conflict:true};
 const folder=listedFolders.find(item=>item.id===request.id);
 if(request.command==='create')listedFolders.push({id:'folder-'+(++folderSequence),name:request.name});
 else if(request.command==='rename'){if(!folder)return {ok:false,error:'Carpeta inexistente'};folder.name=request.name;}
 else if(request.command==='assign'){const item=listedProjects.find(item=>item.path===request.project);if(!item)return {ok:false,error:'Proyecto inexistente'};if(request.folder&&!listedFolders.some(folder=>folder.id===request.folder))return {ok:false,error:'Carpeta inexistente'};item.folder=request.folder;}
 else if(request.command==='delete'){if(!folder)return {ok:false,error:'Carpeta inexistente'};if(listedProjects.some(item=>item.folder===request.id))return {ok:false,error:'La carpeta contiene proyectos'};listedFolders=listedFolders.filter(item=>item.id!==request.id);}
 else return {ok:false,error:'Operación no disponible'};
 return {ok:true,result:{folders:listedFolders.map(item=>({...item})),folderRevision:++folderRevision}};
}
const context={console,document:doc,Map,setTimeout,clearTimeout,Error,Date,Number,Math,Promise,encodeURIComponent};context.window=context;
context.webkit={messageHandlers:{studio:{postMessage({id,request}){calls++;actions.push(request.action);if(request.action==='capabilities'){setTimeout(()=>context.studioReply(id,{ok:true,result:{feedback:true,playbackRate:true}}),0);return;}if(request.action==='playback'&&request.command==='freeze'){setTimeout(()=>context.studioReply(id,{ok:true,result:{frame:vm.runInContext('cursor+1',context)}}),0);return;}if(request.action==='sessionRead'||request.action==='sessionSave'){if(request.action==='sessionSave')testSession=request.session;setTimeout(()=>context.studioReply(id,{ok:true,result:testSession}),0);return;}bridgeRequests.push(request);if(['playback','loadPlayback'].includes(request.action)){setTimeout(()=>context.studioReply(id,{ok:true,result:{}}),0);return;}if(request.action==='preparePlayback'){setTimeout(()=>context.studioReply(id,{ok:true,result:{key:'test-plan',seconds:.1,audioSources:vm.runInContext('p.audio.concat(p.clips).map(x=>({id:x.id}))',context)}}),0);return;}if(request.action==='pasteImage'){request={...request,action:'importImageData',png:clipboardPng};}if(['chooseOverlay','chooseOverlayReplacement'].includes(request.action)){request={...request,action:'import',overlay:true,path:original.assets.find(a=>a.kind==='video').path};}if(['chooseSfx','chooseMusic'].includes(request.action)){if(cancelAudio){cancelAudio=false;setTimeout(()=>context.studioReply(id,{ok:false,cancelled:true,error:'Selección cancelada'}),0);return;}const role=request.action==='chooseSfx'?'sfx':'music';request={...request,action:'import',role,path:original.assets.find(a=>a.name===role+'.wav').path};}if(request.action==='projectFolders'){const response=folderResponse(request);setTimeout(()=>context.studioReply(id,response),0);return;}if(request.action==='create'&&folderFixture){const model={...original,id:'folder-new-project',name:request.name};const file=path.join(work,'Folder-new.studio');fs.writeFileSync(file,JSON.stringify(model));listedProjects.push({id:model.id,path:file,name:request.name,folder:request.folder||null,revision:model.revision,modified:300,duration:0,width:model.width,height:model.height,fps:model.fps});setTimeout(()=>context.studioReply(id,{ok:true,result:{path:file,project:model}}),0);return;}if(request.action==='list'){setTimeout(()=>context.studioReply(id,listError?{ok:false,error:'test list error'}:{ok:true,result:{projects:listedProjects.map(item=>({...item})),folders:listedFolders.map(item=>({...item})),folderRevision}}),0);return;}if(request.project)request.project=project;cp.execFile(python,[engine,'--request',JSON.stringify(request)],{cwd:root,maxBuffer:2e6},(err,stdout)=>{let response;try{response=JSON.parse(stdout);}catch(e){response={ok:false,error:String(err||e)};}if(!response.ok)failures.push(response.error);context.studioReply(id,response);});}}}};
vm.createContext(context);for(const file of ['app.js','audio.js','images.js','timeline.js','playback.js','sync.js','feedback.js','projects.js'])vm.runInContext(fs.readFileSync(path.join(root,'ui',file),'utf8'),context);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));const get=s=>vm.runInContext(s,context);
async function waitFor(fn,attempts=150){for(let i=0;i<attempts;i++){if(fn())return;await sleep(30);}throw Error('UI did not settle');}
(async()=>{
 const legacyElements=Object.fromEntries(['playbackSpeedControls','playbackSpeed','playbackRate','speed1','speed15','speed2'].map(id=>[id,new El()]));
 const legacyContext={state:{},window:{},$:id=>legacyElements[id],api:async()=>({feedback:true}),safe:fn=>fn};
 vm.createContext(legacyContext);vm.runInContext(fs.readFileSync(path.join(root,'ui/playback.js'),'utf8'),legacyContext);await vm.runInContext('playbackRateReady',legacyContext);
 assert.equal(legacyElements.playbackSpeedControls.hidden,true);
 await waitFor(()=>elements.projectGrid.children.length===2);
 assert.equal(get('p'),null);assert.equal(elements.editorWorkspace.hidden,true);assert.equal(elements.projectHome.hidden,false);
 assert.equal(elements.projectGrid.children[0].children[0]['aria-label'],'Editar Zeta');
 elements.projectSort.value='name';elements.projectSort.onchange();assert.equal(elements.projectGrid.children[0].children[0]['aria-label'],'Editar Álbum');
 elements.projectSearch.value='album';elements.projectSearch.oninput();assert.equal(elements.projectGrid.children.length,1);
 elements.projectSearch.value='missing';elements.projectSearch.oninput();assert.equal(elements.projectGrid.children.length,0);assert.equal(elements.homeMessage.hidden,false);
 elements.projectSearch.value='';elements.projectSearch.oninput();elements.projectSort.value='recent';elements.projectSort.onchange();
 await elements.projectGrid.children[0].children[0].onclick();
 assert.equal(elements.projectHome.hidden,true);assert.equal(elements.editorWorkspace.hidden,false);
 assert.equal(elements.projectTitle.textContent,original.name);
 const untouched=fs.readFileSync(project,'utf8');
 // Review speed is independent from edit speed, timeline history and rendered media.
 assert.equal(elements.playbackSpeedControls.hidden,false);assert.equal(get('playbackRate'),1);
 const beforeRateRevision=get('p.revision'),beforeRateActions=actions.length;
 elements.playbackRate.value='1,25';await elements.playbackRate.onchange();
 assert.equal(get('playbackRate'),1.25);assert.equal(elements.playbackSpeed.value,'1.25');assert.equal(elements.playbackRate.value,'1,25');assert.equal(get('playbackPlaying'),false);
 for(const invalid of ['', '0.99', '2.01', '1,25x', 'Infinity', '1.2.5']){
  elements.playbackRate.value=invalid;await elements.playbackRate.onchange();
  assert.equal(get('playbackRate'),1.25);assert.equal(elements.playbackRate.value,'1,25');assert.match(elements.toast.textContent,/entre 1 y 2/);
 }
 elements.playbackRate.value='1,';assert.equal(get('playbackRate'),1.25);
 elements.playbackRate.onkeydown({key:'Escape',preventDefault(){},stopPropagation(){}});assert.equal(elements.playbackRate.value,'1,25');
 elements.playbackRate.focus();elements.playbackRate.value='1.75';elements.playbackRate.onkeydown({key:'Enter',preventDefault(){}});await sleep(0);assert.equal(get('playbackRate'),1.75);assert.equal(doc.activeElement,null);
 elements.playbackSpeed.value='1.5';await elements.playbackSpeed.oninput();assert.equal(get('playbackRate'),1.5);assert.equal(elements.speed15['aria-pressed'],'true');
 await elements.speed2.onclick();assert.equal(get('playbackRate'),2);await elements.speed1.onclick();assert.equal(get('playbackRate'),1);await elements.speed15.onclick();assert.equal(get('playbackRate'),1.5);
 elements.playbackRate.value='1,25';await elements.playbackRate.onchange();
 assert.equal(actions.slice(beforeRateActions).some(a=>['ops','preparePlayback','render'].includes(a)),false);assert.equal(get('p.revision'),beforeRateRevision);assert.equal(fs.readFileSync(project,'utf8'),untouched);
 await elements.play.onclick();assert.equal(get('playbackPlaying'),true);assert.equal(bridgeRequests.filter(r=>r.command==='play').at(-1).rate,1.25);
 const liveRateActions=actions.length,liveRateKey=get('playbackKey'),liveRatePreview=get('previewRevision');
 elements.playbackSpeed.value='1.5';await elements.playbackSpeed.oninput();await elements.speed2.onclick();
 assert.equal(bridgeRequests.at(-1).command,'rate');assert.equal(bridgeRequests.at(-1).rate,2);assert.equal(get('playbackPlaying'),true);
 assert.equal(get('playbackKey'),liveRateKey);assert.equal(get('previewRevision'),liveRatePreview);assert.equal(actions.slice(liveRateActions).some(a=>['ops','preparePlayback','render'].includes(a)),false);
 assert.equal(get('p.revision'),beforeRateRevision);assert.equal(fs.readFileSync(project,'utf8'),untouched);
 await elements.play.onclick();const pausedPlayCount=bridgeRequests.filter(r=>r.command==='play').length;
 elements.playbackRate.value='1,25';await elements.playbackRate.onchange();assert.equal(get('playbackPlaying'),false);assert.equal(bridgeRequests.filter(r=>r.command==='play').length,pausedPlayCount);
 await elements.play.onclick();assert.equal(bridgeRequests.filter(r=>r.command==='play').at(-1).rate,1.25);
 await elements.soundPreview.play();await elements.homeProjects.onclick();
 assert.equal(get('playbackPlaying'),false);assert.equal(elements.soundPreview.paused,true);assert.equal(context.studioPaste(),false);
 assert.equal(fs.readFileSync(project,'utf8'),untouched);
 listedProjects=[];await elements.refreshHome.onclick();assert.equal(elements.projectGrid.children.length,0);assert.equal(actions.includes('create'),false);
 listError=true;await elements.refreshHome.onclick();assert.match(elements.homeMessage.textContent,/volver a intentarlo/);assert.equal(elements.refreshHome.disabled,false);
 listError=false;listedProjects=catalog;await elements.refreshHome.onclick();assert.equal(elements.projectGrid.children.length,2);
 // Folder requests stay in this isolated fixture; they never reach the user's catalog.
 listedProjects=catalog.map((item,index)=>({...item,id:'fixture-'+index,folder:null}));folderFixture=true;
 const folderVideoBefore=fs.readFileSync(project,'utf8'),folderModelBefore=JSON.stringify(get('p')),folderOpsBefore=actions.filter(action=>['ops','undo','redo'].includes(action)).length;
 const submitFolder=()=>elements.folderForm.onsubmit({preventDefault(){}});
 const folderCard=name=>elements.folderGrid.children.find(card=>card['aria-label']==='Abrir carpeta '+name);
 const projectCard=name=>elements.projectGrid.children.find(card=>card.children[0]['aria-label']==='Editar '+name);
 const moveProject=async(name,folder)=>{const select=projectCard(name).children[2].children[0];assert.equal(select['aria-label'],'Mover '+name+' a carpeta');select.value=folder||'';await select.onchange();};
 await elements.newFolder.onclick();assert.equal(elements.folderDialog.open,true);assert.equal(!!get('syncBlocked()'),true);assert.equal(await vm.runInContext('applyEditorUpdate()',context),false);
 const folderCallsBefore=actions.filter(action=>action==='projectFolders').length;
 elements.folderName.value=' ';await submitFolder();assert.equal(elements.folderError.hidden,false);elements.folderName.value='x'.repeat(81);await submitFolder();assert.equal(actions.filter(action=>action==='projectFolders').length,folderCallsBefore);
 elements.folderCancel.onclick();assert.equal(elements.folderDialog.open,false);assert.equal(listedFolders.length,0);doc.activeElement=null;
 await elements.newFolder.onclick();elements.folderName.value='Clientes';folderFailure={error:'No se pudo guardar la carpeta'};await submitFolder();assert.equal(elements.folderDialog.open,true);assert.equal(elements.folderName.value,'Clientes');assert.equal(elements.folderError.textContent,'No se pudo guardar la carpeta');assert.equal(get('state.folderBusy'),false);assert.equal(listedFolders.length,0);
 await submitFolder();assert.equal(elements.folderDialog.open,false);assert.equal(listedFolders.length,1);assert.equal(folderCard('Clientes').children[1].children[1].textContent,'0 proyectos');doc.activeElement=null;
 await elements.newFolder.onclick();elements.folderName.value='Personal';folderFailure={error:'Cancelado',cancelled:true};await submitFolder();assert.equal(elements.folderDialog.open,true);assert.equal(elements.folderError.hidden,true);assert.equal(listedFolders.length,1);await submitFolder();doc.activeElement=null;
 const clientes=listedFolders.find(folder=>folder.name==='Clientes').id,personal=listedFolders.find(folder=>folder.name==='Personal').id;
 const folderTransport=context.webkit.messageHandlers.studio.postMessage;let releaseFolder=null;
 context.webkit.messageHandlers.studio.postMessage=payload=>{if(payload.request.action==='projectFolders'&&payload.request.command==='assign'){releaseFolder=()=>folderTransport(payload);return;}folderTransport(payload);};
 const moving=moveProject('Zeta',clientes);await waitFor(()=>releaseFolder!==null);assert.equal(get('state.folderBusy'),true);assert.equal(await vm.runInContext('applyEditorUpdate()',context),false);assert.equal(elements.homeNew.disabled,true);
 let folderBarrierReleased=false;const folderBarrier=vm.runInContext('flushEdits()',context).then(()=>{folderBarrierReleased=true;});await sleep(0);assert.equal(folderBarrierReleased,false);releaseFolder();await Promise.all([moving,folderBarrier]);context.webkit.messageHandlers.studio.postMessage=folderTransport;
 assert.equal(get('state.folderBusy'),false);assert.equal(elements.projectGrid.children.length,1);assert.equal(folderCard('Clientes').children[1].children[1].textContent,'1 proyecto');assert.equal(folderCard('Personal').children[1].children[1].textContent,'0 proyectos');
 elements.projectSearch.value='zeta';elements.projectSearch.oninput();assert.equal(elements.projectGrid.children.length,1);assert.equal(elements.folderGrid.hidden,true);assert.equal(projectCard('Zeta').children[0].children[1].children[2].textContent,'Clientes');
 elements.projectSearch.value='';elements.projectSearch.oninput();folderCard('Clientes').onclick();assert.equal(get('homeFolder'),clientes);assert.equal(elements.homeTitleText.textContent,'Clientes');assert.equal(elements.folderBack.hidden,false);assert.equal(elements.projectGrid.children.length,1);assert.equal(elements.deleteFolder.disabled,false);
 const beforeOccupiedDelete=actions.filter(action=>action==='projectFolders').length;const cancellingDelete=elements.deleteFolder.onclick();assert.equal(elements.confirmDialog.open,true);elements.confirmCancel.onclick();await cancellingDelete;assert.equal(actions.filter(action=>action==='projectFolders').length,beforeOccupiedDelete);
 elements.projectSearch.value='album';elements.projectSearch.oninput();assert.equal(elements.projectGrid.children.length,0);assert.equal(elements.homeMessage.hidden,false);elements.projectSearch.value='';elements.projectSearch.oninput();
 await projectCard('Zeta').children[0].onclick();await elements.homeProjects.onclick();assert.equal(get('homeFolder'),clientes);assert.equal(elements.projectGrid.children.length,1);
 elements.renameFolder.onclick();elements.folderName.value='Clientes · Sesiones';listError=true;await submitFolder();doc.activeElement=null;assert.equal(elements.folderDialog.open,false);assert.match(elements.toast.textContent,/se guardó/);assert.equal(elements.homeTitleText.textContent,'Clientes · Sesiones');assert.equal(get('homeFolder'),clientes);listError=false;await elements.refreshHome.onclick();
 await vm.runInContext('saveSession()',context);assert.equal(testSession.homeFolder,clientes);elements.folderBack.onclick();await vm.runInContext('restoreSession()',context);assert.equal(get('homeFolder'),clientes);assert.equal(elements.homeTitleText.textContent,'Clientes · Sesiones');
 // Another window changes the classification revision: reload it without touching the video.
 folderRevision++;await moveProject('Zeta',personal);assert.match(elements.toast.textContent,/biblioteca cambió/);assert.equal(projectCard('Zeta').children[2].children[0].value,clientes);assert.equal(get('state.folderRevision'),folderRevision);assert.equal(get('state.saveError')??null,null);
 await moveProject('Zeta',personal);assert.equal(elements.projectGrid.children.length,0);assert.equal(elements.deleteFolder.disabled,false);await elements.deleteFolder.onclick();assert.equal(get('homeFolder'),null);assert.equal(listedFolders.some(folder=>folder.id===clientes),false);
 folderCard('Personal').onclick();await moveProject('Zeta',null);assert.equal(elements.projectGrid.children.length,0);elements.folderBack.onclick();assert.equal(elements.projectGrid.children.length,2);assert.equal(projectCard('Zeta').children[2].children[0].value,'');
 assert.equal(fs.readFileSync(project,'utf8'),folderVideoBefore);assert.equal(JSON.stringify(get('p')),folderModelBefore);assert.equal(actions.filter(action=>['ops','undo','redo'].includes(action)).length,folderOpsBefore);
 // New-project creation uses the selected folder and waits for the pending save.
 folderCard('Personal').onclick();elements.homeNew.onclick();assert.equal(get('state.newProjectFolder'),personal);elements.newName.value='Sesión nueva';elements.newFps.value='30';
 const creationTransport=context.webkit.messageHandlers.studio.postMessage;context.webkit.messageHandlers.studio.postMessage=payload=>{if(payload.request.action==='create'){context.studioReply(payload.id,{ok:false,cancelled:true,error:'Cancelado'});return;}creationTransport(payload);};
 await elements.createProject.onclick({preventDefault(){}});assert.equal(elements.newDialog.open,true);assert.equal(JSON.stringify(get('p')),folderModelBefore);assert.equal(listedProjects.length,2);context.webkit.messageHandlers.studio.postMessage=creationTransport;
 vm.runInContext('mutationTail=new Promise(resolve=>state.releaseFolderCreate=resolve)',context);const createCount=bridgeRequests.filter(request=>request.action==='create').length;
 const creating=elements.createProject.onclick({preventDefault(){}});await sleep(0);assert.equal(bridgeRequests.filter(request=>request.action==='create').length,createCount);vm.runInContext('state.releaseFolderCreate()',context);await creating;
 assert.equal(elements.newDialog.open,false);assert.equal(get('homeVisible'),false);assert.equal(bridgeRequests.filter(request=>request.action==='create').at(-1).folder,personal);assert.equal(listedProjects.find(item=>item.name==='Sesión nueva').folder,personal);
 elements.newProject.onclick();assert.equal(get('state.newProjectFolder'),null);elements.newDialog.close();await elements.homeProjects.onclick();assert.equal(get('homeFolder'),personal);assert.equal(elements.projectGrid.children.length,1);assert.equal(elements.homeTitleText.textContent,'Personal');assert.equal(fs.readFileSync(project,'utf8'),folderVideoBefore);
 folderFixture=false;listedFolders=[];listedProjects=catalog;testSession=null;doc.activeElement=null;await elements.refreshHome.onclick();assert.equal(get('homeFolder'),null);assert.equal(elements.projectGrid.children.length,2);
 await elements.projectGrid.children[0].children[0].onclick();
 assert.equal(elements.saveState.dataset.state,'saved');
 // Renaming uses the existing history and preserves every media/timeline field.
 const beforeRename=JSON.parse(fs.readFileSync(project)),renameRevision=get('p.revision');
 await elements.renameProject.onclick();assert.equal(elements.folderDialog.open,true);assert.equal(get('syncBlocked()'),true);assert.equal(elements.folderName.value,beforeRename.name);
 elements.folderName.value=' ';await submitFolder();assert.equal(elements.folderError.hidden,false);assert.equal(get('p.revision'),renameRevision);
 elements.folderName.value='Mi consulta renombrada';await submitFolder();doc.activeElement=null;assert.equal(elements.folderDialog.open,false);assert.equal(get('p.name'),'Mi consulta renombrada');assert.equal(elements.projectTitle.textContent,'Mi consulta renombrada');
 const renamed=JSON.parse(fs.readFileSync(project));assert.deepEqual({...renamed,name:beforeRename.name,revision:beforeRename.revision},beforeRename);
 await elements.undo.onclick();assert.equal(get('p.name'),beforeRename.name);catalog[0].revision=get('p.revision');
 await elements.homeProjects.onclick();const libraryRename=elements.projectGrid.children[0].children[1].children.find(el=>el.className==='project-rename');await libraryRename.onclick();assert.equal(elements.folderDialogTitle.textContent,'Renombrar proyecto');
 elements.folderCancel.onclick();doc.activeElement=null;assert.equal(get('p.name'),beforeRename.name);
 await libraryRename.onclick();elements.folderName.value='Nombre desde biblioteca';await submitFolder();doc.activeElement=null;assert.equal(elements.folderDialog.open,false);assert.equal(JSON.parse(fs.readFileSync(project)).name,'Nombre desde biblioteca');
 await elements.projectGrid.children[0].children[0].onclick();await elements.undo.onclick();assert.equal(get('p.name'),beforeRename.name);
 const saveTransport=context.webkit.messageHandlers.studio.postMessage;let releaseSave=null;
 context.webkit.messageHandlers.studio.postMessage=payload=>{const q=payload.request;if(q.action==='ops'&&q.ops?.[0]?.values?.music===percent25){releaseSave=()=>saveTransport(payload);return;}saveTransport(payload);};
 elements.music.value='25';elements.music.oninput({target:elements.music});assert.equal(elements.saveState.dataset.state,'dirty');const saving=elements.music.onchange({target:elements.music});await waitFor(()=>releaseSave!==null);assert.equal(elements.saveState.dataset.state,'saving');
 const leaving=elements.homeProjects.onclick();await sleep(30);assert.equal(elements.editorWorkspace.hidden,false);releaseSave();await Promise.all([saving,leaving]);assert.equal(elements.projectHome.hidden,false);context.webkit.messageHandlers.studio.postMessage=saveTransport;
 assert.equal(JSON.parse(fs.readFileSync(project)).mixer.music,percent25);
 await elements.projectGrid.children[0].children[0].onclick();assert.equal(elements.saveState.dataset.state,'saved');
 await elements.undo.onclick();assert.equal(JSON.parse(fs.readFileSync(project)).mixer.music,0);
 await elements.redo.onclick();assert.equal(JSON.parse(fs.readFileSync(project)).mixer.music,percent25);
 // Faders update the loaded player while dragging, persist on release, and never render.
 await elements.play.onclick();const prepared=actions.filter(x=>x==='preparePlayback').length;
 elements.music.value='0';await elements.music.oninput();
 const musicId=get('p.audio.find(x=>x.role==="music").id');
 assert.equal(bridgeRequests.at(-1).command,'levels');assert.equal(bridgeRequests.at(-1).levels[musicId],0);
 await elements.music.onchange();assert.equal(get('playbackPlaying'),true);assert.equal(get('p.mixer.music'),-60);
 assert.equal(actions.filter(x=>x==='preparePlayback').length,prepared);
 elements.music.value='50';await elements.music.oninput();await elements.music.onchange();
 assert.equal(get('p.mixer.music'),20*Math.log10(.5));assert.equal(get('previewRevision===p.revision'),true);
 vm.runInContext('selection={kind:"audio",id:p.audio.find(x=>x.role==="music").id};drawInspector()',context);
 let clipVolume=elements.selectionFields.children.find(e=>e.className==='volume-control').children[1];
 clipVolume.value='0';await clipVolume.oninput();await clipVolume.onchange();
 assert.equal(get('selected().volumeDb'),-60);assert.equal(bridgeRequests.filter(r=>r.command==='levels').at(-1).levels[musicId],0);
 assert.equal(get('playbackPlaying'),true);
 await elements.play.onclick();await elements.undo.onclick();await elements.undo.onclick();await elements.undo.onclick();
 assert.equal(get('p.mixer.music'),percent25);

 // Duplicate selected items with the real engine; every copy stays editable and undoable.
 vm.runInContext('selection=null;drawTimeline()',context);assert.equal(elements.duplicate.disabled,true);
 await vm.runInContext('ops([{op:"add",kind:"audio",item:{id:"dup-music",asset:"music",role:"music",start:40,length:60,in:70,volumeDb:-18,fadeIn:5,fadeOut:9,linked:false}},{op:"add",kind:"graphics",item:{id:"dup-title",type:"title",start:20,length:30,offset:20,motionLength:80,keepTogether:true,props:{text:"Una copia independiente",enter:.01}}},{op:"add",kind:"captions",item:{id:"dup-word",text:"palabra",start:30,length:30}}])',context);
 for(const [kind,id,start] of [['audio','dup-music',100],['graphics','dup-title',50],['captions','dup-word',60]]){
  vm.runInContext(`selection={kind:${JSON.stringify(kind)},id:${JSON.stringify(id)}};draw()`,context);assert.equal(elements.duplicate.disabled,false);
  const source=JSON.stringify(get('selected()')),count=get(`p.${kind}.length`),duration=get('frames()');
  await Promise.all([elements.duplicate.onclick(),elements.duplicate.onclick()]);
  assert.equal(get(`p.${kind}.length`),count+1);assert.notEqual(get('selection.id'),id);assert.equal(get('selected().start'),start);assert.equal(get('selected().length'),JSON.parse(source).length);
  assert.equal(JSON.stringify(get(`p.${kind}.find(x=>x.id===${JSON.stringify(id)})`)),source);assert.equal(get('frames()'),duration);
  await elements.undo.onclick();assert.equal(get(`p.${kind}.length`),count);
 }
 // Blur/save happens before reading the properties to duplicate.
 vm.runInContext('selection={kind:"audio",id:"dup-music"};draw()',context);
 const duplicateField=new El('input');duplicateField.onchange=()=>vm.runInContext('ops([{op:"set",kind:"audio",id:"dup-music",values:{volumeDb:-17}}])',context);duplicateField.focus();
 await elements.duplicate.onclick();assert.equal(get('selected().volumeDb'),-17);assert.equal(get('p.audio.find(a=>a.id==="dup-music").volumeDb'),-17);
 await elements.undo.onclick();await elements.undo.onclick();
 // A full-length item opens placement, never creates an invisible copy beyond the end.
 vm.runInContext('selection={kind:"audio",id:"music-clip"};cursor=400;draw()',context);
 const beforePlacement=fs.readFileSync(project,'utf8');await elements.duplicate.onclick();assert.equal(elements.duplicateDialog.open,true);
 assert.equal(fs.readFileSync(project,'utf8'),beforePlacement);assert.match(elements.duplicateSummary.textContent,/Se copiarán/);assert.match(elements.duplicateSummary.textContent,/superpone/);
 assert.equal(context.studioPaste(),false);assert.equal(context.studioLinkAll(),false);assert.equal(context.studioMarkRange(),false);assert.equal(await vm.runInContext('applyEditorUpdate()',context),false);
 const playsBeforeDuplicate=actions.length;await elements.play.onclick();assert.equal(actions.length,playsBeforeDuplicate);
 for(const invalid of ['', 'NaN', '-1', '2x', '99999']){elements.duplicateStart.value=invalid;elements.duplicateStart.oninput();assert.equal(elements.duplicateApply.disabled,true);}
 elements.duplicateCancel.onclick();assert.equal(elements.duplicateDialog.open,false);assert.equal(fs.readFileSync(project,'utf8'),beforePlacement);
 await elements.duplicate.onclick();elements.duplicateStart.value=(400/get('p.fps')).toFixed(3).replace('.',',');elements.duplicateStart.oninput();assert.equal(elements.duplicateApply.disabled,false);
 await elements.duplicateForm.onsubmit({preventDefault(){}});assert.equal(elements.duplicateDialog.open,false);assert.equal(get('selected().start'),400);assert.equal(get('selected().length'),110);assert.equal(get('p.audio.find(a=>a.id==="music-clip").length'),510);
 await elements.undo.onclick();await elements.undo.onclick(); // Remove the isolated fixture.
 vm.runInContext('selection={kind:"clips",id:p.clips[0].id};draw()',context);
 const videoBeforeCopy=get('frames()');await elements.duplicate.onclick();assert.equal(get('frames()'),videoBeforeCopy*2);assert.equal(get('p.clips.length'),2);assert.equal(get('selection.id'),get('p.clips[1].id'));assert.equal(get('cursor'),videoBeforeCopy);
 await elements.undo.onclick();assert.equal(get('frames()'),videoBeforeCopy);

 await sleep(400);const preparationsBeforeEdit=actions.filter(x=>x==='preparePlayback').length;
 await vm.runInContext('addGraphic("title")',context);assert.equal(JSON.parse(fs.readFileSync(project)).graphics.length,2);
 await sleep(800);assert.equal(actions.filter(x=>x==='preparePlayback').length,preparationsBeforeEdit);
 await elements.delete.onclick();assert.equal(JSON.parse(fs.readFileSync(project)).graphics.length,1);
 // Track joins are discoverable, undoable, and don't group independent words.
 assert.equal(elements['join-video'].disabled,true);assert.equal(elements['join-captions'].disabled,true);
 await vm.runInContext('ops([{op:"add",kind:"graphics",item:{id:"hook-join",type:"title",start:0,length:510,offset:20,motionLength:600,props:{text:"Gancho continuo",enter:.01}}}])',context);
 await vm.runInContext('ops([{op:"splitAt",frame:120}])',context);
 assert.equal(elements['join-video'].disabled,false);assert.equal(elements['join-graphics'].disabled,false);
 const joinVideoBefore=JSON.stringify(get('p.clips')),joinCaptionBefore=JSON.stringify(get('p.captions'));
 await elements['join-graphics'].onclick();
 assert.equal(get('p.graphics.filter(g=>g.props?.text==="Gancho continuo").length'),1);assert.equal(get('p.graphics.find(g=>g.id==="hook-join").keepTogether'),true);
 assert.equal(JSON.stringify(get('p.clips')),joinVideoBefore);assert.equal(JSON.stringify(get('p.captions')),joinCaptionBefore);assert.equal(elements['join-graphics'].disabled,true);
 await vm.runInContext('undo()',context);assert.equal(elements['join-graphics'].disabled,false);
 await vm.runInContext('undo();',context);await vm.runInContext('undo();',context);
 await vm.runInContext('selection={kind:"clips",id:p.clips[0].id};cursor=120;split()',context);
 assert.equal(JSON.parse(fs.readFileSync(project)).clips.length,2);
 await vm.runInContext('undo()',context);assert.equal(JSON.parse(fs.readFileSync(project)).clips.length,1);
 await vm.runInContext('Promise.all([undo(),ops([{op:"mixer",values:{music:-6}}]),ops([{op:"mixer",values:{sfx:-3}}])])',context);
 assert.equal(JSON.parse(fs.readFileSync(project)).mixer.music,-6);assert.equal(JSON.parse(fs.readFileSync(project)).mixer.sfx,-3);
 await sleep(500);assert.deepEqual(failures,[]);
 await vm.runInContext('cursor=0;seek(1)',context);
 assert.equal(get('cursor'),1);
 vm.runInContext('previewRevision=-1',context);
 const handler=context.webkit.messageHandlers.studio.postMessage;
 context.webkit.messageHandlers.studio.postMessage=({id,request})=>{
  if(request.action==='analyze'){context.studioReply(id,{ok:true,result:{revision:get('p.revision'),candidates:[{start:120,end:150}]}});return;}
  handler({id,request});
 };
 await vm.runInContext('analyze()',context);
 const staleCut=elements.analysisItems.children[0].children[2];
 await vm.runInContext('ops([{op:"cutRange",start:0,end:30}])',context);
 assert.equal(elements.analysis.hidden,true);
 const before=fs.readFileSync(project,'utf8');await staleCut.onclick();assert.equal(fs.readFileSync(project,'utf8'),before);
 await vm.runInContext('analyze()',context);
 const queuedCut=elements.analysisItems.children[0].children[2];
 const framesBefore=get('frames()');
 const pendingEdit=vm.runInContext('ops([{op:"cutRange",start:0,end:30}])',context);
 await Promise.all([pendingEdit,queuedCut.onclick()]);
 assert.equal(get('frames()'),framesBefore-30);
 await vm.runInContext('importMedia("pasteImage")',context);
 assert.equal(get('selected().type'),'image');assert.equal(get('selected().props.sound'),true);
 const imageId=get('selected().id');
 await vm.runInContext('imageBox.onpointerdown({button:0,preventDefault(){},stopPropagation(){},clientX:100,clientY:100,pointerId:1,target:{dataset:{}}});imageBox.onpointermove({clientX:220,clientY:160});imageBox.onpointerup()',context);
 assert.equal(get('selected().props.x'),1152);assert.equal(get('selected().props.y'),636);
 await vm.runInContext('openImageCrop(selected());cropState.left=.2;cropState.right=.9',context);
 await elements.cropApply.onclick();assert.equal(get('selected().props.cropLeft'),.2);
 const animationGrid=elements.selectionFields.children.find(e=>e.className==='animation-grid');
 await animationGrid.children[4].onclick();assert.equal(get('selected().props.animation'),'from-bottom');
 const durationField=elements.selectionFields.children.find(e=>e.textContent==='Duración · segundos').children[0],typedLength=get('selected().length')+6;durationField.value=String(typedLength/get('p.fps'));doc.activeElement=durationField;durationField.oninput();assert.equal(elements.saveState.dataset.state,'dirty');await vm.runInContext('flushEdits()',context);
 assert.equal(get('selected().length'),typedLength);assert.equal(JSON.parse(fs.readFileSync(project)).graphics.find(g=>g.id===imageId).length,typedLength);assert.equal(elements.saveState.dataset.state,'saved');
 const imageFrames=get('frames()'),imageLength=get('selected().length');vm.runInContext('drawTimeline()',context);
 let imageClip=tracks.graphics.children.find(e=>e.tagName==='BUTTON'&&e.className.includes('selected')),imageEnd=imageClip.children.find(e=>e.className==='clip-edge end');assert.ok(imageEnd);
 imageEnd.onpointerdown({button:0,clientX:100,pointerId:2,preventDefault(){},stopPropagation(){}});imageEnd.onpointermove({clientX:100-10*get('timelineWidth()')/imageFrames});await imageEnd.onpointerup();
 assert.equal(get('selected().length'),imageLength-10);assert.equal(get('frames()'),imageFrames);
 vm.runInContext('drawTimeline()',context);imageClip=tracks.graphics.children.find(e=>e.tagName==='BUTTON'&&e.className.includes('selected'));imageEnd=imageClip.children.find(e=>e.className==='clip-edge end');
 imageEnd.onpointerdown({button:0,clientX:100,pointerId:3,preventDefault(){},stopPropagation(){}});imageEnd.onpointermove({clientX:100+10*get('timelineWidth()')/imageFrames});await imageEnd.onpointerup();
 assert.equal(get('selected().length'),imageLength);assert.equal(get('frames()'),imageFrames);
 doc.activeElement={tagName:'TEXTAREA'};assert.equal(context.studioPaste(),false);doc.activeElement=null;
 await elements.importSfx.onclick();assert.equal(get('selected().role'),'sfx');
 const beforeMusicCount=get('p.audio.length');await elements.importMusic.onclick();assert.equal(get('selected().role'),'music');assert.equal(get('p.audio.length'),beforeMusicCount+1);assert.equal(bridgeRequests.some(r=>r.action==='chooseMusic'),true);
 const beforeAudioCancel=fs.readFileSync(project,'utf8');cancelAudio=true;await elements.importMusic.onclick();assert.equal(fs.readFileSync(project,'utf8'),beforeAudioCancel);assert.equal(get('state.saveStatus'),'saved');await elements.undo.onclick();assert.equal(get('p.audio.length'),beforeMusicCount);

 // El visor mueve cualquier gráfico anclado en x/y, no solo imágenes.
 await vm.runInContext('addGraphic("stat")',context);
 vm.runInContext('cursor=selected().start;drawImageSelection()',context);
 assert.equal(get('imageBox.hidden'),false);assert.equal(get('imageHandle.hidden'),true);
 await vm.runInContext('imageBox.onpointerdown({button:0,preventDefault(){},stopPropagation(){},clientX:100,clientY:100,pointerId:4,target:{dataset:{resize:"true"}}});imageBox.onpointermove({clientX:220,clientY:160});imageBox.onpointerup()',context);
 assert.equal(get('selected().props.x'),1152);assert.equal(get('selected().props.y'),636);
 await vm.runInContext('addGraphic("channel_intro")',context);vm.runInContext('cursor=selected().start;drawImageSelection()',context);
 assert.equal(get('imageBox.hidden'),true);

 assert.deepEqual(failures,[]);

 const key=async(name,extra={})=>{for(const fn of listeners.keydown)await fn({key:name,code:name,target:{tagName:'DIV'},preventDefault(){},...extra});};
 vm.runInContext('selection={kind:"audio",id:p.audio.find(a=>a.role==="music").id};drawInspector()',context);
 await elements.selectionFields.children.find(e=>e.className.includes('link-item')).onclick();
 assert.equal(get('isLinked("audio",selected())'),false);
 const musicBefore=get('JSON.stringify(p.audio.filter(a=>a.role==="music"))');
 const originalCount=get('p.audio.filter(a=>a.role==="voice").length');
 vm.runInContext('selection={kind:"clips",id:p.clips[0].id};cursor=120',context);await elements.split.onclick();
 assert.equal(get('p.audio.filter(a=>a.role==="voice").length'),originalCount+1);assert.equal(get('selectedCutGroup().end'),120);
 assert.equal(get('JSON.stringify(p.audio.filter(a=>a.role==="music"))'),musicBefore);
 vm.runInContext('cursor=150',context);await elements.split.onclick();
 assert.equal(get('selectedCutGroup().start'),120);assert.equal(get('selectedCutGroup().end'),150);assert.equal(elements.delete.textContent,'Quitar tramo unido');
 const linkedGroupBefore=get('frames()');await elements.delete.onclick();assert.equal(get('frames()'),linkedGroupBefore-30);
 await elements.undo.onclick();assert.equal(get('frames()'),linkedGroupBefore);
 vm.runInContext('cursor=90',context);await key('i');vm.runInContext('cursor=149',context);await key('o');
 assert.equal(get('validRange()'),true);assert.equal(elements.cutRange.disabled,false);
 const groupBefore=get('frames()');await elements.cutRange.onclick();assert.equal(get('frames()'),groupBefore-60);
 assert.equal(get('JSON.stringify(p.audio.filter(a=>a.role==="music"))'),musicBefore);assert.equal(get('validRange()'),false);
 await elements.undo.onclick();assert.equal(get('frames()'),groupBefore);
 const linkRevision=get('p.revision');assert.equal(context.studioLinkAll(),true);await waitFor(()=>get('p.revision')>linkRevision);assert.equal(get('p.audio.every(a=>isLinked("audio",a))'),true);
 assert.equal(get('p.graphics.every(g=>isLinked("graphics",g))'),true);
 const revision=get('p.revision');doc.activeElement={tagName:'INPUT'};assert.equal(context.studioLinkAll(),false);assert.equal(get('p.revision'),revision);doc.activeElement=null;
 vm.runInContext('clearCutRange();timelineFocused=true;cursor=20',context);assert.equal(context.studioMarkRange(),true);assert.equal(get('cutStart'),20);assert.equal(get('cutEnd'),null);
 vm.runInContext('cursor=44',context);assert.equal(context.studioMarkRange(),true);assert.equal(get('cutStart'),20);assert.equal(get('cutEnd'),45);assert.equal(get('validRange()'),true);
 doc.activeElement={tagName:'TEXTAREA'};assert.equal(context.studioMarkRange(),false);doc.activeElement=null;vm.runInContext('clearCutRange();drawTimeline()',context);
 const resizeBefore=get('frames()');await vm.runInContext('ops([{op:"cutRange",start:30,end:60}])',context);const cutFrames=get('frames()');assert.equal(cutFrames,resizeBefore-30);
 vm.runInContext('selection={kind:"clips",id:p.clips[0].id};drawTimeline()',context);const firstVideo=tracks.video.children.find(e=>e.tagName==='BUTTON');const endHandle=firstVideo.children.find(e=>e.className==='clip-edge end');assert.ok(endHandle);
 endHandle.onpointerdown({button:0,clientX:100,pointerId:1,preventDefault(){},stopPropagation(){}});endHandle.onpointermove({clientX:100+10*get('timelineWidth()')/cutFrames});assert.equal(elements.edgePreview.hidden,false);await endHandle.onpointerup();
 assert.equal(get('frames()'),resizeBefore-20);assert.equal(get('p.clips[0].length'),40);assert.equal(get('p.audio.find(a=>a.role==="voice").length'),40);assert.equal(elements.edgePreview.hidden,true);
 await elements.undo.onclick();await elements.undo.onclick();assert.equal(get('frames()'),resizeBefore);
 await elements.zoomIn.onclick();assert.equal(get('zoom'),1.5);assert.ok(Number.isFinite(elements.timelineScroll.scrollLeft));
 assert.ok(parseFloat(elements.timelineContent.style.width)>elements.timelineScroll.clientWidth);
 await key('-');assert.equal(get('zoom'),1);await elements.zoomFit.onclick();assert.equal(elements.timelineScroll.scrollLeft,0);
 elements.ruler.onpointerdown({button:0,clientX:240,pointerId:1,preventDefault(){}});elements.ruler.onpointermove({clientX:480});await elements.ruler.onpointerup({});
 assert.equal(get('validRange()'),true);assert.equal(get('cutStart'),Math.floor(groupBefore*.2));
 const stableFrames=get('frames()');await Promise.all([vm.runInContext('ops([{op:"mixer",values:{sfx:-2}}])',context),elements.cutRange.onclick()]);
 assert.equal(get('frames()'),stableFrames);assert.match(elements.toast.textContent,/proyecto cambió/);
 await key('Escape');assert.equal(get('validRange()'),false);
 elements.newDialog.open=true;assert.equal(context.studioPaste(),false);elements.newDialog.open=false;
 assert.ok(tracks.sfx.children.filter(e=>e.tagName==='BUTTON').some(e=>parseFloat(e.style.top)>4));
 assert.deepEqual(failures,[]);

 await sleep(500);
 // Concurrent edits use the real engine and preserve the review session.
 const remote=ops=>JSON.parse(cp.execFileSync(python,[engine,'--request',JSON.stringify({action:'ops',project,revision:JSON.parse(fs.readFileSync(project)).revision,ops})],{encoding:'utf8'})).result;
 vm.runInContext('selection={kind:"audio",id:p.audio[0].id};cursor=200;zoom=4;draw();',context);elements.timelineScroll.scrollLeft=333;
 const beforeSync=get('p.revision');
 remote([{op:'set',kind:'audio',id:get('p.audio[0].id'),values:{fadeOut:10}}]);
 await vm.runInContext('ops([{op:"mixer",values:{sfx:-7}}])',context);
 assert.equal(get('p.revision'),beforeSync+2);assert.equal(get('p.audio[0].fadeOut'),10);assert.equal(get('p.mixer.sfx'),-7);assert.equal(get('cursor'),200);
 const syncSelection=get('selection.id'),oldVoice=get('p.mixer.voice');remote([{op:'mixer',values:{voice:-4}}]);
 doc.activeElement={tagName:'INPUT'};await vm.runInContext('syncExternal()',context);assert.equal(get('p.mixer.voice'),oldVoice);doc.activeElement=null;
 await vm.runInContext('syncExternal()',context);assert.equal(get('p.mixer.voice'),-4);assert.equal(get('cursor'),200);assert.equal(get('zoom'),4);assert.equal(elements.timelineScroll.scrollLeft,333);assert.equal(get('selection.id'),syncSelection);
 remote([{op:'cutRange',start:10,end:20}]);await vm.runInContext('syncExternal()',context);assert.equal(get('cursor'),190);
 await elements.play.onclick();remote([{op:'mixer',values:{voice:-60}}]);await vm.runInContext('syncExternal()',context);assert.equal(get('playbackPlaying'),true);assert.equal(get('p.mixer.voice'),-60);assert.equal(bridgeRequests.filter(r=>r.command==='levels').at(-1).levels[get('p.audio.find(a=>a.role==="voice").id')],0);
 const playingRevision=get('p.revision');remote([{op:'set',kind:'clips',id:get('p.clips[0].id'),values:{zoom:1.1}}]);await vm.runInContext('syncExternal()',context);assert.equal(get('p.revision'),playingRevision);assert.equal(get('playbackPlaying'),true);assert.match(elements.syncMessage.textContent,/pausar/);
 await elements.play.onclick();assert.equal(get('p.revision'),playingRevision+1);assert.equal(get('playbackPlaying'),false);assert.equal(get('cursor'),190);
 await elements.play.onclick();remote([{op:'set',kind:'clips',id:get('p.clips[0].id'),values:{zoom:1.2}}]);
 await vm.runInContext('ops([{op:"mixer",values:{voice:-5}}],{audioOnly:true})',context);assert.equal(get('playbackPlaying'),false);assert.equal(get('previewRevision'),-1);assert.equal(get('p.clips[0].zoom'),1.2);
 remote([{op:'mixer',values:{music:-20}}]);
 await assert.rejects(vm.runInContext('ops([{op:"mixer",values:{music:-30}}])',context),/mismo elemento/);assert.equal(get('!!state.conflict'),true);assert.equal(elements.syncConflict.hidden,false);assert.equal(JSON.parse(fs.readFileSync(project)).mixer.music,-20);failures.pop();
 await elements.resolveSync.onclick();assert.equal(get('p.mixer.music'),-20);assert.equal(get('state.saveError'),null);assert.equal(get('cursor'),190);
 await vm.runInContext('setPlaybackRate(1.75)',context);await vm.runInContext('saveSession()',context);assert.equal(testSession.playbackRate,1.75);await elements.homeProjects.onclick();assert.equal(get('homeVisible'),true);await elements.speed1.onclick();assert.equal(get('playbackRate'),1);await vm.runInContext('restoreSession()',context);assert.equal(get('homeVisible'),false);assert.equal(get('cursor'),190);assert.equal(get('zoom'),4);assert.equal(elements.timelineScroll.scrollLeft,333);assert.equal(elements.projects.value,project);assert.equal(get('state.booting'),false);assert.equal(get('playbackRate'),1.75);assert.equal(elements.playbackRate.value,'1,75');
 delete testSession.playbackRate;await vm.runInContext('restoreSession()',context);assert.equal(get('playbackRate'),1);
 testSession.playbackRate=3;await vm.runInContext('restoreSession()',context);assert.equal(get('playbackRate'),1);
 context.studioRequestUpdate('interface');assert.equal(elements.updateEditor.hidden,false);vm.runInContext('setSaveState("dirty")',context);assert.equal(await vm.runInContext('applyEditorUpdate()',context),false);vm.runInContext('setSaveState("saved");state.updateAvailable=null',context);
 assert.deepEqual(failures,[]);
 // Feedback: real SQLite, capture, annotation, shortcut and autosave guards.
 const videoBeforeFeedback=fs.readFileSync(project,'utf8');doc.activeElement=null;
 await elements.play.onclick();const reviewedFrame=get('cursor')+1;
 assert.equal(context.studioFeedback(),true);await waitFor(()=>get('feedback.note')&&get('feedback.capturing'));await get('feedback.capturing');assert.equal(get('feedback.note.capture'),'ready');assert.equal(get('playbackPlaying'),false);assert.equal(get('feedback.note.frame'),reviewedFrame);assert.equal(elements.feedbackDialog.open,true);
 elements.feedbackText.value='Cambiar el título por Más clientes';elements.feedbackText.oninput();
 elements.feedbackEllipse.onclick();elements.feedbackDrawing.onpointerdown({button:0,clientX:120,clientY:67.5,pointerId:88,preventDefault(){}});elements.feedbackDrawing.onpointermove({clientX:840,clientY:472.5});elements.feedbackDrawing.onpointerup();
 assert.equal(get('feedback.strokes[0].tool'),'ellipse');assert.deepEqual(JSON.parse(get('JSON.stringify(feedback.strokes[0].points)')),[[.1,.1],[.7,.7]]);assert.match(elements.feedbackDrawing.innerHTML,/<ellipse/);
 const untouchedRevision=get('p.revision');doc.activeElement=null;await key('b');await key('Space',{code:'Space'});assert.equal(get('p.revision'),untouchedRevision);assert.equal(get('playbackPlaying'),false);
 elements.feedbackArrow.onclick();elements.feedbackDrawing.onpointerdown({button:0,clientX:200,clientY:200,pointerId:89,preventDefault(){}});elements.feedbackDrawing.onpointermove({clientX:500,clientY:300});elements.feedbackDrawing.onpointerup();await key('z',{metaKey:true});assert.equal(get('feedback.strokes.length'),1);assert.equal(get('p.revision'),untouchedRevision);
 await vm.runInContext('flushFeedback()',context);const feedbackId=get('feedback.note.id');
 assert.equal(get('feedback.note.text'),'Cambiar el título por Más clientes');assert.ok(fs.existsSync(get('feedback.note.files.annotated')));assert.equal(fs.readFileSync(project,'utf8'),videoBeforeFeedback);
 await elements.feedbackPublish.onclick();await waitFor(()=>!get('feedback.polling'));await vm.runInContext('refreshFeedback(true)',context);assert.equal(elements.feedbackDialog.open,false);assert.equal(get('feedback.notes.filter(n=>n.status==="open").length'),1);assert.equal(elements.feedbackTrack.children.length,1);
 await vm.runInContext(`openFeedback(${JSON.stringify(feedbackId)})`,context);assert.equal(elements.feedbackText.value,'Cambiar el título por Más clientes');assert.equal(get('feedback.strokes.length'),1);
 await elements.feedbackResolve.onclick();await waitFor(()=>!get('feedback.polling'));await vm.runInContext('refreshFeedback(true)',context);assert.equal(get('feedback.notes[0].status'),'resolved');assert.equal(elements.feedbackCount.textContent,0);
 await vm.runInContext(`openFeedback(${JSON.stringify(feedbackId)})`,context);await elements.feedbackResolve.onclick();await waitFor(()=>!get('feedback.polling'));await vm.runInContext('refreshFeedback(true)',context);assert.equal(get('feedback.notes[0].status'),'open');
 await vm.runInContext('openFeedback()',context);await get('feedback.capturing');elements.feedbackText.value='Borrador recuperable';elements.feedbackText.oninput();await vm.runInContext('flushFeedback();',context);const draftId=get('feedback.note.id');
 await vm.runInContext('saveSession()',context);assert.equal(testSession.feedbackId,draftId);assert.equal(await vm.runInContext('applyEditorUpdate()',context),false);
 elements.feedbackDialog.close();await vm.runInContext('restoreSession()',context);assert.equal(elements.feedbackDialog.open,true);assert.equal(elements.feedbackText.value,'Borrador recuperable');
 const feedbackTransport=context.webkit.messageHandlers.studio.postMessage;let failFeedback=true;
 context.webkit.messageHandlers.studio.postMessage=payload=>{if(payload.request.action==='feedback'&&payload.request.command==='update'&&failFeedback){failFeedback=false;context.studioReply(payload.id,{ok:false,error:'test feedback write failure'});return;}feedbackTransport(payload);};
 elements.feedbackText.value='No perder este cambio';elements.feedbackText.oninput();await assert.rejects(vm.runInContext('flushFeedback()',context),/test feedback write failure/);assert.equal(elements.feedbackDialog.open,true);assert.equal(elements.feedbackText.value,'No perder este cambio');
 context.webkit.messageHandlers.studio.postMessage=feedbackTransport;await vm.runInContext('flushFeedback()',context);await vm.runInContext('closeFeedback()',context);await vm.runInContext(`openFeedback(${JSON.stringify(draftId)})`,context);assert.equal(elements.feedbackText.value,'No perder este cambio');
 // Another reviewer resolves the same note: do not lose the local draft or silently overwrite.
 const remoteNote=JSON.parse(cp.execFileSync(python,[engine,'--request',JSON.stringify({action:'feedback',command:'get',project,id:draftId})],{encoding:'utf8'})).result;
 const otherWrite=JSON.parse(cp.execFileSync(python,[engine,'--request',JSON.stringify({action:'feedback',command:'update',project,id:draftId,version:remoteNote.version,values:{text:'Cambio de otra sesión'}})],{encoding:'utf8'}));assert.equal(otherWrite.ok,true);
 elements.feedbackText.value='Mi borrador no guardado';elements.feedbackText.oninput();await assert.rejects(vm.runInContext('flushFeedback()',context),/otra sesión/);failures.pop();assert.equal(elements.feedbackReload.hidden,false);assert.equal(elements.feedbackText.value,'Mi borrador no guardado');
 await elements.feedbackReload.onclick();assert.equal(elements.feedbackText.value,'Cambio de otra sesión');assert.equal(get('feedback.error'),null);
 await elements.feedbackDelete.onclick();assert.equal(elements.feedbackDialog.open,false);assert.equal(fs.readFileSync(project,'utf8'),videoBeforeFeedback);doc.activeElement=null;
 assert.deepEqual(failures,[]);
 // Video overlays use their own lane, geometry, media clock, volume, replacement and promotion.
 await vm.runInContext('seek(0)',context);const overlayBaseCount=get('p.graphics.length'),overlayBaseFrames=get('frames()');
 await elements.importOverlay.onclick();assert.equal(get('selected().type'),'video');assert.equal(get('selected().muted'),true);assert.equal(get('frames()'),overlayBaseFrames);
 assert.equal(get('trackItems("overlays","graphics").length'),1);assert.equal(get('selectedCutGroup()'),null);assert.equal(elements.selectedBadge.textContent,'Superposición');
 assert.equal(get('imageHandle.hidden'),false);const overlayId=get('selected().id');
 const overlayField=label=>elements.selectionFields.children.find(e=>e.textContent===label).children[0];
 const overlayOpacity=overlayField('Opacidad · %');overlayOpacity.value=50;await overlayOpacity.onchange();assert.equal(get('selected().props.opacity'),.5);
 const overlayDuration=overlayField('Duración · segundos');overlayDuration.value=1;await overlayDuration.onchange();assert.equal(get('selected().length'),Math.round(get('p.fps')));
 const overlaySource=overlayField('Desde el original · segundos');overlaySource.value=.1;await overlaySource.onchange();assert.equal(get('selected().in'),Math.round(.1*get('p.fps')));
 await elements.selectionFields.children.find(e=>e.textContent==='Cambiar vídeo').onclick();assert.equal(get('selected().id'),overlayId);assert.equal(get('selected().in'),0);assert.equal(get('selected().props.opacity'),.5);
 await elements.duplicate.onclick();assert.equal(get('selected().type'),'video');assert.notEqual(get('selected().id'),overlayId);const promotedId=get('selected().id'),overlayTotal=get('frames()');
 await elements.selectionFields.children.find(e=>e.textContent==='Pasar a principal').onclick();assert.equal(get('selection.kind'),'clips');assert.equal(get('selected().id'),promotedId);assert.equal(get('frames()'),overlayTotal);
 await elements.undo.onclick();assert.equal(get('p.graphics.some(g=>g.id==='+JSON.stringify(promotedId)+')'),true);assert.equal(get('frames()'),overlayTotal);
 for(let i=0;i<6;i++)await elements.undo.onclick();assert.equal(get('p.graphics.length'),overlayBaseCount);assert.equal(get('frames()'),overlayBaseFrames);assert.deepEqual(failures,[]);
 const normalTransport=context.webkit.messageHandlers.studio.postMessage;let delayedPlan=null;let nativeLoads=0;
 context.webkit.messageHandlers.studio.postMessage=({id,request})=>{
  if(request.action==='preparePlayback'){delayedPlan=id;return;}
  if(request.action==='loadPlayback')nativeLoads++;
  normalTransport({id,request});
 };
 vm.runInContext('invalidatePlayback()',context);
 const interruptedPlayback=vm.runInContext('togglePlay()',context);await waitFor(()=>delayedPlan!==null);
 await vm.runInContext('openFeedback()',context);context.studioReply(delayedPlan,{ok:true,result:{key:'late-feedback',seconds:1}});await interruptedPlayback;
 assert.equal(nativeLoads,0);assert.equal(get('playbackPlaying'),false);assert.equal(elements.feedbackDialog.open,true);await get('feedback.capturing');await vm.runInContext('closeFeedback()',context);doc.activeElement=null;delayedPlan=null;
 const pendingPlayback=vm.runInContext('togglePlay()',context);await waitFor(()=>delayedPlan!==null);
 assert.equal(get('busy'),false);assert.match(elements.previewBadge.textContent,/Preparando/);await elements.homeProjects.onclick();assert.equal(get('busy'),false);
 context.studioReply(delayedPlan,{ok:true,result:{key:'stale',seconds:1}});await pendingPlayback;
 assert.equal(nativeLoads,0);assert.equal(get('playbackPlaying'),false);
 context.webkit.messageHandlers.studio.postMessage=normalTransport;
 await elements.projectGrid.children[0].children[0].onclick();
 await sleep(500);
 const requests=[];context.webkit.messageHandlers.studio.postMessage=({id,request})=>{if(request.action==='frame')requests.push({id,request});};
 vm.runInContext('p.revision=42;previewRevision=-1;path="/private/tmp/one.studio"',context);
 await vm.runInContext('seek(0)',context);await sleep(150);
 vm.runInContext('path="/private/tmp/two.studio";p={...p,id:"two",revision:42}',context);
 await vm.runInContext('seek(0)',context);await sleep(150);
 context.studioReply(requests[1].id,{ok:true,result:{path:'/private/tmp/two.jpg',revision:42,frame:0}});await sleep(0);
 context.studioReply(requests[0].id,{ok:true,result:{path:'/private/tmp/one.jpg',revision:42,frame:0}});await sleep(0);
 assert.equal(elements.still.src,'file:///private/tmp/two.jpg');
 let quitAllowed=null;context.webkit.messageHandlers.studio.postMessage=({id,request})=>{if(request.action==='sessionSave'){context.studioReply(id,{ok:true,result:{}});}if(request.action==='quitReady'){quitAllowed=request.allow;context.studioReply(id,{ok:true,result:{}});}};vm.runInContext('state.saveError=null;mutationTail=new Promise(resolve=>state.releaseQuitSave=resolve)',context);assert.equal(context.studioPrepareToQuit(),true);await sleep(30);assert.equal(quitAllowed,null);vm.runInContext('state.releaseQuitSave()',context);await waitFor(()=>quitAllowed!==null);assert.equal(quitAllowed,true);
 console.log(JSON.stringify({passed:true,engineCalls:calls,checks:['video overlay import and dedicated lane','video overlay selection never deletes underlying group','video overlay opacity duration and source trim','video overlay replacement retains identity and geometry','video overlay duplication promotion and undo','legacy native app hides unavailable review speed','self-contained synthetic media','review rate comma and dot input','review rate rejects invalid and out-of-range values','review rate Enter and Escape','review speed slider and presets','review rate paused without autoplay','review speed changes live without project writes or renders','review rate survives pause and resume','review rate session restore','older and invalid rate sessions default to one','home on launch without creation','isolated folder catalog fixture','folder create rename and cancel','project rename from editor and library','project rename keeps timeline and supports undo','project rename validation and cancellation','folder name and error handling','folder navigation and counts','home search includes folder projects','folder search stays scoped','move projects between folders and root','nonempty folder deletion cancellation','empty folder delete returns home','folder writes wait for close and block updates','folder conflicts refresh without project writes','folder navigation and session preserved','new project uses selected folder after pending save','recent sort','name sort','accent-insensitive search','no search results','card opens editor','home stops video and sound','home blocks image paste','project bytes preserved','empty library','list failure and retry','project open','dirty save state','saving state','project exit waits for save','music fader persisted','saved state restored','undo','redo','edit does not auto-render playback','duplicate selected music text and captions','duplicate independent properties and new selection','double duplicate click creates one copy','duplicate flushes typed changes','duplicate tail placement and explicit shorter duration','placement rejects invalid time and accepts comma','placement cancel leaves project unchanged','placement isolates shortcuts playback and updates','video duplicate repeats linked span and undo','add title','remove title','per-track compatible join button','join preserves other tracks and is undoable','joined static hook stays continuous','frame split','undo split','rapid edits serialized','one-frame playback seek','stale silence rejected','queued stale silence rejected','paste image selected','drag image persisted','visual crop persisted','animation chosen','active image field flushed','typed image duration autosaved','image edge shortens duration','image edge restores duration','image resize preserves video duration','drag motion graphic persisted','motion graphic without resize handle','channel_intro not movable','text paste preserved','quick SFX import','late frame isolated','separate selected music','split linked layers','second split selects middle group','delete linked group from one selection','I/O range','cut range keeps music intact','undo group','native Command J relinks all','shortcut skips text input','Command C range','Command C preserves text copy','drag edge restores source','drag edge restores linked voice','drag edge undo','zoom and fit','ruler drag and Escape','overlapping SFX lanes','stale queued range rejected','new dialog blocks image paste','stale playback plan rejected','playback preparation is non-modal','leaving cancels playback preparation','native quit waits for save','concurrent changes merged','focused field preserved','review anchor survives remote cut','remote volume live','structural sync deferred until pause','conflict explicit without overwrite','session restored','update blocked while dirty','Command F exact native frame','SQLite feedback autosave','annotation raster and UI','feedback shortcuts isolated from cuts','publish marker','resolve and reopen','draft restored on reload','feedback save failure retry','feedback does not mutate video','feedback conflict preserves draft and reloads','late playback blocked by feedback dialog'],scope:'DOM behavior + real CLI. Native host and visual layout are not certified.'}));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>fs.rmSync(work,{recursive:true,force:true}));
