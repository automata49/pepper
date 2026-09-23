# 4대가 점수 엔진 (pepper.scoring)

시트의 분석 항목(펀더멘털 점검·Valuation·Price Setup·시나리오)은 그대로 두고, 판단 기준과 수식을
Mark Minervini · Warren Buffett · Philip Fisher · Peter Lynch 방법론으로 계산합니다.
기준값은 `pepper/rules/*.yaml`에만 있고 코드는 읽기만 합니다.

```bash
python -m pip install -e .
python -m pepper rules-show                                   # 현재 기준 확인
python -m pepper score --input examples/scoring_inputs.json --result data/results/latest.json
python -m pepper rules-diff --old-rules /path/to/old_rules --input data/inputs/2026-09-22.json
```

## 규칙 바꾸는 법

1. `pepper/rules/<대가>.yaml`에서 `bands`(구간 점수), `rule`(통과/미달 조건), `weight`를 수정합니다.
2. 같은 파일의 `version`을 올리고 `rules/CHANGELOG.md`에 이유를 적습니다.
3. `rules-diff`로 판정이 바뀌는 종목을 확인한 뒤 적용합니다.
4. 개인 기준은 저장소 밖 YAML에 `overrides:`로 두고 `--rules-override`로 넘길 수 있습니다(버전에 `+local` 표시).

조건식(`rule`, `when`)은 비교·and/or/not·사칙연산만 허용합니다. 함수 호출·속성 접근은 거부됩니다.
새 지표가 필요하면 `pepper/metrics/`에 `@metric('이름')` 함수를 추가하고 YAML에서 `metric: 이름`으로 씁니다.

## 항목 상태

| 상태 | 의미 | 점수 | 커버리지 |
| --- | --- | --- | --- |
| OK | 계산 완료 | 반영 | 포함 |
| N_A | 예외 태그·적자 등으로 의미 없음 | 제외 | 분모에서 제외 |
| MISSING | 데이터 없음 (0으로 채우지 않음) | 제외 | 감소 |
| UNVERIFIED | LLM 초안·스크래핑 등 미검증 근거 | 제외(값은 표시) | 감소 |

커버리지가 `min_coverage`보다 낮으면 판정은 "판정 보류 (데이터 부족)"입니다.

## inputs JSON (Edgar → Pepper)

```json
{"asof": "2026-09-22",
 "benchmarks": {"US": [일봉], "KR": [일봉]},
 "tickers": {"TICKER": {"market": "US", "tags": [], "bars": [일봉],
   "facts": {...}, "sources": {"필드": {"url": "", "asof": "YYYY-MM-DD", "provider": "", "verified": true}}}}}
```

`sources.asof`가 기준일보다 늦은 필드는 계산에서 빠집니다(미래 정보 차단). `verified: false` 필드를 쓴 항목은 UNVERIFIED입니다.

### facts 필드 (비율은 소수, 연간 리스트는 과거→최근)

| 구분 | 필드 |
| --- | --- |
| 가격 | price, price_asof, (bars가 없을 때) ma50, ma150, ma200, ma200_prev, low_52w, high_52w, pivot, vcp_depths, vcp_volumes, rs_percentile |
| 수익성 | roe_history, roe_ttm, gross_margin, op_margin_history, industry_op_margin_median |
| 재무 | equity, total_debt, long_term_debt, net_income, cash, shares_out, shares_history, inventory_history |
| 성장 | eps_history, eps_ttm, revenue_history, rd_history, eps_quarterly, sales_quarterly |
| 가격 부담 | pe_ttm, forward_pe, pbr, dividend_yield, pe_history, eps_forecast, eps_growth_3y |
| 적정가 | normalized_eps, consensus_eps, blend_weights, d_and_a, capex, maintenance_capex |
| 분류 | tags, asset_type, sector, fundamentals_asof |
| 정성 | qualitative.{moat, sales_organization, management_depth, long_term_outlook, candor_integrity, industry_advantage} = {score 0~100, verified, evidence, source_url} |

`eps_growth_3y`는 출처가 누적/연평균을 밝히지 않아 기본값을 **누적**으로 보고 CAGR로 바꿉니다
(`custom.yaml inputs.eps_growth_3y_basis`). 연도별 컨센서스 `eps_forecast`가 있으면 그것을 우선합니다.

## 적정주가

- Buffett: 오너 어닝스(순이익 + 감가상각 − 유지 CAPEX) 10년 DCF, Bear/Base/Bull은 성장률·할인율만 바꿈.
- Lynch: Blended EPS × 적정 PER(= EPS 연평균 성장률, 8~30배로 제한). 경기순환주는 적용하지 않음.
- 최종 적정가는 기본적으로 두 값 중 낮은 값(`custom.yaml fair_value.method: min`).
- 적정가보다 25% 이상 싸면 CHEAP, 10% 넘게 비싸면 EXPENSIVE. 미검증 입력이 쓰이면 `label_status: UNVERIFIED`.
- 피보나치 61.8%/50%는 4대가 기준이 아니므로 참고값으로만 표시합니다.

결과는 매매 권유가 아니라 점검용 계산입니다. 최종 결정은 사용자가 내립니다.
