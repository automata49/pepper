"""가격 부담·내재가치 (Lynch PEG, Buffett 오너 어닝스 DCF, Blended EPS).

규칙 파일 값(할인율·성장 상한 등)은 f.derived['_rules']로 전달됩니다.
"""
from .base import metric, cagr, MissingData, NotApplicable


def _rules(f):
    return f.derived.get('_rules', {})


# ── 성장률 입력 해석 ────────────────────────────────────────
def forward_eps_cagr(f):
    """향후 EPS 연평균 성장률.

    1순위: 연도별 컨센서스 eps_forecast [FY0, FY1, FY2, (FY3)] 로 직접 계산
    2순위: 외부 'EPS 성장 전망(3년)' + custom.yaml inputs.eps_growth_3y_basis
    """
    if f.has('eps_forecast'):
        s = f.series('eps_forecast', None, 2)
        return cagr(s[0], s[-1], len(s) - 1), 'eps_forecast'
    g = f.num('eps_growth_3y')
    basis = _rules(f).get('inputs', {}).get('eps_growth_3y_basis', 'cumulative')
    if basis == 'cagr':
        return g, 'eps_growth_3y(cagr)'
    if basis != 'cumulative':
        raise ValueError(f'eps_growth_3y_basis 값 오류: {basis}')
    if g <= -1:
        raise NotApplicable('3년 성장 전망 ≤ -100%')
    return (1 + g) ** (1 / 3) - 1, 'eps_growth_3y(cumulative→cagr)'


@metric('eps_cagr_forecast')
def eps_cagr_forecast(f, p):
    return forward_eps_cagr(f)[0]


@metric('peg_forward')
def peg_forward(f, p):
    pe = f.num('forward_pe')
    g, _ = forward_eps_cagr(f)
    if pe <= 0:
        raise NotApplicable('Forward PER ≤ 0')
    if g <= 0:
        raise NotApplicable('성장률 ≤ 0 — PEG 의미 없음')
    return pe / (g * 100)


@metric('dividend_adjusted_growth_ratio')
def dividend_adjusted_growth_ratio(f, p):
    """Lynch: (EPS 성장률% + 배당수익률%) ÷ PER."""
    pe = f.num('pe_ttm')
    if pe <= 0:
        raise NotApplicable('PER ≤ 0')
    g, _ = forward_eps_cagr(f)
    dy = f.num('dividend_yield') if f.has('dividend_yield') else 0.0
    return (g * 100 + dy * 100) / pe


@metric('cyclical_low_pe_warning')
def cyclical_low_pe_warning(f, p):
    """경기순환주: 현재 PER이 과거 PER 분포 하위 구간이면 True(정점 경고)."""
    hist = f.series('pe_history', None, 5)
    pe = f.num('pe_ttm')
    rank = sum(1 for x in hist if x < pe) / len(hist)
    return rank <= p.get('pe_percentile_max', 0.25)


# ── EPS · 적정 PER ─────────────────────────────────────────
def blended_eps(f):
    w = dict(_rules(f).get('inputs', {}).get('blended_eps_weights', {'normalized': .5, 'consensus': .5}))
    if f.has('blend_weights'):
        w = dict(f.get('blend_weights'))
    parts = []
    for key, field in (('normalized', 'normalized_eps'), ('consensus', 'consensus_eps')):
        if w.get(key, 0) > 0 and f.has(field):
            parts.append((w[key], f.num(field)))
    if not parts:
        raise MissingData('normalized_eps/consensus_eps')
    total = sum(x for x, _ in parts)
    return sum(x * v for x, v in parts) / total


@metric('blended_eps')
def blended_eps_metric(f, p):
    return blended_eps(f)


def lynch_fair_pe(f):
    g, _ = forward_eps_cagr(f)
    v = _rules(f).get('lynch', {})
    return min(max(g * 100, v.get('fair_pe_floor', 8)), v.get('fair_pe_cap', 30))


def lynch_fair_value(f):
    eps = blended_eps(f)
    if eps <= 0:
        raise NotApplicable('Blended EPS ≤ 0')
    return eps * lynch_fair_pe(f)


# ── Buffett: 오너 어닝스 DCF ────────────────────────────────
def owner_earnings_per_share(f):
    ni, da = f.num('net_income'), f.num('d_and_a')
    method = _rules(f).get('buffett', {}).get('maintenance_capex', 'min_capex_da')
    if f.has('maintenance_capex'):
        mcx = f.num('maintenance_capex')
    else:
        capex = abs(f.num('capex'))
        mcx = {'capex': capex, 'da': da, 'min_capex_da': min(capex, da)}[method]
    oe = ni + da - mcx
    if oe <= 0:
        raise NotApplicable('오너 어닝스 ≤ 0')
    per_share = oe / f.num('shares_out')
    if f.derived.get('_cyclical') and f.has('normalized_eps') and f.has('eps_ttm') and f.num('eps_ttm') > 0:
        # 경기순환주: 사이클 정점 이익을 그대로 쓰지 않고 정규화 EPS 비율만큼 낮춤
        per_share *= min(1.0, f.num('normalized_eps') / f.num('eps_ttm'))
    return per_share


def dcf(oe, g, r, g_terminal, years):
    if r <= g_terminal:
        raise ValueError('할인율은 영구성장률보다 커야 합니다')
    value, cash = 0.0, oe
    for t in range(1, years + 1):
        cash *= 1 + g
        value += cash / (1 + r) ** t
    terminal = cash * (1 + g_terminal) / (r - g_terminal)
    return value + terminal / (1 + r) ** years


def buffett_growth(f):
    v = _rules(f).get('buffett', {})
    years = v.get('growth_source_years', 5)
    s = f.series('eps_history', years + 1, 4)
    return min(cagr(s[0], s[-1], len(s) - 1), v.get('growth_cap', .15))


def buffett_intrinsic_value(f, scenario='base'):
    v = _rules(f).get('buffett', {})
    sc = v.get('scenarios', {}).get(scenario, {'growth_mult': 1.0})
    g = buffett_growth(f) * sc.get('growth_mult', 1.0)
    r = sc.get('discount_rate', v.get('discount_rate', .10))
    return dcf(owner_earnings_per_share(f), g, r, v.get('terminal_growth', .03), v.get('years', 10))


@metric('margin_of_safety')
def margin_of_safety(f, p):
    """1 − 주가/내재가치. 0.25 이상이면 25% 할인."""
    return 1 - f.num('price') / buffett_intrinsic_value(f)
