export const BOT_CATALOG=[
 {id:'crypto',name:'Cripto · Prudente',market:'Criptomonedas',mode:'paper',symbols:['BTCUSD','ETHUSD','SOLUSD'],provider:'Kraken',executionEnabled:true,description:'Cuenta ficticia existente; conserva su saldo y operaciones.'},
 {id:'forex',name:'Forex · Investigación',market:'Divisas',mode:'pending_data',symbols:['EURUSD','GBPUSD','AUDUSD'],provider:null,executionEnabled:false,description:'Pendiente de una fuente disponible y de validar costes, horarios y simulación. Sin capital asignado ni operaciones.'},
 {id:'gold',name:'Oro · Investigación',market:'Oro',mode:'pending_data',symbols:['XAUUSD'],provider:null,executionEnabled:false,description:'Pendiente de datos de oro al contado y de especificaciones del instrumento. No se sustituye XAU/USD por futuros GC=F. Sin capital asignado.'}
];
export function botCatalog(state){return BOT_CATALOG.map(bot=>({...bot,status:bot.id==='crypto'?(!state?'uninitialized':state.protectionHalted?'protected':state.paused?'paused':state.halted?'daily_pause':'paper_active'):'pending_data',capitalAssignedUSD:bot.id==='crypto'&&state?state.config?.initial??1000:0,openPositions:bot.id==='crypto'&&state?Object.keys(state.positions).length:0,realTradingEnabled:false}));}
export function parseTicker(payload,retrievedAt){
 if(payload.error?.length||!payload.result)throw Error('Kraken no devuelve cotizaciones válidas.');
 const aliases={BTCUSD:'XXBTZUSD',ETHUSD:'XETHZUSD',SOLUSD:'SOLUSD'},quotes={};
 for(const [symbol,alias] of Object.entries(aliases)){
 const r=payload.result[alias],bid=Number(r?.b?.[0]),ask=Number(r?.a?.[0]),last=Number(r?.c?.[0]);
 if(![bid,ask,last].every(x=>Number.isFinite(x)&&x>0)||ask<bid)throw Error('Cotización incompleta o cruzada.');
 quotes[symbol]={bid,ask,last,spreadPct:100*(ask-bid)/bid};
 }
 return {provider:'Kraken public ticker',retrievedAt,exchangeTimestamp:null,refreshSeconds:15,quotes,realTradingEnabled:false};
}
export async function liveQuotes(fetcher=fetch,clock=()=>Date.now()){
 const res=await fetcher('https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD,SOLUSD',{signal:AbortSignal.timeout(15000)});
 if(!res.ok)throw Error('Kraken ticker: HTTP '+res.status);
 return parseTicker(await res.json(),clock());
}
export function markPositions(state,ticker){
 if(!state)return [];
 const cfg=state.config||{fee:.004,slippage:.001};
 return Object.entries(state.positions).map(([symbol,p])=>{
 const q=ticker.quotes[symbol];if(!q)throw Error('Falta la cotización de una posición.');
 const liquidation=p.qty*q.bid*(1-cfg.slippage)*(1-cfg.fee);
 return {botId:'crypto',symbol,entry:p.entry,quantity:p.qty,stop:p.stop,target:p.target,entryTime:p.time,bid:q.bid,ask:q.ask,indicativeNetPnlUSD:liquidation-p.cost,quoteRetrievedAt:ticker.retrievedAt,simulationOnly:true};
 });
}
