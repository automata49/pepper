"""Recalculate from raw inputs, never trust editable sheet output formulas."""
import itertools
import math
from collections import Counter, defaultdict
from datetime import date, timedelta

ITEMS = {'Swing': ['Trend', 'RS', 'Volume', 'Entry', 'Risk'],
         'Growth': ['C', 'A', 'N', 'S', 'L', 'I', 'M', 'DuPont', 'CashFlow', 'Valuation']}


def blank(v):
    return v is None or v == ''


def number(v, name, minimum=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f'{name}: numeric input required')
    if minimum is not None and v < minimum:
        raise ValueError(f'{name}: must be >= {minimum}')
    return v


def day(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return date(1899, 12, 30) + timedelta(days=v)
    return date.fromisoformat(str(v)[:10])


def fresh(v, asof, age, name):
    d = day(v)
    if not 0 <= (asof - d).days <= age:
        raise ValueError(f'{name}: future or stale date')
    return d


def source(v, mode):
    if mode == 'Demo' and v == 'DEMO':
        return
    if not isinstance(v, str) or not v.startswith(('https://', 'http://')):
        raise ValueError('Source URL required')


def dupont(row):
    revenue = number(row['매출'], 'revenue', 1e-12)
    ni = number(row['순이익'], 'net income')
    assets = number(row['평균 총자산'], 'average assets', 1e-12)
    equity = number(row['평균 자기자본'], 'average equity', 1e-12)
    if equity / assets < .02:
        raise ValueError('Thin equity: DuPont interpretation deferred')
    factors = [ni / revenue, revenue / assets, assets / equity]
    cfo = number(row['영업현금흐름'], 'CFO')
    capex = number(row['CAPEX 지출'], 'CAPEX', 0)
    return {'factors': factors, 'roe': math.prod(factors), 'fcf': cfo - capex,
            'cash_conversion': cfo / ni if ni > 0 else None}


def attribution(before, after):
    """Symmetric Shapley attribution; contributions sum to ROE delta."""
    contributions = [0., 0., 0.]
    for order in itertools.permutations(range(3)):
        current = list(before)
        for i in order:
            old = math.prod(current)
            current[i] = after[i]
            contributions[i] += (math.prod(current) - old) / 6
    return dict(zip(['margin', 'turnover', 'leverage'], contributions))


def evaluate(snapshot):
    if snapshot.get('schema') != 'pepper-sheets-v1':
        raise ValueError('Unknown snapshot schema')
    s = snapshot['settings']
    mode, asof = s[0], day(s[1])
    if mode not in ('Demo', 'Live'):
        raise ValueError('Settings mode must be Demo or Live')
    fx = number(s[2], 'FX', 1e-12)
    cash = number(s[4], 'KRW cash', 0) + number(s[5], 'USD cash', 0) * fx
    weight_limit = number(s[6], 'weight limit', 0)
    risk_limit = number(s[7], 'risk limit', 0)
    ages = [number(s[i], 'max age', 0) for i in (8, 9, 10)]
    fresh(s[3], asof, ages[0], 'FX')
    fee = number(s[11], 'fee', 0)
    stress, fx_stress = number(s[12], 'stock stress', -1), number(s[13], 'FX stress', -1)
    if weight_limit > 1 or risk_limit > 1 or fee >= 1:
        raise ValueError('Limits must be fractions in [0,1], fee < 1')
    tables = snapshot['tables']
    issues, prices, financials, valuations = [], {}, {}, {}
    def check_ticker(ticker):
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError('Ticker must be text; preserve Korean leading zeros')
        if mode == 'Live' and ticker.startswith('DEMO'):
            raise ValueError('Replace DEMO rows before Live')
    counts = Counter(r['Ticker'] for r in tables['Prices'])
    for r in tables['Prices']:
        t = r['Ticker']
        try:
            check_ticker(t)
            if counts[t] != 1 or r['가격 검토'] != 'Reviewed':
                raise ValueError('Duplicate or unreviewed price')
            if (r['시장'], r['통화']) not in [('US', 'USD'), ('KR', 'KRW')]:
                raise ValueError('Market/currency mismatch')
            fresh(r['가격일'], asof, ages[0], 'price')
            source(r['출처 URL'], mode)
            number(r['현재가'], 'price', 1e-12)
            prices[t] = r
        except (ValueError, TypeError) as e:
            issues.append(f'Prices/{t}: {e}')
    fc = Counter((r['Ticker'], r['기간 역할']) for r in tables['Financials'])
    for r in tables['Financials']:
        t, role = r['Ticker'], r['기간 역할']
        try:
            check_ticker(t)
            if fc[t, role] != 1 or role not in ('Current', 'Previous'):
                raise ValueError('Duplicate/invalid financial period')
            if r['통화'] not in ('USD', 'KRW') or r['연결 범위'] not in ('Consolidated', 'Separate'):
                raise ValueError('Currency/scope required')
            filed = fresh(r['공시일'], asof, ages[2] if role == 'Current' else 100000, 'filing')
            if day(r['TTM 종료일']) > filed:
                raise ValueError('Period ends after filing')
            source(r['출처 URL'], mode)
            number(r['TTM EPS'], 'EPS')
            financials[t, role] = {'inputs': r, **dupont(r)}
        except (ValueError, TypeError) as e:
            issues.append(f'Financials/{t}/{role}: {e}')
    growth = {}
    for (t, role), current in financials.items():
        if role != 'Current':
            continue
        g = {k: v for k, v in current.items() if k != 'inputs'}
        previous = financials.get((t, 'Previous'))
        if previous:
            a, b = previous['inputs'], current['inputs']
            if all(a[k] == b[k] for k in ('통화', '연결 범위')) and 330 <= (day(b['TTM 종료일']) - day(a['TTM 종료일'])).days <= 400:
                g['roe_change'] = current['roe'] - previous['roe']
                g['roe_drivers'] = attribution(previous['factors'], current['factors'])
            else:
                issues.append(f'Financials/{t}: incomparable periods/currency/scope; no ROE attribution')
        growth[t] = g
    vc = Counter(r['Ticker'] for r in tables['Valuation'])
    for r in tables['Valuation']:
        t = r['Ticker']
        try:
            check_ticker(t)
            if vc[t] != 1 or blank(r['가정 근거']):
                raise ValueError('Duplicate/missing valuation rationale')
            fresh(r['검토일'], asof, ages[1], 'valuation')
            p, fin = prices[t], financials[t, 'Current']['inputs']
            if p['통화'] != fin['통화']:
                raise ValueError('EPS/price currency mismatch')
            years = number(r['기간 년'], 'years', 1e-12)
            pe = number(r['말기 PER'], 'terminal PE', 1e-12)
            eps = number(fin['TTM EPS'], 'positive EPS', 1e-12)
            g = number(r['EPS 성장 가정'], 'growth', -.999999)
            hurdle = number(r['요구수익률'], 'hurdle', -.999999)
            price = p['현재가']
            required = (price * (1 + hurdle) ** years / (eps * pe)) ** (1 / years) - 1
            terminal = eps * (1 + g) ** years * pe
            valuations[t] = {'required_eps_cagr': required, 'assumed_eps_cagr': g,
                             'growth_headroom': g - required, 'terminal_price': terminal,
                             'price_return_cagr': (terminal / price) ** (1 / years) - 1,
                             'assumptions': {k: r[k] for k in ('기간 년', '말기 PER', '요구수익률', '가정 근거')}}
        except (ValueError, TypeError, KeyError, OverflowError) as e:
            issues.append(f'Valuation/{t}: unavailable ({e})')
    evidence = defaultdict(list)
    rc = Counter(r['ID'] for r in tables['Research'])
    for r in tables['Research']:
        t, lens, item = r['Ticker'], r['전략'], r['평가 항목']
        try:
            check_ticker(t)
            if lens not in ITEMS or item not in ITEMS[lens] or rc[r['ID']] != 1 or blank(r['ID']):
                raise ValueError('Invalid lens/item or duplicate/missing ID')
            if r['판정'] not in ('PASS', 'FAIL', 'UNKNOWN'):
                raise ValueError('Invalid verdict')
            if r['판정'] == 'UNKNOWN':
                if not blank(r['평가일']):
                    fresh(r['평가일'], asof, ages[1], 'evidence')
                    evidence[t, lens, item].append(r)
                continue
            fresh(r['평가일'], asof, ages[1], 'evidence')
            source(r['출처 URL'], mode)
            if any(blank(r[k]) for k in ('평가 근거', '판단 기준', '다음 확인 조건')):
                raise ValueError('Rationale, criterion and next check required')
            evidence[t, lens, item].append(r)
        except (ValueError, TypeError) as e:
            issues.append(f'Research/{t}/{item}: {e}')
    research = {}
    tickers = set(prices) | {r['Ticker'] for r in tables['Research'] if isinstance(r['Ticker'], str)}
    for t in sorted(tickers):
        research[t] = {}
        for lens, items in ITEMS.items():
            research[t][lens] = {}
            for item in items:
                rows = sorted(evidence.get((t, lens, item), []), key=lambda r: day(r['평가일']), reverse=True)
                latest = rows[0] if rows else None
                conflict = len(rows) > 1 and day(rows[0]['평가일']) == day(rows[1]['평가일'])
                research[t][lens][item] = {'verdict': latest['판정'] if latest and not conflict else 'UNKNOWN',
                                          'evidence': latest if latest and not conflict else None}
                if conflict:
                    issues.append(f'Research/{t}/{lens}/{item}: same-date conflict')
    positions, errors = [], []
    pc = Counter(r['ID'] for r in tables['Portfolio'])
    for r in tables['Portfolio']:
        t = r['Ticker']
        try:
            check_ticker(t)
            if blank(r['ID']) or pc[r['ID']] != 1 or r['전략'] not in ITEMS:
                raise ValueError('Unique ID and strategy required')
            p = prices[t]
            q = number(r['현재 수량'], 'quantity', 0)
            cost = number(r['평균단가'], 'cost', 0)
            target = q if blank(r['계획 수량']) else number(r['계획 수량'], 'target quantity', 0)
            stop = None if blank(r['손절 기준']) else number(r['손절 기준'], 'stop', 1e-12)
            price, rate = p['현재가'], fx if p['통화'] == 'USD' else 1
            warnings = []
            if stop is None and (q or target):
                warnings.append('가격 위험 미산정')
            if stop is not None and price <= stop and (q or target):
                warnings.append('손절 기준 이탈')
            if blank(r['보유 논리']) or blank(r['무효화 조건']):
                warnings.append('보유 논리/무효화 조건 필요')
            try:
                fresh(r['검토일'], asof, ages[1], 'position review')
            except (ValueError, TypeError):
                warnings.append('보유 논리 검토일 확인')
            positions.append({'id': r['ID'], 'ticker': t, 'strategy': r['전략'], 'sector': p['섹터'],
                              'quantity': q, 'target': target, 'value': q * price * rate,
                              'planned_value': target * price * rate,
                              'trade': (target - q) * price * rate,
                              'price_pnl': q * (price - cost) * rate,
                              'risk': None if stop is None else q * max(price - stop, 0) * rate,
                              'planned_risk': None if stop is None else target * max(price - stop, 0) * rate,
                              'stress_loss': q * price * rate * (1 - (1 + stress) * (1 + (fx_stress if rate != 1 else 0))),
                              'thesis': r['보유 논리'], 'invalidation': r['무효화 조건'], 'warnings': warnings})
        except (ValueError, TypeError, KeyError) as e:
            errors.append(f'Portfolio/{t}: {e}')
    portfolio = {'positions': positions, 'errors': errors, 'complete': not errors}
    if not errors:
        nav = cash + sum(p['value'] for p in positions)
        fees = sum(abs(p['trade']) * fee for p in positions)
        planned_nav = nav - fees
        after_cash = cash - sum(p['trade'] for p in positions) - fees
        weights, planned_weights, sectors, strategies = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
        for p in positions:
            weights[p['ticker']] += p['value'] / nav if nav > 0 else 0
            planned_weights[p['ticker']] += p['planned_value'] / planned_nav if planned_nav > 0 else 0
            sectors[p['sector']] += p['value']
            strategies[p['strategy']] += p['value']
        warnings = [f'{t}: 계획 종목 비중 한도 초과' for t, weight in planned_weights.items() if weight > weight_limit]
        if after_cash < 0 or planned_nav <= 0:
            warnings.append('계획 자금 부족/비중 해석 불가')
        planned_risk = sum(p['planned_risk'] or 0 for p in positions)
        if planned_nav > 0 and planned_risk / planned_nav > risk_limit:
            warnings.append('계획 가격 위험 한도 초과')
        portfolio.update(nav=nav, cash=cash, planned_nav=planned_nav, fees=fees, planned_cash=after_cash,
                         risk=sum(p['risk'] or 0 for p in positions), planned_risk=planned_risk,
                         risk_incomplete=any(p['planned_risk'] is None and p['target'] > 0 for p in positions),
                         weights=dict(weights), planned_weights=dict(planned_weights), sectors=dict(sectors),
                         strategies=dict(strategies), warnings=warnings)
    issues.extend(errors)
    return {'asof': asof.isoformat(), 'mode': mode, 'issues': issues, 'portfolio': portfolio,
            'research': research, 'growth': growth, 'valuation': valuations,
            'prices': {t: r['현재가'] for t, r in prices.items()}}
