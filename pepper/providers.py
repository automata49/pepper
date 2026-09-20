"""Bounded provider adapters. Errors are surfaced, never replaced with invented data."""
import json
import os
import time
import hashlib
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error


class ProviderError(RuntimeError):
    pass


def request_json(url, headers=None, timeout=25):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers or {}),timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==2:
                raise ProviderError(f'HTTP {e.code}') from None
        except (TimeoutError, urllib.error.URLError):
            if attempt==2:raise ProviderError('Network unavailable/timeout') from None
        time.sleep(2**attempt)


def fdr_prices(symbol, start, end):
    import FinanceDataReader as fdr
    # Yahoo-backed readers use an exclusive end; Korean readers may be inclusive.
    frame=fdr.DataReader(symbol,start,(date.fromisoformat(end)+timedelta(days=1)).isoformat())
    if frame is None or frame.empty:
        raise ProviderError('Empty price response')
    required=['Open','High','Low','Close','Volume']
    if any(k not in frame for k in required):
        raise ProviderError('Provider did not return full OHLCV')
    return [{'date':str(i.date()),**{k.lower():float(r[k]) for k in required}} for i,r in frame.iterrows() if str(i.date())<=end]


def sec_company(cik, asof, cache='data/cache'):
    user_agent=os.environ.get('SEC_USER_AGENT','')
    if '@' not in user_agent:
        raise ProviderError('SEC_USER_AGENT must identify application and contact email')
    cik=str(cik).zfill(10)
    if not cik.isdigit():raise ProviderError('Invalid CIK')
    result={}
    for kind,url in [('facts',f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'),('filings',f'https://data.sec.gov/submissions/CIK{cik}.json')]:
        path=Path(cache)/f'sec-{cik}-{kind}-{date.today().isoformat()}.json'
        if path.exists():data=json.loads(path.read_text())
        else:
            data=request_json(url,{'User-Agent':user_agent,'Accept-Encoding':'identity'})
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data))
            time.sleep(.12)
        result[kind]=data
    result['source']=f'https://www.sec.gov/edgar/browse/?CIK={cik}'
    return result


def sec_cik_map():
    agent=os.environ.get('SEC_USER_AGENT','')
    if '@' not in agent:raise ProviderError('SEC_USER_AGENT required')
    data=request_json('https://www.sec.gov/files/company_tickers.json',{'User-Agent':agent})
    return {v['ticker']:str(v['cik_str']).zfill(10) for v in data.values()}


SEC_TAGS={
 'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet'],
 'income':['NetIncomeLoss'], 'assets':['Assets'], 'equity':['StockholdersEquity'],
 'cfo':['NetCashProvidedByUsedInOperatingActivities'],
 'capex':['PaymentsToAcquirePropertyPlantAndEquipment'],
 'eps':['EarningsPerShareDiluted','EarningsPerShareBasic'],
 'shares':['CommonStockSharesOutstanding']}


def normalize_sec(payload, asof):
    """Keep accession, currency, exact duration and filing date for every fact."""
    facts=payload.get('facts',{}).get('facts',{}).get('us-gaap',{})
    normalized={}
    for name,tags in SEC_TAGS.items():
        normalized[name]=[]
        for tag in tags:
            data=facts.get(tag,{})
            unit='USD/shares' if name=='eps' else 'shares' if name=='shares' else 'USD'
            points=[v for v in data.get('units',{}).get(unit,[]) if v.get('filed','9999')<=asof and v.get('end','9999')<=asof and v.get('form') in ('10-K','10-Q','10-K/A','10-Q/A')]
            if points:
                unique={}
                for p in sorted(points,key=lambda v:(v['filed'],v.get('accn',''))):
                    unique[(p.get('start'),p['end'])]={**p,'unit':unit,'tag':tag}
                normalized[name]=list(unique.values());break
    recent=payload.get('filings',{}).get('filings',{}).get('recent',{})
    filings=[]
    for i,d in enumerate(recent.get('filingDate',[])):
        if d<=asof:
            filings.append({'date':d,'form':recent['form'][i],'accession':recent['accessionNumber'][i]})
    return {'facts':normalized,'filings':filings[:30],'source':payload['source'],'currency':'USD'}


