// Library return behavior against the real desktop module, without a native host or real projects.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();
function node(){return {children:[],value:'',hidden:false,style:{},setAttribute(k,v){this[k]=v},append(...xs){this.children.push(...xs)},replaceChildren(){this.children=[]},pause(){},scrollIntoView(options){this.scrolled=options}};}
const $=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
const catalog=Array.from({length:38},(_,i)=>({id:'id-'+i,path:'/fixture/'+i,name:'Clip '+String(i+1).padStart(2,'0'),revision:0,modified:i,duration:0,folder:'clips',width:160,height:90,fps:30}));
const context={assert,console,Date,Number,Map,Promise,clearTimeout,$,state:{projectFolders:[{id:'clips',name:'Clips'}]},
 path:'/fixture/26',p:{},frameTimer:null,flushEdits:async()=>{},invalidatePlayback(){},setSaveState(){},toast(){},
 refreshProjects:async()=>catalog,elem(tag,cls,text){return Object.assign(node(),{tag,className:cls,textContent:text})},safe:fn=>fn,fileURL:x=>x,restoreSession(){},api:async()=>({})};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/projects.js'),'utf8').replace('void restoreSession();',''),context);
vm.runInContext(`(async()=>{
 homeVisible=false;homeFolder='clips';$('projectSort').value='name';$('projectSearch').value='Clip';
 await showProjects();
 let cards=$('projectGrid').children,last=cards.find(x=>x.className.includes('last-opened'));
 assert.equal(cards.length,38);assert.equal(last.children[0]['aria-label'],'Editar Clip 27');
 assert.equal(last.scrolled.block,'start');assert.equal(last['aria-current'],'true');
 assert.equal(homeFolder,'clips');assert.equal($('projectSearch').value,'Clip');
 $('projectSearch').value='Clip 28';drawProjectGrid();assert.equal($('projectGrid').children.length,1);
 assert.equal($('projectGrid').children[0].scrolled,undefined);
 $('projectSearch').value='';homeVisible=false;path='/fixture/27';await showProjects();
 last=$('projectGrid').children.find(x=>x.className.includes('last-opened'));
 assert.equal(last.children[0]['aria-label'],'Editar Clip 28');assert.equal(last.scrolled.block,'start');
 homeVisible=false;path='/fixture/deleted';await showProjects();
 assert.equal($('projectGrid').children.some(x=>x.scrolled),false);
 console.log('PASS · desktop library: 38 clips, stable target, highlight, search/folder, next project and deleted target');
})().catch(error=>{console.error(error);process.exitCode=1})`,Object.assign(context,{process}));
