export const SYMBOLS=['BTCUSD','ETHUSD','SOLUSD'];
export const LEGACY_CFG={initial:1000,risk:.0025,dailyLimit:.01,maxPositions:2,fee:.004,slippage:.001,stopATR:1.5,reward:2};
export const CFG={...LEGACY_CFG,risk:.001,dailyLimit:.005,maxPositions:1,maxExposure:.20,maxDrawdown:.02,minNetRewardRisk:1,takeProfitNetUSD:10.01,profile:'prudente-v2'};
export const policy=state=>state.config||LEGACY_CFG;
export function entryPlan(cash,equity,price,dist,cfg=CFG){
 if(!(price>dist&&dist>0&&equity>0&&cash>0))return null;
 const stop=price-dist,risk=price*(1+cfg.fee)-stop*(1-cfg.slippage)*(1-cfg.fee);
 const conservativeRisk=dist+price*(2*cfg.fee+cfg.slippage);
 const qty=Math.max(0,Math.min(equity*cfg.risk/conservativeRisk,cash/(price*(1+cfg.fee)),equity*(cfg.maxExposure??1)/(price*(1+cfg.fee))));
 if(!qty)return null;
 const cost=qty*price*(1+cfg.fee);
 const target=Math.max(price+cfg.reward*dist,cfg.takeProfitNetUSD?(cost+cfg.takeProfitNetUSD)/(qty*(1-cfg.slippage)*(1-cfg.fee)):0);
 const gain=target*(1-cfg.slippage)*(1-cfg.fee)-price*(1+cfg.fee);
 if(cfg.minNetRewardRisk&&(gain<=0||gain/risk<cfg.minNetRewardRisk))return null;
 return {qty,entry:price,stop,target,cost,plannedRisk:qty*risk,plannedNetReward:qty*gain,targetMovePct:100*(target/price-1)};
}

