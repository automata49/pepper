"""Minervini Trend Template · VCP · 피벗, 그리고 참고용 피보나치 가격.

bars(일봉 OHLCV)가 있으면 derive_from_bars()로 필요한 값을 계산하고,
없으면 facts에 직접 넣은 값(ma50, ma150, ...)을 사용합니다.
"""
from statistics import mean
from .base import metric, MissingData
from ..technical import valid_bars


def derive_from_bars(bars, asof, lookback=22, window_bars=20, windows=3):
    bars = valid_bars(bars, asof)
    closes = [b['close'] for b in bars]
    out = {'price': closes[-1], 'price_asof': bars[-1]['date'], 'bars': len(bars)}
    for n in (50, 150, 200):
        out[f'ma{n}'] = mean(closes[-n:]) if len(closes) >= n else None
    if len(closes) >= 200 + lookback:
        out['ma200_prev'] = mean(closes[-200 - lookback:-lookback])
    if len(bars) >= 252:
        year = bars[-252:]
        out['low_52w'] = min(b['low'] for b in year)
        out['high_52w'] = max(b['high'] for b in year)
    need = window_bars * windows
    if len(bars) >= need:
        segs = [bars[-need + i * window_bars: len(bars) - need + (i + 1) * window_bars] for i in range(windows)]
        out['vcp_depths'] = [1 - min(b['low'] for b in s) / max(b['high'] for b in s) for s in segs]
        out['vcp_volumes'] = [mean(b['volume'] for b in s) for s in segs]
    if len(bars) > window_bars:
        out['pivot'] = max(b['high'] for b in bars[-window_bars - 1:-1])
    for label, n in (('1y', 252), ('6m', 126)):
        if len(bars) >= n:
            seg = bars[-n:]
            out[f'range_low_{label}'] = min(b['low'] for b in seg)
            out[f'range_high_{label}'] = max(b['high'] for b in seg)
    return out


@metric('price_above_ma150_ma200')
def price_above_ma150_ma200(f, p):
    price = f.num('price')
    return price > f.num('ma150') and price > f.num('ma200')


@metric('ma150_above_ma200')
def ma150_above_ma200(f, p):
    return f.num('ma150') > f.num('ma200')


@metric('ma200_change')
def ma200_change(f, p):
    return f.num('ma200') / f.num('ma200_prev') - 1


@metric('ma50_above_ma150_ma200')
def ma50_above_ma150_ma200(f, p):
    ma50 = f.num('ma50')
    return ma50 > f.num('ma150') and ma50 > f.num('ma200')


@metric('price_above_ma50')
def price_above_ma50(f, p):
    return f.num('price') > f.num('ma50')


@metric('price_below_ma200')
def price_below_ma200(f, p):
    return f.num('price') < f.num('ma200')


@metric('pct_above_52w_low')
def pct_above_52w_low(f, p):
    return f.num('price') / f.num('low_52w') - 1


@metric('pct_from_52w_high')
def pct_from_52w_high(f, p):
    """고점 대비 거리 (0 = 신고가, -0.25 = 고점 대비 25% 아래)."""
    return f.num('price') / f.num('high_52w') - 1


@metric('rs_composite_percentile')
def rs_composite_percentile(f, p):
    """유니버스 내 RS 백분위 가중평균. 직접 입력한 rs_percentile이 있으면 우선."""
    if f.has('rs_percentile'):
        return f.num('rs_percentile')
    weights = p.get('weights', {'rs_3m': .4, 'rs_6m': .2, 'rs_12m': .4})
    got = [(w, f.num(k + '_percentile')) for k, w in weights.items() if f.has(k + '_percentile')]
    if not got or sum(w for w, _ in got) < .6 * sum(weights.values()):
        raise MissingData('rs_*_percentile')
    return sum(w * v for w, v in got) / sum(w for w, _ in got)


@metric('vcp_contracting')
def vcp_contracting(f, p):
    """구간별 조정폭이 연속으로 줄고, 마지막 구간 거래량이 첫 구간보다 적으면 True (근사)."""
    d, v = f.get('vcp_depths'), f.get('vcp_volumes')
    if len(d) < 2 or len(d) != len(v):
        raise MissingData('vcp_depths')
    return all(b < a for a, b in zip(d, d[1:])) and v[-1] < v[0]


@metric('pivot_distance')
def pivot_distance(f, p):
    """주가 ÷ 피벗 − 1. 0~0.05 = 매수 가능 범위, 음수 = 돌파 전."""
    return f.num('price') / f.num('pivot') - 1


def fibonacci(f, upper=.618, mid=.5):
    """시트 방식 참고가: 1년·6개월 범위의 61.8%/50% 수준 평균."""
    levels = {}
    for name, ratio in (('fib_upper', upper), ('fib_mid', mid)):
        vals = [f.num(f'range_low_{w}') + (f.num(f'range_high_{w}') - f.num(f'range_low_{w}')) * ratio for w in ('1y', '6m')]
        levels[name] = sum(vals) / 2
    return levels
