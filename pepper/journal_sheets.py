"""Schema shared by the private journal tabs and read-only pipeline."""
from .sheets import SCOPES,column

FIELDS={
 'Journal_Trades':['id','ticker','market','action','date','quantity','price','fee','setup','reason','stop','stage','notes','plan_id','account','strategy','currency'],
 'Journal_Holdings':['ticker','market','quantity','average_cost','account','asof'],
 'Journal_Fundamentals':['ticker','name','roe_ttm','pe_ttm','forward_pe','pbr','eps_forecast_3y','asof_serial','source','note','category'],
 'Watchlist':['ticker','market','asset_class','sector','theme','priority','benchmark','enabled','cik','corp_code'],
 'Orders':['id','ticker','action','entry','stop','target','quantity','fx','decision','reason','review']}
KEYS={'Journal_Trades':'trades','Journal_Holdings':'opening_snapshot','Journal_Fundamentals':'fundamental_reference','Watchlist':'universe','Orders':'plans'}

def rows(journal):
    return {name:[[r.get(k) for k in fields] for r in journal[KEYS[name]]] for name,fields in FIELDS.items()}

def fetch_journal(spreadsheet_id):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials,_=google.auth.default(scopes=SCOPES)
    session=AuthorizedSession(credentials)
    names=list(FIELDS)
    response=session.get(f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet',
        params=[('ranges',f'{n}!A4:{column(len(FIELDS[n]))}2000') for n in names]+[('valueRenderOption','UNFORMATTED_VALUE'),('dateTimeRenderOption','SERIAL_NUMBER')],timeout=60)
    response.raise_for_status()
    result={'schema':'pepper-journal-v1','warnings':['Journal_Holdings is a reconciliation reference, never added to trade-derived holdings.'],'reviews':[]}
    from .engine import day
    for name,value_range in zip(names,response.json()['valueRanges']):
        values=value_range.get('values',[])
        if not values or values[0][:len(FIELDS[name])]!=FIELDS[name]:raise ValueError(f'{name}: header mismatch')
        records=[dict(zip(FIELDS[name],r+[None]*len(FIELDS[name]))) for r in values[1:] if r and r[0]]
        if name=='Journal_Trades':
            for r in records:
                if r.get('date') is not None:r['date']=day(r['date']).isoformat()
        if name=='Watchlist':records=[r for r in records if r.get('enabled') is True or r.get('enabled')=='TRUE']
        result[KEYS[name]]=records
    return result
