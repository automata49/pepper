"""score / rules-diff / rules-show 명령."""
import json
from pathlib import Path
from .bridge import run_file, rules_diff
from .scoring.rules_loader import load_rules, versions, RulesError


def run(args, parser):
    try:
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
