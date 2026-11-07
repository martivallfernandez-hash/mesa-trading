import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from market_data import closed_rows, save_csv
from monitor import archive


class ArchiveTests(unittest.TestCase):
    def test_repeated_cycles_do_not_duplicate_candles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'summary.json').write_text(json.dumps({'provider':'Kraken public OHLC', 'candles':{'BTCUSD':1}}))
            save_csv(root / 'BTCUSD_5m.csv', closed_rows([[0,100,110,90,105,12,299999]], 300000))
            database = root / 'history.sqlite3'
            self.assertEqual(archive(root, database), 1)
            self.assertEqual(archive(root, database), 1)
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute('select close from candles').fetchone()[0], 105)


if __name__ == '__main__':
    unittest.main()
