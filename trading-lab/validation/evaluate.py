"""Comparación preregistrada; no optimiza parámetros ni cambia el bot desplegado."""
import csv
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
from analysis import ema, enrich


def prepare(rows, strategy):
    converted=[dict(timestamp_utc=datetime.fromtimestamp(r['time'],timezone.utc).isoformat(),**{k:r[k] for k in ('open','high','low','close','volume')}) for r in rows]
    out=enrich(converted);closes=[r['close'] for r in rows]
    e55,e200=ema(closes,55),ema(closes,200)
    for i,row in enumerate(out):
        signal='ESPERAR'
        if i>=200:
            if strategy=='ema_cross':signal=row['signal']
            elif strategy=='channel_breakout':
                if row['close']>max(r['high'] for r in rows[i-20:i]) and row['close']>e200[i]:signal='COMPRAR_SIMULADO'
                elif row['close']<row['ema21']:signal='CERRAR_SIMULADO'
            elif strategy=='trend_pullback':
                if row['ema21']>e55[i] and row['close']>e200[i] and out[i-1]['rsi14']<=45<row['rsi14']:signal='COMPRAR_SIMULADO'
                elif row['close']<e55[i]:signal='CERRAR_SIMULADO'
            else:raise ValueError('Estrategia desconocida')
        row['signal']=signal;row['time']=rows[i]['time']
    return out


def plan(cash,equity,price,dist,risk,costs):
    fee,slip=costs['fee_per_side'],costs['slippage_per_side']
    if not 0<dist<price:return None
    qty=max(0,min(equity*risk['risk_fraction']/(dist+price*(2*fee+slip)),cash/(price*(1+fee)),equity*risk['max_exposure']/(price*(1+fee))))
    if not qty:return None
    cost=qty*price*(1+fee)
    target=max(price+risk['target_atr_multiple']*dist,(cost+risk['net_target_usd'])/(qty*(1-slip)*(1-fee)))
    return dict(qty=qty,entry=price,cost=cost,stop=price-dist,target=target,target_move_pct=100*(target/price-1))


def bootstrap_interval(pnls):
    if len(pnls)<10:return None
    rng=random.Random(42);means=[];n=len(pnls)
    for _ in range(1000):
        sample=[]
        while len(sample)<n:
            start=rng.randrange(n);sample.extend(pnls[(start+j)%n] for j in range(min(5,n)))
        means.append(sum(sample[:n])/n)
    means.sort();return [means[25],means[974]]


def simulate(series,start,end,risk,costs):
    symbols=sorted(series);cash=risk['initial_usd'];positions={};trades=[];day=None;day_start=cash;halted=False;blocked=False;peak=cash;dd=0;exposures=[];curve=[]
    fee,slip=costs['fee_per_side'],costs['slippage_per_side']
    def value(i,key):return cash+sum(p['qty']*series[s][i][key]*(1-slip)*(1-fee) for s,p in positions.items())
    def close(s,price,i,reason):
        nonlocal cash
        p=positions.pop(s);exit_price=price*(1-slip);proceeds=p['qty']*exit_price*(1-fee);cash+=proceeds
        trades.append(dict(symbol=s,entry_time=p['time'],exit_time=series[s][i]['time'],entry=p['entry'],exit=exit_price,pnl_usd=proceeds-p['cost'],reason=reason,required_target_move_pct=p['target_move_pct']))
    for i in range(max(start,201),end):
        stamp=series[symbols[0]][i]['time'];today=stamp//86400;eo=value(i,'open')
        if today!=day:day,day_start,halted=today,eo,False
        if eo<=day_start*(1-risk['daily_loss_pause']):halted=True
        if eo<=peak*(1-risk['total_drawdown_pause']):blocked=True
        for s in list(positions):
            reason='protection' if blocked else 'daily_pause' if halted else 'timeout' if i-positions[s]['index']>=risk['max_hold_bars'] else 'signal' if series[s][i-1]['signal']=='CERRAR_SIMULADO' else None
            if reason:close(s,series[s][i]['open'],i,reason)
        if not halted and not blocked:
            for s in symbols:
                if s in positions or len(positions)>=risk['max_positions'] or series[s][i-1]['signal']!='COMPRAR_SIMULADO':continue
                prior=series[s][i-1];p=plan(cash,eo,series[s][i]['open']*(1+slip),risk['stop_atr']*prior['atr14'],risk,costs)
                if p:
                    cash-=p['cost'];positions[s]=dict(p,time=stamp,index=i)
        for s in list(positions):
            bar,p=series[s][i],positions[s]
            if bar['low']<=p['stop']:close(s,min(bar['open'],p['stop']),i,'stop')
            elif bar['high']>=p['target']:close(s,p['target'],i,'target')
        equity=value(i,'close');peak=max(peak,equity);dd=max(dd,1-equity/peak)
        if equity<=day_start*(1-risk['daily_loss_pause']):halted=True
        if equity<=peak*(1-risk['total_drawdown_pause']):blocked=True
        exposures.append(sum(p['qty']*series[s][i]['close'] for s,p in positions.items())/equity)
        curve.append(dict(time=stamp,equity_usd=equity))
    for s in list(positions):close(s,series[s][end-1]['close'],end-1,'segment_end')
    pnls=[t['pnl_usd'] for t in trades];wins=sum(p for p in pnls if p>0);losses=-sum(p for p in pnls if p<0)
    stats=dict(initial_usd=risk['initial_usd'],final_usd=cash,net_profit_usd=cash-risk['initial_usd'],return_pct=100*(cash/risk['initial_usd']-1),trades=len(trades),wins=sum(p>0 for p in pnls),win_rate_pct=100*sum(p>0 for p in pnls)/len(pnls) if pnls else None,profit_factor=wins/losses if losses else None,mean_net_pnl_usd=sum(pnls)/len(pnls) if pnls else None,block_bootstrap_mean_95pct_usd=bootstrap_interval(pnls),max_drawdown_pct=dd*100,mean_exposure_pct=100*sum(exposures)/len(exposures) if exposures else 0,total_protection_triggered=blocked,mean_target_move_pct=sum(t['required_target_move_pct'] for t in trades)/len(trades) if trades else None)
    return stats,trades,curve


