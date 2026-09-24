import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from pepper import indicators as I
from pepper import watchlist as W
from pepper.sheet_cleanup import plan, references, run as clean_run
from pepper.sources.kis import KISClient, consensus_target
from pepper.sources.krx import KRXClient, adjust_splits, short_code
from pepper.sources.prices import fetch_all


def bars(n=320, start=50.0, step=0.25, end='2026-09-22', vol=1_000_000, wiggle=0.0):
    d0 = date.fromisoformat(end) - timedelta(days=n - 1)
    out, price = [], start
    for i in range(n):
        price = max(1.0, price + step + (wiggle if i % 2 else -wiggle))
        out.append({'date': (d0 + timedelta(days=i)).isoformat(), 'open': price, 'high': price * 1.01,
                    'low': price * 0.99, 'close': price, 'volume': vol})
    return out


class IndicatorTests(unittest.TestCase):
    def test_rsi_textbook_example(self):
        # Wilder 교재 예시(StockCharts 표 70.53/66.32는 평균을 소수 2자리로 반올림한 값)
        c = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
        self.assertAlmostEqual(I.rsi(c[:15]), 70.53, delta=0.1)
        self.assertAlmostEqual(I.rsi(c), 66.32, delta=0.1)
        self.assertIsNone(I.rsi(c[:14]))
        self.assertEqual(I.rsi([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]), 100.0)

    def test_macd_linear_trend_is_exact(self):
        # 직선 추세에서 EMA 지연 = 기울기×(n−1)/2 → MACD = 기울기×(25−11)/2 = 7×기울기, 히스토그램 0
        m = I.macd([100 + 2 * i for i in range(80)])
        self.assertAlmostEqual(m['macd'], 14.0, places=9)
        self.assertAlmostEqual(m['hist'], 0.0, places=9)
        self.assertIsNone(I.macd(list(range(30))))

    def test_stochastic_slow_bounds(self):
        up = [float(i) for i in range(1, 40)]
        s = I.stochastic_slow(up, [x - 1 for x in up], up)
        self.assertAlmostEqual(s['k'], 100.0)
        self.assertAlmostEqual(s['d'], 100.0)
        flat = [5.0] * 30
        self.assertEqual(I.stochastic_slow(flat, flat, flat)['k'], 50.0)
        self.assertIsNone(I.stochastic_slow(up[:18], up[:18], up[:18]))

    def test_signals(self):
        cfg = {}
        ind = {'rsi': 75, 'macd': {'hist': 0.2, 'hist_prev': -0.1},
               'stoch': {'k': 25, 'd': 20, 'k_prev': 15, 'd_prev': 18}}
        self.assertEqual(I.signals(ind, cfg), ['RSI 과열', 'MACD 상승 전환', 'Stoch 저점 반등'])
        self.assertEqual(I.signals({'rsi': 50, 'macd': None, 'stoch': None}, cfg), [])


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class KRXTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.calls = []

        def opener(req, timeout=30):
            self.calls.append(req.full_url)
            assert req.get_header('Auth_key') == 'k'
            day = req.full_url.split('basDd=')[1]
            if 'idx/' in req.full_url:
                rows = [{'IDX_NM': '코스피', 'CLSPRC_IDX': '2,500.5', 'OPNPRC_IDX': '2,490', 'HGPRC_IDX': '2,510',
                         'LWPRC_IDX': '2,480', 'ACC_TRDVOL': '100'}]
            elif 'etf_bydd' in req.full_url:
                rows = [{'ISU_CD': '069500', 'TDD_OPNPRC': '30000', 'TDD_HGPRC': '30500', 'TDD_LWPRC': '29900',
                         'TDD_CLSPRC': '30200', 'ACC_TRDVOL': '1,000', 'LIST_SHRS': '100'}]
            elif 'stk_bydd' in req.full_url:
                # 2026-09-22에 1:5 액면분할
                split = day >= '20260922'
                p, sh = ('14,000', '500') if split else ('70,000', '100')
                rows = [{'ISU_CD': 'KR7005930003', 'TDD_OPNPRC': p, 'TDD_HGPRC': p, 'TDD_LWPRC': p,
                         'TDD_CLSPRC': p, 'ACC_TRDVOL': '10', 'LIST_SHRS': sh}]
            else:
                rows = []
            return FakeResponse(json.dumps({'OutBlock_1': rows}).encode())
        self.client = KRXClient('k', cache=self.tmp, opener=opener, pause=0)

    def test_history_split_adjusted_and_cached(self):
        bars, index = self.client.history({'005930', '069500'}, ['KOSPI', 'KOSDAQ', 'ETF'], '2026-09-18', '2026-09-22',
                                          index_name='코스피')
        s = bars['005930']
        self.assertEqual([b['date'] for b in s], ['2026-09-18', '2026-09-21', '2026-09-22'])   # 주말 제외
        self.assertEqual([b['close'] for b in s], [14000, 14000, 14000])                        # 분할 보정
        self.assertEqual(s[0]['volume'], 50)
        self.assertEqual(index[-1]['close'], 2500.5)
        n = len(self.calls)
        self.client.history({'005930'}, ['KOSPI'], '2026-09-18', '2026-09-18')
        self.assertEqual(len(self.calls), n)   # 캐시 사용

    def test_short_code(self):
        self.assertEqual(short_code('KR7005930003'), '005930')
        self.assertEqual(short_code('0080G0'), '0080G0')

    def test_no_split_when_price_does_not_move(self):
        b = [{'date': '1', 'open': 10, 'high': 10, 'low': 10, 'close': 10, 'volume': 1, 'shares': 100},
             {'date': '2', 'open': 10, 'high': 10, 'low': 10, 'close': 10, 'volume': 1, 'shares': 300}]   # 유상증자
        self.assertEqual(adjust_splits(b)[0]['close'], 10)


