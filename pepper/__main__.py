import argparse
import json
from datetime import datetime, timezone, date
from pathlib import Path
from .engine import evaluate
from .reports import write_reports
from .sheets import fetch


def main():
    p = argparse.ArgumentParser(description='Read manual Sheets inputs and generate investment reviews')
    p.add_argument('command', choices=['sync', 'review', 'import-journal', 'automate', 'doctor'])
    p.add_argument('--config', default='config/workspace.json')
    p.add_argument('--snapshot', help='Offline input snapshot (required for review)')
    p.add_argument('--output', default='reports')
    p.add_argument('--history', default='data/history')
    p.add_argument('--journal', help='XLSX for import-journal; imported private JSON for automate')
    p.add_argument('--automation-config', default='config/automation.json')
    p.add_argument('--asof', help='YYYY-MM-DD; default previous calendar day, bounded by available prices')
    p.add_argument('--llm', action='store_true', help='Send validated report to configured OpenAI model')
    p.add_argument('--drive-folder', help='Explicit private Drive folder ID for durable backup')
    p.add_argument('--sheets', action='store_true', help='Read manual inputs and journal tabs from connected workspace')
    p.add_argument('--publish-sheets', action='store_true', help='Write dedicated Review_* and Data_Requests tabs; preserves manual input columns')
    args = p.parse_args()
    if args.publish_sheets and args.command != 'automate':
        p.error('--publish-sheets is only supported with automate')
    if args.command == 'doctor':
        from .operations import doctor
        print(json.dumps(doctor(),indent=2));return
    if args.command == 'import-journal':
        from .journal import import_journal
        if not args.journal:p.error('--journal XLSX path required')
        imported=import_journal(args.journal)
        dest=Path('data/private/journal.json');dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(imported,ensure_ascii=False,indent=2))
        print(f'Imported {len(imported["trades"])} trades and {len(imported["universe"])} instruments to private local storage.');return
    if args.command == 'automate':
        from datetime import timedelta
        from .pipeline import run,save_run
        config=json.loads(Path(args.automation_config).read_text())
        journal=json.loads(Path(args.journal).read_text()) if args.journal else None
        manual=evaluate(json.loads(Path(args.snapshot).read_text())) if args.snapshot else None
        if args.sheets:
            from .journal_sheets import fetch_journal
            sid=json.loads(Path(args.config).read_text())['spreadsheet_id']
            manual=evaluate(fetch(sid)); journal=fetch_journal(sid)
            config['use_journal_universe']=True
        asof=args.asof or (date.today()-timedelta(days=1)).isoformat()
        if manual and manual['asof']!=asof:p.error('Manual snapshot asof must match automated run')
        result=run(config,asof,journal,manual)
        if args.sheets or args.publish_sheets:
            from .workspace import read_requests,session_for_workspace,attach_supplements
            sid=json.loads(Path(args.config).read_text())['spreadsheet_id']
            _,requests=read_requests(sid,session_for_workspace())
            result['data_requests']=requests
            attach_supplements(result,requests)
        if args.drive_folder:
            from .operations import restore_drive
            restore_drive(args.drive_folder)
        dest=save_run(result,output=args.output)
        if args.llm:
            from .llm import interpret
            interpret(result,dest)
        if args.drive_folder:
            from .operations import backup_drive
            backup_drive(dest,args.drive_folder)
        if args.publish_sheets:
            from .workspace import publish
            publish(sid,result)
        print(json.dumps({'coverage':result['coverage'],'issues':len(result['issues']),'saved':str(dest)},ensure_ascii=False))
        return
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
