import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from analysis import enrich
from research import Config, backtest, quantity, run


def bars(n=110):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [dict(timestamp_utc=(start + timedelta(minutes=5*i)).isoformat(),
                 open=100., high=100.5, low=99.5, close=100., volume=20.,
                 atr14=1., signal='ESPERAR') for i in range(n)]


class ResearchTests(unittest.TestCase):
    def test_indicators_do_not_read_future(self):
        rows = bars(140)
        for i, row in enumerate(rows):
            row['close'] = 100 + i / 20
            row['high'] = row['close'] + 1
            row['low'] = min(99, row['close'] - 1)
        self.assertEqual(enrich(rows[:120]), enrich(rows)[:120])

    def test_flat_rsi(self):
        self.assertEqual(enrich(bars())[-1]['rsi14'], 50)

    def test_cash_and_risk_cap(self):
        cfg = Config()
        qty = quantity(1000, 1000, 100, 2, cfg)
        self.assertLessEqual(qty * (2 + 100 * (2*cfg.fee + cfg.slippage)), 2.5)
        self.assertLessEqual(quantity(1, 1000, 100, 2, cfg) * 100 * (1+cfg.fee), 1)

    def test_next_open_and_stop_before_target(self):
        rows = bars()
        rows[100]['signal'] = 'COMPRAR_SIMULADO'
        rows[101].update(open=110., low=90., high=130., close=110.)
        cfg = replace(Config(), fee=0, slippage=0)
        _, trades, _ = backtest({'BTCUSD': rows}, cfg)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]['entry'], 110)
        self.assertEqual(trades[0]['reason'], 'stop')
        self.assertAlmostEqual(trades[0]['pnl_usd'], -2.5)

    def test_two_positions_limit(self):
        series = {s: bars() for s in ('BTCUSD', 'ETHUSD', 'SOLUSD')}
        for rows in series.values():
            rows[100]['signal'] = 'COMPRAR_SIMULADO'
        _, _, equity = backtest(series)
        self.assertEqual(equity[0]['positions'], 2)
        self.assertTrue(all(r['positions'] <= 2 for r in equity))

    def test_daily_halt_after_gap(self):
        rows = bars()
        rows[100]['signal'] = 'COMPRAR_SIMULADO'
        rows[102].update(open=10., low=9., high=10., close=10.)
        rows[102]['signal'] = 'COMPRAR_SIMULADO'
        _, trades, equity = backtest({'BTCUSD': rows})
        self.assertEqual(len(trades), 1)
        self.assertTrue(equity[-1]['daily_halted'])

    def test_failure_preserves_last_success_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            pointer = Path(directory) / 'LATEST'
            pointer.write_text('previous-run')
            with patch('research.fetch', side_effect=ValueError('unavailable')):
                with self.assertRaises(ValueError):
                    run(directory)
            self.assertEqual(pointer.read_text(), 'previous-run')

    def test_emergency_stop_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'STOP').touch()
            with patch('research.fetch') as fetch:
                with self.assertRaises(RuntimeError):
                    run(directory)
                fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
