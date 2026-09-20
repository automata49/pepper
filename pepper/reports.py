"""Inspectable Markdown reports with explicit unknowns and snapshot comparisons."""
import json
from datetime import date
from pathlib import Path


def fmt(v, percent=False):
    if v is None:
        return 'N/A'
    return f'{v:.2%}' if percent else f'{v:,.2f}'


def clean(v):
    return str(v).replace('|', '\\|').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')


def comparison(current, previous, minimum_days=1):
    if previous is None:
        return ['비교 스냅샷 없음 — 변화·성과 판단 보류.']
    gap = (date.fromisoformat(current['asof']) - date.fromisoformat(previous['asof'])).days
    if previous['mode'] != current['mode'] or gap < minimum_days:
        return ['비교 불가 — 동일 모드의 이전 기준일 스냅샷이 필요합니다.']
    lines = [f"비교 기준: {previous['asof']} → {current['asof']} ({gap}일). 가격 변화는 배당·분할 미조정이며 총수익률이 아닙니다."]
    for ticker, price in current['prices'].items():
        old = previous['prices'].get(ticker)
        if old:
            lines.append(f'{clean(ticker)} 가격 변화: {fmt(price / old - 1, True)}')
    for t, lenses in current['research'].items():
        for lens, items in lenses.items():
            for item, result in items.items():
                old = previous['research'].get(t, {}).get(lens, {}).get(item, {}).get('verdict')
                if old and old != result['verdict']:
                    lines.append(f'{clean(t)}/{lens}/{item}: {old} → {result["verdict"]}')
    return lines


def research_lines(result):
    lines = ['## 독립 전략 평가', '', '| Ticker | 전략 | 항목별 평가 |', '|---|---|---|']
    for t, lenses in result['research'].items():
        for lens, items in lenses.items():
            summary = ', '.join(f'{k}: {v["verdict"]}' for k, v in items.items())
            lines.append(f'| {clean(t)} | {lens} | {summary} |')
    lines += ['', 'PASS/FAIL은 사용자가 기록한 판단입니다. 데이터가 없거나 근거 검증에 실패하면 UNKNOWN입니다.', '', '### 근거와 다음 확인']
    for t, lenses in result['research'].items():
        for lens, items in lenses.items():
            for item, entry in items.items():
                r = entry['evidence']
                if r:
                    lines.append(f'- {clean(t)}/{lens}/{item}: {clean(r["평가 근거"])}; 다음: {clean(r["다음 확인 조건"])}; 출처: {clean(r["출처 URL"])}')
    lines += ['', '## Position Growth 계산', '']
    for t, g in result['growth'].items():
        lines.append(f'- {clean(t)}: ROE {fmt(g["roe"], True)}, 순이익률 {fmt(g["factors"][0], True)}, 자산회전 {fmt(g["factors"][1])}, 레버리지 {fmt(g["factors"][2])}, FCF {fmt(g["fcf"])}, CFO/NI {fmt(g["cash_conversion"])}.')
        if 'roe_drivers' in g:
            lines.append('  ROE 변화 기여도(pp): ' + ', '.join(f'{k} {v * 100:.3f}' for k, v in g['roe_drivers'].items()) + '. 순서 독립 Shapley 분해.')
    for t, v in result['valuation'].items():
        lines.append(f'- {clean(t)}: 요구 EPS CAGR {fmt(v["required_eps_cagr"], True)}, 가정 {fmt(v["assumed_eps_cagr"], True)}, 여유 {fmt(v["growth_headroom"], True)}. 가정: {clean(v["assumptions"])}')
    lines += ['', '요구 EPS CAGR은 현재 가격·말기 PER·기간·요구수익률에 조건부인 역산입니다. 시장 컨센서스나 예측이 아닙니다. FCF 절대액 단위는 입력 재무자료와 같습니다.']
    return lines


def portfolio_lines(result):
    p = result['portfolio']
    lines = ['## 포트폴리오', '']
    if not p['complete']:
        lines += ['입력 오류로 총자산·비중 집계를 보류했습니다. 일부 정상 행만으로 총액을 만들지 않습니다.']
    else:
        lines += [f'- 현재 총자산 KRW: {fmt(p["nav"])} / 현금: {fmt(p["cash"])}',
                  f'- 계획 총자산 KRW: {fmt(p["planned_nav"])} / 잔여 현금: {fmt(p["planned_cash"])} / 수수료: {fmt(p["fees"])}',
                  f'- 현재 가격 위험: {fmt(p["risk"])} / 계획 가격 위험: {fmt(p["planned_risk"])} / 미산정 보유 존재: {p["risk_incomplete"]}',
                  f'- 전략별 평가액: {clean(p["strategies"])}', f'- 섹터별 평가액: {clean(p["sectors"])}',
                  f'- 종목 합산 계획 비중: {clean({k: fmt(v, True) for k, v in p["planned_weights"].items()})}']
        lines += [f'- 경고: {clean(w)}' for w in p['warnings']]
    lines += ['', '| ID | Ticker | 전략 | 현재 수량 | 계획 수량 | 증감 KRW | 점검 |', '|---|---|---|---:|---:|---:|---|']
    for r in p['positions']:
        lines.append(f'| {clean(r["id"])} | {clean(r["ticker"])} | {r["strategy"]} | {fmt(r["quantity"])} | {fmt(r["target"])} | {fmt(r["trade"])} | {clean(", ".join(r["warnings"]))} |')
    lines += ['', '자동 주문 없음. KRW 환산 현금은 통화별 결제 가능액을 보장하지 않습니다. 손절 미입력은 위험 0이 아니며 갭 손실·세금·슬리피지·현금 FX 스트레스는 제외됩니다.', '', '### 보유 논리와 무효화 조건']
    for r in p['positions']:
        lines.append(f'- {clean(r["ticker"])} ({r["strategy"]}): {clean(r["thesis"])} / 무효화: {clean(r["invalidation"])}')
    return lines


def write_reports(result, directory, previous_daily=None, previous_weekly=None):
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for kind in ('daily', 'weekly', 'portfolio'):
        lines = [f'# Pepper {kind.title()} — {result["asof"]}', '',
                 f'모드: **{result["mode"]}**' + (' — 전부 가상 예시' if result['mode'] == 'Demo' else ' — 사용자 수작업 입력'), '',
                 '## 데이터 점검', '']
        lines += [f'- {clean(i)}' for i in result['issues']] or ['검증 오류 없음. 내용의 진위와 투자 판단은 별도 확인이 필요합니다.']
        if kind in ('daily', 'weekly'):
            prior = previous_weekly if kind == 'weekly' else previous_daily
            lines += ['', '## 기준일 간 변화', ''] + comparison(result, prior, 7 if kind == 'weekly' else 1)
            lines += ['', '시장 지수·실적 일정·뉴스·테마 순위: 자동 수집 미연결. Research의 M/RS/N 등에 수작업 근거를 기록하세요.', '']
            lines += research_lines(result)
        lines += [''] + portfolio_lines(result)
        if kind == 'weekly':
            lines += ['', '## 주간 복기 입력', '', '- 실제 체결·손익: 별도 기록 필요', '- 유지/수정할 투자 가설:', '- 다음 주 확인 이벤트와 조건:', '- 매매 계획과 실제 행동의 차이:']
        (out / f'{kind}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
