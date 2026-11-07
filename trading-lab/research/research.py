"""Descarga, indicadores y backtest experimental. Sin ejecución de órdenes."""
import argparse
import csv
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from analysis import enrich, load
from market_data import SYMBOLS, fetch, save_csv


@dataclass(frozen=True)
class Config:
    capital_usd: float = 1000.0
    risk: float = 0.0025
    daily_limit: float = 0.01
    max_positions: int = 2
    fee: float = 0.004  # Hipótesis conservadora: 0,40 % en cada lado.
    slippage: float = 0.001  # Coste total adicional supuesto por lado.
    stop_atr: float = 1.5
    reward: float = 2.0


def quantity(cash, equity, price, distance, cfg):
    # Riesgo previsto incluye costes de entrada/salida y deslizamiento del stop.
    loss_per_unit = distance + price * (2 * cfg.fee + cfg.slippage)
    return max(0, min(equity * cfg.risk / loss_per_unit,
                      cash / (price * (1 + cfg.fee))))


def backtest(series, cfg=Config()):
    symbols = sorted(series)
    timeline = [r['timestamp_utc'] for r in series[symbols[0]]]
    if any([r['timestamp_utc'] for r in series[s]] != timeline for s in symbols):
        raise ValueError('Los activos deben compartir exactamente las mismas fechas.')
    cash, positions, trades = cfg.capital_usd, {}, []
    equity_path = []
    day, day_start, halted = None, cash, False
    peak, drawdown = cash, 0

    def exit_position(symbol, price, stamp, reason):
        nonlocal cash
        pos = positions.pop(symbol)
        sell = price * (1 - cfg.slippage)
        proceeds = pos['qty'] * sell * (1 - cfg.fee)
        cash += proceeds
        trades.append(dict(symbol=symbol, entry_time=pos['time'], exit_time=stamp,
                           entry=pos['entry'], exit=sell, quantity=pos['qty'],
                           pnl_usd=proceeds - pos['cost'], reason=reason))

    for i in range(101, len(timeline)):
        stamp = timeline[i]
        # Valor de liquidación en la apertura: incluye coste supuesto de salida.
        equity_open = cash + sum(p['qty'] * series[s][i]['open'] * (1 - cfg.slippage) * (1 - cfg.fee)
                                 for s, p in positions.items())
        if stamp[:10] != day:
            day, day_start, halted = stamp[:10], equity_open, False
        if equity_open <= day_start * (1 - cfg.daily_limit):
            halted = True
        # Señales de la vela anterior; ejecución en la apertura siguiente.
        for s in list(positions):
            if halted or series[s][i - 1]['signal'] == 'CERRAR_SIMULADO':
                exit_position(s, series[s][i]['open'], stamp, 'limite_diario' if halted else 'cruce')
        # Se evita abrir y cerrar el mismo activo en esta misma apertura.
        if not halted:
            for s in symbols:
                prior, current = series[s][i - 1], series[s][i]
                if s in positions or len(positions) >= cfg.max_positions or prior['signal'] != 'COMPRAR_SIMULADO':
                    continue
                distance = cfg.stop_atr * prior['atr14']
                price = current['open'] * (1 + cfg.slippage)
                if distance <= 0 or distance >= price:
                    continue
                qty = quantity(cash, equity_open, price, distance, cfg)
                if qty <= 0:
                    continue
                cost = qty * price * (1 + cfg.fee)
                cash -= cost
                positions[s] = dict(qty=qty, entry=price, cost=cost, time=stamp,
                                    stop=price - distance, target=price + cfg.reward * distance)
        for s in list(positions):
            bar, p = series[s][i], positions[s]
            # Si toca ambos, se aplica el stop; un hueco adverso sale a la apertura.
            if bar['low'] <= p['stop']:
                exit_position(s, min(bar['open'], p['stop']), stamp, 'stop')
            elif bar['high'] >= p['target']:
                exit_position(s, p['target'], stamp, 'objetivo')
        equity = cash + sum(p['qty'] * series[s][i]['close'] * (1 - cfg.slippage) * (1 - cfg.fee)
                            for s, p in positions.items())
        if equity <= day_start * (1 - cfg.daily_limit):
            halted = True  # Se cierra a la siguiente apertura, con posibles huecos.
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
        equity_path.append(dict(timestamp_utc=stamp, equity_usd=equity,
                                positions=len(positions), daily_halted=halted))
    for s in list(positions):
        exit_position(s, series[s][-1]['close'], timeline[-1], 'fin_muestra')
    return dict(capital_initial_usd=cfg.capital_usd, capital_final_usd=cash,
                pnl_usd=cash - cfg.capital_usd, return_pct=100 * (cash / cfg.capital_usd - 1),
                max_drawdown_pct=drawdown * 100, trades=len(trades),
                wins=sum(t['pnl_usd'] > 0 for t in trades)), trades, equity_path


def write_table(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(root, refresh=True):
    # Carpeta nueva por ejecución: un fallo nunca presenta CSV antiguos como actuales.
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'STOP').exists():
        raise RuntimeError('Parada solicitada mediante STOP.')
    run_dir = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    series = {}
    for symbol in SYMBOLS:
        path = run_dir / f'{symbol}_5m.csv'
        if refresh:
            save_csv(path, fetch(symbol))
        else:
            raise ValueError('Este comando exige una descarga nueva.')
        series[symbol] = enrich(load(path))
        write_table(run_dir / f'{symbol}_indicators.csv', series[symbol])
    stats, trades, equity = backtest(series)
    write_table(run_dir / 'trades.csv', trades)
    write_table(run_dir / 'equity.csv', equity)
    summary = dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),
                   provider='Kraken public OHLC', quote_currency='USD',
                   mode='RESEARCH_ONLY', live_trading_enabled=False,
                   sample_start=series[SYMBOLS[0]][0]['timestamp_utc'],
                   sample_end=series[SYMBOLS[0]][-1]['timestamp_utc'],
                   candles={s: len(v) for s, v in series.items()},
                   latest_signals={s: v[-1]['signal'] for s, v in series.items()},
                   assumptions=vars(Config()), backtest=stats,
                   limitations=['Muestra de unas 60 horas: no valida rentabilidad.',
                                'Capital ficticio de 1.000 USD, sin conversión EUR/USD.',
                                'Costes hipotéticos; no representan una cuenta contratada.',
                                'No hay órdenes ni paper trading persistente en tiempo real.',
                                'El límite diario puede superarse por huecos y costes.'])
    (run_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    latest_tmp = root / 'LATEST.tmp'
    latest_tmp.write_text(run_dir.name)
    os.replace(latest_tmp, root / 'LATEST')
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print('Resultados:', run_dir)
    return run_dir


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='runs')
    args = parser.parse_args()
    run(args.output)
