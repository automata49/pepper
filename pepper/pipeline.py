"""Autonomous bounded research run, immutable snapshots, and optional GPT synthesis."""
import hashlib
import json
import os
import subprocess
import sys
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from .technical import calculate,classify,percentiles
from .providers import normalize_sec,normalize_dart
from .fundamentals import evaluate_fundamentals
from .journal import ledger,check_plan


def collect(provider,args,cache='data/cache',timeout=90):
    key=hashlib.sha256(json.dumps(['v2-inclusive-end',provider,args]).encode()).hexdigest()
    path=Path(cache)/f'{provider}-{date.today().isoformat()}-{key}.json'
    if path.exists():return json.loads(path.read_text())
    try:
        run=subprocess.run([sys.executable,'-m','pepper.worker'],input=json.dumps({'provider':provider,'args':args}),capture_output=True,text=True,timeout=timeout)
        # Some libraries print progress; structured response is the last line.
        result=json.loads(run.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:raise RuntimeError(f'{provider}: timeout after {timeout}s') from None
    except (ValueError,IndexError):raise RuntimeError(f'{provider}: invalid response') from None
    if not result.get('ok'):raise RuntimeError(f'{provider}: {result.get("error","failed")}')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result['data'],ensure_ascii=False,allow_nan=False))
    return result['data']


