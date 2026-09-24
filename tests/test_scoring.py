import copy
import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path

from pepper.bridge import score_inputs, rules_diff
from pepper.metrics import Facts
from pepper.metrics import valuation as V
from pepper.metrics.trend import derive_from_bars
from pepper.scoring.expr import evaluate, RuleError, Missing
from pepper.scoring.rules_loader import load_rules, apply_overrides, validate_profile, RulesError

EXAMPLE = Path(__file__).parents[1] / 'examples/scoring_inputs.json'


def bars(n=320, start=50.0, step=0.25, end='2026-09-22', vol=1_000_000):
    d0 = date.fromisoformat(end) - timedelta(days=n - 1)
    out, price = [], start
    for i in range(n):
        price = max(1.0, price + step)
        out.append({'date': (d0 + timedelta(days=i)).isoformat(), 'open': price, 'high': price * 1.01,
                    'low': price * 0.99, 'close': price, 'volume': vol})
    return out


class ExprTests(unittest.TestCase):
    def test_safe_expression(self):
        self.assertTrue(evaluate('value >= 0.3 and not flag', {'value': .4, 'flag': False}))
        self.assertTrue(evaluate("asset_type == 'crypto_treasury'", {'asset_type': 'crypto_treasury'}))
        with self.assertRaises(Missing):
            evaluate('equity <= 0', {})
        for bad in ["__import__('os')", 'value.real', '[1][0]', 'value if 1 else 0']:
            with self.assertRaises(RuleError):
                evaluate(bad, {'value': 1})


class RulesTests(unittest.TestCase):
    def test_default_rules_load_with_versions(self):
        r = load_rules()
        self.assertEqual(set(r['profiles']), {'minervini', 'buffett', 'fisher', 'lynch'})
        self.assertTrue(all(p['version'] for p in r['profiles'].values()))

    def test_invalid_rule_rejected(self):
        r = load_rules()
        prof = copy.deepcopy(r['profiles']['lynch'])
        prof['criteria'][0]['metric'] = 'no_such_metric'
        with self.assertRaises(RulesError):
            validate_profile('lynch', prof, r['exceptions']['tags'])
        prof = copy.deepcopy(r['profiles']['lynch'])
        prof['criteria'][0]['bands'] = [{'max': 1, 'score': 100}]   # 기본 band 없음
        with self.assertRaises(RulesError):
            validate_profile('lynch', prof, r['exceptions']['tags'])

    def test_override_marks_version_and_changes_result(self):
        inputs = json.loads(EXAMPLE.read_text())
        old = load_rules()
        new = apply_overrides(load_rules(), [{'profile': 'lynch', 'criterion': 'peg', 'field': 'bands',
                                              'value': [{'max': 3.0, 'score': 100, 'label': '완화'}, {'score': 0, 'label': '부담'}]}])
        self.assertIn('+override', new['profiles']['lynch']['version'])
        diff = rules_diff(inputs, old, new)
        self.assertTrue(any(c['ticker'] == 'DEMO_QUALITY' and c['profile'] == 'lynch' for c in diff['changes']))


class ValuationTests(unittest.TestCase):
    def facts(self, **kw):
        f = Facts(kw)
        f.derived['_rules'] = {'inputs': {'eps_growth_3y_basis': kw.pop('_basis', 'cumulative')}}
        return f

    def test_peg_basis_matches_sheet_when_cagr(self):
        # 시트 MU 행: Forward PER 6.43, EPS 성장 전망 175%, 시트 PEG 0.04
        f = self.facts(forward_pe=6.43, eps_growth_3y=1.75)
        f.derived['_rules']['inputs']['eps_growth_3y_basis'] = 'cagr'
        self.assertEqual(round(V.peg_forward(f, {}), 2), 0.04)

    def test_peg_cumulative_basis_is_stricter(self):
        f = self.facts(forward_pe=6.43, eps_growth_3y=1.75)
        g = 2.75 ** (1 / 3) - 1
        self.assertAlmostEqual(V.peg_forward(f, {}), 6.43 / (g * 100))
        self.assertAlmostEqual(V.peg_forward(f, {}), 0.1604, places=3)

    def test_eps_forecast_preferred(self):
        f = self.facts(forward_pe=10, eps_growth_3y=5.0, eps_forecast=[1, 1.1, 1.21])
        g, basis = V.forward_eps_cagr(f)
        self.assertAlmostEqual(g, .1)
        self.assertEqual(basis, 'eps_forecast')

    def test_dcf_known_value(self):
        self.assertAlmostEqual(V.dcf(1.0, 0.0, 0.10, 0.0, 10), 10.0)
        with self.assertRaises(ValueError):
            V.dcf(1.0, 0.0, 0.03, 0.03, 10)


