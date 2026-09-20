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

## 재개 절차

2026-09-20 검증: 단위 테스트 27개 통과. 미국/한국 개별 가격 실제 수집 성공. SEC 연락처·DART 키 없음, 한국 투자자별 수급 응답 없음으로 실재무/수급 운영 검증은 미완료. 자동 재개 확인 작업은 5시간 간격으로 등록됨. 생성된 예약은 사용량 제한을 해제하지 않는다.

최신 main과 이 문서를 읽고 현 상태를 먼저 확인한다. `python -m unittest discover -s tests -q`, `python -m pepper doctor`를 실행한다. 추가 구현/검증 결과를 이 문서에 남긴다. data/, reports/, 원본 XLSX, 실제 보유/거래 정보와 비밀키를 공개 GitHub에 올리지 않는다. 사용자 원본 Trading_Journal_V2는 수정하지 않는다.

사용량 한도를 감지하거나 해제할 API는 없다. 예약 재개 작업은 실행 시 사용 가능한 권한·한도 내에서만 수행되며 한도 우회 또는 정확한 리셋 시각 재개를 보장하지 않는다.
