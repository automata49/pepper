"""Watchlist 보드: ETF(기본) + 관심 주식의 가격 지표와 펀더멘털을 한 줄에.

흐름: 가격 수집(공식 우선) → 이동평균·RS·RSI·MACD·Stoch → Minervini Status·4대가 점수 → 표 행
시트에는 'Watchlist_Board' 탭 하나만 씁니다. 기존 'Watchlist' 탭(enabled 체크)은 종목 선택용으로 그대로 둡니다.
"""
import json
from datetime import date
from pathlib import Path

import yaml

from . import indicators
from .bridge import score_inputs
from .technical import calculate, percentiles
from .sources.kis import KISClient, KISError, consensus_target

BOARD_TAB = 'Watchlist_Board'
MANUAL_COLUMNS = ['총보수(입력)', '메모(입력)']
COLUMNS = ['구분', '그룹', 'Ticker', '이름', '기준일', '현재가', '1일%', 'MA50 대비', 'MA200 대비', '52주 고점 대비',
           'RS 백분위', 'RSI14', 'MACD 히스토', 'Stoch %K', 'Stoch %D', '거래량 배수', 'Swing Status', '신호',
           '장기 점수', 'PEG', 'ROE', '적정가 판정', 'Upside', 'KIS 목표가',
           '상위10 비중', '상위 3종목', '가중 Fwd PER(상위10)',
           '가격 출처', '경고'] + MANUAL_COLUMNS
GROUP_ORDER = ['미국 시장', '미국 섹터', '미국 산업·테마', '추가 테마', '한국 시장', '한국 섹터']


def load_config(path='config/watchlist.yaml'):
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def instruments(cfg, sheet_universe=()):
    """기본 ETF + 설정의 stocks + 시트 Watchlist에서 enabled된 주식."""
    items, seen = [], set()
    for e in cfg.get('etfs', []):
        if e.get('enabled', True) is False:
            continue
        items.append({**e, 'ticker': str(e['ticker']), 'asset_class': 'ETF'})
        seen.add(str(e['ticker']))
    for s in list(cfg.get('stocks', [])) + list(sheet_universe):
        t = str(s.get('ticker', '')).strip()
        if not t or t in seen:
            continue
        cls = str(s.get('asset_class') or 'Stock')
        items.append({'ticker': t, 'market': s.get('market', 'US'), 'asset_class': 'ETF' if cls.upper() == 'ETF' else 'Stock',
                      'group': s.get('sector') or s.get('group') or '관심 주식', 'name': s.get('name', '')})
        seen.add(t)
    return items


def _pct(v, n=1):
    return None if v is None else round(v * 100, n)


def _r(v, n=2):
    return None if v is None else round(v, n)


def rs_composite(items, weights):
    """items: {ticker: tech}. 같은 그룹 안에서 3·6·12개월 RS 백분위를 가중평균."""
    percentiles(items)
    for t in items.values():
        got = [(w, t.get(f'{k}_percentile')) for k, w in weights.items() if t.get(f'{k}_percentile') is not None]
        t['rs_composite'] = sum(w * v for w, v in got) / sum(w for w, _ in got) if got else None


def etf_fundamentals(etf, holdings, forward_pe):
    rows = [h for h in holdings if str(h.get('etf')) == etf and str(h.get('kind', 'Equity')).lower() in ('equity', 'stock')]
    if not rows:
        return {}
    rows.sort(key=lambda h: -float(h.get('weight', 0)))
    top = rows[:10]
    out = {'top10_weight': sum(float(h['weight']) for h in top),
           'top3': ', '.join(str(h.get('name') or h.get('ticker')) for h in top[:3]),
           'holdings_asof': max(str(h.get('asof', '')) for h in top)}
    pe = [(float(h['weight']), forward_pe[str(h.get('ticker'))]) for h in top
          if forward_pe.get(str(h.get('ticker'))) and forward_pe[str(h.get('ticker'))] > 0]
    covered = sum(w for w, _ in pe)
    if pe and covered >= 0.5 * out['top10_weight']:
        # 가중 조화평균: 이익 합 ÷ 가격 합과 같은 의미 (PER 단순 가중평균보다 왜곡이 적음)
        out['weighted_forward_pe'] = covered / sum(w / p for w, p in pe)
    return out


