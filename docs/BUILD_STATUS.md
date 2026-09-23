# Pepper 구현·재개 상태

## 최우선 현재 범위 — 2026-09-23

- 아래 Portfolio/Trades/Orders 기록은 과거 이력이다. 현재 범위는 Price_US/Price_KR/Fundamental/보완입력과 ChatGPT 분석이다. 삭제된 장부/주문/복기 탭과 데이터는 재생성하지 않는다.
- 이전 실행에서 Journal 17개 탭과 구 Workspace 장부/대시보드 6개 탭을 삭제하고 보완입력을 Journal로 복사했다. 가격 의존 계산 탭 6개는 숨김 보존, 거래 참조 439개 셀은 비웠다. 이번에는 추가 시트 변경 없음.
- 레거시 CLI 장부/게시 경로 차단. --research-sheets는 비공개 PEPPER_RESEARCH_SHEET_ID의 보완입력만 읽고, 지정 탭 누락은 실패 처리한다. 기존 Review/장부는 조회하지 않는다.
- GitHub workflow는 무조건 중지로 변경. 이전 미게시 workflow 변경은 운영 성공이 아니다. 테스트 47개 통과(새 큐 읽기/누락/레거시 명령 사전 차단 포함).
- Price/Fundamental 읽기와 보완입력 A:J 전용 게시 코드를 구현했다. 다음은 실제 ADC 운영 검증과 구 장부/복원/Portfolio 출력 제거다. 구 workflow 활성화 금지. 간략 안내는 docs/google-sheets.md 참조.

## 구현됨

- 수작업 Sheets 입력·재무/포트폴리오 계산·Daily/Weekly/Portfolio 보고서.
- Trading_Journal_V2 읽기 전용 XLSX importer. 선택한 입력만 추출하고 API 키·수식 캐시는 제외.
- 비공개 Pepper 시트에 Journal_Trades, Journal_Holdings, Journal_Fundamentals, Watchlist, Orders 통합.
- FinanceDataReader OHLCV, SEC Companyfacts/Submissions, OpenDartReader 연결 재무·공시, pykrx 순매수 어댑터.
- SMA21/50/200, ATR20(Wilder), 이전 20일 고점, 이전 20일 평균 대비 거래량, 52주 고점 거리, 벤치마크 대비 RS 1/3/6/12M 및 시장별 현재 유니버스 백분위.
- Swing 상태/Next Leader, CAN SLIM 정량 C/A/L/M + 수작업 N/S/I, DuPont Shapley·FCF·가격 기대.
- 이동평균 원가 장부·부분매도·절대 수수료·초과매도 방지·Plan ID 체결 연결·주문 위험/손익비/현금 검사.
- 공급자 프로세스 timeout, 제한된 재시도, 원자료 캐시, 실행별 스냅샷, 선택적 GPT Responses API.
- GitHub Actions 테스트와 일일 실행 정의, 명시적 비공개 Drive 폴더 백업.

## 운영 차단 사항 — 완료로 표시하지 말 것

1. DART_API_KEY, OPENAI_API_KEY, OPENAI_MODEL, SEC_USER_AGENT 및 별도 실행환경 Google ADC가 아직 제공되지 않았다. 코드 존재와 실제 인증·운영 성공은 다르다.
2. 정기 실행 workflow는 PEPPER_AUTOMATION_ENABLED=true 배포 설정이 있어야 작동한다. 사용자 키나 권한을 임의 생성하지 않는다.
3. 첨부 거래 중 날짜 누락/미래 날짜 항목이 있어 장부 총손익 확정을 보류했다. 계좌와 전략도 UNASSIGNED를 직접 지정해야 한다.
4. DART 표준 계정/12월 결산만 자동 정규화한다. 특수 계정·비12월 결산·금융업 회계는 수작업 매핑이 필요하다. 제공되지 않은 수치는 UNKNOWN으로 유지한다.
5. 수집 가격은 공급자의 조정 기준을 따른다. 배당 포함 총수익률이나 백테스트 PIT 유니버스를 보장하지 않는다.
6. 시장 뉴스/미래 실적 예정일, 기관 후원 N/S/I의 질적 판단은 자동으로 만들어내지 않는다. 수작업 입력 항목으로 남는다.
7. 보완 요청 생성·보고서 상세 쓰기와 입력 보존은 구현했다. 수작업 보완은 출처/날짜 검사 후 '독립 검증 전' 근거로만 표시하며, ROE/점수를 자동 덮어쓰지 않는다. 입력값의 독립 검증 및 정규화 계산 반영은 아직 미완료다. ADC 기반 정기 쓰기 인증도 검증 전이다.

## 2026-09-21 재개 결과

