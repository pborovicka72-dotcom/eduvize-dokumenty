/* Documents bridge: saved settings and one shared V2 controller, never a slot resolver. */
(function(root){'use strict';
 const copy=value=>JSON.parse(JSON.stringify(value));
 const canonical=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
 const equal=(a,b)=>canonical(a)===canonical(b);
 function fail(code,message){throw Object.assign(new Error(message),{code});}
 function presentation(config,mode,interaction,kioskLayout,viewport){
  if(!['web','nsp','kiosk'].includes(mode)||!['interactive','display'].includes(interaction))fail('INVALID_PRESENTATION','Vyberte typ výstupu a ovládání.');
  let geometry=null;
  if(mode==='nsp'){
   const s=config.segment,layoutId=Number(s?.style),segmentId=Number(s?.block);
   if(!['landscape','portrait'].includes(s?.orientation)||!Number.isInteger(layoutId)||!Number.isInteger(segmentId)||segmentId<1||!root.EduvizeNSPLayouts?.layouts?.[s.orientation]?.[layoutId]?.[segmentId-1])fail('INVALID_GEOMETRY','Vyberte existující segment NSP.');
   geometry={registryId:'nsp-4k',registryVersion:1,orientation:s.orientation,layoutId,segmentId};
  }else if(mode==='kiosk'){
   const {width,height}=viewport||{};
   if(![width,height].every(n=>Number.isInteger(n)&&n>=240&&n<=8192)||!['menu','tiles'].includes(kioskLayout))fail('INVALID_GEOMETRY','Chybí platné rozměry kiosku.');
   geometry={registryId:'kiosk-viewport',registryVersion:1,orientation:height>width?'portrait':'landscape',width,height};
  }
  return {mode,geometry,interaction:mode==='kiosk'?'interactive':interaction,kioskLayout:mode==='kiosk'?kioskLayout:null};
 }
 function withPresentation(config,p){
  if(config?.schemaVersion!==1||!config.values||typeof config.values!=='object'||Array.isArray(config.values))fail('INVALID_SETTINGS','Neplatné nastavení Dokumentů.');
  // Preserve the native values/segment envelope; add only full Presentation.
  return {...copy(config),presentation:copy(p)};
 }
 function wrapProfileAdapter(adapter,readPresentation,applyPresentation){
  return {...adapter,read(){const config=adapter.read();return withPresentation(config,readPresentation(config));},async apply(config){await adapter.apply(config);if(config.presentation)await applyPresentation(config.presentation);}};
 }
 function controller({auth,profileAdapter,saved,client,actions,elements,readPresentation,registeredAdapter}){
  function context(){
   const s=auth.status();
   if(!s.connected||!s.schoolId||!/^[a-f0-9]{32}$/.test(s.profileId||''))fail('CONTEXT_REQUIRED','Vyberte uložený profil své školy.');
   return {schoolId:String(s.schoolId),profileId:s.profileId,appId:'documents',presentation:readPresentation(profileAdapter.read())};
  }
  async function draft(){
   const before=context(),current=profileAdapter.read(),stored=await saved.load(before);
   if(!equal(before,context())||!equal(current,profileAdapter.read()))fail('CONTEXT_CHANGED','Profil nebo nastavení se během načítání změnily.');
   if(!equal(stored.config.presentation,before.presentation)||!equal(stored.config.values,current.values)||!equal(stored.config.segment,current.segment))fail('SETTINGS_REQUIRED','Nejprve uložte aktuální nastavení Dokumentů.');
   const adapter=registeredAdapter();
   if(typeof adapter?.draft!=='function')fail('UNSUPPORTED_APP','Vytváření odkazu Dokumentů není připojené k ověřenému adaptéru.');
   const value=await adapter.draft(copy(stored.config),copy(stored.config.presentation));
   if(!equal(context(),before)||!value||value.schemaVersion!==1||value.payloadVersion!==1||!equal(value.presentation,stored.config.presentation))fail('INVALID_DRAFT','Adaptér vrátil neplatný uložený výstup.');
   return value;
  }
  // Remove only the old property handlers; the shared controller binds once.
  elements.copyButton.onclick=null;elements.openButton.onclick=null;
  return actions.mount({client,context,draft,elements});
 }
 async function install(){
  if(root.EduvizeDocumentsOutputActions)return;
  const elements={generateButton:document.getElementById('generate-document-output'),copyButton:document.getElementById('copy'),openButton:document.getElementById('open'),status:document.getElementById('document-output-status')};
  if(!elements.generateButton)return;
  elements.copyButton.onclick=null;elements.openButton.onclick=null;
  const auth=root.EduvizeAdminAuth;
  if(!auth||!root.EduvizeOutputActions||!root.EduvizeOutputClient||!root.EduvizeSavedOutputSettings){elements.status.textContent='Vytváření odkazů nyní není dostupné.';return;}
  await auth.ready;
  const profileAdapter=root.EduvizeProfileAdapter;
  const client=root.EduvizeOutputClient.create({origin:root.location.origin,getAuthorization:()=>{const token=auth.getToken('configurations')||auth.getToken('documents');return token?'Bearer '+token:'';}});
  const actions=controller({auth,profileAdapter,saved:root.EduvizeSavedOutputSettings.create(),client,actions:root.EduvizeOutputActions,elements,readPresentation:config=>config.presentation,registeredAdapter:()=>root.EduvizeDocumentsOutputAdapter});
  root.EduvizeDocumentsOutputActions=actions;
  const refresh=()=>actions.refresh().catch(e=>{elements.status.textContent=e.message||'Odkaz nyní není dostupný.';});
  for(const name of ['eduvize-admin-auth-change','eduvize-profile-selected'])root.addEventListener(name,refresh);
  document.addEventListener('change',event=>{if(event.target.matches?.('#layout,#edu-output-interaction,#edu-output-kiosk-layout')||event.target.closest?.('.ev-segments'))refresh();});
  await refresh();
 }
 root.EduvizeDocumentsOutputBridge=Object.freeze({presentation,withPresentation,wrapProfileAdapter,controller,install});
})(typeof window==='undefined'?globalThis:window);