export function ema(values,n){let v=values[0];return values.map(x=>(v+=2/(n+1)*(x-v)));}
export function wilder(values,n=14){let out=Array(values.length).fill(null);if(values.length<n)return out;let v=values.slice(0,n).reduce((a,b)=>a+b,0)/n;out[n-1]=v;for(let i=n;i<values.length;i++)out[i]=v=(v*(n-1)+values[i])/n;return out;}
export function enrich(rows){
 if(rows.length<101)throw Error('Historial insuficiente');
 const closes=rows.map(r=>r.close),fast=ema(closes,9),slow=ema(closes,21);
 const changes=closes.slice(1).map((x,i)=>x-closes[i]);
 const gains=wilder(changes.map(x=>Math.max(0,x))),losses=wilder(changes.map(x=>Math.max(0,-x)));
 const atr=wilder(rows.map((r,i)=>Math.max(r.high-r.low,Math.abs(r.high-closes[Math.max(0,i-1)]),Math.abs(r.low-closes[Math.max(0,i-1)]))));
 const a=ema(closes,12),b=ema(closes,26),macd=a.map((v,i)=>v-b[i]),ms=ema(macd,9);
 return rows.map((r,i)=>{
 let rsi=null;if(i>=14){let g=gains[i-1],l=losses[i-1];rsi=g===0&&l===0?50:l===0?100:100-100/(1+g/l);}
 let vm=i>=20?rows.slice(i-20,i).reduce((s,x)=>s+x.volume,0)/20:null;
 let signal='ESPERAR';if(i>=100){if(fast[i-1]<=slow[i-1]&&fast[i]>slow[i]&&rsi>50&&rsi<70&&r.volume>vm)signal='COMPRAR';else if(fast[i-1]>=slow[i-1]&&fast[i]<slow[i])signal='CERRAR';}
 return {...r,ema9:fast[i],ema21:slow[i],rsi14:rsi,atr14:atr[i],macd:macd[i],macdSignal:ms[i],volumeMean20:vm,signal};
 });
}
export function validate(rows,now){
 if(rows.length<101)throw Error('Faltan velas cerradas');
 for(let i=0;i<rows.length;i++){
 const r=rows[i];if(![r.time,r.open,r.high,r.low,r.close,r.volume].every(Number.isFinite)||r.time%300000!==0||r.time+300000>now||Math.min(r.open,r.high,r.low,r.close)<=0||r.volume<0||r.low>Math.min(r.open,r.close)||r.high<Math.max(r.open,r.close))throw Error('Datos OHLC inválidos');
 if(i&&r.time-rows[i-1].time!==300000)throw Error('Hueco en los datos; simulación detenida');
 }if(now-(rows.at(-1).time+300000)>600000)throw Error('Datos desactualizados');
 return rows;
}
export function equity(state,prices){const cfg=policy(state);return state.cash+Object.entries(state.positions).reduce((v,[s,p])=>v+p.qty*prices[s]*(1-cfg.slippage)*(1-cfg.fee),0);}
export function closePosition(state,s,price,time,reason,recordedAt=time){const cfg=policy(state);const p=state.positions[s],sell=price*(1-cfg.slippage),proceeds=p.qty*sell*(1-cfg.fee);state.cash+=proceeds;state.trades.push({symbol:s,entryTime:p.time,exitTime:time,entry:p.entry,exit:sell,quantity:p.qty,pnl:proceeds-p.cost,reason,recordedAt});state.events=state.events||[];state.events.push({id:'exit:'+s+':'+time+':'+p.time,botId:'crypto',type:'exit',symbol:s,simulatedAt:time,recordedAt,price:sell,quantity:p.qty,pnlUSD:proceeds-p.cost,reason});state.events=state.events.slice(-2000);delete state.positions[s];}
export function seed(series,now,config=CFG){return {version:2,config:{...config},policyChanges:[],protectionHalted:false,revision:0,startedAt:now,updatedAt:now,paused:false,cash:config.initial,positions:{},trades:[],events:[],curve:[],lastTime:series[SYMBOLS[0]].at(-1).time,day:null,dayStart:config.initial,halted:false,peak:config.initial,maxDrawdown:0,history:series,processed:0};}
export function advance(original,incoming,now){
 const state=structuredClone(original),cfg=policy(state);let series={};
 for(const s of SYMBOLS){let map=new Map(state.history[s].map(r=>[r.time,r]));for(const r of incoming[s])map.set(r.time,r);let rows=[...map.values()].sort((a,b)=>a.time-b.time);validate(rows,now);series[s]=enrich(rows);}
 const times=series[SYMBOLS[0]].map(r=>r.time);if(SYMBOLS.some(s=>series[s].length!==times.length||series[s].some((r,i)=>r.time!==times[i])))throw Error('Los activos tienen fechas diferentes');
 let processed=0;
 for(let i=101;i<times.length;i++){
 const time=times[i];if(time<=state.lastTime)continue;
 if(time-state.lastTime!==300000)throw Error('Faltan velas desde la última simulación');
 const day=new Date(time).toISOString().slice(0,10),open=Object.fromEntries(SYMBOLS.map(s=>[s,series[s][i].open]));
 let eo=equity(state,open);if(day!==state.day){state.day=day;state.dayStart=eo;state.halted=false;}
 if(eo<=state.dayStart*(1-cfg.dailyLimit))state.halted=true;
 if(cfg.maxDrawdown&&eo<=state.peak*(1-cfg.maxDrawdown))state.protectionHalted=true;
 for(const s of Object.keys(state.positions))if(state.paused||state.halted||state.protectionHalted||series[s][i-1].signal==='CERRAR')closePosition(state,s,open[s],time,state.protectionHalted?'proteccion_total':state.paused?'pausa':state.halted?'limite_diario':'cruce',now);
 if(!state.paused&&!state.halted&&!state.protectionHalted)for(const s of SYMBOLS){
 const prior=series[s][i-1];if(state.positions[s]||Object.keys(state.positions).length>=cfg.maxPositions||prior.signal!=='COMPRAR')continue;
 const price=open[s]*(1+cfg.slippage),dist=cfg.stopATR*prior.atr14;
 if(!(dist>0&&dist<price))continue;
 const plan=entryPlan(state.cash,eo,price,dist,cfg);if(!plan)continue;
 state.cash-=plan.cost;state.positions[s]={...plan,time};state.events=state.events||[];state.events.push({id:'entry:'+s+':'+time,botId:'crypto',type:'entry',symbol:s,simulatedAt:time,recordedAt:now,price:plan.entry,quantity:plan.qty,stop:plan.stop,target:plan.target,plannedRiskUSD:plan.plannedRisk});state.events=state.events.slice(-2000);
 }
 for(const s of Object.keys(state.positions)){const r=series[s][i],p=state.positions[s];if(r.low<=p.stop)closePosition(state,s,Math.min(r.open,p.stop),time,'stop',now);else if(r.high>=p.target)closePosition(state,s,p.target,time,'objetivo',now);}
 const prices=Object.fromEntries(SYMBOLS.map(s=>[s,series[s][i].close])),e=equity(state,prices);
 if(e<=state.dayStart*(1-cfg.dailyLimit))state.halted=true;
 if(cfg.maxDrawdown&&e<=state.peak*(1-cfg.maxDrawdown))state.protectionHalted=true;
 state.peak=Math.max(state.peak,e);state.maxDrawdown=Math.max(state.maxDrawdown,1-e/state.peak);
 state.curve.push({time:time+300000,equity:e});state.lastTime=time;processed++;
 }
 state.history=Object.fromEntries(SYMBOLS.map(s=>[s,series[s].map(({time,open,high,low,close,volume})=>({time,open,high,low,close,volume}))]));
 state.updatedAt=now;state.processed+=processed;state.revision++;return state;
}
export function view(state){
 if(!state)return {initialized:false};const cfg=policy(state);
 const prices=Object.fromEntries(SYMBOLS.map(s=>[s,state.history[s].at(-1).close])),eq=equity(state,prices);
 return {initialized:true,startedAt:state.startedAt,updatedAt:state.updatedAt,paused:state.paused,halted:state.halted,cash:state.cash,equity:eq,pnl:eq-cfg.initial,maxDrawdown:state.maxDrawdown,positions:state.positions,trades:state.trades.slice(-500),tradeCount:state.trades.length,activity:activityLog(state),curve:state.curve.slice(-4000),processed:state.processed,dayStart:state.dayStart,lastTime:state.lastTime,markets:Object.fromEntries(SYMBOLS.map(s=>[s,enrich(state.history[s]).at(-1)])),candles:Object.fromEntries(SYMBOLS.map(s=>[s,state.history[s].slice(-120)])),config:cfg,protectionHalted:!!state.protectionHalted,policyChanges:state.policyChanges||[]};
}

