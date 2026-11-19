const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const text=fs.readFileSync(path.join(__dirname,'../published.html'),'utf8');
const start=text.indexOf('function replaceSnapshot(next){'),end=text.indexOf('\nupdate=replaceSnapshot;',start);
const shell={hidden:true};let releases=0;
const context={Map,Set,media:new Map(),imageView:null,pdfRenderId:0,stopPdfPreviews(){},releasePdfCache(){releases++;},refresh(){},document:{querySelector:()=>shell,body:{classList:{toggle(){}}},documentElement:{classList:{toggle(){}}}}};
vm.runInNewContext(text.slice(start,end),context);
const id='a'.repeat(32),media='b'.repeat(32),doc='c'.repeat(32),snapshot={id,presentation:{mode:'web'},payload:{videoSound:false,items:[{id:doc,mediaId:media,mime:'application/pdf',name:'Test.pdf',category:'Ostatní'}]},media:[{id:media,mime:'application/pdf',url:'/api/public/v1/outputs/'+id+'/media/'+media}]};
context.replaceSnapshot(snapshot);assert.equal(context.docs.length,1);assert.equal(shell.hidden,false);assert.equal(releases,1);
for(const change of [s=>s.media[0].url='/api/documents/'+doc+'/file',s=>s.payload.items[0].mediaId='d'.repeat(32),s=>s.media.push(s.media[0]),s=>s.id='bad',s=>s.payload.items[0].mime='text/html']){const bad=structuredClone(snapshot);change(bad);assert.throws(()=>context.replaceSnapshot(bad));assert.equal(context.pdfRenderId,1,'Invalid snapshot must not replace validated content');}
assert.equal(releases,1);context.replaceSnapshot(snapshot);assert.equal(releases,2,'Explicit update releases cached PDF versions');
for(const bad of ['localStorage','sessionStorage','EduvizeAdminAuth','/api/documents','onrender.com','github.io','cdnjs.cloudflare.com'])assert.equal(text.includes(bad),false,bad);
assert.match(text,/isEvalSupported:false/);assert.match(text,/media\.clear\(\)/);
for(const match of text.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))if(match[1].trim())new vm.Script(match[1]);
console.log('Published Documents: 7 snapshot/cache checks and finite-resource/syntax checks PASS');
