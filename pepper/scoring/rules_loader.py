"""rules/*.yaml 읽기 + 형식 검사 + 덮어쓰기(overrides) 적용."""
import copy
from pathlib import Path
import yaml
from ..metrics import REGISTRY
from .expr import compile_rule

DEFAULT_DIR = Path(__file__).resolve().parents[1] / 'rules'
PROFILES = ('minervini', 'buffett', 'fisher', 'lynch')


class RulesError(ValueError):
    pass


def _load(path):
    try:
        return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        raise RulesError(f'{path}: YAML 문법 오류 — {e}') from e


def _check_bands(where, bands):
    if not isinstance(bands, list) or not bands:
        raise RulesError(f'{where}: bands는 비어 있지 않은 리스트여야 합니다')
    if any(('min' in b or 'max' in b) for b in bands[-1:]):
        raise RulesError(f'{where}: 마지막 band는 min/max 없는 기본값이어야 합니다')
    for b in bands:
        if 'score' not in b or not 0 <= float(b['score']) <= 100:
            raise RulesError(f'{where}: band score는 0~100')


def validate_profile(name, prof, tags):
    if prof.get('profile') != name or not prof.get('version'):
        raise RulesError(f'{name}.yaml: profile 이름/version 필요')
    ids = set()
    for c in prof.get('criteria', []):
        where = f'{name}.{c.get("id")}'
        if not c.get('id') or c['id'] in ids:
            raise RulesError(f'{where}: id 누락 또는 중복')
        ids.add(c['id'])
        if c.get('metric') not in REGISTRY:
            raise RulesError(f'{where}: 알 수 없는 metric {c.get("metric")!r}')
        if 'bands' in c and 'rule' in c:
            raise RulesError(f'{where}: bands와 rule 중 하나만 사용')
        if 'bands' in c:
            _check_bands(where, c['bands'])
        if 'rule' in c:
            compile_rule(c['rule'])
        if float(c.get('weight', 1)) <= 0:
            raise RulesError(f'{where}: weight는 양수')
        for t in c.get('skip_if', []) + c.get('only_if', []):
            if t not in tags:
                raise RulesError(f'{where}: exceptions.yaml에 없는 태그 {t!r}')
        if c.get('source', 'auto') not in ('auto', 'llm_draft', 'manual'):
            raise RulesError(f'{where}: source는 auto|llm_draft|manual')
    for k, m in prof.get('context_metrics', {}).items():
        if m.get('metric') not in REGISTRY:
            raise RulesError(f'{name}.context_metrics.{k}: 알 수 없는 metric')
    for s in prof.get('status_rules', []):
        compile_rule(s['when'])
    if prof.get('verdict'):
        _check_bands(f'{name}.verdict', [{**v, 'score': 0} for v in prof['verdict']])


def apply_overrides(rules, overrides, tag='+override'):
    if not overrides:
        return rules
    for o in overrides:
        prof = rules['profiles'].get(o.get('profile'))
        if prof is None:
            raise RulesError(f'override: 알 수 없는 profile {o.get("profile")!r}')
        crit = next((c for c in prof['criteria'] if c['id'] == o.get('criterion')), None)
        if crit is None:
            raise RulesError(f'override: {o["profile"]}에 {o.get("criterion")!r} 없음')
        if o.get('field') not in ('weight', 'bands', 'rule', 'params'):
            raise RulesError('override field는 weight|bands|rule|params')
        if o['field'] == 'bands':
            crit.pop('rule', None)
        if o['field'] == 'rule':
            crit.pop('bands', None)
        crit[o['field']] = o['value']
        prof['version'] = f'{prof["version"]}{tag}' if tag not in str(prof['version']) else prof['version']
    return rules


def load_rules(directory=None, local_override=None):
    d = Path(directory) if directory else DEFAULT_DIR
    exceptions = _load(d / 'exceptions.yaml')
    custom = _load(d / 'custom.yaml')
    tags = exceptions.get('tags', {})
    for t, spec in tags.items():
        if spec.get('when'):
            compile_rule(spec['when'])
    rules = {'dir': str(d), 'exceptions': exceptions, 'custom': custom, 'profiles': {}}
    for name in PROFILES:
        prof = _load(d / f'{name}.yaml')
        validate_profile(name, prof, tags)
        rules['profiles'][name] = prof
    apply_overrides(rules, custom.get('overrides'), '+custom')
    if local_override:
        apply_overrides(rules, _load(local_override).get('overrides'), '+local')
    for name, prof in rules['profiles'].items():
        validate_profile(name, prof, tags)
    for strategy, weights in custom.get('composites', {}).items():
        unknown = set(weights) - set(PROFILES)
        if unknown:
            raise RulesError(f'composites.{strategy}: 알 수 없는 profile {sorted(unknown)}')
    return rules


def versions(rules):
    v = {name: str(p['version']) for name, p in rules['profiles'].items()}
    v['custom'] = str(rules['custom'].get('version'))
    v['exceptions'] = str(rules['exceptions'].get('version'))
    return v


def valuation_params(rules):
    """지표 함수에 넘길 가정값 묶음."""
    return {'inputs': rules['custom'].get('inputs', {}),
            'buffett': rules['profiles']['buffett'].get('valuation', {}),
            'lynch': rules['profiles']['lynch'].get('valuation', {})}


def clone(rules):
    return copy.deepcopy(rules)
