/* Native Documents settings only. Shared controller owns slot, publication and recovery storage. */
(function(root){'use strict';
 const clone=value=>JSON.parse(JSON.stringify(value));
 const modeOf=value=>({normal:'web',signage:'nsp',kiosk:'kiosk'})[value];
 function fail(message){throw new Error(message);}
 function clean(config){
  if(config?.schemaVersion!==1||config.recoveryVersion!==1||!config.values||!modeOf(config.values.layout)||typeof config.values['video-sound']!=='boolean')fail('Rozpracované nastavení Dokumentů není platné.');
  const values={layout:config.values.layout,'video-sound':config.values['video-sound']};
  let segment=null;
  if(config.segment){const s=config.segment;if(!['landscape','portrait'].includes(s.orientation)||!Number.isSafeInteger(Number(s.style))||Number(s.style)<1||!Number.isSafeInteger(Number(s.block))||Number(s.block)<1)fail('Neplatný segment Dokumentů.');segment={orientation:s.orientation,style:Number(s.style),block:Number(s.block)};}
  const p=config.presentation;if(!p||p.mode!==modeOf(values.layout)||!['interactive','display'].includes(p.interaction)||(p.mode==='kiosk'&&(p.interaction!=='interactive'||!['menu','tiles'].includes(p.kioskLayout))))fail('Neplatné zobrazení Dokumentů.');
  let geometry=null;
  if(p.mode==='nsp'&&p.geometry){const g=p.geometry;if(g.registryId!=='nsp-4k'||g.registryVersion!==1||!segment||g.orientation!==segment.orientation||g.layoutId!==segment.style||g.segmentId!==segment.block)fail('Neplatná geometrie Dokumentů.');geometry={registryId:'nsp-4k',registryVersion:1,orientation:g.orientation,layoutId:g.layoutId,segmentId:g.segmentId};}
  if(p.mode==='kiosk'&&p.geometry){const g=p.geometry;if(g.registryId!=='kiosk-viewport'||g.registryVersion!==1||![g.width,g.height].every(n=>Number.isSafeInteger(n)&&n>=240&&n<=8192)||g.orientation!==(g.height>g.width?'portrait':'landscape'))fail('Neplatná geometrie kiosku.');geometry={registryId:'kiosk-viewport',registryVersion:1,orientation:g.orientation,width:g.width,height:g.height};}
  return {schemaVersion:1,recoveryVersion:1,values,segment,presentation:{mode:p.mode,geometry,interaction:p.mode==='kiosk'?'interactive':p.interaction,kioskLayout:p.mode==='kiosk'?p.kioskLayout:null}};
 }
 function draft(config,presentation){
  if(config?.schemaVersion!==1||!config.presentation||JSON.stringify(config.presentation)!==JSON.stringify(presentation))fail('Nejprve uložte nastavení Dokumentů.');
  const c=clean({...config,recoveryVersion:1});
  if(c.presentation.mode!=='web'&&!c.presentation.geometry)fail('Nejprve dokončete a uložte rozměry výstupu.');
  root.EduvizeOutputActions.canonicalSlot(c.presentation);
  return {schemaVersion:1,payloadVersion:1,payload:{selection:'visible-library',videoSound:c.values['video-sound']},presentation:clone(c.presentation)};
 }
 function recovery({readNative,applyNative}){
  return Object.freeze({clean,read(){
   const config=readNative(),mode=modeOf(config.values.layout),segment=config.segment;
   const interaction=mode==='kiosk'?'interactive':root.EduvizeOutputModes.selection(),kioskLayout=mode==='kiosk'?root.EduvizeOutputModes.layoutSelection():null;
   let geometry=null;
   if(mode==='nsp'&&segment)geometry={registryId:'nsp-4k',registryVersion:1,orientation:segment.orientation,layoutId:Number(segment.style),segmentId:Number(segment.block)};
   if(mode==='kiosk'){const g=root.EduvizeSegmentSelection?.kioskGeometry?.();if(g)geometry={registryId:'kiosk-viewport',registryVersion:1,orientation:g.orientation,width:g.width,height:g.height};}
   return clean({...config,recoveryVersion:1,presentation:{mode,geometry,interaction,kioskLayout}});
  },async apply(snapshot){
   const config=clean(snapshot);await applyNative({schemaVersion:1,values:clone(config.values),segment:clone(config.segment)});
   const p=config.presentation;root.EduvizeOutputModes.setInteraction(p.interaction,{notify:false});
   let presentationPending=p.mode==='nsp'&&!p.geometry;
   if(p.mode==='kiosk'){root.EduvizeOutputModes.setKioskLayout(p.kioskLayout,{notify:false});presentationPending=!p.geometry||root.EduvizeSegmentSelection?.setKioskGeometry?.(p.geometry)!==true;}
   return {presentationPending};
  }});
 }
 root.EduvizeDocumentsOutputAdapter=Object.freeze({draft,recovery,cleanRecovery:clean});
})(typeof window==='undefined'?globalThis:window);
