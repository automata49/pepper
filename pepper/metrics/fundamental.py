"""재무 지표 (Buffett · Fisher · Lynch · Minervini 실적 항목).

모든 비율은 소수로 다룹니다 (15% = 0.15). 연간 리스트는 과거→최근 순서입니다.
"""
from statistics import mean
from .base import metric, cagr, growth, MissingData, NotApplicable, Unverified


def _years(f, key, params):
    years, min_years = params.get('years', 5), params.get('min_years', 3)
    return f.series(key, years, min_years)


# ── 수익성 ──────────────────────────────────────────────────
@metric('roe_ttm')
def roe_ttm(f, p):
    return f.num('roe_ttm')


@metric('roe_avg')
def roe_avg(f, p):
    return mean(_years(f, 'roe_history', p))


@metric('roe_min')
def roe_min(f, p):
    return min(_years(f, 'roe_history', p))


@metric('gross_margin')
def gross_margin(f, p):
    return f.num('gross_margin')


@metric('op_margin_vs_industry')
def op_margin_vs_industry(f, p):
    return f.series('op_margin_history')[-1] - f.num('industry_op_margin_median')


@metric('op_margin_trend')
def op_margin_trend(f, p):
    """최근 값 − n년 전 값 (%p를 소수로). 3년이면 4개 값 필요."""
    years = p.get('years', 3)
    s = f.series('op_margin_history', years + 1, years + 1)
    return s[-1] - s[0]


# ── 재무 안정성 ─────────────────────────────────────────────
@metric('debt_to_equity')
def debt_to_equity(f, p):
    equity = f.num('equity')
    if equity <= 0:
        raise NotApplicable('자기자본 ≤ 0')
    return f.num('total_debt') / equity


@metric('debt_payback_years')
def debt_payback_years(f, p):
    """장기부채를 순이익으로 갚는 데 걸리는 연수. 적자면 N/A."""
    ni = f.num('net_income')
    if ni <= 0:
        raise NotApplicable('순이익 ≤ 0')
    return f.num('long_term_debt') / ni


@metric('net_cash_per_share')
def net_cash_per_share(f, p):
    return (f.num('cash') - f.num('total_debt')) / f.num('shares_out')


@metric('inventory_vs_sales')
def inventory_vs_sales(f, p):
    """재고 증가율 − 매출 증가율 (최근 1년). 0 이하면 양호."""
    inv, rev = f.series('inventory_history', 2, 2), f.series('revenue_history', 2, 2)
    return growth(inv[0], inv[1]) - growth(rev[0], rev[1])


# ── 성장 ────────────────────────────────────────────────────
@metric('revenue_cagr')
def revenue_cagr(f, p):
    s = _years(f, 'revenue_history', {**p, 'years': p.get('years', 5) + 1, 'min_years': p.get('min_years', 3) + 1})
    return cagr(s[0], s[-1], len(s) - 1)


@metric('eps_cagr_hist')
def eps_cagr_hist(f, p):
    s = _years(f, 'eps_history', {**p, 'years': p.get('years', 5) + 1, 'min_years': p.get('min_years', 3) + 1})
    return cagr(s[0], s[-1], len(s) - 1)


@metric('eps_loss_years')
def eps_loss_years(f, p):
    return float(sum(1 for x in _years(f, 'eps_history', p) if x <= 0))


def _quarter_yoy(f, key, offset=0):
    """분기 리스트에서 (최근-offset) 분기의 전년 동기 대비 성장률."""
    q = f.series(key, None, 5 + offset)
    cur, prev = q[-1 - offset], q[-5 - offset]
    return growth(prev, cur)


@metric('quarter_eps_yoy')
def quarter_eps_yoy(f, p):
    return _quarter_yoy(f, 'eps_quarterly')


@metric('eps_acceleration')
def eps_acceleration(f, p):
    return _quarter_yoy(f, 'eps_quarterly') - _quarter_yoy(f, 'eps_quarterly', 1)


@metric('quarter_sales_yoy')
def quarter_sales_yoy(f, p):
    return _quarter_yoy(f, 'sales_quarterly')


# ── R&D · 희석 (Fisher) ─────────────────────────────────────
@metric('rd_to_sales')
def rd_to_sales(f, p):
    return f.series('rd_history')[-1] / f.series('revenue_history')[-1]


@metric('rd_productivity')
def rd_productivity(f, p):
    """n년간 매출 증가분 ÷ 같은 기간 누적 R&D."""
    years = p.get('years', 3)
    rev = f.series('revenue_history', years + 1, years + 1)
    rd = f.series('rd_history', years, years)
    if sum(rd) <= 0:
        raise NotApplicable('R&D 합계 0')
    return (rev[-1] - rev[0]) / sum(rd)


@metric('share_dilution_cagr')
def share_dilution_cagr(f, p):
    years = p.get('years', 3)
    s = f.series('shares_history', years + 1, years + 1)
    return cagr(s[0], s[-1], years)


# ── 정성 항목 (LLM 초안 → 사용자 확인) ───────────────────────
@metric('qualitative')
def qualitative(f, p):
    key = p['key']
    items = f.data.get('qualitative') or {}
    item = items.get(key)
    if not item or item.get('score') is None:
        raise MissingData(f'qualitative.{key}')
    if not item.get('verified'):
        raise Unverified(f'qualitative.{key}: 사용자 확인 전')
    score = float(item['score'])
    if not 0 <= score <= 100:
        raise MissingData(f'qualitative.{key}: 0~100 범위 밖')
    return score
