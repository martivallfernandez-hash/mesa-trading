"""Indicadores causales y señales experimentales; solo posiciones al contado."""
import csv
from datetime import datetime
from pathlib import Path


def ema(values, period):
    output = []
    value = values[0]
    for number in values:
        value += 2 / (period + 1) * (number - value)
        output.append(value)
    return output


def wilder(values, period=14):
    output = [None] * len(values)
    if len(values) < period:
        return output
    value = sum(values[:period]) / period
    output[period - 1] = value
    for i in range(period, len(values)):
        value = (value * (period - 1) + values[i]) / period
        output[i] = value
    return output


def enrich(rows):
    if len(rows) < 100:
        raise ValueError('Se necesitan al menos 100 velas.')
    closes = [r['close'] for r in rows]
    fast, slow = ema(closes, 9), ema(closes, 21)
    macd = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26))]
    macd_signal = ema(macd, 9)
    changes = [closes[i] - closes[i - 1] for i in range(1, len(rows))]
    gains = wilder([max(x, 0) for x in changes])
    losses = wilder([max(-x, 0) for x in changes])
    ranges = [max(r['high'] - r['low'], abs(r['high'] - closes[max(0, i - 1)]),
                  abs(r['low'] - closes[max(0, i - 1)])) for i, r in enumerate(rows)]
    atr = wilder(ranges)
    output = []
    for i, row in enumerate(rows):
        rsi = None
        if i >= 14:
            gain, loss = gains[i - 1], losses[i - 1]
            rsi = 50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
        avg_volume = sum(r['volume'] for r in rows[max(0, i - 20):i]) / 20 if i >= 20 else None
        signal = 'ESPERAR'
        if i >= 100:
            if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i] and 50 < rsi < 70 and row['volume'] > avg_volume:
                signal = 'COMPRAR_SIMULADO'
            elif fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
                signal = 'CERRAR_SIMULADO'
        output.append(dict(row, ema9=fast[i], ema21=slow[i], rsi14=rsi, atr14=atr[i],
                           macd=macd[i], macd_signal=macd_signal[i], volume_mean20=avg_volume,
                           signal=signal))
    return output


def load(path):
    with Path(path).open() as source:
        rows = [{k: v if k == 'timestamp_utc' else float(v) for k, v in r.items()}
                for r in csv.DictReader(source)]
    stamps = [datetime.fromisoformat(r['timestamp_utc']).timestamp() for r in rows]
    if any(b - a != 300 for a, b in zip(stamps, stamps[1:])):
        raise ValueError('El análisis requiere velas consecutivas de cinco minutos.')
    return rows