- 최신 main `b727034` 기준으로 재개. 기존 27개 테스트 재통과. 이번 환경은 optional provider 패키지도 없으며, 키/ADC 차단은 그대로다. 설치 존재와 실제 인증을 구분한다.
- 별도 Pepper Journal 네이티브 복사본 존재 확인. Price_US / Price_KR / Added_Stocks와 의존 계산 탭을 보존했다. **기존 Pepper 파일 안으로 세 탭이 병합된 것은 아니다.** 기존 Pepper의 Guide 28~31행에 Journal/ETF 상세 링크를 연결했다. 원본 Trading_Journal_V2는 변경하지 않았다.
- Journal Universe에 신규 86개, Price_US에 신규 55개, ETF_Holdings에 원자료 134개 행 추가. Price_KR은 Universe 기반 수식으로 신규 한국 종목을 반영한다. Added_Stocks 원래 14개 기록은 유지했다.
- 기존 Pepper Watchlist에 중복 없는 신규 후보 86개 추가. CLOU/BUG/CRAK/DRAM만 새로 enabled=true; 개별 구성 종목은 비활성 검토 후보다. Portfolio/Orders/체결 내역은 변경하지 않았다.
- ETF_Review에 원본 티커, 상품 유형, 비중, 원자료 날짜, 시장, 정규화 티커, 검증 상태, 운용사 링크를 기록했다. CLOU 40행(주식38), BUG 34행(주식30), CRAK 32행(주식25), DRAM 28행(주식14·스왑5·기타9). 현금·선물·스왑을 주식으로 오인하지 않는다.
- 운용사 기준일: CLOU/BUG 2026-09-18, CRAK 2026-09-17, DRAM 파일 Date 2026-09-21. Roundhill 웹 화면은 파일 Date에서 하루를 빼므로 날짜 의미를 명시했으며 파일명의 날짜를 기준일로 사용하지 않는다.
- 134행 재조회·비중 합계(99.98%, 99.98%, 100.00%, 99.99%) 확인. 신규 US 55행 가격 표시 및 수식 오류 없음 확인. Watchlist 체크박스 86개 확인. ETF_Review native table 범위 A1:L135 확인. 화면 렌더링은 미검증; API 서식/셀 검증만 수행했다.
- 공식 원자료 파서와 시장 라우팅 보호 추가: `pepper/etf_holdings.py`, `tests/test_etf_holdings.py`. 해외/미확인 시장을 미국 또는 DART로 잘못 전달하지 않는다. 재현용 수집 스크립트는 수동 실행형이며 자동 갱신 완료를 뜻하지 않는다.
- 최종 단위 테스트 32개 통과(기존 27 + 신규 5). 실계좌/실재무/GPT 인증 검증 완료와는 별개다.
- 다음 작업: 보완 요청 큐와 리포트 표시 쓰기 연결, ETF 최신 링크 탐색·정기 갱신, SKHY 거래소/CXMT 스왑 기초자산 확인. 사용자 키 없이 가능한 구현부터 수행한다. 전체 완료 아님.

### 후속 수정 — 위 수량은 이력이며 아래가 현재 상태

- **사용자 요청: DRAM은 ETF만 유지. 구성 종목을 다시 수집/추가하지 말 것.** ETF_Holdings/ETF_Review에서 DRAM 28행 제거. 이번 DRAM 확장으로만 추가한 Universe/Watchlist 11종목 및 Price_US 3종목 제거. 기존 관심종목/보유/다른 ETF의 종목은 유지. 현재 신규 후보 75개, 신규 US 가격 52개, 추가 구성 항목 106개(CLOU40/BUG34/CRAK32). Added_Stocks 원본 기록 유지.
- DRAM 무거래소 티커가 다른 가격(6.22)을 반환하는 문제 발견. 신규 ETF 4개의 가격·기술 계산을 NASDAQ:CLOU, NASDAQ:BUG, NYSEARCA:CRAK, BATS:DRAM으로 한정. DRAM은 59.61로 재확인. 이는 2026-09-18 거래 가격 참조이며 실시간 체결 가격이 아니다.
- 기존 Pepper에 Review_US/KR/Other와 Data_Requests 생성. 현재 ETF 4개 참조 가격을 REFERENCE_ONLY/PARTIAL로 표시하며, 계산을 끝낸 자동 평가로 표시하지 않는다. 실제 거래일·충분한 기술 이력에 관한 보완 요청 8개 생성. ETF에는 기업 ROE/CAN SLIM 요청을 만들지 않는다.
- `pepper/workspace.py`가 stable request ID 생성, 기존 입력 K:Q 보존, 중복 ID/원본 없는 입력 방어, 수작업 근거의 별도 보고서 표시, 전용 자동 탭 발행을 구현한다. `automate --publish-sheets`는 쓰기 권한을 명시적으로 요청한다. 사용자 Portfolio/Orders는 쓰지 않는다.
- 현재 테스트 38개 통과. 자동 실행의 Google 인증·실재무·GPT 검증과 별개다. 다음 작업은 입력 근거 독립 검증/정규화, 최신 ETF 링크 자동 탐색(단 DRAM 제외), 정기 실행 환경 연결이다.

