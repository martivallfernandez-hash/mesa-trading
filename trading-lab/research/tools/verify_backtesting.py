"""Prueba de integración con precios sintéticos. No mide rentabilidad real."""
import warnings
import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
class OneTrade(Strategy):
    def init(self):pass
    def next(self):
        if len(self.data)==10:self.buy(size=1)
        elif len(self.data)==20:self.position.close()

def verify():
    close=100+np.arange(40)*.1
    data=pd.DataFrame({'Open':close,'High':close+1,'Low':close-1,'Close':close,'Volume':100},index=pd.date_range('2026-01-01',periods=40,freq='5min'))
    free=Backtest(data,OneTrade,cash=1000,commission=0,spread=0).run()
    costs=Backtest(data,OneTrade,cash=1000,commission=.004,spread=.001).run()
    assert int(costs['# Trades'])==1
    assert int(costs['_trades'].iloc[0]['EntryBar'])==10
    assert costs['Equity Final [$]']<free['Equity Final [$]']
    print('Backtesting.py 0.6.6: importación, entrada en apertura siguiente y efecto de costes verificados con datos sintéticos.')
if __name__=='__main__':verify()
