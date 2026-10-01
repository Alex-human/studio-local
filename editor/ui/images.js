'use strict';
const imageAnimations=[['pop','▧','Foto · aparición'],['from-left','→','Desde izquierda'],['from-right','←','Desde derecha'],['from-top','↓','Desde arriba'],['from-bottom','↑','Desde abajo'],['none','—','Sin animación']];
// channel_intro ocupa el fotograma entero y el motor ignora su x/y: no es movible.
function movableGraphic(){const g=selected();return selection?.kind==='graphics'&&g&&g.type!=='channel_intro'?g:null;}
function graphicAnchor(g){const q=g.props||{},[dx,dy]=g.type==='lower_third'?[150,880]:[960,540];return {x:q.x??dx,y:q.y??dy};}
function imageRestFrame(item){return item.start+Math.min(item.length-1,Math.max(0,Math.ceil((item.props.enter??.48)*p.fps)-(item.offset||0)));}
function editingText(){return ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)||document.activeElement?.isContentEditable;}
window.studioPaste=()=>{if(homeVisible||editingText()||($('newDialog').open||$('duplicateDialog').open)||($('cropDialog').open||$('feedbackDialog').open)||busy)return false;safe(()=>importMedia('pasteImage'))();return true;};
$('pasteImage').onclick=safe(()=>importMedia('pasteImage'));
function drawImageInspector(box,item,{input,check,set}){
 const props=item.props||{};const prop=(key,value)=>set(current=>({props:{...current.props,[key]:value}}));
 const crop=elem('button','secondary full','✂ Recortar imagen');crop.onclick=()=>openImageCrop(item);box.append(crop);
 box.append(elem('p','muted tiny','Arrastra la imagen en el visor. Usa su esquina para cambiar el tamaño.'));
 input('Tamaño · ancho',Math.round(props.width||760),{min:40,max:3840,step:10},v=>prop('width',v));
 const row=elem('div','row');for(const [style,label] of [['photo','Marco de foto'],['clean','Sin marco']]){const b=elem('button',props.style===style?'chosen':'',label);b.onclick=safe(()=>prop('style',style));row.append(b);}box.append(row);
 input('Giro · grados',props.rotation||0,{min:-180,max:180,step:1},v=>prop('rotation',v));
 box.append(elem('h3',null,'Entrada con sonido'));
 const grid=elem('div','animation-grid');for(const [value,glyph,label] of imageAnimations){const b=elem('button','animation-choice'+((props.animation||'pop')===value?' chosen':''));b.setAttribute('aria-label',label);b.dataset.animation=value;b.append(elem('span','animation-glyph',glyph),elem('small',null,label));b.onclick=safe(()=>prop('animation',value));grid.append(b);}box.append(grid);
 input('Entrada · segundos',props.enter??.48,{min:.12,max:2,step:.05},v=>prop('enter',v));
 check('Sonido sincronizado',props.sound,v=>prop('sound',v));
 if(props.sound&&props.animation!=='none'){
  volumeControl(box,'Volumen del efecto',{kind:'graphics',id:item.id},props.soundDb??-18);
  const listen=elem('button','full','♫ Escuchar entrada');listen.onclick=safe(async()=>{const data=await api({action:'previewSound',project:path,animation:props.animation||'pop',seconds:props.enter||.48});const audio=$('soundPreview');audio.src=fileURL(data.path);audio.volume=Math.min(1,audioGain(props.soundDb??-18)*audioGain(p.mixer.sfx));await audio.play();});box.append(listen);
 }
 box.append(elem('h3',null,'En el vídeo'));
 input('Inicio · segundos',Number((item.start/p.fps).toFixed(3)),{min:0,step:.1},v=>ops([{op:'move',kind:'graphics',id:item.id,start:Math.round(v*p.fps)}]));
 input('Duración · segundos',Number((item.length/p.fps).toFixed(3)),{min:1/p.fps,step:.1},v=>ops([{op:'duration',kind:'graphics',id:item.id,length:Math.max(1,Math.round(v*p.fps))}]));
}
function drawVideoInspector(box,item,{input,check,set}){
 const props=item.props||{},prop=(key,value)=>set(current=>({props:{...current.props,[key]:value}}));
 box.append(elem('p','muted',asset(item.asset)?.name),elem('p','muted tiny','Arrastra el vídeo en el visor y usa su esquina para ajustar el tamaño.'));
 const replace=elem('button','secondary full','Cambiar vídeo');replace.onclick=safe(()=>importMedia('chooseOverlayReplacement',{replaceOverlay:item.id}));box.append(replace);
 check('Ocultar superposición',item.hidden,v=>set({hidden:v}));
 input('Tamaño · ancho',Math.round(props.width??960),{min:40,max:3840,step:10},v=>prop('width',v));
 input('Giro · grados',props.rotation||0,{min:-180,max:180,step:1},v=>prop('rotation',v));
 input('Opacidad · %',Math.round((props.opacity??1)*100),{min:0,max:100,step:1},v=>prop('opacity',v/100));
 for(const [key,label] of [['cropLeft','Recorte izquierdo · %'],['cropRight','Recorte derecho · %'],['cropTop','Recorte superior · %'],['cropBottom','Recorte inferior · %']])input(label,(props[key]||0)*100,{min:0,max:98,step:1},v=>prop(key,v/100));
 box.append(elem('h3',null,'Tramo y sonido'));
 input('Inicio · segundos',Number((item.start/p.fps).toFixed(3)),{min:0,step:.1},v=>ops([{op:'move',kind:'graphics',id:item.id,start:Math.round(v*p.fps)}]));
 input('Desde el original · segundos',Number(((item.in||0)/p.fps).toFixed(3)),{min:0,step:.1},v=>ops([{op:'source',id:item.id,in:Math.round(v*p.fps)}]));
 input('Duración · segundos',Number((item.length/p.fps).toFixed(3)),{min:1/p.fps,step:.1},v=>ops([{op:'duration',kind:'graphics',id:item.id,length:Math.max(1,Math.round(v*p.fps))}]));
 check('Silenciar vídeo',item.muted,v=>set({muted:v}));
 volumeControl(box,'Volumen del vídeo',{kind:'graphics',id:item.id},item.volumeDb??0,item.muted,!asset(item.asset)?.audio);
 const promote=elem('button','secondary full','Pasar a principal');promote.title='Sustituye el vídeo principal en este tramo, a pantalla completa. Se puede deshacer.';
 promote.onclick=safe(async()=>{await flushEdits();await timelineEdit({op:'promoteOverlay',id:item.id});selection={kind:'clips',id:item.id};draw();await seek(item.start);toast('Vídeo colocado en la pista principal. Puedes deshacer con ⌘Z.');});
 box.append(promote,elem('p','muted tiny','Sustituye el vídeo de debajo durante este tramo y lo encuadra a pantalla completa. Conserva los demás elementos.'));
}

