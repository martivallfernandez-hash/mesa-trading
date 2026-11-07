"""Recolector periódico de datos públicos. No mantiene una cuenta de trading."""
import argparse
import csv
import json
import logging
import sqlite3
import time
from pathlib import Path
from research import run


def archive(run_dir, database):
    summary = json.loads((run_dir / 'summary.json').read_text())
    with sqlite3.connect(database) as connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS candles (
            provider TEXT NOT NULL, symbol TEXT NOT NULL, timestamp_utc TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY(provider, symbol, timestamp_utc))''')
        for symbol in summary['candles']:
            with (run_dir / f'{symbol}_5m.csv').open() as source:
                records = [(summary['provider'], symbol, row['timestamp_utc'],
                            *[float(row[k]) for k in ('open','high','low','close','volume')])
                           for row in csv.DictReader(source)]
            connection.executemany('INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)', records)
        return connection.execute('SELECT count(*) FROM candles').fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--continuous', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('runs'))
    parser.add_argument('--interval', type=int, default=300)
    args = parser.parse_args()
    if args.interval < 300:
        parser.error('El intervalo mínimo es de 300 segundos.')
    args.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    while True:
        if (args.output / 'STOP').exists():
            logging.info('Parada solicitada. No se harán nuevas consultas.')
            return 0
        try:
            run_dir = run(args.output)
            count = archive(run_dir, args.output / 'history.sqlite3')
            logging.info('Ciclo completado: %s; %s velas únicas archivadas.', run_dir, count)
        except Exception:
            # Un error no inicia una ejecución de órdenes ni borra datos previos.
            logging.exception('Ciclo fallido. Los resultados anteriores no son datos actuales.')
            return 1  # Supervisor humano o servicio con reintento acotado por systemd.
        if not args.continuous:
            return 0
        # Pausas cortas para respetar STOP; no queda un proceso oculto iniciado por defecto.
        for _ in range(args.interval):
            if (args.output / 'STOP').exists():
                return 0
            time.sleep(1)


if __name__ == '__main__':
    raise SystemExit(main())
