"""가격 출처 선택: 설정된 우선순위대로 공식 출처를 먼저 쓰고, 실패하면 비공식 출처로 내려갑니다.

결과마다 provider와 verified를 붙여 Watchlist에 '가격 출처'로 표시합니다.
"""
from datetime import date, timedelta
from .krx import KRXClient, KRXError

UNOFFICIAL = {'KR': 'NAVER(비공식, FinanceDataReader)', 'US': 'YAHOO(비공식, FinanceDataReader)'}
FDR_BENCH = {'KR': 'KS11', 'US': 'SPY'}


def _fdr(symbol, start, end):
    from ..providers import fdr_prices
    return fdr_prices(symbol, start, end)


def fetch_all(instruments, asof, cfg, krx=None, fdr=_fdr):
    """instruments: [{ticker, market, asset_class}] → ({ticker: {bars, provider, verified}}, {market: bench}, issues)"""
    days = cfg.get('history_days', 400)
    start = (date.fromisoformat(asof) - timedelta(days=days)).isoformat()
    order = cfg.get('price_sources', {'KR': ['krx_openapi', 'fdr'], 'US': ['fdr']})
    krx = krx or KRXClient()
    prices, benches, issues = {}, {}, []

    kr = [i for i in instruments if i['market'] == 'KR']
    if kr and 'krx_openapi' in order.get('KR', []) and krx.available:
        try:
            kinds = ['KOSPI', 'KOSDAQ', 'ETF']
            bars, index = krx.history({i['ticker'] for i in kr}, kinds, start, asof, index_name='코스피')
            for t, b in bars.items():
                if b:
                    prices[t] = {'bars': b, 'provider': 'KRX Open API', 'verified': True}
            if index:
                benches['KR'] = {'bars': index, 'provider': 'KRX Open API', 'verified': True}
        except KRXError as e:
            issues.append(f'KRX Open API 실패 → 예비 출처 사용: {e}')

    for market in ('KR', 'US'):
        if 'fdr' not in order.get(market, []):
            continue
        for i in instruments:
            if i['market'] != market or i['ticker'] in prices:
                continue
            try:
                prices[i['ticker']] = {'bars': fdr(i['ticker'], start, asof), 'provider': UNOFFICIAL[market],
                                       'verified': False}
            except Exception as e:  # noqa: BLE001 — 공급자 오류는 종목별로 기록하고 계속
                issues.append(f'{i["ticker"]}: 가격 수집 실패 ({type(e).__name__})')
        if market not in benches and any(i['market'] == market for i in instruments):
            try:
                benches[market] = {'bars': fdr(FDR_BENCH[market], start, asof), 'provider': UNOFFICIAL[market],
                                   'verified': False}
            except Exception as e:  # noqa: BLE001
                issues.append(f'{market} 벤치마크 수집 실패 ({type(e).__name__})')
    return prices, benches, issues
