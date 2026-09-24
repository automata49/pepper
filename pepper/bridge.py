"""Edgar ↔ Pepper 연결: inputs JSON을 읽어 4대가 점수를 계산하고 results JSON을 씁니다.

inputs 형식 (Edgar가 작성, docs/scoring.md 참고):
{
  "asof": "2026-09-22",
  "benchmarks": {"US": [일봉...], "KR": [일봉...]},          # 선택
  "tickers": {
    "MU": {"market": "US", "facts": {...}, "sources": {"필드": {"url","asof","provider","verified"}},
           "tags": ["cyclical"], "bars": [일봉...]}           # bars 선택
  }
}
"""
import json
from datetime import date
from pathlib import Path
from .metrics import Facts
from .metrics.trend import derive_from_bars
from .technical import calculate, percentiles
from .scoring.profiles import evaluate_ticker
from .scoring.rules_loader import load_rules, versions


def _days(a, b):
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def prepare(inputs):
    """가격 이력 → 파생값, 시장별 RS 백분위 계산."""
    asof = inputs['asof']
    derived, issues = {}, []
    by_market = {}
    for t, entry in inputs.get('tickers', {}).items():
        d = {}
        bars = entry.get('bars')
        if bars:
            try:
                d.update(derive_from_bars(bars, asof))
            except ValueError as e:
                issues.append(f'{t}: 가격 이력 오류 — {e}')
            bench = inputs.get('benchmarks', {}).get(entry.get('market', 'US'))
            if bench:
                try:
                    tech = calculate(bars, bench, asof)
                    d.update({k: tech[k] for k in ('rs_1m', 'rs_3m', 'rs_6m', 'rs_12m')})
                    by_market.setdefault(entry.get('market', 'US'), {})[t] = d
                except ValueError as e:
                    issues.append(f'{t}: RS 계산 불가 — {e}')
        derived[t] = d
    for items in by_market.values():
        percentiles(items)
    return derived, issues


def freshness_flags(entry, derived, asof, rules):
    cfg = rules['custom'].get('freshness', {})
    flags = []
    price_asof = derived.get('price_asof') or entry.get('facts', {}).get('price_asof')
    if not price_asof:
        flags.append('가격 기준일 없음')
    elif _days(asof, price_asof) > cfg.get('max_price_age_days', 4):
        flags.append(f'가격 기준일 오래됨 ({price_asof})')
    fa = entry.get('facts', {}).get('fundamentals_asof')
    if fa and _days(asof, fa) > cfg.get('max_fundamental_age_days', 45):
        flags.append(f'재무 자료 갱신 필요 ({fa})')
    future = [k for k, s in entry.get('sources', {}).items() if s.get('asof') and s['asof'] > asof]
    if future:
        flags.append(f'기준일 이후 자료 제외 필요: {", ".join(sorted(future))}')
    return flags


def score_inputs(inputs, rules=None):
    rules = rules or load_rules()
    asof = inputs['asof']
    date.fromisoformat(asof)
    derived, issues = prepare(inputs)
    results = {}
    for t, entry in sorted(inputs.get('tickers', {}).items()):
        facts_data = dict(entry.get('facts', {}))
        sources = entry.get('sources', {})
        # 미래 정보 차단: 기준일 이후에 나온 필드는 계산에서 뺍니다.
        for k, s in sources.items():
            if s.get('asof') and s['asof'] > asof:
                facts_data.pop(k, None)
        facts = Facts(facts_data, sources, entry.get('tags', []) + facts_data.get('tags', []), derived.get(t, {}))
        r = evaluate_ticker(t, facts, rules)
        r['market'] = entry.get('market')
        r['flags'] = freshness_flags(entry, derived.get(t, {}), asof, rules)
        results[t] = r
    return {'asof': asof, 'engine': 'pepper.scoring', 'rules_version': versions(rules),
            'issues': issues, 'tickers': results}


def rules_diff(inputs, old_rules, new_rules):
    """같은 입력에 대해 규칙 버전별로 판정이 바뀐 종목 목록."""
    a, b = score_inputs(inputs, old_rules), score_inputs(inputs, new_rules)
    changes = []
    for t in sorted(b['tickers']):
        x, y = a['tickers'].get(t), b['tickers'][t]
        if not x:
            continue
        for p in y['profiles']:
            ox, oy = x['profiles'][p], y['profiles'][p]
            if (ox['verdict'], ox.get('status')) != (oy['verdict'], oy.get('status')) or ox['score'] != oy['score']:
                changes.append({'ticker': t, 'profile': p, 'old': [ox['score'], ox['verdict'], ox.get('status')],
                                'new': [oy['score'], oy['verdict'], oy.get('status')]})
        if x['valuation'].get('label') != y['valuation'].get('label'):
            changes.append({'ticker': t, 'profile': 'valuation', 'old': x['valuation'].get('label'),
                            'new': y['valuation'].get('label')})
    return {'old_version': a['rules_version'], 'new_version': b['rules_version'], 'changes': changes}


def run_file(input_path, output_path, rules_dir=None, local_override=None):
    inputs = json.loads(Path(input_path).read_text(encoding='utf-8'))
    result = score_inputs(inputs, load_rules(rules_dir, local_override))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