## 재개 절차

2026-09-20 검증: 단위 테스트 27개 통과. 미국/한국 개별 가격 실제 수집 성공. SEC 연락처·DART 키 없음, 한국 투자자별 수급 응답 없음으로 실재무/수급 운영 검증은 미완료. 자동 재개 확인 작업은 5시간 간격으로 등록됨. 생성된 예약은 사용량 제한을 해제하지 않는다.

최신 main과 이 문서를 읽고 현 상태를 먼저 확인한다. `python -m unittest discover -s tests -q`, `python -m pepper doctor`를 실행한다. 추가 구현/검증 결과를 이 문서에 남긴다. data/, reports/, 원본 XLSX, 실제 보유/거래 정보와 비밀키를 공개 GitHub에 올리지 않는다. 사용자 원본 Trading_Journal_V2는 수정하지 않는다.

사용량 한도를 감지하거나 해제할 API는 없다. 예약 재개 작업은 실행 시 사용 가능한 권한·한도 내에서만 수행되며 한도 우회 또는 정확한 리셋 시각 재개를 보장하지 않는다.

## 2026-09-23 간략 연구 시트 경로 구현

- 최신 main `abdd3ee`에서 별도 clean worktree로 작업해 이전 작업 폴더의 변경을 건드리지 않았다.
- `--research-sheets`가 보완입력뿐 아니라 Price_US·Price_KR·Fundamental을 직접 읽고, 설정된 유니버스 행만 `REFERENCE_ONLY_NOT_INDEPENDENTLY_VERIFIED`로 결과에 첨부한다. 이 값은 공급자 계산·ROE·점수를 덮어쓰지 않는다.
- 읽기 대상은 표시 4개 탭으로 고정했다. Settings와 숨김 계산 탭, 삭제된 거래·보유·주문 탭은 읽지 않는다. 실제 시트의 탭 존재와 헤더를 읽기 전용으로 대조했다.
- `--publish-research-sheets`는 기존 보완입력 A:J 시스템 열만 갱신한다. K:Q는 쓰기 요청에 포함하지 않으며, ID 없는 비어 있지 않은 행·중복 ID·잘못된 행 위치·용량 초과는 실패 처리한다.
- 예약 workflow 명령을 새 간략 옵션으로 바꿨지만 job은 계속 무조건 중지 상태다. 실제 ADC 인증·게시 성공 전에는 활성화하지 않는다.
- 공개 README와 config에 남아 있던 이전 시트 주소/ID를 제거했다. 새 Journal ID는 환경변수로만 주입한다.
- 단위 테스트 50개 통과. doctor에서 optional 공급자·Google·GPT 패키지/인증 미설정을 확인했다. 실제 ADC 게시와 전체 정기 운영은 아직 미완료다.


## 최신 사용자 지시 — Sheets 간략화

- Journal은 Home/Price_US/Price_KR/Portfolio/Trades/ETF_Review 6개 탭만 노출한다. 기존 20개 탭은 삭제/이름 변경 없이 숨김으로 보존한다. Home은 맨 뒤에 추가하여 기존 순서를 유지한다.
- **Price_US와 Price_KR을 수정하지 말 것.** 값·수식·서식·행열·그룹·시트 속성 변경 모두 제외한다. 의존 계산 탭의 데이터도 이번 정리에서 수정하지 않았다.
- 보완 입력/Watchlist/자동 평가 상세는 Home에서 기존 연결 Workspace로 이동한다. 입력 원본을 중복 생성하지 않는다. Journal 장부와 기존 연결 장부는 자동 양방향 동기화되지 않는다.
- 종합 시장/뉴스/공시 분석과 Daily/Weekly/Portfolio 서술은 ChatGPT 담당. Sheets는 입력·상세 근거·실행 기록 중심이다. 새로운 근거 없이는 Growth 판단을 바꾸지 않는다.
- 상세 운영 규칙은 docs/google-sheets.md를 먼저 읽는다. 이 화면 정리를 전체 자동화 완료로 오인하지 않는다. DRAM ETF-only 정책 유지.

## 2026-09-21 보완 입력 보존 회귀 검증

