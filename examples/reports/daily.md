# Pepper Daily — 2026-09-18

모드: **Demo** — 전부 가상 예시

## 데이터 점검

검증 오류 없음. 내용의 진위와 투자 판단은 별도 확인이 필요합니다.

## 기준일 간 변화

비교 스냅샷 없음 — 변화·성과 판단 보류.

시장 지수·실적 일정·뉴스·테마 순위: 자동 수집 미연결. Research의 M/RS/N 등에 수작업 근거를 기록하세요.

## 독립 전략 평가

| Ticker | 전략 | 항목별 평가 |
|---|---|---|
| DEMO_KR | Swing | Trend: UNKNOWN, RS: UNKNOWN, Volume: UNKNOWN, Entry: UNKNOWN, Risk: UNKNOWN |
| DEMO_KR | Growth | C: UNKNOWN, A: UNKNOWN, N: UNKNOWN, S: UNKNOWN, L: UNKNOWN, I: UNKNOWN, M: UNKNOWN, DuPont: UNKNOWN, CashFlow: UNKNOWN, Valuation: UNKNOWN |
| DEMO_US | Swing | Trend: UNKNOWN, RS: UNKNOWN, Volume: UNKNOWN, Entry: UNKNOWN, Risk: UNKNOWN |
| DEMO_US | Growth | C: UNKNOWN, A: UNKNOWN, N: UNKNOWN, S: UNKNOWN, L: UNKNOWN, I: UNKNOWN, M: UNKNOWN, DuPont: UNKNOWN, CashFlow: UNKNOWN, Valuation: UNKNOWN |

PASS/FAIL은 사용자가 기록한 판단입니다. 데이터가 없거나 근거 검증에 실패하면 UNKNOWN입니다.

### 근거와 다음 확인

## Position Growth 계산

- DEMO_US: ROE 36.92%, 순이익률 16.00%, 자산회전 1.25, 레버리지 1.85, FCF 180.00, CFO/NI 1.17.
  ROE 변화 기여도(pp): margin 7.537, turnover 4.171, leverage 0.214. 순서 독립 Shapley 분해.
- DEMO_US: 요구 EPS CAGR 10.00%, 가정 20.00%, 여유 10.00%. 가정: {'기간 년': 3, '말기 PER': 25, '요구수익률': 0.1, '가정 근거': '가상 시나리오: 컨센서스 아님'}

요구 EPS CAGR은 현재 가격·말기 PER·기간·요구수익률에 조건부인 역산입니다. 시장 컨센서스나 예측이 아닙니다. FCF 절대액 단위는 입력 재무자료와 같습니다.

## 포트폴리오

- 현재 총자산 KRW: 7,900,000.00 / 현금: 5,600,000.00
- 계획 총자산 KRW: 7,899,350.00 / 잔여 현금: 4,949,350.00 / 수수료: 650.00
- 현재 가격 위험: 330,000.00 / 계획 가격 위험: 395,000.00 / 미산정 보유 존재: False
- 전략별 평가액: {'Swing': 1300000.0, 'Growth': 1000000.0}
- 섹터별 평가액: {'Technology': 1300000.0, 'Industrials': 1000000.0}
- 종목 합산 계획 비중: {'DEMO_US': '24.69%', 'DEMO_KR': '12.66%'}
- 경고: 계획 가격 위험 한도 초과

| ID | Ticker | 전략 | 현재 수량 | 계획 수량 | 증감 KRW | 점검 |
|---|---|---|---:|---:|---:|---|
| DEMO-P1 | DEMO_US | Swing | 10.00 | 15.00 | 650,000.00 |  |
| DEMO-P2 | DEMO_KR | Growth | 20.00 | 20.00 | 0.00 |  |

자동 주문 없음. KRW 환산 현금은 통화별 결제 가능액을 보장하지 않습니다. 손절 미입력은 위험 0이 아니며 갭 손실·세금·슬리피지·현금 FX 스트레스는 제외됩니다.

### 보유 논리와 무효화 조건
- DEMO_US (Swing): 가상 예시: 주도주 돌파 / 무효화: 가상 예시: 가격 기준 이탈
- DEMO_KR (Growth): 가상 예시: 실적 성장 / 무효화: 가상 예시: 성장 논리 훼손
