import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const html=fs.readFileSync(new URL('../config.html',import.meta.url),'utf8');
for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
const start=html.indexOf('const usagePanel=');
const end=html.indexOf('const summary=',start);
const original=html.slice(start,end);
const dialogStart=original.indexOf('function confirmDocumentDeletion(');
const clickStart=original.indexOf('del.onclick=async',dialogStart);
assert.ok(start>=0&&end>start&&dialogStart>=0&&clickStart>dialogStart);
const source=original.slice(0,dialogStart)+original.slice(clickStart);

function element(){return {children:[],append(...nodes){this.children.push(...nodes)},replaceChildren(...nodes){this.children=nodes},setAttribute(){},removeAttribute(){},querySelectorAll(){return []},remove(){},textContent:''};}
function content(node){return String(node?.textContent||'')+(node?.children||[]).map(content).join(' ');}
async function run({items=[],cancel=false,complete=true,race=false,offline=false}={}){
 const requests=[],messages=[];let confirms=0,flushes=0;
 const del=element(),save=element(),container=element();
 const request=async(path,options={})=>{
  requests.push({path,options});
  if(offline)throw Error('Kontrola není dostupná.');
  if(options.method==='DELETE'){
   assert.deepEqual(JSON.parse(options.body),{confirm:'document-id',expectedRevision:'revision'});
   if(race){const error=Error('Soubor se používá.');error.detail={code:'material_in_use',items:[{app:'kiosk',name:'Nové použití'}]};throw error;}
   return {ok:true};
  }
  return {id:'document-id',complete,canDelete:!items.length,items,name:'Řád.pdf',revision:'revision',coverage:'Kontrolované zdroje'};
 };
 const context={del,save,row:element(),item:{id:'document-id'},document:{createElement:element},editor:{async flush(){flushes++}},
  documentEditors:new Map([['document-id',{}]]),openDocumentEditors:new Set(),encodeURIComponent,
  status:message=>messages.push(message),captureDocumentDeleteContext:()=>()=>{},
  documentDeleteRequest:async(path,options,check)=>{check();const result=await request(path,options);check();return result;},
  confirmDocumentDeletion:async name=>{confirms++;assert.equal(name,'Řád.pdf');return !cancel;},
  $:id=>{assert.equal(id,'items');return container;},refreshDocumentCatalogPreview(){} };
 vm.runInNewContext(source,context);await del.onclick();
 assert.equal(del.disabled,false);assert.equal(save.disabled,false);assert.equal(flushes,1);
 return {requests,confirms,text:content(vm.runInNewContext('usagePanel',context)),messages};
}
let result=await run({items:[{app:'kiosk',name:'Hala',state:'publikovaný výstup',location:'Řády'}]});
assert.equal(result.requests.length,1);assert.equal(result.confirms,0);assert.match(result.text,/Hala/);assert.match(result.text,/Řády/);
result=await run({cancel:true});assert.equal(result.requests.length,1);assert.equal(result.confirms,1);
result=await run();assert.equal(result.requests.length,2);assert.equal(result.confirms,1);
result=await run({race:true});assert.match(result.text,/Nové použití/);
for(const options of [{complete:false},{offline:true}]){result=await run(options);assert.equal(result.requests.length,1);assert.equal(result.confirms,0);}
console.log('Deletion UI: used material, cancel, confirmed delete, new usage, incomplete/offline check pass.');
