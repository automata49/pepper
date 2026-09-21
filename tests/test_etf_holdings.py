import unittest
from unittest.mock import patch
from pepper.etf_holdings import holding, parse_globalx, parse_roundhill, security_universe, validate


class ETFTests(unittest.TestCase):
    def test_globalx_footer_cash_and_korean_symbol(self):
        data = 'Fund\nFund Holdings Data as of 09/18/2026\n% of Net Assets,Ticker,Name,SEDOL\n99.9,053800 KS,Ahnlab,id\n0.1,,CASH,\nLegal footer\n'
        rows = parse_globalx(data, 'BUG', 'https://example.com/data.csv')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['ticker'], '053800')
        self.assertEqual(rows[0]['market'], 'KR')
        self.assertEqual(len(security_universe(rows)), 1)

    def test_swaps_and_collateral_are_not_extra_stock_candidates(self):
        header = 'Account,Date,StockTicker,CUSIP,SecurityName,Weightings,MoneyMarketFlag\n'
        data = header + 'DRAM,09/21/2026,MU,595112103,Micron,25%,\nDRAM,09/21/2026,595112103 TRS 052427 GS,595112103 TRS 052427 GS,Micron SWAP,25%,\nDRAM,09/21/2026,FGXXX,id,Money market,50%,Y\n'
        rows = parse_roundhill(data, 'DRAM', 'https://example.com/data.csv')
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(security_universe(rows)), 1)
        self.assertEqual(rows[1]['instrument_type'], 'Swap')
        self.assertEqual(rows[0]['asof'], '2026-09-21')
        self.assertIn('minus one', rows[0]['date_note'])

    def test_unknown_swap_and_venue_stay_unverified(self):
        r = holding('DRAM', 'BTMTQT8 TRS X', 'CXMT', 100, 'Swap', 'BTMTQT8 TRS X', '2026-09-21', 'source')
        self.assertEqual(r['ticker'], '')
        self.assertEqual(security_universe([r]), [])
        r = holding('DRAM', 'SKHY', 'SK hynix', 100, 'Equity', 'id', '2026-09-21', 'source')
        self.assertEqual(r['market'], 'UNVERIFIED')

    def test_bad_weights_and_mixed_dates_rejected(self):
        with self.assertRaises(ValueError):
            holding('X', 'Y', 'Name', 'NaN', 'Equity', '', '2026-09-21', '')
        a = holding('X', 'Y', 'Name', 50, 'Equity', '', '2026-09-21', '')
        with self.assertRaises(ValueError):
            validate([a])
        b = dict(a, asof='2026-09-20')
        with self.assertRaises(ValueError):
            validate([a, b])

    def test_foreign_candidate_is_not_routed_to_dart(self):
        from pepper.pipeline import run
        config = {'universe': [{'ticker': '4716', 'market': 'JP', 'benchmark': 'SPY'}]}
        with patch('pepper.pipeline.collect', return_value=[]) as collect:
            result = run(config, '2026-09-18')
        self.assertEqual(result['instruments']['JP:4716']['swing']['status'], 'COVERAGE_PENDING')
        self.assertEqual(collect.call_count, 1)  # benchmark only


if __name__ == '__main__':
    unittest.main()