def run(config,asof,journal=None,manual=None):
    day=date.fromisoformat(asof)
    if day>date.today():raise ValueError('Cannot collect future dates')
    start=(day-timedelta(days=550)).isoformat()
    universe=config['universe']
    if journal and config.get('use_journal_universe'):
        universe=journal['universe']
    selectors=config.get('tickers')
    if selectors:universe=[u for u in universe if u['ticker'] in selectors]
    max_symbols=config.get('max_symbols',30)
    if len(universe)>max_symbols:raise ValueError(f'Universe has {len(universe)} entries; set tickers or explicitly raise max_symbols={max_symbols}')
    if not universe:raise ValueError('Universe is empty')
    if len({(u['market'],u['ticker']) for u in universe})!=len(universe):raise ValueError('Duplicate universe instruments')
    result={'asof':asof,'mode':'Live','generated_at':datetime.now(timezone.utc).isoformat(),'instruments':{},'issues':[],
            'method':'FDR daily OHLCV; price adjustment follows provider, not audited total return',
            'configured_universe_size':len(universe),'manual_review':manual}
    benchmarks={}
    for symbol in sorted({u['benchmark'] for u in universe}):
        try:benchmarks[symbol]=collect('prices',[symbol,start,asof],timeout=config.get('provider_timeout',90))
        except RuntimeError as e:result['issues'].append(f'{symbol}: {e}')
    for u in universe:
        t,market=u['ticker'],u['market'];key=f'{market}:{t}'
        entry={**u,'technical':None,'swing':{'status':'DATA_REQUIRED'},'growth':None,'flows':None}
        result['instruments'][key]=entry
        if market not in ('US', 'KR'):
            entry['swing']={'status':'COVERAGE_PENDING'}
            result['issues'].append(f'{key}: unsupported or unverified market; not routed to US prices or DART')
            continue
        try:
            bars=collect('prices',[u.get('provider_symbol',t),start,asof],timeout=config.get('provider_timeout',90))
            m=calculate(bars,benchmarks.get(u['benchmark'],[]),asof)
            entry['technical']=m;entry['swing']=classify(m,config.get('rules',{}))
            entry['price_source']='https://github.com/FinanceData/FinanceDataReader'
        except (RuntimeError,ValueError) as e:result['issues'].append(f'{key}: {e}')
        if u.get('asset_class')=='ETF':
            entry['growth']={'status':'NOT_APPLICABLE','reason':'Company CAN SLIM and DuPont not applied to ETF'}
            continue
        try:
            if market=='US':
                if not u.get('cik'):raise RuntimeError('CIK mapping required for SEC fundamentals')
                normalized=normalize_sec(collect('sec',[u['cik'],asof],timeout=config.get('provider_timeout',90)),asof)
            else:
                if not u.get('corp_code'):raise RuntimeError('DART corp_code required')
                normalized=normalize_dart(collect('dart',[u['corp_code'],asof],timeout=180),asof)
            g=evaluate_fundamentals(normalized,asof,config.get('rules',{}))
            if entry['technical']:
                g['criteria']['L']=entry['swing'].get('criteria',{}).get('RS','UNKNOWN')
            b=benchmarks.get(u['benchmark'])
            if b:
                bm=calculate(b,b,asof)
                if bm['ma50'] is not None and bm['ma200'] is not None and bm['stale_days']<=4:
                    g['criteria']['M']='PASS' if bm['price']>bm['ma50']>bm['ma200'] else 'FAIL'
            # N/S/I qualitative evidence is supplied through the manual review.
            manual_items=(manual or {}).get('research',{}).get(t,{}).get('Growth',{})
            for criterion in ('N','S','I'):
                verdict=manual_items.get(criterion,{}).get('verdict')
                if verdict:g['criteria'][criterion]=verdict
            valuation=(manual or {}).get('valuation',{}).get(t)
            if valuation:
                g['valuation']=valuation
                g['criteria']['Valuation']='PASS' if valuation['growth_headroom']>=0 else 'FAIL'
            g['status']='INCOMPLETE' if 'UNKNOWN' in g['criteria'].values() else 'REVIEWED'
            entry['growth']=g
        except (RuntimeError,ValueError,KeyError) as e:
            result['issues'].append(f'{key}/fundamentals: {e}')
        if market=='KR' and config.get('collect_kr_flows',True):
            try:entry['flows']=collect('flows',[t,(day-timedelta(days=35)).isoformat(),asof],timeout=60)
            except RuntimeError as e:result['issues'].append(f'{key}/flows: {e}')
    # Percentiles are not comparable across US and KR universes.
    for market in ('US','KR'):
        percentiles({k:v['technical'] for k,v in result['instruments'].items() if v['market']==market and v['technical'] and v['technical']['stale_days']<=4})
    result['coverage']={'prices':sum(v['technical'] is not None for v in result['instruments'].values()),
                        'fundamentals':sum(bool(v['growth'] and 'criteria' in v['growth']) for v in result['instruments'].values())}
    if journal:
        result['ledger']=ledger(journal['trades'],asof)
        result['journal_warnings']=journal['warnings']
        result['opening_snapshot']=journal['opening_snapshot']
        # Opening snapshot is a separate reconciliation reference, never summed.
        result['plans']=journal['plans']
        checks=[]
        portfolio=(manual or {}).get('portfolio',{})
        remaining_cash=portfolio.get('cash')
        total_risk=0.
        for plan in journal['plans']:
            if not portfolio.get('complete') or remaining_cash is None:
                checks.append({'id':plan['id'],'status':'PORTFOLIO_INPUT_REQUIRED'});continue
            held=sum(p['quantity'] for p in portfolio['positions'] if p['ticker']==plan['ticker'])
            fills=result['ledger']['fills_by_plan'].get(plan['id'],0)
            check=check_plan(plan,portfolio['nav'],remaining_cash,held,fills)
            checks.append({'id':plan['id'],**check})
            if check['status']=='PASS' and plan['action']=='BUY':
                remaining_cash-=check['remaining']*plan['entry']*plan['fx']
                total_risk+=check['risk']
        result['order_checks']={'checks':checks,'reserved_buy_risk':total_risk,'cash_after_approved_buys':remaining_cash,
                                'note':'Pending sell proceeds are not spendable cash. Plan checks exclude fees and need execution confirmation.'}
        result['fundamental_reference']=journal['fundamental_reference']
    return result


