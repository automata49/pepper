"""한국투자증권 KIS Open API (공식). https://apiportal.koreainvestment.com

- 필요: 한국투자증권 계좌 + KIS Developers에서 발급한 App Key/Secret
  (환경변수 KIS_APP_KEY, KIS_APP_SECRET, 선택 KIS_ENV=prod|vps)
- 여기서는 시세 조회만 합니다. 주문 API는 쓰지 않습니다.
- 종목투자의견[국내주식-188]: 증권사 목표주가 → 컨센서스 목표가(중앙값)
- 종목추정실적[국내주식-187]: 응답 구조를 실제 키로 확인한 뒤 연결 (현재는 원자료 저장만)
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

DOMAINS = {'prod': 'https://openapi.koreainvestment.com:9443', 'vps': 'https://openapivts.koreainvestment.com:29443'}


class KISError(RuntimeError):
    pass


class KISClient:
    def __init__(self, app_key=None, app_secret=None, env=None, cache='data/cache/kis', opener=None):
        self.app_key = app_key or os.environ.get('KIS_APP_KEY', '')
        self.app_secret = app_secret or os.environ.get('KIS_APP_SECRET', '')
        self.base = DOMAINS[env or os.environ.get('KIS_ENV', 'prod')]
        self.cache = Path(cache)
        self.opener = opener or urllib.request.urlopen
        self._token = None

    @property
    def available(self):
        return bool(self.app_key and self.app_secret)

    def _open(self, req):
        try:
            with self.opener(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise KISError(f'KIS HTTP {e.code}') from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise KISError(f'KIS 요청 실패: {type(e).__name__}') from None

    def token(self):
        """접근토큰은 하루 유효·발급 횟수 제한이 있어 파일에 캐시합니다 (data/는 Git 제외)."""
        if self._token:
            return self._token
        path = self.cache / 'token.json'
        if path.exists():
            t = json.loads(path.read_text())
            if datetime.fromisoformat(t['expires']) > datetime.now() + timedelta(minutes=10):
                self._token = t['access_token']
                return self._token
        if not self.available:
            raise KISError('KIS_APP_KEY/KIS_APP_SECRET이 없습니다')
        body = json.dumps({'grant_type': 'client_credentials', 'appkey': self.app_key,
                           'appsecret': self.app_secret}).encode()
        res = self._open(urllib.request.Request(f'{self.base}/oauth2/tokenP', data=body, method='POST',
                                                headers={'content-type': 'application/json'}))
        if not res.get('access_token'):
            raise KISError(f'KIS 토큰 발급 실패: {res.get("error_description", "")}')
        expires = datetime.now() + timedelta(seconds=int(res.get('expires_in', 86400)))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'access_token': res['access_token'], 'expires': expires.isoformat()}))
        os.chmod(path, 0o600)
        self._token = res['access_token']
        return self._token

    def get(self, api, tr_id, params):
        headers = {'content-type': 'application/json; charset=utf-8', 'authorization': f'Bearer {self.token()}',
                   'appkey': self.app_key, 'appsecret': self.app_secret, 'tr_id': tr_id, 'custtype': 'P'}
        url = f'{self.base}{api}?' + urllib.parse.urlencode(params)
        res = self._open(urllib.request.Request(url, headers=headers))
        if res.get('rt_cd') not in ('0', 0):
            raise KISError(f'KIS 오류 {res.get("msg_cd", "")}: {res.get("msg1", "")}')
        time.sleep(0.06)   # 초당 호출 제한 대비
        return res

    def invest_opinions(self, code, start, end):
        res = self.get('/uapi/domestic-stock/v1/quotations/invest-opinion', 'FHKST663300C0', {
            'FID_COND_MRKT_DIV_CODE': 'J', 'FID_COND_SCR_DIV_CODE': '16633', 'FID_INPUT_ISCD': code,
            'FID_INPUT_DATE_1': start.replace('-', ''), 'FID_INPUT_DATE_2': end.replace('-', '')})
        return res.get('output') or []

    def estimate_raw(self, code):
        """종목추정실적 원자료를 캐시에 저장만 합니다 (필드 구조 확인 전 계산에 쓰지 않음)."""
        res = self.get('/uapi/domestic-stock/v1/quotations/estimate-perform', 'HHKST668300C0', {'SHT_CD': code})
        path = self.cache / 'estimate' / f'{code}-{date.today().isoformat()}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(res, ensure_ascii=False))
        return res


def consensus_target(opinions, asof, days=90):
    """최근 days일 투자의견의 목표주가 중앙값. 목표가 0(미제시)은 제외."""
    cutoff = (date.fromisoformat(asof) - timedelta(days=days)).strftime('%Y%m%d')
    limit = asof.replace('-', '')
    prices = []
    for o in opinions:
        d = str(o.get('stck_bsop_date', ''))
        try:
            p = float(str(o.get('hts_goal_prc', '0')).replace(',', ''))
        except ValueError:
            continue
        if cutoff <= d <= limit and p > 0:
            prices.append(p)
    if not prices:
        return None
    return {'target_price': median(prices), 'count': len(prices), 'window_days': days,
            'provider': 'KIS', 'verified': True, 'asof': asof}
