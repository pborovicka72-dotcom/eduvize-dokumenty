import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const listeners={},buttons=[];
function element(){return {classList:{add(){}},children:[],attributes:{},append(...items){this.children.push(...items);},setAttribute(k,v){this.attributes[k]=v;}};}
const document={createElement(tag){const el=element();if(tag==='button')buttons.push(el);return el;},addEventListener(type,fn){listeners[type]=fn;},fullscreenElement:null,async exitFullscreen(){this.fullscreenElement=null;listeners.fullscreenchange();}};
const host=element(),target=element();target.requestFullscreen=async()=>{document.fullscreenElement=target;listeners.fullscreenchange();};
const scope={window:{},document,WeakSet,Math};
vm.runInNewContext(fs.readFileSync(new URL('../../eduvize-styly/design-system/document-viewport.js',import.meta.url),'utf8'),scope);
scope.window.EduvizeDocumentViewport.mount(host,{fullscreenTarget:target});
const button=buttons.find(b=>b.attributes['aria-label']==='Celá obrazovka');
assert.ok(button);assert.equal(button.attributes['aria-pressed'],'false');
await button.onclick();assert.equal(button.attributes['aria-pressed'],'true');assert.match(button.textContent,/Ukončit/);
await button.onclick();assert.equal(button.attributes['aria-pressed'],'false');assert.match(button.textContent,/Celá obrazovka/);
await button.onclick();document.fullscreenElement=null;listeners.fullscreenchange();assert.equal(button.attributes['aria-label'],'Celá obrazovka');assert.equal(button.attributes['aria-pressed'],'false');
console.log('Fullscreen labels and pressed state follow entry, exit and external Escape.');

const pages=Array(3).fill({width:595,height:842}),overview=scope.window.EduvizeDocumentViewport.overview;
assert.equal(overview(pages,400,700).columns,1);
assert.equal(overview(pages,900,650).columns,2);
assert.equal(overview(pages,1500,650).columns,3);
assert.equal(overview(pages.slice(0,1),1500,650).columns,1);
assert.equal(overview(Array(3).fill({width:842,height:595}),1500,650).columns,2);
console.log('PDF overview selects 1, 2 or 3 pages from available space and page proportions.');