class SourceRoutingTests(unittest.TestCase):
    def test_official_first_then_unofficial(self):
        class FakeKRX:
            available = True

            def history(self, codes, kinds, start, end, index_name=None):
                return {c: bars(end=end) for c in codes}, bars(end=end, start=2500)
        calls = []

        def fdr(sym, start, end):
            calls.append(sym)
            return bars(end=end)
        items = [{'ticker': '069500', 'market': 'KR'}, {'ticker': 'SPY', 'market': 'US'}]
        prices, benches, issues = fetch_all(items, '2026-09-22', {}, krx=FakeKRX(), fdr=fdr)
        self.assertTrue(prices['069500']['verified'])
        self.assertEqual(prices['069500']['provider'], 'KRX Open API')
        self.assertFalse(prices['SPY']['verified'])
        self.assertTrue(benches['KR']['verified'])
        self.assertEqual(calls, ['SPY', 'SPY'])   # 한국은 공식 출처로 끝나 비공식 호출 없음

    def test_no_krx_key_falls_back_and_labels_unofficial(self):
        class NoKey:
            available = False
        prices, benches, _ = fetch_all([{'ticker': '069500', 'market': 'KR'}], '2026-09-22', {},
                                       krx=NoKey(), fdr=lambda s, a, b: bars(end=b))
        self.assertIn('NAVER', prices['069500']['provider'])
        self.assertFalse(prices['069500']['verified'])


