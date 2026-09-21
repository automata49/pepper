"""Official holdings parsers. Preserve cash/derivatives; never treat them as stocks."""
import csv
import io
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date

VENUES = {'KS': ('KR', 'KRX'), 'JP': ('JP', 'TYO'), 'SS': ('SE', 'STO'),
          'LN': ('GB', 'LON'), 'LI': ('GB', 'LON'), 'FH': ('FI', 'HEL'),
          'PW': ('PL', 'WSE'), 'TI': ('TR', 'IST'), 'HB': ('HU', 'BUD'),
          'AV': ('AT', 'VIE'), 'PL': ('PT', 'ELI'), 'AU': ('AU', 'ASX'),
          'GA': ('GR', 'ATH'), 'TT': ('TW', 'TPE'), 'TB': ('TH', 'BKK'),
          'C1': ('CN', 'SHA')}
SWAPS = {'595112103': ('MU', 'US', 'US'), '6450267': ('000660', 'KR', 'KRX'),
         '6771720': ('005930', 'KR', 'KRX')}


def holding(etf, ticker, name, percent, kind, identifier, asof, source):
    weight = float(str(percent).replace('%', '').replace(',', '')) / 100
    if not math.isfinite(weight):
        raise ValueError('Non-finite holding weight')
    date.fromisoformat(asof)
    raw = str(ticker or '').strip()
    symbol, market, exchange = raw, 'US', 'US'
    status = 'SOURCE_REPORTED'
    pieces = raw.rsplit(' ', 1)
    if len(pieces) == 2 and pieces[1] in VENUES:
        symbol = pieces[0]
        market, exchange = VENUES[pieces[1]]
    elif len(pieces) == 2 or raw == 'SKHY':
        market = exchange = 'UNVERIFIED'
        status = 'EXCHANGE_UNVERIFIED'
    if kind == 'Swap':
        mapped = SWAPS.get(identifier.split(' ')[0])
        if mapped:
            symbol, market, exchange = mapped
            status = 'UNDERLYING_MAPPED'
        else:
            symbol, market, exchange, status = '', 'UNVERIFIED', 'UNVERIFIED', 'UNDERLYING_UNVERIFIED'
    elif kind != 'Equity':
        symbol, market, exchange = '', 'N/A', 'N/A'
    if market == 'KR' and symbol.isdigit():
        symbol = symbol.zfill(6)
    return dict(etf=etf, raw_ticker=raw, name=name, weight=weight, instrument_type=kind,
                identifier=identifier, ticker=symbol, market=market, exchange=exchange,
                asof=asof, source=source, verification=status)


def parse_globalx(text, etf, source):
    lines = text.lstrip('\ufeff').splitlines()
    match = re.search(r'as of (\d{2}/\d{2}/\d{4})', '\n'.join(lines[:3]))
    if not match or not any('Ticker' in line for line in lines[:4]):
        raise ValueError('Unexpected Global X header')
    asof = datetime.strptime(match[1], '%m/%d/%Y').date().isoformat()
    start = next(i for i, line in enumerate(lines) if line.startswith('% of Net Assets,'))
    result = []
    for r in csv.DictReader(lines[start:]):
        if not r.get('Name'):  # legal footer, not a position
            continue
        ticker = r.get('Ticker') or ''
        kind = 'Future' if ticker.endswith(' Index') else 'Equity' if ticker else 'Cash/Other'
        result.append(holding(etf, ticker, r['Name'], r['% of Net Assets'], kind,
                              r.get('SEDOL') or '', asof, source))
    return validate(result)


def xlsx_rows(content):
    """Read the first holdings sheet, without evaluating or importing formulas."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        sheet = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        rows = []
        for row in sheet.findall('.//s:sheetData/s:row', ns):
            values = {}
            for c in row.findall('s:c', ns):
                if c.find('s:f', ns) is not None:
                    raise ValueError('Unexpected formula in holdings source')
                v = c.find('s:v', ns)
                val = v.text if v is not None else ''.join(c.find('s:is', ns).itertext()) if c.find('s:is', ns) is not None else ''
                if c.get('t') == 's':
                    val = strings[int(val)]
                col = re.match(r'[A-Z]+', c.get('r'))[0]
                values[col] = val
            rows.append(values)
        return rows


def parse_vaneck(content, etf, source):
    rows = xlsx_rows(content)
    match = re.search(r'(\d{2}/\d{2}/\d{4})', rows[0].get('A', ''))
    if not match:
        raise ValueError('VanEck holdings date missing')
    asof = datetime.strptime(match[1], '%m/%d/%Y').date().isoformat()
    header = next((i for i, r in enumerate(rows) if r.get('B') == 'Ticker'), None)
    if header is None or rows[header].get('I') != '% of Net Assets':
        raise ValueError('VanEck schema changed')
    result = [holding(etf, r['B'], r.get('C') or r['B'], r['I'],
                      'Equity' if r['F'] == 'Stock' else 'Cash/Other' if 'Cash' in r['F'] else 'Other',
                      r.get('D', ''), asof, source)
              for r in rows[header + 1:] if r.get('A', '').isdigit()]
    return validate(result)


def parse_roundhill(text, etf, source):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    required = {'Account', 'Date', 'StockTicker', 'CUSIP', 'SecurityName', 'Weightings', 'MoneyMarketFlag'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Roundhill schema changed')
    result = []
    for r in reader:
        if r['Account'] != etf:
            continue
        ticker, name, identifier = r['StockTicker'], r['SecurityName'], r['CUSIP']
        kind = ('Swap' if ' TRS ' in ticker else 'Cash/Other' if identifier.startswith('CASH') or ticker == 'Cash&Other'
                else 'MoneyMarket' if r['MoneyMarketFlag'] == 'Y' else 'Treasury' if 'Treasury Bill' in name else 'Equity')
        # Keep source Date verbatim; the website subtracts one calendar day for display.
        asof = datetime.strptime(r['Date'], '%m/%d/%Y').date().isoformat()
        item = holding(etf, ticker, name, r['Weightings'], kind, identifier, asof, source)
        item['date_note'] = 'Source file Date; website displays Date minus one calendar day. Not a verified trading timestamp.'
        result.append(item)
    return validate(result)


def validate(rows):
    if not rows:
        raise ValueError('No holdings returned')
    if len({r['asof'] for r in rows}) != 1:
        raise ValueError('Mixed holdings dates')
    # Includes signed cash and swaps; not a stock-only normalization.
    if abs(sum(r['weight'] for r in rows) - 1) > .01:
        raise ValueError('Full holdings weights do not reconcile to 100% within rounding tolerance')
    return rows


def security_universe(rows):
    """Unique exchange-aware review candidates, not an automatic buy/enable list."""
    unique = {}
    for r in rows:
        if r['instrument_type'] not in ('Equity', 'Swap') or not r['ticker']:
            continue
        key = (r['market'], r['ticker'])
        item = unique.setdefault(key, {k: r[k] for k in ('ticker', 'market', 'exchange', 'name')})
        item.setdefault('etfs', [])
        if r['etf'] not in item['etfs']:
            item['etfs'].append(r['etf'])
    return list(unique.values())
