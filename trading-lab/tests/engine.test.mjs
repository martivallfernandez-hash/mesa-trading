import {test} from 'node:test';import assert from 'node:assert/strict';
import {seed,advance,enrich,validate,SYMBOLS,CFG,LEGACY_CFG,entryPlan,applyConservative} from '../worker/engine.mjs';
function bars(n=120){return Array.from({length:n},(_,i)=>({time:Date.UTC(2026,0,1)+i*300000,open:100,high:101,low:99,close:100,volume:20}));}
function series(n=120){return Object.fromEntries(SYMBOLS.map(s=>[s,bars(n)]));}
test('los indicadores no leen velas futuras',()=>{let r=bars(150);for(let i=0;i<r.length;i++){r[i].close+=i/100;r[i].high+=i/100;}assert.deepEqual(enrich(r).slice(0,120),enrich(r.slice(0,120)));assert.equal(enrich(bars()).at(-1).rsi14,50);});
test('no retroopera antes de crear la cuenta ni duplica velas',()=>{let data=series(),now=data.BTCUSD.at(-1).time+300000,s=seed(data,now);let a=advance(s,data,now);assert.equal(a.trades.length,0);assert.equal(a.processed,0);assert.equal(a.cash,CFG.initial);let next=series(121),b=advance(a,next,now+300000),c=advance(b,next,now+300000);assert.equal(b.processed,1);assert.equal(c.processed,1);assert.equal(c.curve.length,b.curve.length);});
test('rechaza velas abiertas, datos antiguos y huecos',()=>{let rows=bars(),now=rows.at(-1).time+300000;assert.throws(()=>validate(rows,now-1));assert.throws(()=>validate(rows,now+900000));rows.splice(80,1);assert.throws(()=>validate(rows,now));});
test('la pausa conserva saldo y evita nuevas entradas',()=>{let data=series(),now=data.BTCUSD.at(-1).time+300000,s=seed(data,now);s.paused=true;let next=advance(s,series(130),now+3000000);assert.equal(next.cash,1000);assert.equal(Object.keys(next.positions).length,0);assert.equal(next.processed,10);assert.equal(s.processed,0);});
test('un error no modifica el estado original',()=>{let data=series(),now=data.BTCUSD.at(-1).time+300000,s=seed(data,now),before=JSON.stringify(s);let invalid=series(121);invalid.ETHUSD.at(-1).close=-1;assert.throws(()=>advance(s,invalid,now+300000));assert.equal(JSON.stringify(s),before);});
test('indicadores y señales equivalen al motor Python sobre velas reales',async()=>{
 const {readFile}=await import('node:fs/promises'),fixture=JSON.parse(await readFile(new URL('./fixtures/python-parity.json',import.meta.url),'utf8'));
 const out=enrich(fixture.rows);for(let i=0;i<out.length;i++){
 for(const [js,py] of [['ema9','ema9'],['ema21','ema21'],['rsi14','rsi14'],['atr14','atr14'],['macd','macd'],['macdSignal','macd_signal']]){if(fixture.expected[i][py]===null)assert.equal(out[i][js],null);else assert.ok(Math.abs(out[i][js]-fixture.expected[i][py])<1e-9,js+' '+i);}
 const translate={ESPERAR:'ESPERAR',COMPRAR_SIMULADO:'COMPRAR',CERRAR_SIMULADO:'CERRAR'};assert.equal(out[i].signal,translate[fixture.expected[i].signal]);
 }
});
test('la cartera reproduce el backtest Python sobre 2.160 velas reales',async()=>{
 const {readFile}=await import('node:fs/promises'),{closePosition}=await import('../worker/engine.mjs');
 const f=JSON.parse(await readFile(new URL('./fixtures/portfolio-parity.json',import.meta.url),'utf8'));
 const first=Object.fromEntries(SYMBOLS.map(s=>[s,f.series[s].slice(0,101)])),now=f.series.BTCUSD.at(-1).time+300000;
 let state=advance(seed(first,first.BTCUSD.at(-1).time+300000,LEGACY_CFG),f.series,now);
 for(const s of Object.keys(state.positions))closePosition(state,s,f.series[s].at(-1).close,now,'fin_muestra');
 assert.equal(state.trades.length,f.expected.trades);assert.ok(Math.abs(state.cash-f.expected.capital_final_usd)<1e-8);
 for(let i=0;i<state.trades.length;i++)assert.ok(Math.abs(state.trades[i].pnl-f.trades[i].pnl_usd)<1e-8);
});
test('perfil prudente limita riesgo, exposición y objetivo sin subir la cantidad',()=>{
 const p=entryPlan(1000,1000,100,2),baseline=entryPlan(1000,1000,100,2,{...CFG,takeProfitNetUSD:0,minNetRewardRisk:0});
 assert.ok(p.plannedRisk<=1);assert.ok(p.cost<=200);assert.ok(p.plannedNetReward>=10.01-1e-9);assert.equal(p.qty,baseline.qty);assert.ok(p.target>baseline.target);assert.ok(p.targetMovePct>0);
 assert.ok(entryPlan(1,1000,100,2).cost<=1);
});
test('migrar el perfil no reinicia saldo, fecha ni historial',()=>{
 let s=seed(series(),Date.UTC(2026,0,2),LEGACY_CFG);s.cash=980;s.trades=[{pnl:-20}];let started=s.startedAt;applyConservative(s,Date.UTC(2026,0,3));
 assert.equal(s.cash,980);assert.equal(s.startedAt,started);assert.equal(s.trades.length,1);assert.equal(s.config.risk,.001);assert.equal(s.policyChanges.length,1);applyConservative(s,Date.UTC(2026,0,4));assert.equal(s.policyChanges.length,1);
});
test('protección total bloquea entradas y liquida una posición al siguiente paso',()=>{
 let data=series(),now=data.BTCUSD.at(-1).time+300000,s=seed(data,now);s.cash=950;s.positions.BTCUSD={qty:.1,entry:100,cost:10,time:now,stop:90,target:200};
 const next=advance(s,series(122),now+600000);assert.ok(next.protectionHalted);assert.equal(Object.keys(next.positions).length,0);assert.equal(next.trades[0].reason,'proteccion_total');
});
