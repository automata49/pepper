"""Daily-bar indicators. Relative strength is benchmark-relative, not an IBD rating."""
import math
from statistics import mean
from datetime import date


def valid_bars(bars, asof):
    result = sorted((b for b in bars if b['date'] <= asof), key=lambda b: b['date'])
    if len({b['date'] for b in result}) != len(result):
        raise ValueError('Duplicate price dates')
    for b in result:
        date.fromisoformat(b['date'])
        if any(not isinstance(b.get(k), (float, int)) or not math.isfinite(b[k]) for k in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('Incomplete OHLCV')
        if b['low'] <= 0 or b['volume'] < 0 or not b['low'] <= min(b['open'], b['close']) <= max(b['open'], b['close']) <= b['high']:
            raise ValueError('Invalid OHLCV')
    return result


def calculate(bars, benchmark, asof):
    bars, benchmark = valid_bars(bars, asof), valid_bars(benchmark, asof)
    if len(bars) < 21:
        raise ValueError('At least 21 bars required')
    closes = [b['close'] for b in bars]
    close = closes[-1]
    result = {'asof': bars[-1]['date'], 'price': close, 'bars': len(bars),
              'stale_days': (date.fromisoformat(asof) - date.fromisoformat(bars[-1]['date'])).days}
    for n in (21, 50, 200):
        result[f'ma{n}'] = mean(closes[-n:]) if len(closes) >= n else None
    tr = [max(b['high'] - b['low'], abs(b['high'] - bars[i-1]['close']), abs(b['low'] - bars[i-1]['close'])) for i,b in enumerate(bars) if i]
    atr = mean(tr[:20])
    for x in tr[20:]:
        atr = (atr * 19 + x) / 20
    result['atr20'] = atr
    result['atr_pct'] = atr / close
    result['volume_ratio20'] = bars[-1]['volume'] / mean(b['volume'] for b in bars[-21:-1]) if sum(b['volume'] for b in bars[-21:-1]) > 0 else None
    high = max(b['high'] for b in bars[-252:])
    result['dist_52w_high'] = close / high - 1 if len(bars) >= 252 else None
    result['prior_high20'] = max(b['high'] for b in bars[-21:-1])
    result['breakout_distance'] = close / result['prior_high20'] - 1
    a, b = {x['date']:x['close'] for x in bars}, {x['date']:x['close'] for x in benchmark}
    dates = sorted(a.keys() & b.keys())
    for label,n in [('1m',21),('3m',63),('6m',126),('12m',252)]:
        result[f'rs_{label}'] = ((a[dates[-1]] / a[dates[-n-1]]) / (b[dates[-1]] / b[dates[-n-1]]) - 1) if len(dates) > n and dates[-1] == bars[-1]['date'] else None
    result['return_1d'] = close / closes[-2] - 1
    result['atr_drawdown_limit'] = -max(.25, min(.45, result['atr_pct'] * 6))
    return result


def classify(m, rules):
    if m['stale_days'] > rules.get('max_price_age_days', 4) or any(m.get(k) is None for k in ('ma21','ma50','ma200','rs_1m','rs_3m','volume_ratio20')):
        return {'status':'DATA_REQUIRED', 'leader':None, 'next_leader':None}
    p = m['price']
    trend = p > m['ma21'] > m['ma50'] > m['ma200']
    leader = m['rs_3m'] > 0 and m['rs_1m'] > 0 and p > m['ma50'] > m['ma200']
    extended = p/m['ma21']-1 > .10 or p/m['ma50']-1 > .15 or m['breakout_distance'] > .05
    if p < m['ma200']:
        status = 'AVOID'
    elif extended:
        status = 'EXTENDED'
    elif leader and trend and -.02 <= m['breakout_distance'] <= .05 and m['volume_ratio20'] >= 1:
        status = 'ACTIONABLE'
    elif leader and abs(p/m['ma21']-1) <= .03:
        status = 'PULLBACK ENTRY'
    else:
        status = 'WATCH'
    dist = m.get('dist_52w_high')
    next_leader = (m['rs_3m'] < 0 < m['rs_1m'] and not extended and dist is not None
                   and dist >= m['atr_drawdown_limit'] and p > m['ma21'] > m['ma50']
                   and (dist >= -.30 or (p > m['ma200'] and m['volume_ratio20'] >= 1.5)))
    return {'status':status,'leader':leader,'next_leader':next_leader,
            'criteria':{'Trend':'PASS' if trend else 'FAIL', 'RS':'PASS' if leader else 'FAIL',
                        'Volume':'PASS' if m['volume_ratio20'] >= 1 else 'FAIL',
                        'Entry':'PASS' if status in ('ACTIONABLE','PULLBACK ENTRY') else 'FAIL',
                        'Risk':'UNKNOWN'}}


def percentiles(items):
    """Percentile within successful configured universe, average rank for ties."""
    for field in ('rs_1m','rs_3m','rs_6m','rs_12m'):
        values = [x[field] for x in items.values() if x.get(field) is not None]
        for item in items.values():
            v = item.get(field)
            item[field+'_percentile'] = (100*(sum(x < v for x in values)+(sum(x == v for x in values)-1)/2)/(len(values)-1)) if v is not None and len(values)>1 else None
    return items
