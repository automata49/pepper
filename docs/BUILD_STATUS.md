# Pepper 구현·재개 상태

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
7. 사용자가 정의한 Sheets 역할 중 자동 보완요청 생성/응답 재검증과 전체 자동 리포트 쓰기 연결은 아직 미완료다. 기존 수작업 양식과 혼동하지 않는다.

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

## 재개 절차

2026-09-20 검증: 단위 테스트 27개 통과. 미국/한국 개별 가격 실제 수집 성공. SEC 연락처·DART 키 없음, 한국 투자자별 수급 응답 없음으로 실재무/수급 운영 검증은 미완료. 자동 재개 확인 작업은 5시간 간격으로 등록됨. 생성된 예약은 사용량 제한을 해제하지 않는다.

최신 main과 이 문서를 읽고 현 상태를 먼저 확인한다. `python -m unittest discover -s tests -q`, `python -m pepper doctor`를 실행한다. 추가 구현/검증 결과를 이 문서에 남긴다. data/, reports/, 원본 XLSX, 실제 보유/거래 정보와 비밀키를 공개 GitHub에 올리지 않는다. 사용자 원본 Trading_Journal_V2는 수정하지 않는다.

사용량 한도를 감지하거나 해제할 API는 없다. 예약 재개 작업은 실행 시 사용 가능한 권한·한도 내에서만 수행되며 한도 우회 또는 정확한 리셋 시각 재개를 보장하지 않는다.
