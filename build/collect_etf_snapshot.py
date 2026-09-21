"""One-off official-source snapshot; private output, no portfolio data."""
import concurrent.futures
import json
from pathlib import Path
from urllib.request import urlopen, Request
from pepper.etf_holdings import parse_globalx, parse_vaneck, parse_roundhill

SOURCES = {
    'CLOU': 'https://assets.globalxetfs.com/funds/holdings/clou_full-holdings_20260918.csv',
    'BUG': 'https://assets.globalxetfs.com/funds/holdings/bug_full-holdings_20260918.csv',
    'CRAK': 'https://www.vaneck.com/us/en/etf/equity/crak/holdings/download/xlsx/',
    'DRAM': 'https://www.roundhillinvestments.com/assets/data/FilepointRoundhill.40RU.RU_Holdings_09182026.csv',
}

def collect(item):
    ticker, url = item
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=35) as response:
        raw = response.read()
    parser = parse_vaneck if ticker == 'CRAK' else parse_roundhill if ticker == 'DRAM' else parse_globalx
    rows = parser(raw if ticker == 'CRAK' else raw.decode('utf-8-sig'), ticker, url)
    return ticker, rows

if __name__ == '__main__':
    output = Path('data/private/etf_holdings.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for ticker, rows in pool.map(collect, SOURCES.items()):
            result[ticker] = rows
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: {'rows': len(v), 'asof': v[0]['asof'], 'sum': round(sum(r['weight'] for r in v), 6)} for k, v in result.items()}))