- main `bc7a2f9`에서 기존 38개 테스트 재통과. Data_Requests 읽기의 고정 2000행 제한을 실제 grid rowCount로 교체했다. 확장된 큐의 입력/ID를 누락해 후속 게시가 기존 행을 덮어쓸 위험을 방지한다.
- 읽기 단계에서 중복 request_id를 거부하고, 게시 단계에서 헤더 영역/음수/비정수 행 위치를 거부한다. 수작업 K:Q 쓰기 금지 정책 유지.
- 확장 큐/중복 ID/잘못된 행 위치 회귀 테스트 추가: 총 41개 통과. mock 기반 검증이며 실제 ADC 게시 성공을 의미하지 않는다.
- 이번 실행은 코드/테스트만 변경. 사용자 장부, Price_US/Price_KR 및 원본 시트는 수정하지 않았다. doctor에서 optional 공급자 패키지·인증 미설정 확인; 전체 운영 검증 및 보완값 독립 검증/계산 반영은 여전히 미완료다.

## 2026-09-22 주문 안전성과 연결 시트 스키마 검증

- 연결된 Pepper Workspace의 지정 5개 장부 탭과 Data_Requests를 헤더 행만 읽어 코드 스키마와 일치함을 확인했다. 실제 포트폴리오/체결 행은 조회·출력·저장하지 않았고 원본 및 Price 탭도 수정하지 않았다.
- 주문 계획 ID가 누락/중복이면 모든 주문 점검을 차단하고 현금·위험 예약값을 만들지 않는다. 거래 장부에 날짜·중복 ID·초과매도 등 오류가 하나라도 있으면 체결수량/보유수량이 신뢰 불가하므로 모든 주문 계획을 차단한다.
- 실패 폐쇄 회귀 테스트를 추가해 총 42개 테스트 통과. 인증이 필요한 실제 자동 수집·게시와 보완값 독립 검증은 계속 미완료다.

## 2026-09-22 정기 실행 경로 보완

- 예약 workflow가 코드만 실행하고 연결 Workspace를 읽거나 Review/Data_Requests를 게시하지 않던 누락을 수정했다. 배포 게이트가 열린 실행은 `--sheets --publish-sheets --llm`으로 지정 장부를 읽고, 전용 자동 탭 게시와 GPT 종합 리포트를 함께 수행한다.
- 배포 전 검증에 OPENAI_API_KEY/OPENAI_MODEL을 포함했다. 원문 Google credential JSON은 준비 step에만 노출하고 이후 step에는 파일 경로만 전달한다.
- workflow 회귀 테스트 2개 추가, 총 44개 통과. 실제 동작은 PEPPER_AUTOMATION_ENABLED와 기존 비밀값/ADC가 설정된 뒤의 성공 실행으로만 검증 완료 처리한다. 이번 실행에서 사용자 시트는 수정하지 않았다.

## 2026-09-23 4대가 규칙 엔진 추가 (feature/master-rules)

- `pepper/rules/*.yaml`(Minervini·Buffett·Fisher·Lynch·custom·exceptions)과 `pepper/metrics`, `pepper/scoring`, `pepper/bridge.py` 추가. 기준값은 YAML에만 있고 버전이 results에 기록된다.
- CLI: `score`, `rules-show`, `rules-diff`. Edgar와는 inputs/results JSON으로만 연결한다.
- EPS 3년 성장 전망은 정의 미확인이라 기본 누적→CAGR 변환(보수적). 시트 PEG(0.04)는 연평균 가정과 일치함을 테스트로 확인.
- 정성 항목(해자·경영진 등)은 LLM 초안이면 UNVERIFIED로 점수 제외. 사용자가 확인(verified=true)해야 반영.
- 테스트 62개 통과(기존 42 + 신규 20). 실제 종목 데이터·Edgar 수집 연결은 미검증.

## 2026-09-23 Watchlist 보드·공식 데이터 출처·시트 정리 도구

- `pepper watchlist`: ETF 60개 기본 + enabled 주식. RSI(14)·MACD(12/26/9)·Stoch Slow(14/3/3)·RS 백분위(ETF/주식 분리, 레버리지 제외)·Minervini Status·4대가 펀더멘털·ETF 상위10 지표. `Watchlist_Board` 탭 게시 시 수동 열 보존(clear 없이 덮어쓰기).
- 공식 출처 추가: KRX Open API(한국 일봉·코스피, 분할 보정·날짜 캐시), KIS 종목투자의견(목표가 중앙값). 네이버·Yahoo(FinanceDataReader)는 예비 출처로 '비공식 가격' 표시. 네이버 컨센서스는 사용하지 않음.
- `pepper sheets-clean`: 숨김 탭 의존성(수식·INDIRECT·차트·피벗·이름 범위) 검사, 기본 점검만, `--apply` 시 Drive 사본 후 삭제.
- 테스트 80개 통과(기존 62 + 신규 18). 이 개발 환경에서는 KRX·KIS·Yahoo·네이버 접속이 차단돼 실제 호출은 검증하지 못함(모의 응답으로만 검증). 시트 정리와 게시는 사용자 ADC 인증이 필요해 실행하지 않음.
