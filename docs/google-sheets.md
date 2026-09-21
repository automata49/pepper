# Pepper Google Sheets 사용 안내

연결된 Journal 파일의 Home 탭에서 시작한다. 비공개 파일 주소는 공개 문서에 기재하지 않는다.

## 역할

**시트는 보완 입력·근거 상세·보유/행동 기록, Python은 계산, ChatGPT는 종합 투자 분석, 사용자는 매매 결정**을 담당한다.

공통 데이터 → 검증/계산 → Swing·Position Growth 각각 평가 → US/KR Daily·통합 Weekly·Portfolio 리뷰 → 행동/복기 기록 순서다. Swing과 Growth를 합쳐 단일 매수 점수를 만들지 않는다. 시트의 상태나 점수만으로 뉴스·시장·투자 논리를 종합한 보고서를 대체하지 않는다.

## 간략 화면: 6개 탭

| 탭 | 용도 | 편집 |
|---|---|---|
| Home | 보완 입력·평가 대상·상세 조회 바로가기 | 안내 |
| Price_US | 미국 가격과 기존 지표 상세 | 이번 정리에서 수정하지 않음 |
| Price_KR | 한국 가격과 기존 지표 상세 | 이번 정리에서 수정하지 않음 |
| Portfolio | 보유 내역과 수작업 조정 계획 | 기존 입력 셀만 |
| Trades | 실제 체결과 Plan ID·복기 기록 | 실제 체결 후 |
| ETF_Review | 구성 항목·비중·원자료 날짜·검증 상태·출처 | 조회 |

기존 Simple/Fundamental/Added_Stocks/Valuation/Positions/Perf/Review/Hub/Day/Cycle/Calendar/Trade_Top10/Plan 및 계산·설정 탭은 **삭제·이름 변경 없이 숨김**으로 보존했다. 숨겨도 수식 참조는 유지된다. 필요하면 Google Sheets의 **보기 → 숨겨진 시트**에서 복원한다. ETF_Holdings는 계산용 원자료로 숨기고 ETF_Review를 주요 조회 화면으로 사용한다.

Price_US/Price_KR의 값·수식·서식·행열·숨김·그룹·시트 속성을 대상으로 한 쓰기는 하지 않았다. GOOGLEFINANCE 등의 자체 재계산은 계속될 수 있다. 다른 탭도 데이터와 계산식은 재작성하지 않았다. Home은 맨 뒤에 추가해 기존 탭 순서도 유지했다.

## 보완 입력과 자동 평가: Home에서 연결

연결 Workspace는 기존 자동화의 입력 원본이다. 두 파일을 실제 병합하거나 양방향 동기화한 것은 아니다. 입력 원본 중복을 피하려고 Journal의 Home에서 다음 기존 탭으로 연결한다.

| 연결 탭 | 사용법 |
|---|---|
| Data_Requests | 자동 보완 요청 A:J 조회, **K:Q만 수작업 입력** |
| Watchlist | 평가 후보와 enabled 선택 |
| Review_US / Review_KR / Review_Other | 계산 결과와 누락 상태 상세 조회 |
| Orders / Journal_Trades | 기존 자동화의 주문 계획·체결 입력 경로. Journal 기록과 중복 입력하지 않음 |

Data_Requests의 K:Q는 값·출처 URL·출처 날짜·기간 시작·기간 끝·통화·메모다. 금액 단위와 연결/별도·귀속 기준도 메모에 명시한다. 한국 티커는 `005930`처럼 텍스트로 보존한다.

- request_id와 시스템 열을 바꾸지 않는다. 자동 갱신은 수작업 입력 칸을 덮어쓰지 않는다.
- ROE 등이 미확인되면 관련 원자료와 근거를 보완한다. TTM 손익과 대응하는 평균 자산/자본, 같은 통화·단위·회계 범위를 맞춘다.
- 입력과 URL/날짜 형식 검사는 사실 확인이 아니다. 현재 코드는 보완값을 보고서의 **독립 검증 전 근거**로 표시하며 자동 점수·ROE를 덮어쓰지 않는다.
- 자료 부족은 판단 보류로 표시한다. 추정치/회사 가이던스/컨센서스는 구분한다.
- 초기 Review의 REFERENCE_ONLY/PARTIAL은 완전한 기술 평가 결과가 아니다. 생성일과 실제 가격 거래일도 구분한다.

## Portfolio와 체결 기록

Journal Portfolio는 기존 구조를 유지한다. 6행이 제목이며 7행부터 기록한다.

