"""Automatic review views and an input-preserving data-repair queue.

Human supplements are evidence to review, never silent overrides of model inputs.
"""
import hashlib
import json
from datetime import date
from urllib.parse import urlparse, quote
from .sheets import column

REVIEW_HEADERS = ['instrument', 'asof', 'price_asof', 'price', 'ma21', 'ma50', 'ma200',
                  'rs_1m', 'rs_3m', 'rs_6m', 'rs_12m', 'volume_ratio20', 'atr_pct',
                  'swing', 'growth', 'roe', 'profit_margin', 'asset_turnover',
                  'equity_multiplier', 'fcf', 'cash_conversion', 'source', 'coverage']
SYSTEM_HEADERS = ['request_id', 'market', 'ticker', 'field', 'scope', 'first_seen',
                  'last_seen', 'auto_state', 'reason', 'required_input']
INPUT_HEADERS = ['input_value', 'source_url', 'source_date', 'period_start',
                 'period_end', 'currency', 'review_note']
REQUEST_HEADERS = SYSTEM_HEADERS + INPUT_HEADERS
MANAGED = ['Review_US', 'Review_KR', 'Review_Other', 'Data_Requests']


def request_id(market, ticker, field, scope='Current'):
    return hashlib.sha256(json.dumps([market, ticker, field, scope]).encode()).hexdigest()[:20]


def build_workspace(result, previous=()):
    old = {}
    for row in previous:
        key = row['request_id']
        if key in old:
            raise ValueError('Duplicate request_id; refusing to overwrite manual input')
        old[key] = row
    pending = {}
    views = {name: [] for name in MANAGED[:3]}

    def need(entry, field, hint, scope='Current'):
        key = request_id(entry['market'], entry['ticker'], field, scope)
        prior = old.get(key, {})
        pending[key] = {**prior, 'request_id': key, 'market': entry['market'],
                        'ticker': entry['ticker'], 'field': field, 'scope': scope,
                        'first_seen': prior.get('first_seen') or result['asof'],
                        'last_seen': result['asof'], 'auto_state': 'NEEDS_INPUT',
                        'reason': '자동 평가 근거 미확인', 'required_input': hint}
        if prior.get('input_value') not in (None, ''):
            pending[key]['auto_state'] = 'SUBMITTED_NOT_VERIFIED'

    for key, entry in result['instruments'].items():
        t = entry.get('technical') or {}
        g = entry.get('growth') or {}
        period = g.get('ttm') or {}
        factors = list(period.get('factors') or [])
        factors += [None] * (3-len(factors))
        bucket = 'Review_' + entry['market'] if entry['market'] in ('US', 'KR') else 'Review_Other'
        values = [key, result['asof'], t.get('asof'), t.get('price'), t.get('ma21'), t.get('ma50'),
                  t.get('ma200'), t.get('rs_1m'), t.get('rs_3m'), t.get('rs_6m'), t.get('rs_12m'),
                  t.get('volume_ratio20'), t.get('atr_pct'), entry['swing']['status'],
                  g.get('status', 'INCOMPLETE'), period.get('roe'), *factors[:3], period.get('fcf'),
                  period.get('cash_conversion'), g.get('source') or entry.get('price_source', ''),
                  'PRICE_UNAVAILABLE' if not t else 'PARTIAL' if not g or not t.get('asof') or t.get('ma200') is None else 'SEE_CRITERIA']
        views[bucket].append(values)
        if not t:
            need(entry, 'price_history', '수집 연결/가격 원자료 확인. 단일 수작업 가격으로 기술 지표를 대체하지 않습니다.')
        else:
            if not t.get('asof'):
                need(entry, 'price_timestamp', '현재가의 실제 거래일·시각 확인. 보고서 생성일로 대체하지 않습니다.')
            missing = [name for name in ('ma21', 'ma50', 'ma200', 'rs_1m', 'rs_3m', 'rs_6m', 'rs_12m', 'volume_ratio20', 'atr_pct') if t.get(name) is None]
            if missing:
                need(entry, 'technical_history', '추가 가격/벤치마크 이력 필요: ' + ', '.join(missing))
            if t.get('stale_days', 0) > 4:
                need(entry, 'price_freshness', '최근 거래일 및 공급자 갱신 여부 확인')
        if entry.get('asset_class') == 'ETF' or entry['market'] not in ('US', 'KR'):
            continue
        if not period:
            for field, hint in [('revenue', '매출'), ('net_income', '순이익'), ('average_assets', '평균 총자산'),
                                ('average_equity', '평균 자기자본'), ('cfo', '영업현금흐름'), ('capex', 'CAPEX 지출(양수)')]:
                need(entry, field, hint + ': 동일 TTM 기간·통화·단위와 공시 링크 입력')
        if not g.get('roe_drivers'):
            need(entry, 'prior_dupont', '전년 동기 TTM 매출/순이익/평균자산/평균자본과 기간·통화·출처')
        criteria = g.get('criteria') or {}
        for criterion in ('C', 'A', 'N', 'S', 'I', 'Valuation'):
            if criteria.get(criterion, 'UNKNOWN') == 'UNKNOWN':
                need(entry, criterion, 'CAN SLIM/가격 기대 판단의 원자료·가정·해당 기간 및 출처')
    # Keep human entries even when a later provider run resolves the data gap.
    for key, row in old.items():
        if key not in pending:
            instrument = f'{row.get("market")}:{row.get("ticker")}'
            pending[key] = {**row, 'auto_state': 'RESOLVED_BY_SOURCE' if instrument in result['instruments'] else 'OUT_OF_SCOPE'}
    return {'views': views, 'requests': list(pending.values())}


