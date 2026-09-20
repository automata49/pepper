import copy
import json
import unittest
from pathlib import Path
from pepper.engine import evaluate, attribution, dupont
from pepper.reports import comparison
from pepper.sheets import parse_ranges, SCHEMA

FIXTURE = Path(__file__).parents[1] / 'examples/demo.json'


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.s = json.loads(FIXTURE.read_text())

    def test_demo_reconciles_native_sheet(self):
        r = evaluate(self.s)
        self.assertEqual(r['issues'], [])
        p = r['portfolio']
        self.assertEqual(p['nav'], 7900000)
        self.assertEqual(p['planned_cash'], 4949350)
        self.assertEqual(p['fees'], 650)
        self.assertAlmostEqual(r['valuation']['DEMO_US']['required_eps_cagr'], .1)

    def test_zero_means_liquidate_blank_means_hold(self):
        self.s['tables']['Portfolio'][0]['계획 수량'] = 0
        p = evaluate(self.s)['portfolio']['positions']
        self.assertEqual(p[0]['planned_value'], 0)
        self.assertEqual(p[0]['trade'], -1300000)
        self.assertEqual(p[1]['target'], 20)

    def test_missing_price_does_not_understate_nav(self):
        self.s['tables']['Prices'][0]['현재가'] = None
        p = evaluate(self.s)['portfolio']
        self.assertFalse(p['complete'])
        self.assertNotIn('nav', p)

    def test_duplicate_price_blocks_nav(self):
        self.s['tables']['Prices'].append(copy.deepcopy(self.s['tables']['Prices'][0]))
        self.assertFalse(evaluate(self.s)['portfolio']['complete'])

    def test_future_and_stale_price_block_nav(self):
        for d in (46284, 46000):
            with self.subTest(d=d):
                self.s['tables']['Prices'][0]['가격일'] = d
                self.assertFalse(evaluate(self.s)['portfolio']['complete'])

    def test_demo_cannot_be_live(self):
        self.s['settings'][0] = 'Live'
        r = evaluate(self.s)
        self.assertFalse(r['portfolio']['complete'])
        self.assertFalse(r['growth'])

    def test_missing_stop_is_unknown_risk(self):
        self.s['tables']['Portfolio'][0]['손절 기준'] = None
        p = evaluate(self.s)['portfolio']
        self.assertIsNone(p['positions'][0]['risk'])
        self.assertTrue(p['risk_incomplete'])

    def test_overspend_and_concentration_flagged(self):
        self.s['tables']['Portfolio'][0]['계획 수량'] = 100
        p = evaluate(self.s)['portfolio']
        self.assertLess(p['planned_cash'], 0)
        self.assertTrue(any('비중' in x for x in p['warnings']))

    def test_stop_breached_is_warning_not_safe(self):
        self.s['tables']['Portfolio'][0]['손절 기준'] = 110
        p = evaluate(self.s)['portfolio']['positions'][0]
        self.assertEqual(p['risk'], 0)
        self.assertIn('손절 기준 이탈', p['warnings'])

    def test_shapley_reconciles(self):
        g = evaluate(self.s)['growth']['DEMO_US']
        self.assertAlmostEqual(sum(g['roe_drivers'].values()), g['roe_change'])
        self.assertAlmostEqual(attribution([1, 1, 1], [2, 1, 1])['margin'], 1.)

    def test_negative_equity_is_not_roe(self):
        self.s['tables']['Financials'][0]['평균 자기자본'] = -1
        self.assertNotIn('DEMO_US', evaluate(self.s)['growth'])

    def test_comparability_and_currency(self):
        self.s['tables']['Financials'][1]['연결 범위'] = 'Separate'
        self.assertNotIn('roe_drivers', evaluate(self.s)['growth']['DEMO_US'])
        self.s['tables']['Financials'][0]['통화'] = 'KRW'
        self.assertNotIn('DEMO_US', evaluate(self.s)['valuation'])

    def test_evidence_requires_source(self):
        r = self.s['tables']['Research'][0]
        r['판정'], r['평가일'] = 'PASS', 46283
        actual = evaluate(self.s)['research']['DEMO_US']['Swing']['Trend']
        self.assertEqual(actual['verdict'], 'UNKNOWN')
        r['출처 URL'] = 'DEMO'
        self.assertEqual(evaluate(self.s)['research']['DEMO_US']['Swing']['Trend']['verdict'], 'PASS')

    def test_conflicting_same_date_is_unknown(self):
        r = self.s['tables']['Research'][0]
        r.update({'판정': 'PASS', '평가일': 46283, '출처 URL': 'DEMO'})
        other = dict(r, ID='DEMO-other', 판정='FAIL')
        self.s['tables']['Research'].append(other)
        self.assertEqual(evaluate(self.s)['research']['DEMO_US']['Swing']['Trend']['verdict'], 'UNKNOWN')

    def test_fx_date_guard_even_cash_only(self):
        self.s['settings'][3] = 46000
        with self.assertRaises(ValueError):
            evaluate(self.s)

    def test_weekly_refuses_short_interval(self):
        r = evaluate(self.s)
        old = dict(r, asof='2026-09-17')
        self.assertIn('비교 불가', comparison(r, old, 7)[0])

    def test_schema_rejects_changed_header_and_overflow(self):
        ranges = {'Settings': [[v] for v in self.s['settings']]}
        for name, headers in SCHEMA['headers'].items():
            ranges[name] = [headers] + [[r[k] for k in headers] for r in self.s['tables'][name]]
        self.assertEqual(parse_ranges(ranges), self.s)
        ranges['Portfolio'] += [[] for _ in range(100)] + [['overflow']]
        with self.assertRaises(ValueError):
            parse_ranges(ranges)


if __name__ == '__main__':
    unittest.main()