def build(cfg, items, prices, benches, asof, fundamentals=None, holdings=(), consensus=None):
    """표 행 목록과 issues를 돌려줍니다. prices/benches: sources.prices.fetch_all 결과."""
    icfg = cfg.get('indicators', {})
    tech, issues = {}, []
    for it in items:
        p = prices.get(it['ticker'])
        bench = benches.get(it['market'])
        if not p or not bench:
            continue
        try:
            tech[it['ticker']] = calculate(p['bars'], bench['bars'], asof)
        except ValueError as e:
            issues.append(f'{it["ticker"]}: 지표 계산 불가 — {e}')
    # RS 순위: ETF끼리·주식끼리, 시장별. 레버리지 ETF 제외
    groups = {}
    for it in items:
        if it['ticker'] in tech and not it.get('leveraged'):
            groups.setdefault((it['asset_class'], it['market']), {})[it['ticker']] = tech[it['ticker']]
    for g in groups.values():
        rs_composite(g, icfg.get('rs_weights', {'rs_3m': .4, 'rs_6m': .2, 'rs_12m': .4}))

    # Minervini Status + (주식) 4대가 점수: 가격 이력과 RS를 기존 펀더멘털 입력에 합쳐 한 번에 계산
    fund = fundamentals or {'tickers': {}}
    scoring = {'asof': asof, 'tickers': {}}
    for it in items:
        t = it['ticker']
        if t not in prices:
            continue
        entry = json.loads(json.dumps(fund.get('tickers', {}).get(t, {})))
        entry.setdefault('facts', {})
        entry['market'] = it['market']
        entry['bars'] = prices[t]['bars']
        rs = tech.get(t, {}).get('rs_composite')
        if rs is not None:
            entry['facts']['rs_percentile'] = rs
        if it['asset_class'] == 'ETF':
            entry['tags'] = list(set(entry.get('tags', [])) | {'etf'})
        scoring['tickers'][t] = entry
    scored = score_inputs(scoring)['tickers'] if scoring['tickers'] else {}
    forward_pe = {t: e.get('facts', {}).get('forward_pe') for t, e in fund.get('tickers', {}).items()}

    rows = []
    for it in items:
        t = it['ticker']
        p, tc, s = prices.get(t), tech.get(t), scored.get(t, {})
        ind = indicators.compute(p['bars'], icfg) if p else {}
        warn = []
        if not p:
            warn.append('가격 없음')
        elif not p['verified']:
            warn.append('비공식 가격')
        if tc and tc['stale_days'] > cfg.get('max_price_age_days', 4):
            warn.append(f'가격 {tc["asof"]} 기준')
        if it.get('leveraged'):
            warn.append(f'레버리지 {it["leveraged"]}x — RS 순위 제외')
        prof = (s.get('profiles') or {})
        val = s.get('valuation') or {}
        row = {
            '구분': it['asset_class'], '그룹': it.get('group', ''), 'Ticker': t, '이름': it.get('name', ''),
            '기준일': tc['asof'] if tc else None, '현재가': _r(tc['price'], 4) if tc else None,
            '1일%': _pct(tc.get('return_1d')) if tc else None,
            'MA50 대비': _pct(tc['price'] / tc['ma50'] - 1) if tc and tc.get('ma50') else None,
            'MA200 대비': _pct(tc['price'] / tc['ma200'] - 1) if tc and tc.get('ma200') else None,
            '52주 고점 대비': _pct(tc.get('dist_52w_high')) if tc else None,
            'RS 백분위': _r(tc.get('rs_composite'), 0) if tc else None,
            'RSI14': _r(ind.get('rsi'), 1),
            'MACD 히스토': _r((ind.get('macd') or {}).get('hist'), 4),
            'Stoch %K': _r((ind.get('stoch') or {}).get('k'), 1),
            'Stoch %D': _r((ind.get('stoch') or {}).get('d'), 1),
            '거래량 배수': _r(tc.get('volume_ratio20')) if tc else None,
            'Swing Status': s.get('swing_status'),
            '신호': ', '.join(ind.get('signals', [])),
            '가격 출처': p['provider'] if p else None,
        }
        if it['asset_class'] == 'Stock':
            peg = next((c.get('value') for c in prof.get('lynch', {}).get('criteria', []) if c['id'] == 'peg'), None)
            roe = fund.get('tickers', {}).get(t, {}).get('facts', {}).get('roe_ttm')
            label = val.get('label')
            if label and val.get('label_status') == 'UNVERIFIED':
                label += '*'
            row.update({'장기 점수': (s.get('composites', {}).get('position') or {}).get('score'),
                        'PEG': _r(peg), 'ROE': _pct(roe), '적정가 판정': label,
                        'Upside': _pct(val.get('upside'))})
            c = (consensus or {}).get(t)
            if c:
                row['KIS 목표가'] = c['target_price']
        else:
            ef = etf_fundamentals(t, holdings, forward_pe) if it.get('holdings', True) is not False else {}
            row.update({'상위10 비중': _pct(ef.get('top10_weight')), '상위 3종목': ef.get('top3'),
                        '가중 Fwd PER(상위10)': _r(ef.get('weighted_forward_pe'), 1)})
            if ef.get('holdings_asof') and (date.fromisoformat(asof) - date.fromisoformat(ef['holdings_asof'])).days > 45:
                warn.append(f'구성 종목 {ef["holdings_asof"]} 기준')
        row['경고'] = ', '.join(warn)
        rows.append(row)
    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    rows.sort(key=lambda r: (r['구분'] != 'ETF', order.get(r['그룹'], 99), r['그룹'],
                             -(r['RS 백분위'] if r['RS 백분위'] is not None else -1)))
    return rows, issues


