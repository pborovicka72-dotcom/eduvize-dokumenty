import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html=fs.readFileSync(new URL('../config.html',import.meta.url),'utf8');
for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
const start=html.indexOf('const usagePanel=');
const source=html.slice(start,html.indexOf('const summary=',start));
function element(){return {children:[],append(...nodes){this.children.push(...nodes)},replaceChildren(...nodes){this.children=nodes},setAttribute(){},removeAttribute(){},textContent:''};}
async function run({items=[],cancel=false,complete=true,race=false,offline=false}={}){
 const requests=[],messages=[];let confirms=0,loads=0,flushes=0;
 const del=element(),save=element();
 const context={del,save,row:element(),item:{id:'document-id'},document:{createElement:element},editor:{async flush(){flushes++}},documentEditors:new Map([['document-id',{}]]),encodeURIComponent,
  status:message=>messages.push(message),load:async()=>loads++,confirm:message=>{confirms++;assert.match(message,/Smazat soubor/);return !cancel},
  request:async(path,options={})=>{requests.push({path,options});if(offline)throw Error('Kontrola není dostupná.');if(options.method==='DELETE'){
   assert.deepEqual(JSON.parse(options.body),{confirm:'document-id',expectedRevision:'revision'});
   if(race){const error=Error('Soubor se používá.');error.detail={code:'material_in_use',items:[{app:'kiosk',name:'Nové použití'}]};throw error;}return {ok:true};
  }return {complete,canDelete:!items.length,items,name:'Řád.pdf',revision:'revision',coverage:'Kontrolované zdroje'};}
 };
 vm.runInNewContext(source,context);await del.onclick();
 const text=vm.runInNewContext('usagePanel.children.map(x=>x.textContent+(x.children||[]).map(y=>y.textContent).join(" ")).join(" ")',context);
 assert.equal(del.disabled,false);assert.equal(save.disabled,false);assert.equal(flushes,1);
 return {requests,confirms,loads,text,messages};
}
let r=await run({items:[{app:'kiosk',name:'Hala',state:'publikovaný výstup',location:'Řády'}]});
assert.equal(r.requests.length,1);assert.equal(r.confirms,0);assert.match(r.text,/Hala/);assert.match(r.text,/Řády/);
r=await run({cancel:true});assert.equal(r.requests.length,1);assert.equal(r.confirms,1);assert.equal(r.loads,0);
r=await run();assert.equal(r.requests.length,2);assert.equal(r.loads,1);
r=await run({race:true});assert.match(r.text,/Nové použití/);assert.equal(r.loads,0);
for(const options of [{complete:false},{offline:true}]){r=await run(options);assert.equal(r.requests.length,1);assert.equal(r.confirms,0);assert.equal(r.loads,0);}
console.log('Deletion UI: used material, cancel, confirmed delete, new usage, incomplete/offline check pass.');
