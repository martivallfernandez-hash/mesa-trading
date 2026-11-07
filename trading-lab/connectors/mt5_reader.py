"""Lectura de MT5 demo en Windows. No envía ni modifica órdenes."""
import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen

DEFAULT_SYMBOLS={'EURUSD':'EURUSD','GBPUSD':'GBPUSD','AUDUSD':'AUDUSD','XAUUSD':'XAUUSD','BTCUSD':'BTCUSD','ETHUSD':'ETHUSD','SOLUSD':'SOLUSD'}

def number(value):
    value=float(value)
    if not math.isfinite(value):raise ValueError('Valor numérico no válido')
    return value


def collect(mt5,mapping=None,now=None):
    now=time.time() if now is None else now
    info=mt5.account_info();terminal=mt5.terminal_info()
    if info is None or terminal is None or not terminal.connected:raise RuntimeError('MT5 no está conectado a una cuenta.')
    if info.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:raise RuntimeError('Solo se admite una cuenta DEMO. Lectura cancelada.')
    account_ref=hashlib.sha256((str(info.server)+':'+str(info.login)).encode()).hexdigest()[:16]
    data={'schemaVersion':1,'source':'MetaTrader5 demo terminal','generatedAt':int(now*1000),'account':{'mode':'demo','reference':account_ref,'currency':info.currency},'executionEnabled':False,'quotes':{},'candles':{},'unavailable':{}}
    for canonical,broker_symbol in (mapping or DEFAULT_SYMBOLS).items():
        if canonical not in DEFAULT_SYMBOLS or not isinstance(broker_symbol,str) or not broker_symbol or len(broker_symbol)>80:raise ValueError('Mapa de instrumentos no permitido')
        spec=mt5.symbol_info(broker_symbol)
        if spec is None or not mt5.symbol_select(broker_symbol,True):
            data['unavailable'][canonical]='Símbolo no disponible: indicar el nombre exacto del bróker.';continue
        tick=mt5.symbol_info_tick(broker_symbol)
        if tick is None:
            data['unavailable'][canonical]='No se recibió una cotización.';continue
        bid,ask=number(tick.bid),number(tick.ask)
        source_ms=int(getattr(tick,'time_msc',0) or tick.time*1000)
        if bid<=0 or ask<bid or source_ms>now*1000+60000:
            data['unavailable'][canonical]='Cotización inválida.';continue
        data['quotes'][canonical]={'brokerSymbol':broker_symbol,'bid':bid,'ask':ask,'sourceTime':source_ms,'fresh':0<=now*1000-source_ms<=120000,'contractSize':number(spec.trade_contract_size),'volumeMin':number(spec.volume_min),'volumeStep':number(spec.volume_step),'volumeMax':number(spec.volume_max),'digits':int(spec.digits),'profitCurrency':spec.currency_profit,'tradeMode':int(spec.trade_mode)}
        rates=mt5.copy_rates_from_pos(broker_symbol,mt5.TIMEFRAME_M5,0,220)
        candles=[]
        if rates is not None:
            for r in rates:
                stamp=int(r['time'])*1000
                # MT5 entrega tiempos UTC. No se infiere un desfase con ticks de un mercado cerrado.
                if stamp+300000>now*1000:continue
                o,h,l,c=map(number,(r['open'],r['high'],r['low'],r['close']))
                if stamp%300000 or min(o,h,l,c)<=0 or l>min(o,c) or h<max(o,c):raise ValueError('Vela inválida')
                candles.append({'time':stamp,'open':o,'high':h,'low':l,'close':c,'tickVolume':int(r['tick_volume'])})
        if any(b['time']<=a['time'] for a,b in zip(candles,candles[1:])):raise ValueError('Velas desordenadas o duplicadas')
        data['candles'][canonical]=candles
    return data


def upload(snapshot,url,token):
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('El receptor debe ser HTTPS y no contener credenciales en la URL.')
    if not token:raise ValueError('Falta el token del receptor de datos, no una contraseña del bróker.')
    request=Request(url,data=json.dumps(snapshot).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token},method='POST')
    with urlopen(request,timeout=20) as response:
        if response.status not in (200,201,202,204):raise RuntimeError('El receptor no aceptó los datos.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=Path('mt5-demo-snapshot.json'));parser.add_argument('--upload',action='store_true');args=parser.parse_args()
    try:import MetaTrader5 as mt5
    except ImportError:raise SystemExit('Falta la integración de MetaTrader 5 para Python en el equipo Windows. Revisa la guía del proyecto.')
    terminal=os.environ.get('MT5_TERMINAL_PATH')
    initialized=mt5.initialize(path=terminal,timeout=20000) if terminal else mt5.initialize(timeout=20000)
    if not initialized:raise SystemExit('No se pudo conectar con el terminal MT5 local.')
    try:
        mapping=json.loads(os.environ.get('MT5_SYMBOL_MAP','null'))
        snapshot=collect(mt5,mapping)
        args.output.write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
        if args.upload:upload(snapshot,os.environ.get('TRADING_RELAY_URL',''),os.environ.get('TRADING_RELAY_TOKEN',''))
        print('Lectura demo completada. No se han enviado órdenes. Instrumentos:',len(snapshot['quotes']))
    finally:mt5.shutdown()

if __name__=='__main__':main()