function fitImageRect(container,width,height){const b=container.getBoundingClientRect();const scale=Math.min(b.width/width,b.height/height);return {left:(b.width-width*scale)/2,top:(b.height-height*scale)/2,width:width*scale,height:height*scale,scale};}
function imageDimensions(item){const a=asset(item.type==='video'?item.asset:item.props.asset),q=item.props;return {width:a.width*(1-(q.cropLeft||0)-(q.cropRight||0)),height:a.height*(1-(q.cropTop||0)-(q.cropBottom||0))};}
const imageBox=elem('div','image-box');imageBox.id='imageBox';imageBox.hidden=true;imageBox.setAttribute('aria-label','Mover el elemento seleccionado');
const imageHandle=elem('button','image-handle','↘');imageHandle.dataset.resize='true';imageHandle.setAttribute('aria-label','Cambiar tamaño de imagen');imageBox.append(imageHandle);$('viewer').append(imageBox);
let imageDrag=null;
function drawImageSelection(){
 const g=movableGraphic();imageBox.hidden=!g||g.hidden||cursor<g.start||cursor>=g.start+g.length||playbackPlaying;
 if(imageBox.hidden)return;
 const r=fitImageRect($('viewer'),p.width,p.height),sc=r.width/1920,q=g.props||{},a=graphicAnchor(g);
 imageHandle.hidden=!['image','video'].includes(g.type);
 let width=160,height=160;
 if(['image','video'].includes(g.type)){const d=imageDimensions(g),pad=q.style==='clean'?0:24;width=(q.width||760)+pad;height=(q.width||760)*d.height/d.width+pad;}
 Object.assign(imageBox.style,{left:(r.left+a.x*sc-width*sc/2)+'px',top:(r.top+a.y*sc-height*sc/2)+'px',width:width*sc+'px',height:height*sc+'px',transform:`rotate(${q.rotation||0}deg)`});
}
imageBox.onpointerdown=e=>{
 if(e.button!==0)return;e.preventDefault();e.stopPropagation();const item=movableGraphic();if(!item)return;
 imageDrag={id:item.id,path,revision:p.revision,x:e.clientX,y:e.clientY,width:item.props?.width||760,anchor:graphicAnchor(item),scale:fitImageRect($('viewer'),p.width,p.height).width/1920,resize:['image','video'].includes(item.type)&&e.target.dataset.resize==='true'};
 imageBox.setPointerCapture(e.pointerId);
};
imageBox.onpointermove=e=>{
 if(!imageDrag)return;const drag=imageDrag,dx=(e.clientX-drag.x)/drag.scale,dy=(e.clientY-drag.y)/drag.scale;
 const values=drag.resize?{width:Math.min(3840,Math.max(40,drag.width+dx*2))}:{x:Math.min(3840,Math.max(-1920,drag.anchor.x+dx)),y:Math.min(3840,Math.max(-1080,drag.anchor.y+dy))};
 drag.values=values;const item=movableGraphic();if(!item)return;const original=item.props;item.props={...original,...values};drawImageSelection();item.props=original;
};
imageBox.onpointerup=safe(async()=>{const drag=imageDrag;imageDrag=null;if(!drag?.values)return;await ops(()=>{if(path!==drag.path||p.revision!==drag.revision)throw new Error('El elemento cambió mientras lo movías. Repite el gesto.');const item=p.graphics.find(x=>x.id===drag.id);return [{op:'set',kind:'graphics',id:drag.id,values:{props:{...item.props,...drag.values}}}];});});
imageBox.onpointercancel=()=>{imageDrag=null;drawImageSelection();};
if(typeof ResizeObserver!=='undefined')new ResizeObserver(drawImageSelection).observe($('viewer'));
let cropState=null,cropDrag=null;
function openImageCrop(item){const q=item.props;cropState={id:item.id,path,revision:p.revision,left:q.cropLeft||0,top:q.cropTop||0,right:1-(q.cropRight||0),bottom:1-(q.cropBottom||0)};$('cropSource').src=fileURL(asset(q.asset).path);$('cropDialog').showModal();drawCropRect();}
function cropArea(){const img=$('cropSource');return fitImageRect($('cropStage'),img.naturalWidth||1,img.naturalHeight||1);}
function drawCropRect(){if(!cropState)return;const r=cropArea(),q=cropState;Object.assign($('cropRect').style,{left:r.left+q.left*r.width+'px',top:r.top+q.top*r.height+'px',width:(q.right-q.left)*r.width+'px',height:(q.bottom-q.top)*r.height+'px'});}
$('cropSource').onload=drawCropRect;
$('cropRect').onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();cropDrag={x:e.clientX,y:e.clientY,corner:e.target.dataset.corner,q:{...cropState},rect:cropArea()};$('cropRect').setPointerCapture(e.pointerId);};
$('cropRect').onpointermove=e=>{
 if(!cropDrag)return;const d=cropDrag,q=d.q,dx=(e.clientX-d.x)/d.rect.width,dy=(e.clientY-d.y)/d.rect.height,clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
 if(!d.corner){const width=q.right-q.left,height=q.bottom-q.top;cropState.left=clamp(q.left+dx,0,1-width);cropState.top=clamp(q.top+dy,0,1-height);cropState.right=cropState.left+width;cropState.bottom=cropState.top+height;}
 else{if(d.corner.includes('l'))cropState.left=clamp(q.left+dx,0,q.right-.03);if(d.corner.includes('r'))cropState.right=clamp(q.right+dx,q.left+.03,1);if(d.corner.includes('t'))cropState.top=clamp(q.top+dy,0,q.bottom-.03);if(d.corner.includes('b'))cropState.bottom=clamp(q.bottom+dy,q.top+.03,1);}
 drawCropRect();
};
$('cropRect').onpointerup=$('cropRect').onpointercancel=()=>cropDrag=null;
$('cropReset').onclick=()=>{Object.assign(cropState,{left:0,top:0,right:1,bottom:1});drawCropRect();};
$('cropCancel').onclick=()=>$('cropDialog').close();
$('cropApply').onclick=safe(async()=>{const q={...cropState};await ops(()=>{if(path!==q.path||p.revision!==q.revision)throw new Error('La imagen cambió. Abre el recorte de nuevo.');const item=p.graphics.find(x=>x.id===q.id);return [{op:'set',kind:'graphics',id:q.id,values:{props:{...item.props,cropLeft:q.left,cropTop:q.top,cropRight:1-q.right,cropBottom:1-q.bottom}}}];});$('cropDialog').close();});