class KISTests(unittest.TestCase):
    def test_consensus_median_within_window(self):
        ops = [{'stck_bsop_date': '20260910', 'hts_goal_prc': '100000'},
               {'stck_bsop_date': '20260801', 'hts_goal_prc': '120000'},
               {'stck_bsop_date': '20260701', 'hts_goal_prc': '0'},          # 목표가 미제시
               {'stck_bsop_date': '20260301', 'hts_goal_prc': '50000'},      # 90일 밖
               {'stck_bsop_date': '20260930', 'hts_goal_prc': '999999'}]     # 기준일 이후
        c = consensus_target(ops, '2026-09-22')
        self.assertEqual((c['target_price'], c['count'], c['verified']), (110000, 2, True))
        self.assertIsNone(consensus_target([], '2026-09-22'))

    def test_token_cached_and_errors_surface(self):
        tmp = tempfile.mkdtemp()
        hits = []

        def opener(req, timeout=30):
            hits.append(req.full_url)
            if req.full_url.endswith('/oauth2/tokenP'):
                return FakeResponse(json.dumps({'access_token': 'T', 'expires_in': 86400}).encode())
            assert req.get_header('Authorization') == 'Bearer T'
            return FakeResponse(json.dumps({'rt_cd': '0', 'output': [{'stck_bsop_date': '20260920', 'hts_goal_prc': '1'}]}).encode())
        k = KISClient('a', 'b', cache=tmp, opener=opener)
        self.assertEqual(len(k.invest_opinions('005930', '2026-01-01', '2026-09-22')), 1)
        k2 = KISClient('a', 'b', cache=tmp, opener=opener)
        k2.invest_opinions('005930', '2026-01-01', '2026-09-22')
        self.assertEqual(sum(u.endswith('tokenP') for u in hits), 1)


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'etfs': [{'ticker': 'AAA', 'market': 'US', 'group': '미국 섹터', 'name': 'A'},
                             {'ticker': 'BBB', 'market': 'US', 'group': '미국 시장'},
                             {'ticker': 'LEV', 'market': 'US', 'group': '미국 시장', 'leveraged': 3},
                             {'ticker': 'OFF', 'market': 'US', 'group': '미국 시장', 'enabled': False}],
                    'stocks': [{'ticker': 'STK', 'market': 'US'}]}
        self.items = W.instruments(self.cfg)
        self.prices = {'AAA': {'bars': bars(step=0.4), 'provider': 'X', 'verified': True},
                       'BBB': {'bars': bars(step=0.1), 'provider': 'X', 'verified': True},
                       'LEV': {'bars': bars(step=0.9), 'provider': 'Y', 'verified': False},
                       'STK': {'bars': bars(step=0.3), 'provider': 'Y', 'verified': False}}
        self.benches = {'US': {'bars': bars(step=0.2, start=100), 'provider': 'X', 'verified': True}}
        self.fund = {'tickers': {'STK': {'facts': {'roe_ttm': 0.25, 'forward_pe': 20, 'eps_growth_3y': 0.5}},
                                 'H1': {'facts': {'forward_pe': 10}}, 'H2': {'facts': {'forward_pe': 40}}}}
        self.holdings = [{'etf': 'AAA', 'ticker': 'H1', 'name': 'Hold1', 'weight': 0.3, 'kind': 'Equity', 'asof': '2026-09-18'},
                         {'etf': 'AAA', 'ticker': 'H2', 'name': 'Hold2', 'weight': 0.1, 'kind': 'Equity', 'asof': '2026-09-18'},
                         {'etf': 'AAA', 'ticker': 'CASH', 'name': 'Cash', 'weight': 0.6, 'kind': 'Cash', 'asof': '2026-09-18'}]

    def test_board_rows(self):
        rows, issues = W.build(self.cfg, self.items, self.prices, self.benches, '2026-09-22', self.fund, self.holdings,
                               {'STK': {'target_price': 1}})
        by = {r['Ticker']: r for r in rows}
        self.assertNotIn('OFF', by)
        self.assertEqual([r['구분'] for r in rows][:3], ['ETF', 'ETF', 'ETF'])
        self.assertEqual(rows[-1]['Ticker'], 'STK')
        self.assertIsNone(by['LEV']['RS 백분위'])
        self.assertIn('레버리지', by['LEV']['경고'])
        self.assertEqual(by['AAA']['RS 백분위'], 100)          # ETF끼리 순위
        self.assertEqual(by['AAA']['상위10 비중'], 40.0)       # 현금 제외
        self.assertAlmostEqual(by['AAA']['가중 Fwd PER(상위10)'], 0.4 / (0.3 / 10 + 0.1 / 40), places=1)
        self.assertEqual(by['STK']['ROE'], 25.0)
        self.assertIsNotNone(by['STK']['PEG'])
        self.assertIn('비공식 가격', by['STK']['경고'])
        self.assertIsNotNone(by['AAA']['RSI14'])
        self.assertIn(by['AAA']['Swing Status'], ('ACTIONABLE', 'EXTENDED', 'SETUP', 'WATCH', 'AVOID'))
        json.dumps(rows, allow_nan=False)

    def test_manual_columns_preserved(self):
        rows = [{'Ticker': 'AAA'}, {'Ticker': 'BBB'}]
        existing = [W.COLUMNS, ['ETF', '', 'AAA'] + [''] * (len(W.COLUMNS) - 5) + ['0.09%', '핵심'],
                    ['ETF', '', 'GONE'] + [''] * (len(W.COLUMNS) - 5) + ['', '예전 메모']]
        rows, orphans = W.merge_manual(rows, existing)
        self.assertEqual(rows[0]['메모(입력)'], '핵심')
        self.assertEqual(orphans, [{'Ticker': 'GONE', '메모(입력)': '예전 메모'}])
        values = W.to_values(rows, orphans)
        self.assertEqual(values[-1][2], 'GONE')
        self.assertEqual(values[-1][-1], '예전 메모')
        with self.assertRaises(ValueError):
            W.merge_manual(rows, [W.COLUMNS, existing[1], existing[1]])

    def test_publish_overwrites_without_clearing(self):
        class Resp:
            def __init__(self, data=None):
                self.data = data or {}

            def raise_for_status(self):
                pass

            def json(self):
                return self.data

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, params=None, timeout=None):
                self.calls.append(('GET', url))
                if url.endswith('values/Watchlist_Board'):
                    return Resp({'values': [W.COLUMNS] + [['ETF', '', f'T{i}'] for i in range(5)]})
                return Resp({'sheets': [{'properties': {'title': 'Watchlist_Board'}}]})

            def put(self, url, params=None, json=None, timeout=None):
                self.calls.append(('PUT', url))
                self.values = json['values']
                return Resp()

            def post(self, url, json=None, timeout=None):
                self.calls.append(('POST', url))
                return Resp()
        s = Session()
        W.publish('sid', [{'Ticker': 'AAA'}], session=s)
        self.assertFalse(any(':clear' in u for _, u in s.calls))
        self.assertEqual(len(s.values), 6)   # 옛 행 수만큼 빈 행으로 덮어씀
        self.assertEqual(s.values[1][2], 'AAA')


