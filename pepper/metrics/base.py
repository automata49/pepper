"""지표 계산 공통 도구.

- Facts: 종목의 원자료. 어떤 필드를 읽었는지 기록해 출처 검증 상태를 추적합니다.
- 지표 함수는 값(float/bool)을 돌려주거나 MissingData / NotApplicable / Unverified 예외를 던집니다.
- @metric('이름') 으로 등록하면 규칙 YAML의 metric: 이름 으로 불러 쓸 수 있습니다.
"""
import math

REGISTRY = {}


class MissingData(Exception):
    """계산에 필요한 원자료가 없음."""


class NotApplicable(Exception):
    """이 종목에는 의미 없는 지표 (예: 적자 기업의 PER)."""


class Unverified(Exception):
    """값은 있으나 사용자가 확인하지 않은 근거 (예: LLM 초안)."""


def metric(name):
    def wrap(fn):
        if name in REGISTRY:
            raise ValueError(f'중복 지표 이름: {name}')
        REGISTRY[name] = fn
        return fn
    return wrap


class Facts:
    """facts dict 래퍼. get()으로 읽은 필드를 used에 모읍니다."""

    def __init__(self, data, sources=None, tags=None, derived=None):
        self.data = data or {}
        self.sources = sources or {}
        self.tags = set(tags or [])
        self.derived = derived or {}      # 가격 이력 등에서 계산한 값
        self.used = set()

    def has(self, key):
        return self._raw(key) is not None

    def _raw(self, key):
        return self.derived[key] if key in self.derived else self.data.get(key)

    def get(self, key):
        v = self._raw(key)
        if v is None:
            raise MissingData(key)
        self.used.add(key)
        if isinstance(v, float) and not math.isfinite(v):
            raise MissingData(key)
        return v

    def num(self, key):
        v = self.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise MissingData(f'{key}: 숫자가 아님')
        return float(v)

    def series(self, key, n=None, min_len=1):
        """연도순(과거→최근) 숫자 리스트. n개만 잘라 씀."""
        v = self.get(key)
        if not isinstance(v, list):
            raise MissingData(f'{key}: 리스트가 아님')
        vals = [float(x) for x in v if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)]
        if len(vals) != len(v):
            raise MissingData(f'{key}: 빈 값 포함')
        if n:
            vals = vals[-n:]
        if len(vals) < min_len:
            raise MissingData(f'{key}: {min_len}개 이상 필요 (현재 {len(vals)})')
        return vals

    def unverified_fields(self):
        return sorted(k for k in self.used if self.sources.get(k, {}).get('verified') is False)


def cagr(first, last, years):
    if years <= 0 or first <= 0 or last <= 0:
        raise NotApplicable('CAGR: 시작·끝 값이 양수여야 함')
    return (last / first) ** (1 / years) - 1


def growth(prev, cur):
    if prev <= 0:
        raise NotApplicable('성장률: 기준값이 0 이하')
    return cur / prev - 1
