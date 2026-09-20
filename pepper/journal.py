"""Read selected Trading_Journal_V2 data. Never extract Settings or API keys."""
import hashlib
import json
import math
import posixpath
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, timedelta

NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
ALLOWED = {'Trades','Portfolio','Fundamental','Added_Stocks','Universe','Review','Plan','Cycle'}


def read_xlsx(path):
    with zipfile.ZipFile(path) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        rels = {x.get('Id'):x.get('Target') for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        result = {}
        for sh in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS):
            name = sh.get('name')
            if name not in ALLOWED:
                continue
            target = rels[sh.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            cells = {}
            for c in ET.fromstring(z.read(target)).findall('.//s:sheetData/s:row/s:c',NS):
                # Do not import formula caches: GOOGLEFINANCE snapshots may be stale.
                if c.find('s:f',NS) is not None:
                    continue
                v, inline = c.find('s:v',NS), c.find('s:is',NS)
                value = v.text if v is not None else ''.join(inline.itertext()) if inline is not None else None
                if c.get('t') == 's' and value is not None:
                    value = strings[int(value)]
                elif c.get('t') not in ('inlineStr','str','e','b') and value is not None:
                    value = float(value)
                if value is not None:
                    cells[c.get('r')] = value
            result[name] = cells
        return result


def ticker(value, market=None):
    s = str(value).strip()
    if s.endswith('.0') and s[:-2].isdigit():
        s = s[:-2]
    return s.zfill(6) if market == 'KR' and s.isdigit() else s


def import_journal(path):
    cells = read_xlsx(path)
    trades, holdings, fundamentals, universe, reviews, plans = [], [], [], {}, [], []
    for row in range(2, 10001):
        c = cells.get('Trades',{})
        if not c.get(f'B{row}'):
            continue
        raw = {col:c.get(f'{col}{row}') for col in 'ABCDEFGHIJKLMNOPQ'}
        market = raw['C']
        t = {'id':raw['A'] or f'journal-trade-row-{row}', 'ticker':ticker(raw['B'],market),
             'market':market,'action':raw['D'],'date':(date(1899,12,30)+timedelta(days=raw['E'])).isoformat() if isinstance(raw['E'],(int,float)) else raw['E'],
             'quantity':raw['F'],'price':raw['G'],'fee':raw['H'] if raw['H'] is not None else 0,
             'setup':raw['I'],'reason':raw['J'],'stop':raw['K'],'stage':raw['L'],
             'notes':raw['M'],'plan_id':raw['P'],'currency':'KRW' if market=='KR' else 'USD',
             'source_row':row,'account':'UNASSIGNED','strategy':'UNASSIGNED'}
        trades.append(t)
    c=cells.get('Portfolio',{})
    for row in range(7,1001):
        if c.get(f'A{row}'):
            market='KR' if c.get(f'B{row}') in ('KRX','KOSPI','KOSDAQ') else 'US'
            holdings.append({'ticker':ticker(c[f'A{row}'],market),'market':market,'quantity':c.get(f'H{row}'),
                             'average_cost':c.get(f'I{row}'),'account':str(c.get(f'AB{row}','UNASSIGNED')),
                             'asof':None,'source_row':row})
        if c.get(f'AD{row}'):
            plans.append({'id':c.get(f'AS{row}') or f'journal-plan-row-{row}', 'ticker':ticker(c[f'AD{row}']),
                          'action':c.get(f'AE{row}'),'entry':c.get(f'AH{row}'),'stop':c.get(f'AI{row}'),
                          'target':c.get(f'AJ{row}'),'quantity':c.get(f'AK{row}'),'fx':c.get(f'AL{row}'),
                          'decision':c.get(f'AQ{row}'),'reason':c.get(f'AR{row}'),'review':c.get(f'AV{row}')})
    c=cells.get('Fundamental',{})
    for row in range(8,109):
        if c.get(f'A{row}'):
            fundamentals.append({key:c.get(f'{col}{row}') for col,key in [('A','ticker'),('B','name'),('C','roe_ttm'),('D','pe_ttm'),('E','forward_pe'),('F','pbr'),('G','eps_forecast_3y'),('M','asof_serial'),('N','source'),('O','note'),('P','category')]})
    c=cells.get('Universe',{})
    for row in range(2,10001):
        if not c.get(f'D{row}'):
            continue
        exchange=c.get(f'E{row}','')
        market='KR' if exchange in ('KRX','KOSPI','KOSDAQ','KR') else 'US'
        t=ticker(c[f'D{row}'],market)
        universe[(market,t)]={'ticker':t,'market':market,'asset_class':c.get(f'A{row}'),
                              'sector':c.get(f'B{row}'),'theme':c.get(f'H{row}'),'priority':c.get(f'G{row}'),
                              'benchmark':'KS11' if market=='KR' else 'SPY'}
    for h in holdings:
        universe.setdefault((h['market'],h['ticker']),{'ticker':h['ticker'],'market':h['market'],'benchmark':'KS11' if h['market']=='KR' else 'SPY','asset_class':'Unknown'})
    # Preserve human review text only; no formula caches or cross-sheet copies.
    for address,value in cells.get('Review',{}).items():
        if isinstance(value,str): reviews.append({'cell':address,'text':value})
    return {'schema':'pepper-journal-v1','source_sha256':hashlib.sha256(open(path,'rb').read()).hexdigest(),
            'source_kind':'uploaded_snapshot','trades':trades,'opening_snapshot':holdings,
            'fundamental_reference':fundamentals,'universe':list(universe.values()),'plans':plans,'reviews':reviews,
            'warnings':['Snapshot as-of unknown; never add opening_snapshot to trade-derived holdings.',
                        'Trade accounts/strategies require assignment before account-level reconciliation.',
                        'Imported price caches and Settings/secrets intentionally excluded.',
                        'Fundamental reference ratios are not raw statements and cannot reconstruct DuPont inputs.']}


def ledger(trades, asof):
    positions=defaultdict(lambda:{'quantity':0.,'cost':0.,'realized':0.,'cash_flow':0.})
    seen=set(); errors=[]; closed=[]; fills=defaultdict(float)
    for t in sorted(trades,key=lambda x:(str(x.get('date') or ''),x.get('source_row',0))):
        try:
            if not t.get('date') or date.fromisoformat(t['date']) > date.fromisoformat(asof):
                raise ValueError('Missing/future trade date')
            if not t.get('id') or t['id'] in seen:
                raise ValueError('Missing/duplicate trade ID')
            seen.add(t['id'])
            if t['action'] not in ('BUY','SELL') or t['currency'] not in ('KRW','USD'):
                raise ValueError('Invalid action/currency')
            q,p,f=t['quantity'],t['price'],t['fee']
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (q,p,f)) or q<=0 or p<=0 or f<0:
                raise ValueError('Invalid quantity/price/absolute fee')
            key=(t.get('account','UNASSIGNED'),t['ticker'],t['currency'])
            pos=positions[key]
            if t['action']=='BUY':
                pos['quantity']+=q; pos['cost']+=q*p+f; pos['cash_flow']-=q*p+f
            else:
                if q>pos['quantity']+1e-9:
                    raise ValueError('Sell exceeds ledger holdings; opening trades missing')
                basis=pos['cost']/pos['quantity']*q
                pnl=q*p-f-basis
                pos['quantity']-=q;pos['cost']-=basis;pos['realized']+=pnl;pos['cash_flow']+=q*p-f
                closed.append({'trade_id':t['id'],'ticker':t['ticker'],'currency':t['currency'],'realized':pnl,'plan_id':t.get('plan_id')})
            if t.get('plan_id'):fills[t['plan_id']]+=q
        except (ValueError,KeyError,TypeError) as e:
            errors.append({'trade_id':t.get('id'),'reason':str(e)})
    return {'complete':not errors,'errors':errors,'positions':[dict(account=k[0],ticker=k[1],currency=k[2],average_cost=v['cost']/v['quantity'] if v['quantity']>0 else None,**v) for k,v in positions.items()],
            'realizations':closed,'fills_by_plan':dict(fills),
            'win_rate':sum(x['realized']>0 for x in closed)/len(closed) if closed and not errors else None,
            'note':'Moving-average cost, fees in quote currency. Partial sells are realization events, not completed trading cycles. No tax-lot advice.'}