export function applyConservative(state,now){
 if(state.config?.profile===CFG.profile)return state;
 for(const s of Object.keys(state.positions))closePosition(state,s,state.history[s].at(-1).close,now,'cambio_perfil_prudente');
 state.policyChanges=state.policyChanges||[];state.policyChanges.push({time:now,from:policy(state).profile||'original-v1',to:CFG.profile,cash:state.cash});
 state.config={...CFG};state.version=2;state.protectionHalted=false;state.revision++;return state;
}

export function activityLog(state){
 const events=new Map((state.events||[]).map(e=>[e.id,e]));
 const entry=(symbol,p)=>{const id='entry:'+symbol+':'+p.time;if(!events.has(id))events.set(id,{id,botId:'crypto',type:'entry',symbol,simulatedAt:p.time,recordedAt:null,price:p.entry,quantity:p.qty});};
 for(const t of state.trades){entry(t.symbol,{time:t.entryTime,entry:t.entry,qty:t.quantity});const id='exit:'+t.symbol+':'+t.exitTime+':'+t.entryTime;if(!events.has(id))events.set(id,{id,botId:'crypto',type:'exit',symbol:t.symbol,simulatedAt:t.exitTime,recordedAt:t.recordedAt??null,price:t.exit,quantity:t.quantity,pnlUSD:t.pnl,reason:t.reason});}
 for(const [s,p] of Object.entries(state.positions))entry(s,p);
 return [...events.values()].sort((a,b)=>b.simulatedAt-a.simulatedAt||(a.type==='exit'?-1:1)).slice(0,500);
}