def attach_supplements(result, requests):
    """Show sourced human input separately; never promote it to verified metrics."""
    accepted, rejected = [], []
    for row in requests:
        if row.get('input_value') in (None, ''):
            continue
        instrument = f'{row.get("market")}:{row.get("ticker")}'
        if instrument not in result['instruments']:
            continue
        reason = None
        url = urlparse(str(row.get('source_url') or ''))
        if url.scheme not in ('http', 'https') or not url.netloc:
            reason = 'Missing/invalid source URL'
        try:
            stamp = date.fromisoformat(str(row.get('source_date')))
            if stamp > date.fromisoformat(result['asof']):
                reason = 'Source date is after report asof'
        except ValueError:
            reason = 'Missing/invalid ISO source date'
        if reason:
            rejected.append({'request_id': row.get('request_id'), 'reason': reason})
        else:
            accepted.append({'instrument': instrument, 'field': row['field'],
                             'status': 'USER_PROVIDED_NOT_INDEPENDENTLY_VERIFIED',
                             **{k: row.get(k) for k in INPUT_HEADERS}})
    result['manual_supplements'] = accepted
    result['supplement_issues'] = rejected
    return result


def parse_request_values(values):
    if not values:
        return []
    if values[0] != REQUEST_HEADERS:
        raise ValueError('Data_Requests header mismatch')
    if any(row and not row[0] and any(x not in (None, '') for x in row[10:]) for row in values[1:]):
        raise ValueError('Manual input without request_id; restore row identity before publishing')
    parsed = [dict(zip(REQUEST_HEADERS, row + [None]*len(REQUEST_HEADERS)))
              for row in values[1:] if row and row[0]]
    if len({row['request_id'] for row in parsed}) != len(parsed):
        raise ValueError('Duplicate request_id; refusing ambiguous manual input')
    return parsed


