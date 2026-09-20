# 자동 수집·거래일지 운영

```bash
python -m pip install -e '.[automation]'
python -m pepper doctor
python -m pepper import-journal --journal /private/path/Trading_Journal_V2.xlsx
python -m pepper automate --asof 2026-09-18 --journal data/private/journal.json
```

기본 config/automation.json은 AAPL/005930 공개 연결 점검용이다. 사용자 보유 추천이 아니다. 실제 실행은 비공개 config에 종목·시장·benchmark와 미국 CIK/한국 corp_code를 넣고 `--automation-config data/private/automation.json`으로 지정한다. 거래일지 유니버스 전체는 524종목이므로 무심코 전부 호출하지 않도록 기본 max_symbols=30을 둔다.

## Google Sheets 연결

`--sheets`는 기존 Pepper 입력과 새 거래일지 탭을 읽는다. Watchlist의 enabled 체크박스를 선택한 종목만 분석한다. Settings 기준일과 `--asof`를 맞춘다. CIK/corp_code는 각 국가 공식 기업 식별자이며 티커와 다르다. 한국 티커의 선행 0을 유지한다.

```bash
python -m pepper automate --sheets --asof 2026-09-18
```

Journal_Trades의 fee는 통화 단위의 절대 수수료다. 수수료율로 해석하지 않는다. Journal_Holdings는 날짜 미확인 기존 스냅샷으로, 거래 누적 수량에 더하지 않는다. Journal_Fundamentals는 과거 수작업 비율·전망 자료이며 현재 원자료나 DuPont 3요소의 대용으로 사용하지 않는다. Orders는 고정 id로 체결과 연결된다. 주문 전 점검은 실제 체결을 발생시키지 않는다.

## 선택적 GPT 및 보관

환경변수 OPENAI_API_KEY와 OPENAI_MODEL을 설정하고 `--llm`을 명시해야 외부 GPT에 결과를 전송한다. 실패해도 이미 계산된 보고서는 data/runs에 남는다. 계산은 Python이 담당하며 GPT는 해석만 한다.

`--drive-folder 실제폴더ID`는 해당 폴더 접근 권한이 있는 ADC로 비공개 보고서를 업로드한다. 키 내용은 출력하지 않는다. 스케줄러 환경은 별도 인증이 필요하며 ChatGPT 연결 토큰과 공유되지 않는다.

## 정기 실행

.github/workflows/review.yml: 평일 07:30/21:30 UTC. 한국 16:30/익일 06:30, 미국 서머타임과 휴장일은 데이터 기준일 검사로 처리한다. PEPPER_AUTOMATION_ENABLED=true일 때만 동작한다.

GitHub Secrets: SEC_USER_AGENT(앱명+연락 이메일), DART_API_KEY, GOOGLE_CREDENTIALS_JSON. 선택적 GPT용 OPENAI_API_KEY. Variables: PEPPER_DRIVE_FOLDER, PEPPER_AUTOMATION_ENABLED, 선택적 OPENAI_MODEL. 기본 workflow는 공개 점검용 유니버스로 실행하며 사용자 장부를 읽으려면 인증·Watchlist·기준일 설정 후 실행 명령에 --sheets를 추가한다. --llm도 명시적으로 추가한다.

보고서를 공개 Actions artifact나 Git 커밋으로 올리지 않는다. 상시 실행 머신은 data/runs를 유지하며, GitHub 호스티드 runner에서는 지정 Drive 폴더의 최근 최대 100개 결과 스냅샷을 복원하여 주간 비교에 사용한다.

## 소스와 의미

- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader): 가격 수집, 라이선스·공급자 정책은 원 프로젝트 확인.
- [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces): filing cutoff, 기간별 XBRL fact 및 공시 목록.
- [OpenDartReader](https://github.com/gyusu/OpenDartReader), [DART 전체 재무](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020): 분기 단독/누적 구분.
- [pykrx](https://github.com/sharebook-kr/pykrx): 한국 투자자별 순매수.

RS는 벤치마크 대비 수익률 비율이며 IBD 공식 등급이 아니다. CAN SLIM의 C/A 25% 기준은 수정 가능한 스크리닝 규칙이다. 뉴스·기관 수급의 질·경영진 변화는 출처를 가진 사람의 판단으로 보완한다.
