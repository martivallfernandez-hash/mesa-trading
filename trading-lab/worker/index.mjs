import {SYMBOLS,CFG,seed,advance,validate,view,equity,closePosition,applyConservative,PRACTICE_CFG,PRACTICE_SESSION_ID,newPracticeSession} from './engine.mjs';
import {botCatalog,liveQuotes,markPositions} from './live.mjs';
import {MT5_KEY,validateMT5Snapshot,goldReference} from './mt5.mjs';
import {PAGE} from './page.mjs';
async function download(){
 const timeResponse=await fetch('https://api.kraken.com/0/public/Time',{signal:AbortSignal.timeout(20000)});if(!timeResponse.ok)throw Error('No se pudo consultar Kraken');const clock=await timeResponse.json();if(clock.error?.length)throw Error('Kraken no devuelve la hora');let now=clock.result.unixtime*1000;
 let series={};
 for(const s of SYMBOLS){let pair=s==='BTCUSD'?'XBTUSD':s;const res=await fetch('https://api.kraken.com/0/public/OHLC?interval=5&pair='+pair,{signal:AbortSignal.timeout(20000)});if(!res.ok)throw Error('Kraken no responde: '+res.status);let d=await res.json();if(d.error?.length)throw Error('Kraken ha rechazado OHLC');let lists=Object.entries(d.result).filter(([k])=>k!=='last');if(lists.length!==1)throw Error('Respuesta de mercado inesperada');const rows=lists[0][1].map(r=>({time:Number(r[0])*1000,open:+r[1],high:+r[2],low:+r[3],close:+r[4],volume:+r[6]})).filter(r=>r.time+300000<=now);series[s]=validate(rows,now);}
 return {series,now};
}
const KEY='paper/state-v1.json';
async function read(env){if(!env.BUCKET)throw Error('Almacenamiento persistente no disponible');const obj=await env.BUCKET.get(KEY);return {state:obj?await obj.json():null,etag:obj?.etag};}
async function save(env,state,etag){const result=await env.BUCKET.put(KEY,JSON.stringify(state),{onlyIf:etag?{etagMatches:etag}:{etagDoesNotMatch:'*'},httpMetadata:{contentType:'application/json'}});if(!result)throw Error('Otro ciclo ha actualizado la cuenta. Recarga antes de repetir.');}
function json(data,status=200){return Response.json(data,{status,headers:{'Cache-Control':'no-store'}});}
export default {
 async fetch(request,env){
 const path=new URL(request.url).pathname;
 try{
 if(path==='/')return new Response(PAGE,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'"}});
 if(path==='/api/state'&&request.method==='GET'){const {state}=await read(env);return json({...view(state),bots:botCatalog(state)});}
 if(path==='/api/bots'&&request.method==='GET'){const {state}=await read(env);return json({bots:botCatalog(state),sharedCapital:true,realTradingEnabled:false});}
 if(path==='/api/live'&&request.method==='GET'){const {state}=await read(env);const ticker=await liveQuotes();return json({...ticker,positions:markPositions(state,ticker)});}
 if(path==='/api/gold'&&request.method==='GET')return json(await goldReference());
 if(path==='/api/practice/previous'&&request.method==='GET'){const {state}=await read(env);if(!state?.practiceArchiveKey)return json({error:'No hay sesión anterior archivada.'},404);const archive=await env.BUCKET.get(state.practiceArchiveKey);if(!archive)return json({error:'Archivo no disponible.'},404);return new Response(JSON.stringify(await archive.json()),{headers:{'Content-Type':'application/json','Cache-Control':'no-store','Content-Disposition':'attachment; filename=sesion-anterior.json'}});}
 if(path==='/api/practice/start-10000'&&request.method==='POST'){const origin=request.headers.get('Origin');if(origin&&origin!==new URL(request.url).origin)return json({error:'Origen no permitido'},403);const {state:old,etag}=await read(env);if(old?.practiceSessionId===PRACTICE_SESSION_ID)return json({...view(old),bots:botCatalog(old)});const {series,now}=await download();let archiveKey=null;if(old){archiveKey='paper/archives/before-demo-usd10000-'+old.startedAt+'-'+(old.revision||0)+'.json';const existing=await env.BUCKET.get(archiveKey);if(!existing){const archived=await env.BUCKET.put(archiveKey,JSON.stringify({archivedAt:now,reason:'Cambio solicitado a demo 10000 USD y riesgo diario 150 USD',state:old}),{onlyIf:{etagDoesNotMatch:'*'},httpMetadata:{contentType:'application/json'}});if(!archived)throw Error('No se pudo confirmar el archivo de la sesión anterior.');}}const state=newPracticeSession(series,now,old,archiveKey);await save(env,state,etag);return json({...view(state),bots:botCatalog(state)});}
 if(path==='/api/mt5'&&request.method==='GET'){if(!env.BUCKET)throw Error('Almacenamiento no disponible.');const obj=await env.BUCKET.get(MT5_KEY);return json(obj?{connected:true,snapshot:await obj.json(),executionEnabled:false}:{connected:false,executionEnabled:false});}
 if(path==='/api/mt5/import'&&request.method==='POST'){const origin=request.headers.get('Origin');if(origin&&origin!==new URL(request.url).origin)return json({error:'Origen no permitido'},403);if(!env.BUCKET)throw Error('Almacenamiento no disponible.');if(Number(request.headers.get('Content-Length')||0)>1000000)return json({error:'Lectura demasiado grande'},413);const text=await request.text();if(text.length>1000000)return json({error:'Lectura demasiado grande'},413);const snapshot=validateMT5Snapshot(JSON.parse(text));const previous=await env.BUCKET.get(MT5_KEY);if(previous){const old=await previous.json();if(snapshot.generatedAt<=old.generatedAt)return json({error:'La lectura es anterior o ya se importó.'},409);}const result=await env.BUCKET.put(MT5_KEY,JSON.stringify(snapshot),{onlyIf:previous?{etagMatches:previous.etag}:{etagDoesNotMatch:'*'},httpMetadata:{contentType:'application/json'}});if(!result)return json({error:'Otra lectura se ha guardado antes. Recarga.'},409);return json({connected:true,snapshot,executionEnabled:false});}
 if(path==='/api/history.csv'&&request.method==='GET'){
 const {state}=await read(env);if(!state)return json({error:'Sin datos'},404);
 let lines=['symbol,timestamp_utc,open,high,low,close,volume'];for(const s of SYMBOLS)for(const r of state.history[s])lines.push([s,new Date(r.time).toISOString(),r.open,r.high,r.low,r.close,r.volume].join(','));
 return new Response(lines.join('\n'),{headers:{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename="historial-kraken.csv"','Cache-Control':'no-store'}});
 }
 if(path.startsWith('/api/')&&request.method==='POST'){
 // El Site es privado. La plataforma exige acceso del propietario o acceso de servicio.
 const origin=request.headers.get('Origin');if(origin&&origin!==new URL(request.url).origin)return json({error:'Origen no permitido'},403);
 if(!['/api/tick','/api/pause','/api/resume','/api/stop'].includes(path))return json({error:'Ruta no disponible'},404);
 const {state:old,etag}=await read(env);
 if(path==='/api/tick'){
 const {series,now}=await download();let state=old?applyConservative(advance(old,series,now),now):newPracticeSession(series,now);
 if(!old)state.curve=[{time:now,equity:PRACTICE_CFG.initial}];
 await save(env,state,etag);return json({...view(state),bots:botCatalog(state)});
 }
 if(!old)return json({error:'Primero actualiza los datos'},409);
 let state=structuredClone(old);
 if(path==='/api/pause')state.paused=true;
 if(path==='/api/resume'){const {series,now}=await download();state=advance(state,series,now);state.paused=false;}
 if(path==='/api/stop'){
 const {series,now}=await download();state.paused=true;state=advance(state,series,now);
 for(const s of Object.keys(state.positions))closePosition(state,s,series[s].at(-1).close,now,'emergencia_cierre_ficticio');
 state.curve.push({time:now,equity:state.cash});
 }
 state.revision++;await save(env,state,etag);return json({...view(state),bots:botCatalog(state)});
 }
 return json({error:'No encontrado'},404);
 }catch(error){return json({error:error.message,liveTrading:false},503);}
 }
};
