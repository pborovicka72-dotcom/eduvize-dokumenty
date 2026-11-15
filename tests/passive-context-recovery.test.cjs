const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../documents-output-actions.js'),'utf8');
test('install avoids obsolete background lookup while explicit Copy still validates current context',async()=>{
 let mounted,refreshes=0,profile='b'.repeat(32),resolveSaved;
 const presentation={mode:'web',geometry:null,interaction:'display',kioskLayout:null};
 const nodes={};for(const id of ['copy','open','document-output-status'])nodes[id]={textContent:'',dataset:{}};
 const root={location:{origin:'https://example.invalid',href:'https://example.invalid/config.html'},
  EduvizeAdminAuth:{ready:Promise.resolve(),status:()=>({connected:true,schoolId:'a'.repeat(32),profileId:profile}),getToken:()=>null},
  EduvizeProfiles:{fields(){},segment(){}},EduvizeProfileAdapter:{read:()=>({presentation})},
  EduvizeOutputClient:{create:()=>({})},
  EduvizeSavedOutputSettings:{create:()=>({load:()=>new Promise(r=>{resolveSaved=r;})})},
  EduvizeOutputActions:{mount(options){mounted=options;return {workflow:'saved-copy-preview',withSavedCommit(){},ensurePublishedFromSaved(){},previewDraft(){},refresh(){refreshes++;throw Error('Unexpected background IO');}};}},
  EduvizeDocumentsOutputAdapter:{draft:async(config,p)=>({schemaVersion:1,payloadVersion:1,presentation:p,payload:{}})},
  addEventListener(){throw Error('Obsolete automatic context subscription');}
 };
 vm.runInNewContext(source,{window:root,document:{getElementById:id=>nodes[id],addEventListener(){throw Error('Obsolete presentation subscription');}},URL});
 await root.EduvizeDocumentsOutputBridge.install();assert.ok(mounted);assert.equal(refreshes,0);
 const pending=mounted.draft();profile='c'.repeat(32);resolveSaved({config:{presentation}});
 await assert.rejects(pending,e=>e.code==='CONTEXT_CHANGED');
 assert.equal(nodes['document-output-status'].textContent,'');
});