def check_plan(plan, nav, cash, held_qty, fills=0, risk_limit=.01, min_rr=2):
    try:
        q,p,stop,target,fx=(float(plan[k]) for k in ('quantity','entry','stop','target','fx'))
        if not all(math.isfinite(x) for x in (q,p,stop,target,fx,nav,cash,fills)) or min(q,p,stop,target,fx,nav)<=0 or not 0<=fills<=q:
            raise ValueError('Invalid inputs/fills')
        remaining=q-fills
        if plan['action']=='SELL':
            return {'remaining':remaining,'status':'PASS' if remaining<=held_qty else 'BLOCKED_OVERSELL','risk':None,'reward_risk':None}
        if plan['action']!='BUY' or not stop<p<target:
            raise ValueError('BUY requires stop < entry < target')
        risk=remaining*(p-stop)*fx; rr=(target-p)/(p-stop)
        reasons=[]
        if remaining*p*fx>cash:reasons.append('CASH')
        if risk/nav>risk_limit:reasons.append('RISK')
        if rr<min_rr:reasons.append('REWARD_RISK')
        return {'remaining':remaining,'risk':risk,'reward_risk':rr,'status':'PASS' if not reasons else 'BLOCKED_'+','.join(reasons)}
    except (ValueError,KeyError,TypeError):
        return {'status':'INPUT_REQUIRED','risk':None,'reward_risk':None}