- 기존 보유: A 티커, H 수량, I 평균 매입가, AB 계좌. 수식 셀은 덮어쓰지 않는다.
- 계획: AD 티커, AE BUY/SELL, AH 계획 체결가, AI 손절가, AJ 목표가, AK 계획 수량, AL 환율, AQ 최종 결정, AR 근거, AS 고정 Plan ID, AV 복기.
- 실제 체결 후 Trades에 기록하고 P열 Plan ID를 연결한다. 계획 수량 변경은 실제 체결이나 주문 전송이 아니다.
- Journal Portfolio/Trades와 연결 Workspace Orders/Journal_Trades는 자동 양방향 동기화되지 않는다. 보고서를 요청할 때 어느 파일의 장부가 최신인지 명시한다. 같은 체결을 두 원본에서 합산하지 않는다.
- Swing/Growth별 수량·원가·무효화 조건을 구분하고 종목 전체 노출은 합산한다. 현재 전략별 자동 장부 분리 구현 완료를 의미하지 않는다. 전략/진입 논리/전략 변경 이유는 근거·메모에 기록하고 분석 시 대조한다.
- 손절까지의 계획 손실액은 최대 손실이 아니다. 갭·슬리피지·이벤트·환율 스트레스를 별도로 검토한다.

## ChatGPT 보고서 작성 기준

| 보고서 | 핵심 |
|---|---|
| US/KR Daily | 시장 환경·주도 테마·Swing 변화·신규 뉴스/공시·보유 경고, 다음 거래일 확인 조건 3개 |
| 통합 Weekly | 시장/섹터 비교·두 전략 후보·투자 논리 변화·다음 주 이벤트·판단 복기 |
| Portfolio Daily | 비중·가격 이탈·이벤트·집중도 변화 |
| Portfolio Weekly | 전략/투자 논리·위험 예산·ETF 중복 노출·확대/축소/재평가 조건 |

ChatGPT는 실행 시 확인한 시장정보·뉴스·공시와 검증된 수치/시트 입력을 종합한다. 보고서마다 기준 거래일, 자료/공시일, 출처, 규칙 버전, 마지막 검토일, 이전 판단 대비 변경 이유를 남긴다. 새로운 근거가 없으면 Growth 판단을 유지한다. 이 문서 정리가 뉴스 수집/자동 보고서 운영 검증까지 완료했다는 뜻은 아니다.

Swing은 시장 → 테마 → ETF → 종목, RS·21/50/200MA·거래량·ATR·진입/무효화 조건을 확인한다. Next Leader는 진입 가능 상태와 구분한다. 요청한 표시 명칭 PULLBACK/BROKEN과 기존 계산기의 PULLBACK ENTRY/AVOID는 동일 규칙이라고 가정하지 않는다. 필요 시 보고서에 원래 상태와 적용 규칙을 함께 표시하며 이번 작업에서 Price 탭의 상태 수식은 변경하지 않았다.

Position Growth는 CAN SLIM + DuPont + 현금흐름 + 가격 기대를 각각 평가한다. DuPont 변화 기여도는 코드의 Shapley 방식을 명시한다. 음수/매우 작은 자기자본이나 비교 불가능한 기간은 평가 보류한다. 현금흐름에는 FCF 외 운전자본·SBC·희석도 검토한다. 가격 기대에는 보수/기준/낙관 가정과 근거 종류를 표시한다.

DRAM은 **ETF만 유지하며 구성 종목 수집/추가 제외**다. 따라서 DRAM의 구성 종목 기반 중복 노출을 계산 완료로 표시하지 않는다.

## 자동화 연결과 실제 상태

`config/workspace.json`의 기존 연결 Workspace ID를 유지했다. Journal ID로 단순 교체하면 기존 Settings/입력 스키마와 맞지 않으므로 교체하지 않는다.

```bash
python -m pepper automate --asof YYYY-MM-DD --sheets --publish-sheets
```

- `--sheets`: 기존 입력·장부·보완 요청 읽기. 수작업 Settings 기준일과 실행 기준일이 같아야 한다.
- `--publish-sheets`: 전용 Review_* / Data_Requests 게시. Price_US/Price_KR·Portfolio/Orders를 게시 대상으로 삼지 않는다.
- Google ADC와 Sheets 쓰기 권한이 있는 별도 실행 환경이 필요하다. ChatGPT 연결과 서버 인증은 별개다. 키·실보유·원자료·보고서는 공개 GitHub에 올리지 않는다.
- 기존 `pepper sync`는 이전 수작업 양식용 읽기 경로다. 연결 Workspace의 DEMO 행/현금은 실제 자료로 간주하지 않는다.
- 실행 정의/코드와 운영 성공은 다르다. 인증·데이터 수집·게시 성공 및 기준일을 확인하기 전 최신 자동 보고서라고 표시하지 않는다.
- 현재 미완료 항목은 [BUILD_STATUS.md](BUILD_STATUS.md), 보완 큐 구현은 [review-workspace.md](review-workspace.md)를 확인한다.

## 이번 정리의 확인 범위

6개 탭 노출, 20개 기존 탭 숨김, Home의 실제 연결 대상과 서식/셀 내용을 API로 확인했다. Price 두 탭은 쓰기 대상에서 제외하고 속성을 전후 대조해 일치함을 확인했다. 네이티브 화면 렌더링 검증은 별도다. 이번 변경은 화면/사용 규칙 정리이며 계산 엔진이나 매매 기록을 수정하지 않는다.
