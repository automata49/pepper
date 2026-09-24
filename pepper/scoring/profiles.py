"""종목 하나를 4대가 프로필로 평가하고, 종합 점수·적정주가·참고값을 묶습니다."""
from ..metrics import Facts, MissingData, NotApplicable, Unverified
from ..metrics import valuation as V
from ..metrics.trend import fibonacci
from .evaluator import detect_tags, score_profile
from .rules_loader import valuation_params, versions


def _safe(fn, *args):
    try:
        return fn(*args), None
    except (MissingData, NotApplicable, Unverified, ZeroDivisionError) as e:
        return None, f'{type(e).__name__}: {e}'


def _r(v, n=4):
    return round(v, n) if isinstance(v, float) else v


def lynch_category(facts, tags, spec):
    for t in spec.get('tag_categories', []):
        if t in tags:
            return t
    g, err = _safe(lambda: V.forward_eps_cagr(facts)[0])
    if g is None:
        return None
    if g < spec['slow_grower']['max_growth']:
        return 'slow_grower'
    if g >= spec['fast_grower']['min_growth']:
        return 'fast_grower'
    return 'stalwart'


def valuation_summary(facts, tags, rules):
    cfg = rules['custom'].get('fair_value', {})
    out = {'model': 'NAV' if 'nav_company' in tags else 'EARNINGS'}
    facts.used = set()
    if out['model'] == 'NAV':
        out['note'] = 'NAV/mNAV 모델 필요 — P/E 기반 적정가 미산출'
        return out
    g, err = _safe(V.forward_eps_cagr, facts)
    if g:
        out['eps_cagr_forecast'], out['eps_cagr_basis'] = _r(g[0]), g[1]
    out['blended_eps'], _ = _safe(V.blended_eps, facts)
    out['lynch_fair_pe'], _ = _safe(V.lynch_fair_pe, facts)
    if 'cyclical' in tags:
        out['lynch_fair_value'], lerr = None, None
        out['cyclical_note'] = '경기순환주: Lynch PER=성장률 적정가 미적용, Buffett 가치는 정규화 EPS로 낮춰 계산'
    else:
        out['lynch_fair_value'], lerr = _safe(V.lynch_fair_value, facts)
    scen = {}
    for name in ('bear', 'base', 'bull'):
        scen[name], berr = _safe(V.buffett_intrinsic_value, facts, name)
    out['buffett_scenarios'] = {k: _r(v, 2) for k, v in scen.items()}
    out['buffett_intrinsic_value'] = scen.get('base')
    candidates = {'buffett': scen.get('base'), 'lynch': out['lynch_fair_value']}
    method = cfg.get('method', 'min')
    vals = [v for v in candidates.values() if v]
    if method in candidates:
        fv = candidates[method]
    elif not vals:
        fv = None
    elif method == 'mean':
        fv = sum(vals) / len(vals)
    else:
        fv = min(vals)
    out['fair_value'], out['fair_value_method'] = fv, method
    notes = [e for e in (lerr, berr) if e]
    if notes:
        out['notes'] = notes
    price = facts.data.get('price') or facts.derived.get('price')
    if fv and price:
        upside = fv / price - 1
        out['upside'] = upside
        if price <= fv * (1 - cfg.get('cheap_discount', .25)):
            out['label'] = 'CHEAP'
        elif price > fv * (1 + cfg.get('expensive_premium', .10)):
            out['label'] = 'EXPENSIVE'
        else:
            out['label'] = 'FAIR'
        s = out['buffett_scenarios']
        if all(s.values()):
            out['scenario_position'] = ('BELOW_BEAR' if price < s['bear'] else 'ABOVE_BULL' if price > s['bull']
                                        else 'BEAR_TO_BASE' if price < s['base'] else 'BASE_TO_BULL')
    else:
        out['label'] = 'INPUT_NEEDED'
    unverified = facts.unverified_fields()
    if unverified:
        out['unverified_inputs'] = unverified
        out['label_status'] = 'UNVERIFIED'
    return {k: _r(v, 4) for k, v in out.items()}


def evaluate_ticker(ticker, facts, rules):
    """facts: metrics.Facts (derived에 가격 이력 계산값 포함)."""
    facts.derived['_rules'] = valuation_params(rules)
    tags = detect_tags(ticker, facts, rules['exceptions'])
    facts.derived['_cyclical'] = 'cyclical' in tags
    profiles = {name: score_profile(prof, facts, tags) for name, prof in rules['profiles'].items()}
    composites = {}
    for strategy, weights in rules['custom'].get('composites', {}).items():
        got = [(w, profiles[p]['score']) for p, w in weights.items()
               if profiles[p]['score'] is not None and not profiles[p]['verdict'].startswith('판정 보류')]
        total = sum(weights.values())
        cov = sum(w for w, _ in got) / total if total else 0
        composites[strategy] = {'score': round(sum(w * s for w, s in got) / sum(w for w, _ in got), 1) if got else None,
                                'profiles_used': round(cov, 3)}
    ref = rules['custom'].get('reference', {}).get('fibonacci', {})
    fib, _ = _safe(fibonacci, facts, ref.get('upper_level', .618), ref.get('mid_level', .5))
    return {
        'ticker': ticker,
        'tags': tags,
        'lynch_category': lynch_category(facts, tags, rules['profiles']['lynch'].get('categories', {})),
        'swing_status': profiles['minervini'].get('status'),
        'stop_price': profiles['minervini'].get('stop_price'),
        'composites': composites,
        'profiles': profiles,
        'valuation': valuation_summary(facts, tags, rules),
        'reference': {'fibonacci': {k: _r(v, 4) for k, v in fib.items()} if fib else None,
                      'note': '4대가 기준 없음 — 참고값, 점수 미반영'},
    }


def rules_versions(rules):
    return versions(rules)
