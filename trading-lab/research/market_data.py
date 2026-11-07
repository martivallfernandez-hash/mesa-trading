"""Fase 1: datos públicos. No contiene funciones para enviar órdenes."""
import argparse
import csv
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

SYMBOLS = ('BTCUSD', 'ETHUSD', 'SOLUSD')
FIELDS = ('timestamp_utc', 'open', 'high', 'low', 'close', 'volume')
INTERVAL_MS = 300_000


def closed_rows(candles, now_ms):
    if not isinstance(candles, list):
        raise ValueError('El proveedor no ha devuelto una lista de velas.')
    result = []
    previous = None
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 7:
            raise ValueError('Vela incompleta o mal formada.')
        timestamp = int(candle[0])
        if timestamp % INTERVAL_MS or int(candle[6]) != timestamp + INTERVAL_MS - 1:
            raise ValueError('Intervalo de vela incorrecto.')
        if previous is not None and timestamp <= previous:
            raise ValueError('Velas duplicadas o desordenadas.')
        previous = timestamp
        values = [float(v) for v in candle[1:6]]
        opening, high, low, close, volume = values
        if (not all(math.isfinite(v) for v in values)
                or min(opening, high, low, close) <= 0 or volume < 0
                or low > min(opening, close) or high < max(opening, close)):
            raise ValueError('Precios o volumen inválidos.')
        if timestamp + INTERVAL_MS > now_ms:
            continue
        result.append((datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(), *values))
    if not result:
        raise ValueError('No se han recibido velas cerradas.')
    return result


def fetch(symbol):
    if symbol not in SYMBOLS:
        raise ValueError('Activo no permitido.')
    pair = 'XBTUSD' if symbol == 'BTCUSD' else symbol
    base = 'https://api.kraken.com/0/public/'
    with urlopen(base + 'Time', timeout=20) as response:
        clock = json.load(response)
    if clock.get('error'):
        raise ValueError('Kraken ha rechazado la consulta de hora.')
    now_ms = int(clock['result']['unixtime']) * 1000
    with urlopen(base + f'OHLC?pair={pair}&interval=5', timeout=20) as response:
        payload = json.load(response)
    if payload.get('error'):
        raise ValueError('Kraken ha rechazado la consulta OHLC.')
    series = [v for k, v in payload['result'].items() if k != 'last']
    if len(series) != 1:
        raise ValueError('Respuesta OHLC inesperada.')
    # Kraken usa segundos y sitúa el volumen en la columna 6.
    candles = [[int(c[0]) * 1000, *c[1:5], c[6],
                int(c[0]) * 1000 + INTERVAL_MS - 1] for c in series[0]]
    rows = closed_rows(candles, now_ms)
    last_ms = int(datetime.fromisoformat(rows[-1][0]).timestamp() * 1000)
    if now_ms - (last_ms + INTERVAL_MS) > 2 * INTERVAL_MS:
        raise ValueError('Datos de mercado desactualizados.')
    return rows


def save_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8',
                                         dir=path.parent, delete=False) as output:
            temporary = output.name
            writer = csv.writer(output)
            writer.writerow(FIELDS)
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/kraken'))
    args = parser.parse_args()
    failures = 0
    for symbol in SYMBOLS:
        try:
            rows = fetch(symbol)
            save_csv(args.output / f'{symbol}_5m.csv', rows)
            print(f'{symbol}: {len(rows)} velas cerradas; última: {rows[-1][0]} UTC')
        except HTTPError as error:
            failures += 1
            print(f'{symbol}: HTTP {error.code}; descarga rechazada. No se actualiza el CSV.', file=sys.stderr)
            if error.code in (403, 418, 429, 451):
                print('Proceso detenido: revisar acceso o límite del proveedor antes de reintentar.', file=sys.stderr)
                return 1
        except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as error:
            failures += 1
            print(f'{symbol}: descarga fallida ({type(error).__name__}); no se actualiza el CSV.', file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
