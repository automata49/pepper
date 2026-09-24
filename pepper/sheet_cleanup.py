"""숨김 탭 정리: 보이는 탭(특히 Price_US·Price_KR)이 쓰는 탭은 남기고, 아무도 참조하지 않는 숨김 탭만 삭제합니다.

기본은 점검만(dry-run). --apply를 주면 먼저 Drive에 전체 사본을 만든 뒤 삭제합니다.
사본을 못 만들면 아무것도 지우지 않습니다.
"""
import json
import re
from urllib.parse import quote

ALWAYS_KEEP = ('Price_US', 'Price_KR')


def references(formula, titles):
    """수식 한 칸이 참조하는 탭 이름들. 'Tab'!A1, Tab!A1, INDIRECT("Tab!A1") 같은 문자열 모두 검사."""
    if not isinstance(formula, str) or not formula.startswith('='):
        return set()
    found = set()
    for t in titles:
        if f"'{t}'!" in formula or f"'{t.replace(chr(39), chr(39) * 2)}'!" in formula:
            found.add(t)
        elif re.search(rf'(?<![\w가-힣]){re.escape(t)}!', formula):
            found.add(t)
        elif f'"{t}' in formula:        # INDIRECT 등 문자열 안의 탭 이름 (보수적으로 참조로 간주)
            found.add(t)
    return found


def plan(sheets, formulas, named_ranges=(), protect=ALWAYS_KEEP, chart_refs=None):
    """sheets: [{title, sheetId, hidden}], formulas: {title: 2차원 리스트} → 삭제·유지 계획."""
    titles = [s['title'] for s in sheets]
    by_id = {s['sheetId']: s['title'] for s in sheets}
    refs = {t: set() for t in titles}
    for t, grid in formulas.items():
        for row in grid:
            for cell in row:
                refs[t] |= references(cell, [x for x in titles if x != t])
    for t, ids in (chart_refs or {}).items():   # 차트·피벗의 원본 범위도 참조로 취급
        refs.setdefault(t, set()).update(by_id[i] for i in ids if i in by_id and by_id[i] != t)
    keep = {s['title'] for s in sheets if not s.get('hidden')} | {t for t in protect if t in refs}
    for nr in named_ranges:   # 이름 있는 범위가 가리키는 탭은 보존
        sid = nr.get('range', {}).get('sheetId', 0)
        if sid in by_id:
            keep.add(by_id[sid])
    reason = {t: '보이는 탭' if t in keep else None for t in titles}
    for t in protect:
        if t in reason:
            reason[t] = '보호 탭'
    stack = list(keep)
    while stack:   # 보존 탭이 참조하는 탭도 보존 (연쇄)
        cur = stack.pop()
        for dep in refs.get(cur, ()):
            if dep not in keep:
                keep.add(dep)
                reason[dep] = f'{cur}에서 참조'
                stack.append(dep)
    delete = [s for s in sheets if s['title'] not in keep]
    kept_hidden = [{'title': s['title'], 'reason': reason[s['title']]} for s in sheets if s.get('hidden') and s['title'] in keep]
    if len(delete) == len(sheets):
        raise ValueError('모든 탭이 삭제 대상 — 계획 오류로 중단')
    return {'delete': [{'title': s['title'], 'sheetId': s['sheetId']} for s in delete], 'keep_hidden': kept_hidden}


def fetch(spreadsheet_id, session):
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe="")}'
    r = session.get(base, params={'fields': 'properties.title,sheets(properties,charts.spec,data.rowData.values.pivotTable.source),namedRanges'}, timeout=120)
    r.raise_for_status()
    meta = r.json()
    chart_refs = {}
    for s in meta.get('sheets', []):
        blob = json.dumps({k: v for k, v in s.items() if k != 'properties'})
        chart_refs[s['properties']['title']] = {int(x) for x in re.findall(r'"sheetId": (\d+)', blob)}
    meta['chart_refs'] = chart_refs
    sheets = [{'title': s['properties']['title'], 'sheetId': s['properties']['sheetId'],
               'hidden': bool(s['properties'].get('hidden'))} for s in meta.get('sheets', [])]
    params = [('ranges', f"'{s['title'].replace(chr(39), chr(39) * 2)}'") for s in sheets]
    params.append(('valueRenderOption', 'FORMULA'))
    r = session.get(f'{base}/values:batchGet', params=params, timeout=120)
    r.raise_for_status()
    formulas = {s['title']: vr.get('values', []) for s, vr in zip(sheets, r.json().get('valueRanges', []))}
    return meta, sheets, formulas


def backup(spreadsheet_id, title, session):
    r = session.post(f'https://www.googleapis.com/drive/v3/files/{quote(spreadsheet_id, safe="")}/copy',
                     params={'supportsAllDrives': 'true'}, json={'name': f'{title} (정리 전 백업)'}, timeout=120)
    r.raise_for_status()
    return r.json()['id']


def run(spreadsheet_id, apply=False, session=None, backup_session=None):
    if session is None:
        from .workspace import session_for_workspace
        session = session_for_workspace(write=apply)
    meta, sheets, formulas = fetch(spreadsheet_id, session)
    p = plan(sheets, formulas, meta.get('namedRanges', []), chart_refs=meta.get('chart_refs'))
    p['spreadsheet'] = meta.get('properties', {}).get('title')
    p['applied'] = False
    if not apply or not p['delete']:
        return p
    if backup_session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive'])
        backup_session = AuthorizedSession(creds)
    p['backup_id'] = backup(spreadsheet_id, p['spreadsheet'] or spreadsheet_id, backup_session)
    requests = [{'deleteSheet': {'sheetId': d['sheetId']}} for d in p['delete']]
    r = session.post(f'https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe="")}:batchUpdate',
                     json={'requests': requests}, timeout=120)
    r.raise_for_status()
    p['applied'] = True
    return p
