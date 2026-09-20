"""Read-only Google Sheets integration. No public sharing or write scope."""
import json
from importlib.resources import files
from urllib.parse import quote

SCHEMA = json.loads(files('pepper').joinpath('schema.json').read_text())
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


def column(n):
    result = ''
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def parse_ranges(ranges):
    """Input mapping: sheet name -> values from A5 onward (Settings B5:B19)."""
    settings = [r[0] if r else None for r in ranges['Settings']]
    if len(settings) != 15 or settings[-1] != SCHEMA['version']:
        raise ValueError('Settings schema/version mismatch')
    tables = {}
    for name, headers in SCHEMA['headers'].items():
        values = ranges.get(name, [])
        if not values or values[0] != headers:
            raise ValueError(f'{name}: row 5 headers changed; restore template headers')
        rows = values[1:]
        # Reject overflow instead of silently ignoring holdings after row 105.
        input_count = {'Portfolio': 10, 'Research': 12, 'Financials': 14,
                       'Valuation': 7, 'Prices': 9}[name]
        if any(any(v not in (None, '') for v in r[:input_count]) for r in rows[100:]):
            raise ValueError(f'{name}: more than 100 records; extend schema and sheet formulas first')
        tables[name] = [dict(zip(headers, r + [None] * (len(headers) - len(r))))
                        for r in rows[:100] if any(v not in (None, '') for v in r[:input_count])]
    return {'schema': SCHEMA['version'], 'settings': settings, 'tables': tables}


def fetch(spreadsheet_id):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=SCOPES)
    session = AuthorizedSession(credentials)
    names = ['Settings', *SCHEMA['headers']]
    ranges = ['Settings!B5:B19'] + [f'{n}!A5:{column(len(h))}' for n, h in SCHEMA['headers'].items()]
    response = session.get(
        f'https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe="")}/values:batchGet',
        params=[('ranges', r) for r in ranges] + [('valueRenderOption', 'UNFORMATTED_VALUE'),
                                                 ('dateTimeRenderOption', 'SERIAL_NUMBER')], timeout=60)
    response.raise_for_status()
    return parse_ranges(dict(zip(names, [r.get('values', []) for r in response.json()['valueRanges']])))
