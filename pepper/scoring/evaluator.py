"""한 종목 × 한 대가 프로필 점수 계산.

항목 상태:
  OK          점수에 반영
  N_A         이 종목엔 의미 없음 (예외 태그·적자 등) → 분모에서도 제외
  MISSING     데이터 없음 → 점수 제외, 커버리지 감소
  UNVERIFIED  미검증 근거(LLM 초안·스크래핑) → 값은 보여주되 점수 제외, 커버리지 감소
"""
from ..metrics import REGISTRY, MissingData, NotApplicable, Unverified
from .expr import evaluate as eval_rule, Missing

CAN_NOT_SCORE = ('MISSING', 'UNVERIFIED')


def detect_tags(ticker, facts, exceptions):
    tags = set(facts.tags)
    ctx = {k: v for k, v in facts.data.items() if not isinstance(v, (list, dict))}
    ctx.update({k: v for k, v in facts.derived.items() if not isinstance(v, (list, dict)) and not k.startswith('_')})
    ctx['rd_expense_missing'] = not facts.has('rd_history')
    for tag, spec in exceptions.get('tags', {}).items():
        if ticker in [str(t) for t in spec.get('tickers', [])]:
            tags.add(tag)
            continue
        if spec.get('when'):
            try:
                if eval_rule(spec['when'], ctx):
                    tags.add(tag)
            except (Missing, TypeError):
                pass
    return sorted(tags)


def band_for(value, bands):
    for b in bands:
        if 'min' in b and value < b['min']:
            continue
        if 'max' in b and value > b['max']:
            continue
        return b
    return bands[-1]


def _json_value(v):
    return round(v, 6) if isinstance(v, float) else v


def score_criterion(c, facts, tags):
    out = {'id': c['id'], 'label': c.get('label', c['id']), 'weight': float(c.get('weight', 1)),
           'source': c.get('source', 'auto'), 'group': c.get('group')}
    if c.get('only_if') and not set(c['only_if']) & set(tags):
        return {**out, 'status': 'N_A', 'reason': f'해당 없음 (필요 태그: {", ".join(c["only_if"])})', 'applies': False}
    hit = set(c.get('skip_if', [])) & set(tags)
    if hit:
        return {**out, 'status': 'N_A', 'reason': f'예외 태그: {", ".join(sorted(hit))}'}
    facts.used = set()
    try:
        value = REGISTRY[c['metric']](facts, c.get('params', {}))
    except MissingData as e:
        return {**out, 'status': 'MISSING', 'reason': f'데이터 없음: {e}'}
    except NotApplicable as e:
        return {**out, 'status': 'N_A', 'reason': str(e)}
    except Unverified as e:
        return {**out, 'status': 'UNVERIFIED', 'reason': str(e)}
    out['value'] = _json_value(value)
    out['inputs'] = sorted(facts.used)
    if 'bands' in c:
        b = band_for(value, c['bands'])
        out.update(score=float(b['score']), label_result=b.get('label'))
    elif 'rule' in c:
        passed = bool(eval_rule(c['rule'], {'value': value}))
        out.update(score=100.0 if passed else 0.0, label_result='통과' if passed else '미달')
    else:
        out.update(score=max(0.0, min(100.0, float(value))), label_result=None)
    unverified = facts.unverified_fields()
    if unverified:
        return {**out, 'status': 'UNVERIFIED', 'reason': f'미검증 출처: {", ".join(unverified)}'}
    return {**out, 'status': 'OK'}


def score_profile(prof, facts, tags):
    items = [score_criterion(c, facts, tags) for c in prof.get('criteria', [])]
    applicable = [i for i in items if i['status'] != 'N_A']
    scored = [i for i in applicable if i['status'] == 'OK']
    w_all = sum(i['weight'] for i in applicable)
    w_ok = sum(i['weight'] for i in scored)
    coverage = w_ok / w_all if w_all else 0.0
    score = sum(i['weight'] * i['score'] for i in scored) / w_ok if w_ok else None
    min_cov = prof.get('min_coverage', .6)
    if score is None or coverage < min_cov:
        verdict = '판정 보류 (데이터 부족)'
    else:
        verdict = band_for(score, [{**v, 'score': 0} for v in prof.get('verdict', [{'label': ''}])]).get('label')
    result = {'version': str(prof['version']), 'score': round(score, 1) if score is not None else None,
              'coverage': round(coverage, 3), 'verdict': verdict, 'criteria': items,
              'missing': [i['id'] for i in items if i['status'] == 'MISSING'],
              'unverified': [i['id'] for i in items if i['status'] == 'UNVERIFIED']}
    if prof.get('status_rules'):
        result.update(status_context(prof, facts, items))
    return result


def status_context(prof, facts, items):
    """Minervini처럼 Status 규칙이 있는 프로필: 그룹별 통과 수 + context_metrics로 판정."""
    ctx = dict(prof.get('params', {}))
    for group in {i['group'] for i in items if i.get('group')}:
        g = [i for i in items if i.get('group') == group and i['status'] != 'N_A']
        ctx[f'total_{group}'] = len(g)
        ctx[f'passed_{group}'] = sum(1 for i in g if i['status'] == 'OK' and i['score'] >= 50)
        ctx[f'missing_{group}'] = sum(1 for i in g if i['status'] in CAN_NOT_SCORE)
    extra = {}
    for name, spec in prof.get('context_metrics', {}).items():
        try:
            extra[name] = REGISTRY[spec['metric']](facts, spec.get('params', {}))
        except (MissingData, NotApplicable, Unverified):
            extra[name] = None
    ctx.update(extra)
    status = 'DATA_REQUIRED'
    for rule in prof['status_rules']:
        try:
            if eval_rule(rule['when'], ctx):
                status = rule['status']
                break
        except Missing:
            continue
    out = {'status': status, 'status_context': {k: _json_value(v) for k, v in ctx.items()}}
    params = prof.get('params', {})
    if status in ('ACTIONABLE', 'SETUP') and facts.has('pivot'):
        entry = max(facts.num('pivot'), facts.num('price'))
        out['stop_price'] = round(entry * (1 - params.get('stop_loss_pct', .08)), 4)
        out['stop_price_max'] = round(entry * (1 - params.get('stop_loss_max_pct', .10)), 4)
    return out