def kis_consensus(items, asof, client=None):
    client = client or KISClient()
    if not client.available:
        return {}, ['KIS 키 없음 — 한국 주식 목표가 컨센서스 생략']
    out, issues = {}, []
    start = date.fromisoformat(asof).replace(year=date.fromisoformat(asof).year - 1).isoformat()
    for it in items:
        if it['market'] == 'KR' and it['asset_class'] == 'Stock':
            try:
                c = consensus_target(client.invest_opinions(it['ticker'], start, asof), asof)
                if c:
                    out[it['ticker']] = c
            except KISError as e:
                issues.append(f'{it["ticker"]}: KIS 투자의견 실패 — {e}')
    return out, issues


# ── 시트 게시 ──────────────────────────────────────────────
def merge_manual(rows, existing_values):
    """기존 탭의 수동 입력 열을 Ticker 기준으로 옮겨 붙입니다. 사라진 종목의 입력은 따로 돌려줌."""
    if not existing_values:
        return rows, []
    header = existing_values[0]
    if 'Ticker' not in header:
        raise ValueError(f'{BOARD_TAB} 탭 헤더에 Ticker가 없습니다 — 수동 입력 보존을 위해 게시를 중단합니다')
    ti = header.index('Ticker')
    idx = {c: header.index(c) for c in MANUAL_COLUMNS if c in header}
    saved = {}
    for line in existing_values[1:]:
        if len(line) > ti and line[ti]:
            vals = {c: line[i] for c, i in idx.items() if len(line) > i and line[i] != ''}
            if vals:
                if line[ti] in saved:
                    raise ValueError(f'{BOARD_TAB} 탭에 Ticker {line[ti]} 중복 — 게시 중단')
                saved[line[ti]] = vals
    tickers = {r['Ticker'] for r in rows}
    for r in rows:
        r.update(saved.get(r['Ticker'], {}))
    orphans = [{'Ticker': t, **v} for t, v in saved.items() if t not in tickers]
    return rows, orphans


def to_values(rows, orphans=()):
    values = [COLUMNS]
    for r in rows:
        values.append(['' if r.get(c) is None else r.get(c) for c in COLUMNS])
    for o in orphans:   # 목록에서 빠진 종목의 수동 입력도 지우지 않고 맨 아래에 보존
        values.append(['' if c not in o else o[c] for c in COLUMNS[:2]] + [o['Ticker']] + [''] * (len(COLUMNS) - 3 - len(MANUAL_COLUMNS))
                      + [o.get(c, '') for c in MANUAL_COLUMNS])
    return values


def publish(spreadsheet_id, rows, session=None):
    from urllib.parse import quote
    from .workspace import session_for_workspace
    session = session or session_for_workspace(write=True)
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe="")}'
    meta = session.get(base, params={'fields': 'sheets.properties'}, timeout=60)
    meta.raise_for_status()
    sheets = {s['properties']['title']: s['properties'] for s in meta.json().get('sheets', [])}
    if BOARD_TAB not in sheets:
        r = session.post(f'{base}:batchUpdate', json={'requests': [{'addSheet': {'properties': {
            'title': BOARD_TAB, 'gridProperties': {'frozenRowCount': 1, 'frozenColumnCount': 3}}}}]}, timeout=60)
        r.raise_for_status()
        existing = []
    else:
        r = session.get(f'{base}/values/{quote(BOARD_TAB)}', timeout=60)
        r.raise_for_status()
        existing = r.json().get('values', [])
    rows, orphans = merge_manual(rows, existing)
    values = to_values(rows, orphans)
    # clear 후 쓰기는 중간 실패 시 수동 입력이 사라질 수 있어, 남는 옛 행을 빈 값으로 덮어쓰는 방식으로 한 번에 씁니다.
    width = max([len(COLUMNS)] + [len(x) for x in existing])
    values = [v + [''] * (width - len(v)) for v in values]
    values += [[''] * width for _ in range(max(0, len(existing) - len(values)))]
    rng = quote(BOARD_TAB)
    r = session.put(f'{base}/values/{rng}!A1', params={'valueInputOption': 'RAW'}, json={'values': values}, timeout=90)
    r.raise_for_status()
    return {'rows': len(rows), 'orphans': len(orphans)}
