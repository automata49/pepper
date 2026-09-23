"""KRX Open API (한국거래소 공식). https://openapi.krx.co.kr

- 인증: 발급받은 키를 AUTH_KEY 헤더로 전송 (환경변수 KRX_API_KEY)
- 키 발급 후 서비스별 이용 신청·승인이 따로 필요 (유가증권/코스닥/ETF 일별매매정보, KOSPI 시리즈)
- 날짜별로 시장 전체를 한 번에 돌려주므로 날짜 단위로 캐시합니다 (키당 하루 10,000회)
- 가격은 수정주가가 아니므로 상장주식수 변화로 액면분할·병합을 보정합니다.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE_URL = 'https://data-dbg.krx.co.kr/svc/apis'
ENDPOINTS = {'KOSPI': 'sto/stk_bydd_trd', 'KOSDAQ': 'sto/ksq_bydd_trd', 'ETF': 'etp/etf_bydd_trd',
             'INDEX': 'idx/kospi_dd_trd'}


class KRXError(RuntimeError):
    pass


def _num(v):
    s = str(v).replace(',', '').strip()
    if s in ('', '-'):
        return None
    return float(s)


def short_code(isu_cd):
    s = str(isu_cd).strip()
    return s[3:9] if len(s) == 12 and s.startswith('KR') else s


class KRXClient:
    def __init__(self, api_key=None, cache='data/cache/krx', opener=None, pause=0.05):
        self.api_key = (api_key or os.environ.get('KRX_API_KEY', '')).strip()
        self.cache = Path(cache)
        self.opener = opener or urllib.request.urlopen
        self.pause = pause

    @property
    def available(self):
        return bool(self.api_key)

    def day(self, kind, basdd):
        """kind: KOSPI|KOSDAQ|ETF|INDEX, basdd: YYYYMMDD → 행 목록 (휴장일은 빈 목록)."""
        path = self.cache / kind / f'{basdd}.json'
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        if not self.available:
            raise KRXError('KRX_API_KEY가 없습니다')
        url = f'{BASE_URL}/{ENDPOINTS[kind]}.json?' + urllib.parse.urlencode({'basDd': basdd})
        req = urllib.request.Request(url, headers={'AUTH_KEY': self.api_key, 'User-Agent': 'pepper-review'})
        try:
            with self.opener(req, timeout=30) as r:
                body = json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            hint = ' (키 또는 서비스 이용 승인 확인)' if e.code in (401, 403) else ''
            raise KRXError(f'KRX HTTP {e.code}{hint}') from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise KRXError(f'KRX 요청 실패: {type(e).__name__}') from None
        if body.get('respCode'):
            raise KRXError(f'KRX 오류 {body.get("respCode")}: {body.get("respMsg", "")}')
        blocks = [v for k, v in body.items() if k.startswith('OutBlock_') and isinstance(v, list)]
        if len(blocks) != 1:
            raise KRXError('KRX 응답 형식 확인 필요')
        rows = blocks[0]
        if basdd < date.today().strftime('%Y%m%d'):   # 당일 자료는 확정 전이라 캐시하지 않음
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        time.sleep(self.pause)
        return rows

    def history(self, codes, kinds, start, end, index_name=None):
        """여러 종목의 일봉을 한 번에 모읍니다. codes: 6자리 코드 집합."""
        codes, out, index = set(codes), {c: [] for c in codes}, []
        d, last = date.fromisoformat(start), date.fromisoformat(end)
        while d <= last:
            if d.weekday() < 5:
                basdd = d.strftime('%Y%m%d')
                for kind in kinds:
                    for row in self.day(kind, basdd):
                        code = short_code(row.get('ISU_CD', ''))
                        if code in codes:
                            bar = _bar(row, d.isoformat())
                            if bar:
                                out[code].append(bar)
                if index_name:
                    for row in self.day('INDEX', basdd):
                        if row.get('IDX_NM') == index_name:
                            c = _num(row.get('CLSPRC_IDX'))
                            if c:
                                index.append({'date': d.isoformat(), 'open': _num(row.get('OPNPRC_IDX')) or c,
                                              'high': _num(row.get('HGPRC_IDX')) or c, 'low': _num(row.get('LWPRC_IDX')) or c,
                                              'close': c, 'volume': _num(row.get('ACC_TRDVOL')) or 0.0})
            d += timedelta(days=1)
        return {c: adjust_splits(b) for c, b in out.items()}, index


def _bar(row, day):
    o, h, l, c, v = (_num(row.get(k)) for k in ('TDD_OPNPRC', 'TDD_HGPRC', 'TDD_LWPRC', 'TDD_CLSPRC', 'ACC_TRDVOL'))
    if not c or not h or not l or v is None:
        return None   # 거래정지 등 가격 없는 날
    o = o or c
    return {'date': day, 'open': o, 'high': max(h, o, c), 'low': min(l, o, c), 'close': c, 'volume': v,
            'shares': _num(row.get('LIST_SHRS'))}


def adjust_splits(bars, threshold=1.5):
    """상장주식수가 threshold배 이상 바뀌고 가격이 반대로 비슷하게 움직인 날을 분할·병합으로 보고
    그 이전 가격을 나눠(거래량은 곱해) 연속성을 맞춥니다."""
    bars = [dict(b) for b in bars]
    for i in range(len(bars) - 1, 0, -1):
        s0, s1 = bars[i - 1].get('shares'), bars[i].get('shares')
        if not s0 or not s1:
            continue
        ratio = s1 / s0
        if ratio >= threshold or ratio <= 1 / threshold:
            price_ratio = bars[i - 1]['close'] / bars[i]['close']
            if 0.6 * ratio <= price_ratio <= 1.6 * ratio:
                for b in bars[:i]:
                    for k in ('open', 'high', 'low', 'close'):
                        b[k] /= ratio
                    b['volume'] *= ratio
    for b in bars:
        b.pop('shares', None)
    return bars