class TrendTests(unittest.TestCase):
    def test_uptrend_passes_template(self):
        inputs = {'asof': '2026-09-22', 'tickers': {'UP': {'market': 'US', 'bars': bars(), 'facts': {'rs_percentile': 85}}}}
        r = score_inputs(inputs)['tickers']['UP']
        m = r['profiles']['minervini']
        tmpl = [c for c in m['criteria'] if c['group'] == 'template']
        self.assertTrue(all(c['status'] == 'OK' and c['score'] >= 50 for c in tmpl))
        self.assertIn(r['swing_status'], ('ACTIONABLE', 'EXTENDED', 'SETUP'))
        self.assertIsNotNone(r['reference']['fibonacci'])

    def test_downtrend_avoid(self):
        inputs = {'asof': '2026-09-22', 'tickers': {'DN': {'market': 'US', 'bars': bars(start=200, step=-0.3),
                                                           'facts': {'rs_percentile': 10}}}}
        self.assertEqual(score_inputs(inputs)['tickers']['DN']['swing_status'], 'AVOID')

    def test_short_history_requires_data(self):
        inputs = {'asof': '2026-09-22', 'tickers': {'NEW': {'market': 'US', 'bars': bars(n=60)}}}
        self.assertEqual(score_inputs(inputs)['tickers']['NEW']['swing_status'], 'DATA_REQUIRED')

    def test_vcp_from_bars(self):
        d = derive_from_bars(bars(), '2026-09-22')
        self.assertEqual(len(d['vcp_depths']), 3)
        self.assertAlmostEqual(d['ma200'], sum(b['close'] for b in bars()[-200:]) / 200)


class ExampleTests(unittest.TestCase):
    def setUp(self):
        self.inputs = json.loads(EXAMPLE.read_text())
        self.r = score_inputs(self.inputs)['tickers']

    def test_quality_company(self):
        q = self.r['DEMO_QUALITY']
        self.assertEqual(q['swing_status'], 'ACTIONABLE')
        self.assertAlmostEqual(q['stop_price'], 100 * 0.92)
        self.assertGreaterEqual(q['profiles']['buffett']['score'], 75)

    def test_unverified_qualitative_not_scored(self):
        fisher = self.r['DEMO_QUALITY']['profiles']['fisher']
        self.assertIn('management_depth', fisher['unverified'])
        item = next(c for c in fisher['criteria'] if c['id'] == 'management_depth')
        self.assertNotIn('score', item)
        moat = next(c for c in self.r['DEMO_QUALITY']['profiles']['buffett']['criteria'] if c['id'] == 'moat')
        self.assertEqual((moat['status'], moat['score']), ('OK', 80.0))

    def test_negative_equity_is_not_applicable(self):
        b = self.r['DEMO_NEGEQ']['profiles']['buffett']
        roe = next(c for c in b['criteria'] if c['id'] == 'roe_consistency')
        self.assertEqual(roe['status'], 'N_A')
        self.assertIn('negative_equity', self.r['DEMO_NEGEQ']['tags'])

    def test_nav_company_uses_nav_model(self):
        n = self.r['DEMO_NAV']
        self.assertEqual(n['valuation']['model'], 'NAV')
        peg = next(c for c in n['profiles']['lynch']['criteria'] if c['id'] == 'peg')
        self.assertEqual(peg['status'], 'N_A')

    def test_cyclical_skips_peg_and_flags_unverified_consensus(self):
        c = self.r['DEMO_CYCLE']
        peg = next(x for x in c['profiles']['lynch']['criteria'] if x['id'] == 'peg')
        self.assertEqual(peg['status'], 'N_A')
        warn = next(x for x in c['profiles']['lynch']['criteria'] if x['id'] == 'cyclical_peak_warning')
        self.assertEqual(warn['score'], 0.0)       # 정점의 낮은 PER 경고
        self.assertIsNone(c['valuation']['lynch_fair_value'])
        self.assertEqual(c['valuation']['label_status'], 'UNVERIFIED')

    def test_missing_is_not_zero(self):
        m = self.r['DEMO_CYCLE']['profiles']['minervini']
        self.assertIn('vcp', m['missing'])
        self.assertLess(m['coverage'], 1)
        ok = [c for c in m['criteria'] if c['status'] == 'OK']
        self.assertAlmostEqual(m['score'], round(sum(c['weight'] * c['score'] for c in ok) / sum(c['weight'] for c in ok), 1))

    def test_future_source_dropped(self):
        inputs = copy.deepcopy(self.inputs)
        t = inputs['tickers']['DEMO_QUALITY']
        t['sources']['consensus_eps']['asof'] = '2026-09-30'
        r = score_inputs(inputs)['tickers']['DEMO_QUALITY']
        self.assertAlmostEqual(r['valuation']['blended_eps'], 6.2)
        self.assertTrue(any('기준일 이후' in f for f in r['flags']))

    def test_result_is_json_serializable(self):
        json.dumps(score_inputs(self.inputs), allow_nan=False)


if __name__ == '__main__':
    unittest.main()
