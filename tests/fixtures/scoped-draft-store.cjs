/* Data-only scoped draft store. No DOM, network, publication or automatic restore. */
'use strict';
const allowed={
 config:['schemaVersion','recoveryVersion','values','segment','presentation'],
 values:['url','mode','categories','limit','seconds','viewMode','showImages','imageFit','showDate','paging','sourceName','sources','selectedSource'],
 source:['id','name','url','mode','categories'],segment:['orientation','style','block'],
 presentation:['mode','geometry','interaction','kioskLayout'],
 geometry:['registryId','registryVersion','orientation','layoutId','segmentId','width','height']
};
function object(value,keys){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!keys.includes(k)))throw Error('Unsupported recovery fields');}
function clean(config){
 const copy=JSON.parse(JSON.stringify(config));object(copy,allowed.config);if(copy.schemaVersion!==1||copy.recoveryVersion!==1)throw Error('Invalid recovery schema');object(copy.values,allowed.values);
 if(copy.segment!==null&&copy.segment!==undefined)object(copy.segment,allowed.segment);
 if(copy.presentation!==null&&copy.presentation!==undefined){object(copy.presentation,allowed.presentation);if(copy.presentation.geometry!==null&&copy.presentation.geometry!==undefined)object(copy.presentation.geometry,allowed.geometry);}
 if(copy.values.sources!==undefined){if(!Array.isArray(copy.values.sources)||copy.values.sources.length>100)throw Error('Invalid sources');for(const source of copy.values.sources)object(source,allowed.source);}
 const walk=(value,key='')=>{if(value===null||typeof value==='boolean'||typeof value==='number'&&Number.isFinite(value))return;
  if(typeof value==='string'){if(value.length>8192)throw Error('Recovery value too large');if(key==='url'&&value){const u=new URL(value);if(!['https:','http:'].includes(u.protocol)||u.username||u.password||u.hash||[...u.searchParams.keys()].some(k=>/token|secret|password|authorization|credential|api.?key|signature|^key$|^code$/i.test(k)))throw Error('Private source URL cannot be stored');}return;}
  if(Array.isArray(value)){for(const item of value)walk(item,key);return;}if(value&&typeof value==='object'){for(const [k,v]of Object.entries(value)){if(v&&typeof v==='object'&&!['values','sources','segment','presentation','geometry'].includes(k))throw Error('Unexpected nested recovery field');walk(v,k);}return;}throw Error('Unsupported recovery value');};
 walk(copy);if(JSON.stringify(copy).length>131072)throw Error('Recovery draft too large');return copy;
}
function create({storage,appId='news',cleanSnapshot,now=Date.now,ttl=7200000}){
 if(!/^[a-z][a-z0-9-]{0,47}$/.test(appId))throw Error('Invalid recovery app');
 if(appId!=='news'&&typeof cleanSnapshot!=='function')throw Error('Native recovery cleaner required');
 const nativeClean=typeof cleanSnapshot==='function'?cleanSnapshot:clean;
 function safeSnapshot(value){
  const cleaned=JSON.parse(JSON.stringify(nativeClean(JSON.parse(JSON.stringify(value)))));
  if(!cleaned||typeof cleaned!=='object'||Array.isArray(cleaned))throw Error('Native recovery cleaner must return object');
  let nodes=0;
  function guard(v){if(++nodes>20000)throw Error('Recovery too large');
   if(typeof v==='string'&&/^https?:\/\//i.test(v)){const u=new URL(v);if(u.username||u.password||[...u.searchParams.keys()].some(k=>/token|secret|password|authorization|credential|api.?key|signature|^key$|^code$/i.test(k)))throw Error('Private URL cannot be stored');}
   if(v&&typeof v==='object'){for(const[k,x]of Object.entries(v)){if(/password|secret|credential|authorization|(^|[_-])(access|refresh|auth)[_-]?token|^token$|^api.?key$/i.test(k))throw Error('Private recovery field');guard(x);}}
  }
  guard(cleaned);if(JSON.stringify(cleaned).length>131072)throw Error('Recovery too large');return cleaned;
 }
 function key(scope){if(scope?.appId!==appId||!(/^[a-f0-9]{32}$/.test(scope.schoolId||''))||!(/^[a-f0-9]{32}$/.test(scope.profileId||'')))throw Error('Verified school/profile scope required');return (appId==='news'?'eduvize-news-draft-v1:':'eduvize-app-draft-v1:')+scope.schoolId+':'+scope.profileId+':'+scope.appId;}
 function revision(value){if(!Number.isSafeInteger(value)||value<0)throw Error('Confirmed profile revision required');return value;}
 return Object.freeze({
  write(scope,config){const k=key(scope),value={schemaVersion:1,schoolId:scope.schoolId,profileId:scope.profileId,appId:scope.appId,revision:revision(scope.revision),createdAt:now(),config:safeSnapshot(config)};storage.setItem(k,JSON.stringify(value));},
  read(scope){const k=key(scope),expected=revision(scope.revision);let value;try{value=JSON.parse(storage.getItem(k)||'null');}catch{return {status:'invalid'};}if(!value)return {status:'absent'};
   if(value.schemaVersion!==1||value.schoolId!==scope.schoolId||value.profileId!==scope.profileId||value.appId!==scope.appId||!Number.isFinite(value.createdAt)||now()-value.createdAt<0||now()-value.createdAt>ttl)return {status:'invalid'};
   if(value.revision!==expected)return {status:'conflict'};
   try{return {status:'available',config:safeSnapshot(value.config),createdAt:value.createdAt};}catch{return {status:'invalid'};}},
  remove(scope){storage.removeItem(key(scope));}
 });
}
module.exports={create,clean};
