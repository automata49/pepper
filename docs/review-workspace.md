# 자동 리뷰와 보완 입력

- Review_US / Review_KR / Review_Other: 기계가 갱신하는 가격·이평선·RS·Swing·Growth·DuPont·현금흐름 상세. 입력 탭이 아니다.
- Data_Requests A:J: 자동 보완 요청. 동일 시장/종목/필드/역할에 같은 ID를 사용한다.
- Data_Requests K:Q: 사용자의 값, 출처 URL, 출처 날짜, 기간 시작/끝, 통화, 메모. 갱신 시 이 영역을 쓰거나 지우지 않는다. 날짜는 YYYY-MM-DD.
- 기존 Portfolio / Orders: 수동 조정 영역이며 자동 게시에서 변경하지 않는다. 자동 주문은 없다.

보완 값과 유효한 HTTP(S) 출처, 보고 기준일 이전의 출처 날짜가 있으면 Daily/Weekly/Portfolio에 **독립 검증 전 수작업 근거**로 표시한다. 링크 형식/날짜 검사는 사실 확인과 다르다. 입력만으로 ROE/현금흐름/평가 점수를 바꾸지 않는다. 계산 반영 전 동일 기간·통화·회계 범위·단위를 대조해야 한다.

```sh
python -m pepper automate --asof YYYY-MM-DD --sheets --publish-sheets
```

`--sheets`는 기존 입력/Journal과 보완 큐를 읽는다. `--publish-sheets`는 별도 쓰기 권한으로 전용 자동 탭만 갱신한다. Google ADC와 동의된 spreadsheets scope가 필요하다. 기존 수작업 Settings의 기준일은 실행 기준일과 일치해야 한다.

`save_run`은 실행 결과와 함께 `workspace.json`을 보존한다. API가 없을 때 이 JSON은 게시용 계획일 뿐, Google Sheet 갱신 성공을 뜻하지 않는다. 게시자는 직렬 실행해야 한다. 동시 정렬/행 삭제/다른 게시자와 경쟁하는 상황은 지원하지 않으며, 조회 직후 갱신해야 한다.

기존 행의 request_id를 삭제하지 않는다. ID 없는 수작업 값, 중복 ID, 헤더 변경, 수용 행 초과는 중단한다. 새 유니버스에 없어진 요청은 OUT_OF_SCOPE로 남기므로 기존 입력을 잃지 않는다. 데이터가 자동 확보된 요청도 입력은 보존한다.

현재 설치된 첫 Review_US는 네이티브 시트에서 읽은 ETF 4개 가격의 REFERENCE_ONLY 표시다. 완전한 일봉 수집/기술 평가를 수행한 결과가 아니다. 가격 거래시점이나 이력이 확인되지 않으면 보완 요청이 남는다. DRAM은 ETF만 유지한다.
