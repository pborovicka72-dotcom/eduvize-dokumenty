/* Registered Documents payload: current visible school library, pinned at explicit Generate/Update. */
(function(root){'use strict';
 function draft(config,presentation){
  if(config?.schemaVersion!==1||typeof config.values?.['video-sound']!=='boolean'||!config.presentation)throw Error('Nejprve uložte nastavení Dokumentů.');
  return {schemaVersion:1,payloadVersion:1,payload:{selection:'visible-library',videoSound:config.values['video-sound']},presentation:JSON.parse(JSON.stringify(presentation))};
 }
 root.EduvizeDocumentsOutputAdapter=Object.freeze({draft});
})(typeof window==='undefined'?globalThis:window);