def dart_company(corp_code, asof):
    import OpenDartReader
    key=os.environ.get('DART_API_KEY')
    if not key:raise ProviderError('DART_API_KEY missing')
    dart=OpenDartReader(key)
    filings=dart.list(corp=corp_code,start=(date.fromisoformat(asof)-timedelta(days=1500)).isoformat(),end=asof)
    records=[] if filings is None else filings.to_dict('records')
    statements=[]
    year=date.fromisoformat(asof).year
    # Past four fiscal years, exact disclosure IDs gate revised/future records.
    for y in range(year-3,year+1):
        for code in ('11011','11013','11012','11014'):
            frame=dart.finstate_all(corp_code,y,reprt_code=code,fs_div='CFS')
            if frame is None:continue
            for row in frame.to_dict('records'):
                receipt=str(row.get('rcept_no',''))
                if len(receipt)>=8 and receipt[:8]<=asof.replace('-',''):
                    row['_year']=y;row['_report']=code;statements.append(row)
    return {'statements':statements,'filings':[r for r in records if str(r.get('rcept_dt',''))<=asof.replace('-','')],
            'source':'https://opendart.fss.or.kr','currency':'KRW'}


DART_TAGS={'revenue':['ifrs-full_Revenue'], 'income':['ifrs-full_ProfitLoss'],
 'assets':['ifrs-full_Assets'], 'equity':['ifrs-full_Equity'],
 'cfo':['ifrs-full_CashFlowsFromUsedInOperatingActivities'],
 'capex':['ifrs-full_PurchaseOfPropertyPlantAndEquipment'],
 'eps':['ifrs-full_DilutedEarningsLossPerShare','ifrs-full_BasicEarningsLossPerShare']}


def normalize_dart(payload,asof):
    result={k:[] for k in SEC_TAGS}
    for r in payload['statements']:
        if r.get('currency','KRW')!='KRW':continue
        if r.get('sj_div') not in ('BS','IS','CIS','CF'):continue
        name=next((n for n,tags in DART_TAGS.items() if r.get('account_id') in tags),None)
        if not name:continue
        year,code=r['_year'],r['_report']
        end=f'{year}-'+{'11011':'12-31','11013':'03-31','11012':'06-30','11014':'09-30'}[code]
        receipt=str(r.get('rcept_no','')); filed=f'{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}'
        if end>asof or filed>asof:continue
        # CF amount is cumulative. IS/CIS interim amount is standalone 3 months;
        # use explicit cumulative amount for additive flow identities.
        raw=r.get('thstrm_amount') if name in ('assets','equity') or code=='11011' or r['sj_div']=='CF' else r.get('thstrm_add_amount')
        if raw is None or str(raw).strip() in ('','-'):continue
        try:value=float(str(raw).replace(',',''))
        except ValueError:continue
        point={'end':end,'filed':filed,'val':value,'accn':receipt,'unit':'KRW/shares' if name=='eps' else 'KRW','tag':r['account_id']}
        if name not in ('assets','equity'):point['start']=f'{year}-01-01'
        # EPS cannot be derived by subtracting YTD weighted averages reliably.
        # Preserve explicit standalone quarterly EPS if available.
        if name=='eps' and code!='11011':
            raw=r.get('thstrm_amount')
            if not raw or str(raw).strip()=='-':continue
            point['val']=float(str(raw).replace(',',''))
            point['start']=f'{year}-'+{'11013':'01-01','11012':'04-01','11014':'07-01'}[code]
        result[name].append(point)
    # Custom account tags and non-December fiscal years require explicit mapping.
    return {'facts':result,'filings':payload['filings'],'source':payload['source'],'currency':'KRW',
            'limitations':['Standard IFRS tags and December fiscal-year companies only; missing custom tags remain UNKNOWN.']}


def kr_flows(ticker,start,end):
    from pykrx import stock
    frame=stock.get_market_trading_value_by_date(start.replace('-',''),end.replace('-',''),ticker,on='순매수')
    if frame is None or frame.empty:raise ProviderError('No KRX investor flows')
    return [{'date':str(i.date()),'values':{str(k):float(v) for k,v in r.items()}} for i,r in frame.iterrows() if str(i.date())<=end]
