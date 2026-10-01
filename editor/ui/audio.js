'use strict';
const audioRoles={voice:'Voz',music:'Música',sfx:'Efectos'};
function audioGain(db,muted=false){return muted||db<=-60?0:10**(db/20);}
function volumePercent(db,muted=false){const gain=audioGain(db,muted);return gain?Math.max(.1,Math.round(gain*1000)/10):0;}
function percentDb(value){return value<=0?-60:Math.max(-59.999,20*Math.log10(value/100));}
function audioLevels(model=p,draft=null){
 const mix=role=>audioGain(draft?.kind==='mixer'&&draft.role===role?draft.db:model.mixer[role]);
 const levels={};
 for(const kind of ['clips','audio'])for(const item of model[kind]){
  const changed=draft?.kind===kind&&draft.id===item.id;
  levels[item.id]=audioGain(changed?draft.db:(item.volumeDb??0),changed?false:item.muted)*mix(kind==='clips'?'voice':item.role);
 }
 for(const g of model.graphics){const q=g.props||{},changed=draft?.kind==='graphics'&&draft.id===g.id;
  if(g.type==='video'){levels[g.id]=audioGain(changed?draft.db:(g.volumeDb??0),g.hidden||(changed?false:g.muted))*mix('voice');continue;}
  levels[g.id]=audioGain(changed?draft.db:(q.soundDb??-18),g.hidden||!q.sound||q.animation==='none')*mix('sfx');
 }
 return levels;
}
function liveAudioReady(target=null){return playbackKey&&previewRevision===p.revision&&state.nativeAudio&&!p.ducking&&(!target||target.kind==='mixer'||state.audioIds?.has(target.id));}
async function previewAudioVolume(target=null,db=null){
 if(liveAudioReady())await api({action:'playback',command:'levels',key:playbackKey,levels:audioLevels(p,target?{...target,db}:null)});
}
async function setAudioVolume(target,db){
 const resume=playbackPlaying,live=liveAudioReady(target);
 try{
  await ops(()=>target.kind==='mixer'?[{op:'mixer',values:{[target.role]:db}}]:[{op:'set',kind:target.kind,id:target.id,values:target.kind==='graphics'&&p.graphics.find(g=>g.id===target.id)?.type!=='video'?{props:{...p.graphics.find(g=>g.id===target.id).props,soundDb:db}}:{volumeDb:db,muted:false}}],{audioOnly:live});
  if(resume&&!playbackPlaying)await togglePlay();
 }catch(error){await previewAudioVolume();throw error;}
}
function volumeControl(parent,label,target,db,muted=false,disabled=false,id=null){
 const box=elem('div','volume-control'),head=elem('div','volume-heading');
 const name=elem('span',null,label),field=elem('input'),range=elem('input'),unit=elem('span','volume-unit','%');
 const value=volumePercent(db,muted),max=Math.max(100,Math.ceil(value));
 field.type='number';range.type='range';
 for(const input of [field,range]){input.min=0;input.max=max;input.step=.1;input.value=value;input.disabled=disabled;input.setAttribute('aria-label',label+(input===field?' · porcentaje':''));}
 if(id){range.id=id;field.id=id+'Value';}
 head.append(name,field,unit);box.append(head,range,elem('div','volume-scale',disabled?'Sin audio propio':'0 · Silencio                         100 · Original'));parent.append(box);
 const sync=input=>{const value=Number(input.value);if(input.value===''||!Number.isFinite(value))return null;const clamped=Math.min(max,Math.max(0,value));field.value=range.value=clamped;return percentDb(clamped);};
 for(const input of [field,range]){
  input.oninput=safe(async()=>{const db=sync(input);if(db===null)return;setSaveState('dirty');await previewAudioVolume(target,db);});
  input.onchange=safe(async()=>{const db=sync(input);if(db!==null)await setAudioVolume(target,db);});
  input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();input.blur();}};
 }
}
function drawMixer(){
 const box=$('mixerVolumes');box.replaceChildren();
 for(const [role,label] of Object.entries(audioRoles))volumeControl(box,label,{kind:'mixer',role},p.mixer[role],false,false,role);
}
