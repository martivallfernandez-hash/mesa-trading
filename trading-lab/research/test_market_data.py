import csv
import tempfile
import unittest
from pathlib import Path
from market_data import closed_rows, save_csv


def candle(timestamp=0):
    return [timestamp, '100', '110', '90', '105', '12', timestamp + 299999]


class DataTests(unittest.TestCase):
    def test_open_candle_is_excluded(self):
        self.assertEqual(len(closed_rows([candle(), candle(300000)], 450000)), 1)

    def test_just_closed_candle_is_included(self):
        self.assertEqual(len(closed_rows([candle()], 300000)), 1)

    def test_bad_data_is_rejected(self):
        for data in ([candle(), candle()], [candle(300000), candle()],
                     [[0, 'nan', 110, 90, 105, 12, 299999]], {'error': 'denied'}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                closed_rows(data, 900000)

    def test_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.csv'
            save_csv(path, closed_rows([candle()], 300000))
            with path.open() as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 1)
            self.assertEqual(float(rows[0]['close']), 105)


if __name__ == '__main__':
    unittest.main()
