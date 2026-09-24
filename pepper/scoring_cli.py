"""score / rules-diff / rules-show 명령."""
import json
from pathlib import Path
from .bridge import run_file, rules_diff
from .scoring.rules_loader import load_rules, versions, RulesError


def _spreadsheet(args):
    return args.spreadsheet or json.loads(Path(args.config).read_text())['spreadsheet_id']


def run_watchlist(args):
    from datetime import date, timedelta
    from . import watchlist as W
    from .sources.prices import fetch_all
    cfg = W.load_config(args.watchlist_config)
    asof = args.asof or (date.today() - timedelta(days=1)).isoformat()
    universe = []
    if args.sheets:
        from .journal_sheets import fetch_journal
        universe = [u for u in fetch_journal(_spreadsheet(args)).get('universe', [])
                    if str(u.get('asset_class', '')).upper() != 'ETF']
    items = W.instruments(cfg, universe)
    prices, benches, issues = fetch_all(items, asof, cfg)
    fundamentals = json.loads(Path(args.input).read_text(encoding='utf-8')) if args.input else None
    holdings = json.loads(Path(args.holdings).read_text(encoding='utf-8')) if args.holdings else []
    consensus, more = W.kis_consensus(items, asof)
    rows, more2 = W.build(cfg, items, prices, benches, asof, fundamentals, holdings, consensus)
    issues += more + more2
    out = Path(args.output) / 'watchlist.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'asof': asof, 'rows': rows, 'issues': issues}, ensure_ascii=False, indent=1), encoding='utf-8')
    summary = {'asof': asof, 'rows': len(rows), 'etf': sum(r['구분'] == 'ETF' for r in rows),
               'official_prices': sum(1 for x in prices.values() if x['verified']), 'issues': len(issues), 'saved': str(out)}
    if args.publish:
        summary['published'] = W.publish(_spreadsheet(args), rows)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def run_clean(args):
    from .sheet_cleanup import run as clean
    result = clean(_spreadsheet(args), apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if not args.apply and result['delete']:
        print('점검만 했습니다. 목록을 확인한 뒤 --apply로 실행하면 Drive 백업 후 삭제합니다.')
    return 0


def run(args, parser):
    try:
        if args.command == 'watchlist':
            return run_watchlist(args)
        if args.command == 'sheets-clean':
            return run_clean(args)
        if args.command == 'rules-show':
            rules = load_rules(args.rules, args.rules_override)
            for name, prof in rules['profiles'].items():
                print(f'\n[{name}] {prof.get("title")} v{prof["version"]}')
                for c in prof['criteria']:
                    how = c.get('rule') or ' / '.join(
                        f'{"≥"+str(b["min"]) if "min" in b else "≤"+str(b["max"]) if "max" in b else "그 외"}→{b["score"]}'
                        for b in c.get('bands', [])) or '값 그대로(0~100)'
                    print(f'  - {c["label"]} (w={c.get("weight", 1)}): {how}')
            print('\n' + json.dumps(versions(rules), ensure_ascii=False))
            return 0
        if not args.input:
            parser.error('--input inputs.json 필요')
        if args.command == 'score':
            r = run_file(args.input, args.result, args.rules, args.rules_override)
            summary = {t: {'swing': v['swing_status'], 'position': v['composites'].get('position', {}).get('score'),
                           'valuation': v['valuation'].get('label')} for t, v in r['tickers'].items()}
            print(json.dumps({'saved': args.result, 'rules_version': r['rules_version'], 'summary': summary},
                             ensure_ascii=False, indent=1))
            return 0
        if not args.old_rules:
            parser.error('rules-diff는 --old-rules 필요')
        inputs = json.loads(Path(args.input).read_text(encoding='utf-8'))
        diff = rules_diff(inputs, load_rules(args.old_rules), load_rules(args.rules, args.rules_override))
        print(json.dumps(diff, ensure_ascii=False, indent=1))
        return 0
    except (RulesError, ValueError, KeyError, OSError) as e:
        print(f'Pepper: {e}')
        return 2
