"""A process boundary bounds third-party clients that do not expose timeouts."""
import json
import sys
from . import providers

ALLOWED={'prices':providers.fdr_prices,'sec':providers.sec_company,'dart':providers.dart_company,'flows':providers.kr_flows}

if __name__=='__main__':
    request=json.load(sys.stdin)
    try:
        value=ALLOWED[request['provider']](*request['args'])
        print(json.dumps({'ok':True,'data':value},allow_nan=False,ensure_ascii=False))
    except Exception as e:
        # Provider exceptions may include request URLs with API keys. Never print them.
        message=str(e) if isinstance(e,providers.ProviderError) else type(e).__name__
        print(json.dumps({'ok':False,'error':message}))
        sys.exit(1)
