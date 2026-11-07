"""Datos públicos reproducibles. No necesita claves ni modifica la cuenta ficticia."""
import csv
import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

def timestamp(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())

def fetch_chunk(job):
    symbol, start, end, step = job
    cache=ROOT/'data/chunks'/f'{symbol}-{start}-{end}-{step}.json'
    if cache.exists():return symbol,json.loads(cache.read_text())
    def iso(t):return datetime.fromtimestamp(t, timezone.utc).isoformat().replace('+00:00','Z')
    query = urlencode(dict(start=iso(start), end=iso(end), granularity=step))
    url = f'https://api.exchange.coinbase.com/products/{symbol}/candles?{query}'
    for attempt in range(4):
        try:
            with urlopen(Request(url,headers={'User-Agent':'TradingLab-Research/1.0','Accept':'application/json'}), timeout=25) as response: rows=json.load(response)
            if not isinstance(rows, list):raise ValueError('Respuesta de velas inesperada')
            normalized=[[int(r[0]), float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5])]
                            for r in rows if start <= int(r[0]) < end]
            cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(json.dumps(normalized))
            return symbol,normalized
        except HTTPError as error:
            if error.code not in (429,500,502,503,504) or attempt==3:raise
            time.sleep(min(30, max(1, float(error.headers.get('Retry-After', 2**attempt)))))
        except (TimeoutError, URLError):
            if attempt==3:raise
            time.sleep(2**attempt)
    raise RuntimeError('Descarga incompleta')

def audit(rows, start, end, step):
    expected=list(range(start,end,step))
    if [r[0] for r in rows] != expected:raise ValueError('Faltan velas, hay duplicados o fechas incorrectas')
    for t,o,h,l,c,v in rows:
        if not all(math.isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or l>min(o,c) or h<max(o,c):raise ValueError('OHLCV inválido')

def main():
    protocol_bytes=(ROOT/'validation/protocol.json').read_bytes()
    protocol=json.loads(protocol_bytes)
    start,end,step=timestamp(protocol['start_utc']),timestamp(protocol['end_utc_exclusive']),protocol['interval_seconds']
    out=ROOT/'data/coinbase-15m';out.mkdir(parents=True,exist_ok=True)
    jobs=[(s,t,min(t+280*step,end),step) for s in protocol['symbols'] for t in range(start,end,280*step)]
    by_symbol={s:{} for s in protocol['symbols']}
    for symbol in protocol['symbols']:
        for cache in (ROOT/'data/chunks').glob(f'{symbol}-*-{step}.json'):
            for row in json.loads(cache.read_text()):
                if start<=row[0]<end:
                    if row[0] in by_symbol[symbol] and by_symbol[symbol][row[0]]!=row:raise ValueError('Versiones contradictorias de la misma vela')
                    by_symbol[symbol][row[0]]=row
    jobs=[j for j in jobs if not all(t in by_symbol[j[0]] for t in range(j[1],j[2],step))]
    print(f'Protocolo SHA256: {hashlib.sha256(protocol_bytes).hexdigest()}; {len(jobs)} consultas',flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(fetch_chunk,j) for j in jobs]
        for i,future in enumerate(as_completed(futures),1):
            symbol,rows=future.result();by_symbol[symbol].update({r[0]:r for r in rows})
            if i%20==0 or i==len(jobs):print(f'Descarga: {i}/{len(jobs)} consultas completas',flush=True)
    manifest=dict(provider=protocol['source'],protocol_sha256=hashlib.sha256(protocol_bytes).hexdigest(),downloaded_at_utc=datetime.now(timezone.utc).isoformat(),files={})
    for symbol,items in by_symbol.items():
        rows=sorted(items.values())
        missing=sorted(set(range(start,end,step))-set(items))
        if missing:
            print(json.dumps({'asset':symbol,'received':len(rows),'expected':len(range(start,end,step)),'missing':len(missing),'first_missing_utc':[datetime.fromtimestamp(t,timezone.utc).isoformat() for t in missing[:8]]}),flush=True)
        audit(rows,start,end,step)
        path=out/f'{symbol}.csv'
        with path.open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['time','open','high','low','close','volume']);writer.writerows(rows)
        manifest['files'][symbol]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2),flush=True)

if __name__=='__main__':main()
