const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
let checks=0;const root={EduvizeOutputActions:{canonicalSlot:p=>p},EduvizeNSPLayouts:{layouts:{landscape:{1:[[3840,2160]]},portrait:{1:[[2160,3840]]}}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../documents-output-actions.js'),'utf8'),{window:root});
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../documents-output-adapter.js'),'utf8'),{window:root});
const b=root.EduvizeDocumentsOutputBridge;
const plain=v=>JSON.parse(JSON.stringify(v));
const native={schemaVersion:1,values:{layout:'normal','video-sound':false},segment:{orientation:'landscape',style:1,block:1}};
const p=b.presentation(native,'web','interactive');assert.deepEqual(plain(p),{mode:'web',geometry:null,interaction:'interactive',kioskLayout:null});checks++;
assert.equal(b.presentation(native,'nsp','display').geometry.segmentId,1);assert.throws(()=>b.presentation({...native,segment:{orientation:'landscape',style:1,block:2}},'nsp','interactive'));checks++;
assert.equal(b.presentation(native,'kiosk','display','menu',{width:3840,height:2160}).interaction,'interactive');assert.throws(()=>b.presentation(native,'kiosk','interactive','menu',{width:100,height:10}));checks++;
const config=b.withPresentation(native,p);assert.deepEqual(plain(config.values),native.values);assert.deepEqual(plain(config.presentation),plain(p));assert.equal(native.data,undefined);checks++;
let applied,appliedPresentation;const wrapped=b.wrapProfileAdapter({app:'documents',read:()=>native,apply:v=>{applied=v;}},()=>p,v=>{appliedPresentation=v;});assert.deepEqual(plain(wrapped.read().presentation),plain(p));await wrapped.apply(config);assert.equal(applied,config);assert.deepEqual(plain(appliedPresentation),plain(p));checks++;
let state={connected:true,schoolId:'a'.repeat(32),profileId:'b'.repeat(32)},current=config,stored=plain(config),options;
const buttons={generateButton:{},copyButton:{onclick:()=>{throw Error('legacy');}},openButton:{onclick:()=>{throw Error('legacy');}},status:{}};
const adapter=root.EduvizeDocumentsOutputAdapter;
let savedLoads=0;
b.controller({auth:{status:()=>state},profileAdapter:{read:()=>current},saved:{load:async ctx=>{savedLoads++;assert.equal(ctx.profileId,state.profileId);return {config:stored,data:stored.presentation};}},client:{},actions:{mount:o=>{options=o;return {workflow:'saved-copy-preview',withSavedCommit(){},ensurePublishedFromSaved(){},previewDraft(){},refresh:async()=>{}};}},elements:buttons,readPresentation:c=>c.presentation,registeredAdapter:()=>adapter});
assert.equal(buttons.copyButton.onclick,null);assert.equal(buttons.openButton.onclick,null);assert.equal(options.context().presentation.mode,'web');assert.equal('slotId' in options.context(),false);assert.equal('resolve' in options,false);checks++;
// Reordering the server JSON keys is semantically equivalent.
stored.values={'video-sound':false,layout:'normal'};const draft=await options.draft();assert.deepEqual(plain(draft.payload),{selection:'visible-library',videoSound:false});assert.equal(savedLoads,1);checks++;
current=plain(config);current.values['video-sound']=true;assert.equal((await options.draft()).payload.videoSound,false,'First Copy must use saved settings despite newer form edits');checks++;
current=config;state={...state,connected:false};assert.throws(()=>options.context(),e=>e.code==='CONTEXT_REQUIRED');state={...state,connected:true};checks++;
b.controller({auth:{status:()=>state},profileAdapter:{read:()=>config},saved:{load:async()=>{state={...state,profileId:'c'.repeat(32)};return {config:stored,data:stored.presentation};}},client:{},actions:{mount:o=>{options=o;return {workflow:'saved-copy-preview',withSavedCommit(){},ensurePublishedFromSaved(){},previewDraft(){}};}},elements:buttons,readPresentation:c=>c.presentation,registeredAdapter:()=>adapter});await assert.rejects(options.draft(),e=>e.code==='CONTEXT_CHANGED');checks++;
console.log('Documents V2 bridge:',checks,'behavior checks PASS');return checks;
})();

