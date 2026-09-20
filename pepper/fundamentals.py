"""Conservative public-statement period alignment, TTM and CAN SLIM evidence."""
from datetime import date,timedelta
from .engine import dupont,attribution


def days(p):
    return (date.fromisoformat(p['end'])-date.fromisoformat(p['start'])).days+1


def exact(points,start,end):
    choices=[p for p in points if p.get('start')==start and p['end']==end]
    return max(choices,key=lambda p:p['filed']) if choices else None


def annual(points):
    result={}
    for p in points:
        if p.get('start') and 350<=days(p)<=380:
            if p['end'] not in result or p['filed']>result[p['end']]['filed']:result[p['end']]=p
    return sorted(result.values(),key=lambda p:p['end'])


def ttm_flow(points,end):
    direct=[p for p in annual(points) if p['end']==end]
    if direct:return direct[-1]
    # Latest YTD + prior FY - comparable prior YTD. No summing overlapping YTD.
    currents=[p for p in points if p.get('start') and p['end']==end and 45<=days(p)<350]
    for cur in sorted(currents,key=days,reverse=True):
        fys=[p for p in annual(points) if p['end']<cur['start'] and (date.fromisoformat(cur['start'])-date.fromisoformat(p['end'])).days==1]
        for fy in reversed(fys):
            prev=[p for p in points if p.get('start')==fy['start'] and abs(days(p)-days(cur))<=7 and 350<=(date.fromisoformat(cur['end'])-date.fromisoformat(p['end'])).days<=380]
            if prev:
                old=max(prev,key=lambda p:p['filed'])
                return {'start':(date.fromisoformat(old['end'])+timedelta(days=1)).isoformat(),'end':end,
                        'val':cur['val']+fy['val']-old['val'],'filed':max(x['filed'] for x in (cur,fy,old)),
                        'sources':[cur,fy,old]}
    return None


def quarters(points):
    return sorted([p for p in points if p.get('start') and 75<=days(p)<=105],key=lambda p:(p['end'],p['filed']))


def evaluate_fundamentals(normalized,asof,rules):
    facts=normalized['facts'];eps=facts.get('eps',[])
    result={'criteria':{k:'UNKNOWN' for k in ['C','A','N','S','L','I','M','DuPont','CashFlow','Valuation']},
            'source':normalized['source'],'filings':normalized.get('filings',[]),'currency':normalized['currency'],
            'limitations':normalized.get('limitations',[]),'metrics':{}}
    q=quarters(eps)
    if q:
        current=q[-1]
        if (date.fromisoformat(asof)-date.fromisoformat(current['end'])).days>200:q=[]
    if q:
        current=q[-1]
        previous=[p for p in q if 350<=(date.fromisoformat(current['end'])-date.fromisoformat(p['end'])).days<=380]
        if previous and previous[-1]['val']>0:
            growth=current['val']/previous[-1]['val']-1
            result['metrics']['quarter_eps_yoy']=growth
            result['criteria']['C']='PASS' if growth>=rules.get('quarter_eps_growth',.25) else 'FAIL'
    years=annual(eps)
    if years and (date.fromisoformat(asof)-date.fromisoformat(years[-1]['end'])).days>550:years=[]
    if len(years)>=4:
        last=years[-4:]
        gaps=[(date.fromisoformat(b['end'])-date.fromisoformat(a['end'])).days for a,b in zip(last,last[1:])]
        if all(350<=g<=380 for g in gaps) and all(p['val']>0 for p in last):
            cagr=(last[-1]['val']/last[0]['val'])**(1/3)-1
            result['metrics']['annual_eps_cagr3']=cagr
            result['criteria']['A']='PASS' if cagr>=rules.get('annual_eps_cagr',.25) and all(b['val']>a['val'] for a,b in zip(last,last[1:])) else 'FAIL'
    ends=sorted({p['end'] for p in facts.get('revenue',[])},reverse=True)
    periods=[]
    for end in ends:
        flows={k:ttm_flow(facts.get(k,[]),end) for k in ('revenue','income','cfo','capex')}
        if not all(flows.values()):continue
        start=flows['revenue']['start']
        if any(v['start']!=start for v in flows.values()):continue
        start_balance=(date.fromisoformat(start)-timedelta(days=1)).isoformat()
        stocks={}
        for k in ('assets','equity'):
            a=[p for p in facts.get(k,[]) if p['end']==start_balance]
            b=[p for p in facts.get(k,[]) if p['end']==end]
            if a and b:stocks[k]=(max(a,key=lambda p:p['filed'])['val']+max(b,key=lambda p:p['filed'])['val'])/2
        if len(stocks)!=2:continue
        row={'매출':flows['revenue']['val'],'순이익':flows['income']['val'],'평균 총자산':stocks['assets'],
             '평균 자기자본':stocks['equity'],'영업현금흐름':flows['cfo']['val'],'CAPEX 지출':flows['capex']['val']}
        try:g=dupont(row)
        except ValueError:continue
        periods.append({'end':end,'start':start,'filed':max(p['filed'] for p in flows.values()),'inputs':row,**g})
        if len(periods)>=8:break
    if periods:
        current=periods[0]
        if (date.fromisoformat(asof)-date.fromisoformat(current['end'])).days>rules.get('max_fundamental_period_age_days',200):
            result['limitations'].append('Latest complete TTM period is stale; do not score C/A or fundamentals')
            result['criteria']['C']=result['criteria']['A']='UNKNOWN'
            return result
        result['ttm']=current
        prior=next((p for p in periods[1:] if 350<=(date.fromisoformat(current['end'])-date.fromisoformat(p['end'])).days<=380),None)
        if prior:
            result['roe_drivers']=attribution(prior['factors'],current['factors'])
            operating=result['roe_drivers']['margin']+result['roe_drivers']['turnover']
            result['criteria']['DuPont']='PASS' if current['roe']>prior['roe'] and operating>0 else 'FAIL'
        result['criteria']['CashFlow']='PASS' if current['fcf']>0 and current['cash_conversion'] is not None and current['cash_conversion']>=1 else 'FAIL'
    # Annual EPS is never relabeled TTM. Four standalone contiguous quarters only.
    if len(q)>=4:
        tail=q[-4:]
        if all((date.fromisoformat(b['start'])-date.fromisoformat(a['end'])).days==1 for a,b in zip(tail,tail[1:])) and 350<=(date.fromisoformat(tail[-1]['end'])-date.fromisoformat(tail[0]['start'])).days+1<=380:
            result['metrics']['ttm_eps']=sum(p['val'] for p in tail)
    return result
