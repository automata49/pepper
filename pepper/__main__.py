import argparse
import json
from datetime import datetime, timezone, date
from pathlib import Path
from .engine import evaluate
from .reports import write_reports
from .sheets import fetch


def main():
    p = argparse.ArgumentParser(description='Read manual Sheets inputs and generate investment reviews')
    p.add_argument('command', choices=['sync', 'review'])
    p.add_argument('--config', default='config/workspace.json')
    p.add_argument('--snapshot', help='Offline input snapshot (required for review)')
    p.add_argument('--output', default='reports')
    p.add_argument('--history', default='data/history')
    args = p.parse_args()
    if args.command == 'review' and not args.snapshot:
        p.error('review requires --snapshot')
    try:
        snap = (fetch(json.loads(Path(args.config).read_text())['spreadsheet_id'])
                if args.command == 'sync' else json.loads(Path(args.snapshot).read_text()))
        result = evaluate(snap)
        history = Path(args.history) / result['mode'].lower()
        history.mkdir(parents=True, exist_ok=True)
        prior = []
        for file in sorted(history.glob('*/review.json'), reverse=True):
            record = json.loads(file.read_text())
            if record['mode'] == result['mode'] and record['asof'] < result['asof']:
                prior.append(record)
        daily = max(prior, key=lambda r: r['asof']) if prior else None
        weekly = [r for r in prior if (date.fromisoformat(result['asof']) - date.fromisoformat(r['asof'])).days >= 7]
        weekly = max(weekly, key=lambda r: r['asof']) if weekly else None
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        checkpoint = history / f'{result["asof"]}_{stamp}'
        checkpoint.mkdir()
        (checkpoint / 'snapshot.json').write_text(json.dumps(snap, ensure_ascii=False, indent=2, allow_nan=False))
        (checkpoint / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        write_reports(result, args.output, daily, weekly)
        print(f'{result["mode"]} {result["asof"]}: {args.output}/daily.md, weekly.md, portfolio.md')
        print(f'{len(result["issues"])} data issues; portfolio complete={result["portfolio"]["complete"]}')
    except (ValueError, KeyError, OSError, ImportError) as e:
        p.exit(2, f'Pepper: {e}\n')


if __name__ == '__main__':
    main()