class CleanupTests(unittest.TestCase):
    sheets = [{'title': 'Home', 'sheetId': 1, 'hidden': False},
              {'title': 'Price_US', 'sheetId': 2, 'hidden': False},
              {'title': 'Calc 1', 'sheetId': 3, 'hidden': True},
              {'title': 'Calc2', 'sheetId': 4, 'hidden': True},
              {'title': 'Old', 'sheetId': 5, 'hidden': True},
              {'title': 'Dyn', 'sheetId': 6, 'hidden': True},
              {'title': 'Chart src', 'sheetId': 7, 'hidden': True},
              {'title': 'Named', 'sheetId': 8, 'hidden': True}]

    def test_plan_keeps_dependencies(self):
        formulas = {'Price_US': [['=\'Calc 1\'!A1*2']], 'Calc 1': [['=Calc2!B2']], 'Home': [['=INDIRECT("Dyn!A1")']],
                    'Old': [['=Price_US!A1']]}
        p = plan(self.sheets, formulas, named_ranges=[{'range': {'sheetId': 8}}], chart_refs={'Home': {7}})
        self.assertEqual([d['title'] for d in p['delete']], ['Old'])
        reasons = {k['title']: k['reason'] for k in p['keep_hidden']}
        self.assertEqual(reasons['Calc2'], 'Calc 1에서 참조')
        self.assertIn('Chart src', reasons)
        self.assertIn('Named', reasons)

    def test_references_do_not_match_substrings(self):
        self.assertEqual(references('=MyCalc2!A1', ['Calc2']), set())
        self.assertEqual(references('=Calc2!A1', ['Calc2']), {'Calc2'})
        self.assertEqual(references('plain text Calc2!', ['Calc2']), set())

    def test_apply_aborts_without_backup(self):
        class Resp:
            def __init__(self, d):
                self.d = d

            def raise_for_status(self):
                pass

            def json(self):
                return self.d

        class S:
            posts = []

            def get(self, url, params=None, timeout=None):
                if 'batchGet' in url:
                    return Resp({'valueRanges': [{'values': []}, {'values': []}]})
                return Resp({'properties': {'title': 'T'}, 'sheets': [
                    {'properties': {'title': 'A', 'sheetId': 1}}, {'properties': {'title': 'B', 'sheetId': 2, 'hidden': True}}]})

            def post(self, url, json=None, timeout=None):
                self.posts.append(url)
                return Resp({})

        class Broken:
            def post(self, *a, **k):
                raise RuntimeError('drive denied')
        s = S()
        with self.assertRaises(RuntimeError):
            clean_run('sid', apply=True, session=s, backup_session=Broken())
        self.assertEqual(s.posts, [])   # 백업 실패 → 삭제 요청 없음
        dry = clean_run('sid', apply=False, session=s)
        self.assertEqual([d['title'] for d in dry['delete']], ['B'])
        self.assertFalse(dry['applied'])


class ConfigTests(unittest.TestCase):
    def test_default_config_has_60_etfs_and_dram_etf_only(self):
        cfg = W.load_config(Path(__file__).parents[1] / 'config/watchlist.yaml')
        etfs = cfg['etfs']
        self.assertEqual(len(etfs), 60)
        self.assertEqual(len({str(e['ticker']) for e in etfs}), 60)
        dram = next(e for e in etfs if e['ticker'] == 'DRAM')
        self.assertIs(dram['holdings'], False)
        self.assertTrue(all(isinstance(e['ticker'], str) for e in etfs))   # 한국 코드 앞자리 0 유지
        self.assertEqual(next(e for e in etfs if e['ticker'] == 'TQQQ')['leveraged'], 3)


if __name__ == '__main__':
    unittest.main()
