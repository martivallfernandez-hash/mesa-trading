import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from download_history import audit
from evaluate import plan, prepare, qualifies, simulate
P=json.loads((Path(__file__).with_name('protocol.json')).read_text())

def rows(n=500):
    return [dict(time=i*900,open=100+i*.01,high=102+i*.01,low=99+i*.01,close=101+i*.01,volume=10+i%7) for i in range(n)]

class ValidationTests(unittest.TestCase):
    def test_all_candidate_signals_are_causal(self):
        data=rows()
        for name in P['candidates']:
            with self.subTest(strategy=name):self.assertEqual(prepare(data[:350],name),prepare(data,name)[:350])

    def test_missing_candles_cannot_be_silently_accepted(self):
        data=[[0,100,102,99,101,10],[1800,100,102,99,101,10]]
        with self.assertRaises(ValueError):audit(data,0,2700,900)

    def test_target_does_not_raise_position_size(self):
        risk=P['risk'];base=plan(1000,1000,100,2,risk,P['costs']['base'])
        lower=plan(1000,1000,100,2,{**risk,'net_target_usd':0},P['costs']['base'])
        self.assertEqual(base['qty'],lower['qty']);self.assertGreater(base['target'],lower['target'])
        self.assertLessEqual(base['cost'],200)
        net=base['qty']*base['target']*(1-.001)*(1-.004)-base['cost']
        self.assertGreaterEqual(net,10.01-1e-9)

    def test_stop_wins_if_both_levels_touch_and_entry_is_next_open(self):
        data=prepare(rows(205),'ema_cross')
        for r in data:r['signal']='ESPERAR'
        data[200]['signal']='COMPRAR_SIMULADO';data[201].update(open=110,high=200,low=1,close=110)
        stats,trades,_=simulate({'BTC-USD':data},201,205,P['risk'],P['costs']['base'])
        self.assertEqual(len(trades),1);self.assertEqual(trades[0]['reason'],'stop')
        self.assertAlmostEqual(trades[0]['entry'],110*1.001)
        self.assertLess(trades[0]['pnl_usd'],0);self.assertGreater(stats['final_usd'],0)

    def test_high_win_rate_without_net_profit_does_not_qualify(self):
        stats=dict(trades=100,net_profit_usd=-1,profit_factor=.9,max_drawdown_pct=.1)
        self.assertFalse(qualifies(stats,P['selection_on_development_only']))
        stats.update(net_profit_usd=1,profit_factor=1.2,trades=2)
        self.assertFalse(qualifies(stats,P['selection_on_development_only']))

    def test_one_position_and_pauses_are_shared_by_all_markets(self):
        data=prepare(rows(205),'ema_cross')
        for r in data:r['signal']='ESPERAR'
        data[200]['signal']='COMPRAR_SIMULADO'
        stats,trades,_=simulate({'BTC-USD':data,'ETH-USD':data},201,205,P['risk'],P['costs']['base'])
        self.assertEqual(len(trades),1)

if __name__=='__main__':unittest.main()
