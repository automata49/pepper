import unittest
from datetime import date,timedelta
from pepper.technical import calculate,classify,percentiles
from pepper.fundamentals import ttm_flow
from pepper.journal import ledger,check_plan,ticker

def bars(n=300):
    return [dict(date=(date(2025,1,1)+timedelta(days=i)).isoformat(),open=100+i,high=102+i,low=99+i,close=101+i,volume=1000) for i in range(n)]

class AutomationTests(unittest.TestCase):
    def test_indicators(self):
        b=bars();m=calculate(b,b,b[-1]['date'])
        self.assertAlmostEqual(m['ma21'],390)
        self.assertAlmostEqual(m['atr20'],3)
        self.assertEqual(m['rs_12m'],0)
        self.assertEqual(m['volume_ratio20'],1)
    def test_duplicate_bar(self):
        b=bars()
        with self.assertRaises(ValueError):calculate(b+[b[-1]],b,b[-1]['date'])
    def test_future_excluded(self):
        b=bars();m=calculate(b,b,b[-2]['date'])
        self.assertEqual(m['price'],399)
    def test_missing_benchmark(self):
        b=bars();m=calculate(b,[],b[-1]['date'])
        self.assertEqual(classify(m,{})['status'],'DATA_REQUIRED')
    def test_percentile_ties(self):
        a={'a':{'rs_1m':2},'b':{'rs_1m':2},'c':{'rs_1m':1}}
        percentiles(a)
        self.assertEqual(a['a']['rs_1m_percentile'],75)
    def test_ttm_no_ytd_double_count(self):
        p=[dict(start='2024-01-01',end='2024-12-31',val=100,filed='2025-02-01'),dict(start='2024-01-01',end='2024-06-30',val=40,filed='2024-08-01'),dict(start='2025-01-01',end='2025-06-30',val=60,filed='2025-08-01')]
        self.assertEqual(ttm_flow(p,'2025-06-30')['val'],120)
    def test_ledger_partial_sale(self):
        base=dict(ticker='TEST',currency='USD',account='A',date='2025-01-01',fee=1)
        t=[dict(base,id='1',action='BUY',quantity=10,price=10),dict(base,id='2',action='SELL',quantity=4,price=20)]
        r=ledger(t,'2025-01-02')
        self.assertTrue(r['complete']);self.assertAlmostEqual(r['positions'][0]['cost'],60.6)
        self.assertAlmostEqual(r['positions'][0]['realized'],38.6)
    def test_oversell_blocked(self):
        t=[dict(id='1',ticker='T',currency='USD',date='2025-01-01',fee=0,action='SELL',quantity=1,price=10)]
        r=ledger(t,'2025-01-02');self.assertFalse(r['complete']);self.assertIsNone(r['win_rate'])
    def test_plan(self):
        p=dict(quantity=10,entry=100,stop=90,target=130,fx=1,action='BUY')
        r=check_plan(p,10000,1000,0);self.assertEqual(r['status'],'PASS');self.assertEqual(r['reward_risk'],3)
        self.assertIn('CASH',check_plan(p,10000,500,0)['status'])
    def test_kr_ticker(self):
        self.assertEqual(ticker(660,'KR'),'000660')

if __name__=='__main__':unittest.main()