def qualifies(stats,rules):
    return stats['trades']>=rules['min_closed_trades'] and stats['net_profit_usd']>0 and stats['profit_factor'] is not None and stats['profit_factor']>=rules['min_profit_factor'] and stats['max_drawdown_pct']<=100*rules['max_drawdown_fraction']


def passive(series,start,end,initial,costs):
    # 20 % invertido por igual entre los activos; resto en efectivo, sin rebalanceo.
    allocation=initial*.2/len(series);final=initial*.8
    for rows in series.values():
        qty=allocation/(rows[start]['open']*(1+costs['slippage_per_side'])*(1+costs['fee_per_side']))
        final+=qty*rows[end-1]['close']*(1-costs['slippage_per_side'])*(1-costs['fee_per_side'])
    return dict(final_usd=final,net_profit_usd=final-initial,return_pct=100*(final/initial-1))


def main():
    protocol_path=ROOT/'validation/protocol.json';p=json.loads(protocol_path.read_text());manifest=json.loads((ROOT/'data/coinbase-15m/manifest.json').read_text())
    if hashlib.sha256(protocol_path.read_bytes()).hexdigest()!=manifest['protocol_sha256']:raise ValueError('El protocolo cambió después de la descarga')
    raw={}
    for symbol,info in manifest['files'].items():
        path=ROOT/'data/coinbase-15m'/f'{symbol}.csv'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Los datos cambiaron')
        with path.open() as f:raw[symbol]=[{k:int(v) if k=='time' else float(v) for k,v in row.items()} for row in csv.DictReader(f)]
    timeline=[r['time'] for r in next(iter(raw.values()))]
    if any([r['time'] for r in rows]!=timeline for rows in raw.values()):raise ValueError('Fechas distintas entre activos')
    n=len(timeline);a=int(n*.6);b=int(n*.8);rules=p['selection_on_development_only']
    # No se preparan indicadores ni se ejecuta ninguna estrategia sobre el tramo final.
    prepared={name:{s:prepare(rows[:b],name) for s,rows in raw.items()} for name in p['candidates']}
    development={};validation={};stress={}
    for name,series in prepared.items():
        development[name]=simulate(series,201,a,p['risk'],p['costs']['base'])[0]
    eligible=[name for name,stats in development.items() if qualifies(stats,rules)]
    selected=max(eligible,key=lambda name:development[name]['net_profit_usd']) if eligible else None
    if selected:
        validation[selected]=simulate(prepared[selected],a,b,p['risk'],p['costs']['base'])[0]
        stress[selected]=simulate(prepared[selected],a,b,p['risk'],p['costs']['stress'])[0]
    validation_pass=bool(selected and qualifies(validation[selected],rules) and qualifies(stress[selected],rules))
    report=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),protocol_sha256=manifest['protocol_sha256'],provider=p['source'],interval_minutes=15,rows_per_asset=n,symbols=list(raw),boundaries_utc={k:datetime.fromtimestamp(t,timezone.utc).isoformat() for k,t in [('start',timeline[0]),('validation_start',timeline[a]),('sealed_holdout_start',timeline[b]),('end_exclusive',timeline[-1]+900)]},development=development,selected_on_development=selected,validation=validation,stress=stress,benchmarks={'no_trade':{'return_pct':0},'passive_20pct_development':passive(raw,201,a,1000,p['costs']['base'])},sealed_holdout={'rows_per_asset':n-b,'evaluated':False,'eligible_for_future_one_time_evaluation':validation_pass},live_trading_enabled=False,decision='READY_FOR_SEALED_HOLDOUT_ONLY' if validation_pass else 'NO_CANDIDATE_APPROVED',limitations=['Candidates use 15-minute bars and are not the deployed 5-minute strategy.','Coinbase supplies historical prices; costs are assumptions, not verified execution fees.','Strategies and risk rules are hypotheses, not guarantees.','Historical qualification alone never authorizes real-money execution.','Block bootstrap uses blocks of five trades and does not establish a future success probability.'])
    out=ROOT/'reports';out.mkdir(exist_ok=True);(out/'validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
