export const MT5_KEY='connections/mt5-demo-v1.json';
export function validateMT5Snapshot(input,now=Date.now()){
 if(input?.schemaVersion!==1||input.account?.mode!=='demo'||input.executionEnabled!==false)throw Error('Solo se acepta una lectura de cuenta DEMO sin ejecución.');
 if(!Number.isFinite(input.generatedAt)||input.generatedAt>now+60000||now-input.generatedAt>86400000)throw Error('Lectura demasiado antigua o con fecha futura.');
 const allowed=['EURUSD','GBPUSD','AUDUSD','XAUUSD','BTCUSD','ETHUSD','SOLUSD'],quotes={},candles={};
 for(const [symbol,q] of Object.entries(input.quotes||{})){
 if(!allowed.includes(symbol))throw Error('Instrumento no permitido.');
 for(const field of ['bid','ask','sourceTime','contractSize','volumeMin','volumeStep','volumeMax','digits'])if(!Number.isFinite(q[field]))throw Error('Metadatos de cotización incompletos.');
 if(q.bid<=0||q.ask<q.bid||q.contractSize<=0||q.volumeMin<=0||q.volumeStep<=0||q.volumeMax<q.volumeMin||q.sourceTime>now+60000)throw Error('Cotización o contrato no válidos.');
 const brokerSymbol=String(q.brokerSymbol||'');if(!brokerSymbol||brokerSymbol.length>80||!/^[-\w.+# ]+$/.test(brokerSymbol))throw Error('Nombre de símbolo inválido.');
 quotes[symbol]={brokerSymbol,bid:q.bid,ask:q.ask,sourceTime:q.sourceTime,fresh:now-q.sourceTime>=0&&now-q.sourceTime<=120000,contractSize:q.contractSize,volumeMin:q.volumeMin,volumeStep:q.volumeStep,volumeMax:q.volumeMax,digits:q.digits,profitCurrency:String(q.profitCurrency||'').slice(0,10)};
 const rows=input.candles?.[symbol]||[];if(!Array.isArray(rows)||rows.length>300)throw Error('Demasiadas velas.');
 let previous=null;
 candles[symbol]=rows.map(r=>{if(!['time','open','high','low','close','tickVolume'].every(k=>Number.isFinite(r[k]))||r.time%300000||r.time+300000>input.generatedAt||Math.min(r.open,r.high,r.low,r.close)<=0||r.tickVolume<0||r.low>Math.min(r.open,r.close)||r.high<Math.max(r.open,r.close)||(previous!==null&&r.time<=previous))throw Error('Velas de MT5 inválidas o abiertas.');previous=r.time;return {time:r.time,open:r.open,high:r.high,low:r.low,close:r.close,tickVolume:r.tickVolume};});
 }
 if(!Object.keys(quotes).length)throw Error('La lectura no contiene cotizaciones válidas.');
 return {schemaVersion:1,source:'MetaTrader5 demo terminal',receivedAt:now,generatedAt:input.generatedAt,account:{mode:'demo',reference:String(input.account.reference||'').slice(0,64),currency:String(input.account.currency||'').slice(0,10)},executionEnabled:false,quotes,candles};
}
export async function goldReference(fetcher=fetch,clock=()=>Date.now()){
 const response=await fetcher('https://api.gold-api.com/price/XAU',{signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('Gold API: HTTP '+response.status);
 const d=await response.json(),retrievedAt=clock(),price=Number(d.price),providerUpdatedAt=Date.parse(d.updatedAt);
 if(d.symbol!=='XAU'||d.currency!=='USD'||!Number.isFinite(price)||price<=0||!Number.isFinite(providerUpdatedAt)||providerUpdatedAt>retrievedAt+60000||retrievedAt-providerUpdatedAt>86400000)throw Error('Referencia de oro inválida o antigua.');
 return {symbol:'XAUUSD',price,currency:'USD',provider:'Gold API',providerUpdatedAt,retrievedAt,referenceOnly:true,hasBidAsk:false,executionEnabled:false,historyAvailable:false};
}