def publish_requests(metadata, workspace, previous):
    """Sheets REST requests: write only system columns on existing queue rows.

    Caller must re-read metadata/queue before publishing and serialize writers.
    Human-input cells K:Q are NEVER rewritten or cleared, including when resolved.
    """
    by_name = {s['properties']['title']: s['properties'] for s in metadata['sheets']}
    requests = []
    used = {s['sheetId'] for s in by_name.values()}
    for index, name in enumerate(MANAGED):
        if name not in by_name:
            sid = 9211000+index
            while sid in used:
                sid += 10
            used.add(sid)
            props = {'sheetId': sid, 'title': name, 'gridProperties': {'rowCount': 2000, 'columnCount': 23, 'frozenRowCount': 4, 'hideGridlines': True}}
            requests.append({'addSheet': {'properties': props}})
            by_name[name] = props
            end = max(5, 4 + (len(workspace['requests']) if name == 'Data_Requests' else len(workspace['views'][name])))
            requests.extend([
                {'repeatCell': {'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': end, 'startColumnIndex': 0, 'endColumnIndex': 23}, 'cell': {'userEnteredFormat': {'textFormat': {'fontFamily': 'Roboto Condensed', 'fontSize': 10}, 'wrapStrategy': 'WRAP', 'verticalAlignment': 'TOP'}}, 'fields': 'userEnteredFormat'}},
                {'repeatCell': {'range': {'sheetId': sid, 'startRowIndex': 3, 'endRowIndex': 4, 'startColumnIndex': 0, 'endColumnIndex': 17 if name == 'Data_Requests' else 23}, 'cell': {'userEnteredFormat': {'backgroundColor': {'red': .09, 'green': .20, 'blue': .36}, 'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}}}, 'fields': 'userEnteredFormat(backgroundColor,textFormat)'}},
                {'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': 23}, 'properties': {'pixelSize': 145}, 'fields': 'pixelSize'}},
            ])
            if name == 'Data_Requests':
                requests.extend([
                    {'repeatCell': {'range': {'sheetId': sid, 'startRowIndex': 4, 'endRowIndex': 2000, 'startColumnIndex': 12, 'endColumnIndex': 15}, 'cell': {'userEnteredFormat': {'numberFormat': {'type': 'DATE', 'pattern': 'yyyy-mm-dd'}}}, 'fields': 'userEnteredFormat.numberFormat'}},
                    {'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 8, 'endIndex': 12}, 'properties': {'pixelSize': 280}, 'fields': 'pixelSize'}},
                ])
        rows = len(workspace['requests']) if name == 'Data_Requests' else len(workspace['views'][name])
        if rows+4 > by_name[name]['gridProperties']['rowCount']:
            raise ValueError(f'{name}: capacity exceeded; extend grid explicitly')

    def cells(sid, start, rows, col=0):
        def cell(value):
            if value is None:
                return {}
            # Literal string protects against formula injection from sources/input.
            return {'userEnteredValue': {'numberValue': value} if isinstance(value, (int, float)) and not isinstance(value, bool) else {'stringValue': str(value)}}
        return {'updateCells': {'start': {'sheetId': sid, 'rowIndex': start, 'columnIndex': col},
                                'rows': [{'values': [cell(x) for x in row]} for row in rows], 'fields': 'userEnteredValue'}}
    for name in MANAGED[:3]:
        sid = by_name[name]['sheetId']
        requests.append(cells(sid, 0, [[name + ' | 자동 평가 상세'], ['입력 탭 아님 · 보완 입력은 Data_Requests · 자동 주문 없음']]))
        # These dedicated views are machine-owned; never target user Portfolio/Orders.
        requests.append({'updateCells': {'range': {'sheetId': sid, 'startRowIndex': 3, 'endRowIndex': by_name[name]['gridProperties']['rowCount'], 'startColumnIndex': 0, 'endColumnIndex': len(REVIEW_HEADERS)}, 'rows': [], 'fields': 'userEnteredValue'}})
        requests.append(cells(sid, 3, [REVIEW_HEADERS, *workspace['views'][name]]))
    sid = by_name['Data_Requests']['sheetId']
    requests.append(cells(sid, 0, [['자동 보완 요청'], ['K:Q에 값·출처·날짜·기간·통화·메모 입력. 수작업 보완은 검증 전 근거로 보고서에 표시됩니다.']]))
    requests.append(cells(sid, 3, [REQUEST_HEADERS]))
    positions = {r['request_id']: r.get('_sheet_row', i+4) for i, r in enumerate(previous)}
    if len(positions) != len(previous):
        raise ValueError('Duplicate request IDs')
    if len(set(positions.values())) != len(positions):
        raise ValueError('Duplicate request row positions')
    if any(type(pos) is not int or pos < 4 for pos in positions.values()):
        raise ValueError('Invalid request row position; refusing header overwrite')
    next_row = max(positions.values(), default=3)+1
    for row in workspace['requests']:
        key = row['request_id']
        if key not in positions:
            positions[key] = next_row
            next_row += 1
        if positions[key] >= by_name['Data_Requests']['gridProperties']['rowCount']:
            raise ValueError('Data_Requests capacity exceeded')
        requests.append(cells(sid, positions[key], [[row.get(k) for k in SYSTEM_HEADERS]]))
    return requests


def read_requests(spreadsheet_id, session):
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe="")}'
    meta = session.get(base, params={'fields': 'sheets(properties)'}, timeout=60)
    meta.raise_for_status()
    metadata = meta.json()
    existing = {s['properties']['title'] for s in metadata['sheets']}
    for name in MANAGED[:3]:
        if name in existing:
            check = session.get(base+f'/values/{name}!A4:W4', timeout=60)
            check.raise_for_status()
            if check.json().get('values') != [REVIEW_HEADERS]:
                raise ValueError(f'{name}: not a recognized machine-owned view; refusing to clear it')
    if not any(s['properties']['title'] == 'Data_Requests' for s in metadata['sheets']):
        return metadata, []
    # Read the entire queue, including manually extended grids. A fixed bound
    # can hide existing IDs/inputs and cause later publication to overwrite them.
    queue = next(s['properties'] for s in metadata['sheets']
                 if s['properties']['title'] == 'Data_Requests')
    last_row = queue['gridProperties']['rowCount']
    response = session.get(base+f'/values/Data_Requests!A4:Q{last_row}', params={'valueRenderOption': 'UNFORMATTED_VALUE', 'dateTimeRenderOption': 'FORMATTED_STRING'}, timeout=60)
    response.raise_for_status()
    values = response.json().get('values', [])
    parsed = parse_request_values(values)
    positions = {row[0]: i+4 for i, row in enumerate(values[1:]) if row and row[0]}
    for row in parsed:
        row['_sheet_row'] = positions[row['request_id']]
    return metadata, parsed


def session_for_workspace(write=False):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    scope = 'https://www.googleapis.com/auth/spreadsheets' + ('' if write else '.readonly')
    credentials, _ = google.auth.default(scopes=[scope])
    return AuthorizedSession(credentials)


def publish(spreadsheet_id, result):
    session = session_for_workspace(write=True)
    metadata, previous = read_requests(spreadsheet_id, session)
    workspace = build_workspace(result, previous)
    requests = publish_requests(metadata, workspace, previous)
    response = session.post(f'https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe="")}:batchUpdate', json={'requests': requests}, timeout=90)
    response.raise_for_status()
    return workspace
