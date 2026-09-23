"""가격 모멘텀 지표: RSI(Wilder), MACD, Stochastic Slow.

입력은 과거→최근 순서의 숫자 리스트입니다. 데이터가 모자라면 None을 돌려줍니다(0으로 채우지 않음).
"""


def ema(values, n):
    """지수이동평균. 첫 값은 처음 n개의 단순평균에서 시작합니다."""
    if len(values) < n:
        return []
    k = 2 / (n + 1)
    out = [sum(values[:n]) / n]
    for v in values[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return out   # 길이 = len(values) - n + 1


def rsi(closes, n=14):
    """Wilder RSI. 첫 평균은 n일 단순평균, 이후 (이전×(n-1) + 현재)/n."""
    if len(closes) < n + 1:
        return None
    diffs = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(d, 0) for d in diffs[:n]) / n
    loss = sum(max(-d, 0) for d in diffs[:n]) / n
    for d in diffs[n:]:
        gain = (gain * (n - 1) + max(d, 0)) / n
        loss = (loss * (n - 1) + max(-d, 0)) / n
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def macd(closes, fast=12, slow=26, signal=9):
    """MACD 선, 시그널, 히스토그램(최근값)과 직전 히스토그램."""
    if len(closes) < slow + signal:
        return None
    f, s = ema(closes, fast), ema(closes, slow)
    line = [a - b for a, b in zip(f[slow - fast:], s)]
    sig = ema(line, signal)
    hist = [a - b for a, b in zip(line[signal - 1:], sig)]
    return {'macd': line[-1], 'signal': sig[-1], 'hist': hist[-1],
            'hist_prev': hist[-2] if len(hist) > 1 else None}


def stochastic_slow(highs, lows, closes, n=14, k_smooth=3, d_smooth=3):
    """Slow %K = Fast %K의 k_smooth일 평균, Slow %D = Slow %K의 d_smooth일 평균."""
    need = n + k_smooth + d_smooth - 2
    if len(closes) < need + 1:
        return None
    fast = []
    for i in range(n - 1, len(closes)):
        hh, ll = max(highs[i - n + 1:i + 1]), min(lows[i - n + 1:i + 1])
        fast.append(50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100)
    slow_k = [sum(fast[i - k_smooth + 1:i + 1]) / k_smooth for i in range(k_smooth - 1, len(fast))]
    slow_d = [sum(slow_k[i - d_smooth + 1:i + 1]) / d_smooth for i in range(d_smooth - 1, len(slow_k))]
    return {'k': slow_k[-1], 'd': slow_d[-1], 'k_prev': slow_k[-2], 'd_prev': slow_d[-2]}


def signals(ind, cfg):
    """지표 → 짧은 신호 문구 목록. 점수에는 넣지 않는 참고용."""
    out = []
    r = ind.get('rsi')
    if r is not None:
        if r >= cfg.get('rsi_overbought', 70):
            out.append('RSI 과열')
        elif r <= cfg.get('rsi_oversold', 30):
            out.append('RSI 과매도')
    m = ind.get('macd')
    if m and m.get('hist_prev') is not None:
        if m['hist_prev'] <= 0 < m['hist']:
            out.append('MACD 상승 전환')
        elif m['hist_prev'] >= 0 > m['hist']:
            out.append('MACD 하락 전환')
    s = ind.get('stoch')
    if s:
        up = s['k_prev'] <= s['d_prev'] and s['k'] > s['d']
        down = s['k_prev'] >= s['d_prev'] and s['k'] < s['d']
        if up and min(s['k_prev'], s['k']) <= cfg.get('stoch_oversold', 20):
            out.append('Stoch 저점 반등')
        elif down and max(s['k_prev'], s['k']) >= cfg.get('stoch_overbought', 80):
            out.append('Stoch 고점 꺾임')
    return out


def compute(bars, cfg=None):
    cfg = cfg or {}
    closes = [b['close'] for b in bars]
    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]
    ind = {
        'rsi': rsi(closes, cfg.get('rsi_period', 14)),
        'macd': macd(closes, *cfg.get('macd', [12, 26, 9])),
        'stoch': stochastic_slow(highs, lows, closes, *cfg.get('stoch_slow', [14, 3, 3])),
    }
    ind['signals'] = signals(ind, cfg)
    return ind