def markdown(result,kind,previous=None):
    from .reports import clean,fmt,portfolio_lines
    lines=[f'# Pepper {kind} — {result["asof"]}','','실데이터 수집 결과. 공급자별 누락은 아래에 표시하며 매수 지시가 아닙니다.',
           f'가격 수집 {result["coverage"]["prices"]}/{result["configured_universe_size"]}, 재무 수집 {result["coverage"]["fundamentals"]}.',
           '', '## 데이터 점검','']
    lines += [f'- {clean(x)}' for x in result['issues']] or ['수집 오류 없음.']
    if previous:
        lines+=['',f'비교 기준일: {previous["asof"]}. 신규/변경된 상태:']
        for k,e in result['instruments'].items():
            old=previous['instruments'].get(k,{}).get('swing',{}).get('status')
            if old!=e['swing']['status']:lines.append(f'- {clean(k)}: {old or "신규"} → {e["swing"]["status"]}')
    else:lines+=['','비교 가능한 이전 스냅샷 없음. 변화·성과 판단 보류.']
    lines+=['','## Swing 후보','','| 종목 | 상태 | RS 1M | RS 3M | 거래량/20D | ATR% | Next Leader |','|---|---|---:|---:|---:|---:|---|']
    ranked=sorted(result['instruments'].items(),key=lambda kv:((kv[1]['technical'] or {}).get('rs_3m') is not None,(kv[1]['technical'] or {}).get('rs_3m') or -999),reverse=True)
    for k,e in ranked:
        m=e['technical'] or {}
        lines.append(f'| {clean(k)} | {e["swing"]["status"]} | {fmt(m.get("rs_1m"),True)} | {fmt(m.get("rs_3m"),True)} | {fmt(m.get("volume_ratio20"))} | {fmt(m.get("atr_pct"),True)} | {e["swing"].get("next_leader")} |')
    lines+=['','가격 기반 후보 정렬이며 종합 투자 점수가 아닙니다. 20일 이전 고점은 자동 pivot 대용치로, 수작업 차트 확인이 필요합니다.','', '## Position Growth','']
    for k,e in result['instruments'].items():
        g=e['growth']
        lines.append(f'### {clean(k)}')
        if not g:lines.append('공시·재무 자료 부족. 평가 보류.');continue
        if 'criteria' not in g:lines.append(g.get('reason','N/A'));continue
        lines.append(' · '.join(f'{c}: {v}' for c,v in g['criteria'].items()))
        lines.append('지표: '+clean(g['metrics']))
        if g.get('ttm'):lines.append('DuPont/현금흐름: '+clean({k:v for k,v in g['ttm'].items() if k!='inputs'}))
        if g.get('roe_drivers'):lines.append('ROE 변화 기여도: '+clean(g['roe_drivers']))
        lines.append('출처: '+g['source'])
        lines+=['- '+clean(x) for x in g.get('limitations',[])]
        lines+=['- 공시: '+clean(f) for f in g.get('filings',[])[:3]]
    if result.get('manual_review'):
        lines+=['']+portfolio_lines(result['manual_review'])
    if result.get('ledger'):
        l=result['ledger'];lines+=['','## 체결 기록 및 복기',f'장부 완전성: {l["complete"]}. 오류 {len(l["errors"])}건.',l['note']]
        if l['complete']:
            lines.append('체결별 실현 승률: '+fmt(l['win_rate'],True))
            for p in l['positions']:lines.append('- '+clean(p))
        else:lines.append('오류가 있는 장부에서 총손익과 승률을 확정하지 않습니다.')
        lines+=['- '+clean(e) for e in l['errors']]
        lines+=['','## 주문 계획 점검',clean(result.get('order_checks',{}))]
    if kind=='Weekly':lines+=['','## 주간 복기','- 신규 진입·분할매수·청산 사유와 원래 Plan ID 대조','- 손절 준수 여부, Setup별 실현 결과 검토','- N/S/I와 향후 이벤트는 수작업 근거 확인. 공시일은 미래 실적 발표 예정일이 아닙니다.']
    return '\n'.join(lines)+'\n'


def save_run(result,root='data/runs',output='reports',llm=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    prior=[]
    for p in sorted(root.glob('*/result.json'),reverse=True):
        r=json.loads(p.read_text())
        if r['asof']<result['asof']:prior.append(r)
    daily=max(prior,key=lambda r:r['asof']) if prior else None
    old=[r for r in prior if (date.fromisoformat(result['asof'])-date.fromisoformat(r['asof'])).days>=7]
    weekly=max(old,key=lambda r:r['asof']) if old else None
    dest=root/(result['asof']+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    dest.mkdir();out=Path(output);out.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    (dest/'result.json').write_text(encoded)
    (out/'result.json').write_text(encoded)
    for kind in ['Daily','Weekly','Portfolio']:
        text=markdown(result,kind,weekly if kind=='Weekly' else daily)
        (dest/(kind.lower()+'.md')).write_text(text)
        (out/(kind.lower()+'.md')).write_text(text)
    return dest
