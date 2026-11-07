import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mt5_reader import collect,upload
class MT5:
    ACCOUNT_TRADE_MODE_DEMO=0;TIMEFRAME_M5=5
    def __init__(self,mode=0):self.mode=mode;self.price_reads=0
    def account_info(self):return NS(trade_mode=self.mode,login=123456,password='never-export',server='Broker-Demo',currency='EUR')
    def terminal_info(self):return NS(connected=True)
    def symbol_info(self,s):return NS(trade_contract_size=100,volume_min=.01,volume_step=.01,volume_max=10,digits=2,currency_profit='USD',trade_mode=4)
    def symbol_select(self,*a):return True
    def symbol_info_tick(self,s):self.price_reads+=1;return NS(bid=2000,ask=2000.2,time=300,time_msc=300000)
    def copy_rates_from_pos(self,*a):return [dict(time=0,open=2000,high=2001,low=1999,close=2000,tick_volume=10),dict(time=600,open=2000,high=2001,low=1999,close=2000,tick_volume=10)]
class ReaderTests(unittest.TestCase):
    def test_real_and_contest_accounts_rejected_before_prices(self):
        for mode in (1,2):
            mt=MT5(mode)
            with self.assertRaises(RuntimeError):collect(mt,{'XAUUSD':'XAUUSD'},now=700)
            self.assertEqual(mt.price_reads,0)
    def test_no_credentials_or_account_login_exported(self):
        data=collect(MT5(),{'XAUUSD':'XAUUSD'},now=700)
        self.assertFalse(data['executionEnabled']);self.assertNotIn('login',data['account']);self.assertNotIn('password',str(data))
    def test_weekend_old_tick_is_stale_and_does_not_shift_candle_times(self):
        data=collect(MT5(),{'XAUUSD':'XAUUSD'},now=86400)
        self.assertFalse(data['quotes']['XAUUSD']['fresh']);self.assertEqual(data['candles']['XAUUSD'][0]['time'],0)
    def test_open_candles_excluded(self):
        data=collect(MT5(),{'XAUUSD':'XAUUSD'},now=700)
        self.assertEqual(len(data['candles']['XAUUSD']),1)
    def test_insecure_upload_refused_without_network(self):
        with self.assertRaises(ValueError):upload({},'http://example.com','abc')
        with self.assertRaises(ValueError):upload({},'https://example.com','')
if __name__=='__main__':unittest.main()
