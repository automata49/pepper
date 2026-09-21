# ETF 구성 종목 연결

현재 사용자 정책: **DRAM은 ETF만 추적하며 구성 종목은 수집/추가하지 않는다.** 재현 수집 스크립트에서도 DRAM을 제외했다. Roundhill parser 자체는 범용 테스트용으로 남아 있으나 활성 수집 설정에 포함되지 않는다.

`pepper.etf_holdings`는 Global X CSV, VanEck XLSX, Roundhill CSV를 검사한다. 가격/투자 판단은 계산하지 않는다.

- 원본 instrument 행을 보존한다. 주식만으로 비중을 다시 100%로 만들지 않는다.
- 음수 현금, MMF, 국채, 선물, TRS를 주식 후보와 분리한다.
- 식별자가 확인된 Micron/SK hynix/Samsung TRS만 기초 종목에 연결한다. 미확인 매핑은 빈 티커와 UNVERIFIED로 남긴다.
- 매핑 후 시장+티커로 검토 후보를 중복 제거한다. ADR과 우선주는 별도 증권으로 유지한다.
- 보유 종목 구성에 있다는 사실은 사용자의 실제 보유 또는 매수 승인과 무관하다.
- 전체 비중 합계가 반올림 허용 범위 1%p를 벗어나거나 날짜가 섞이면 import를 중단한다.

## 재현

```sh
PYTHONPATH=. python build/collect_etf_snapshot.py
python -m unittest discover -s tests -q
```

수집 스크립트는 2026-09-21 작업 재현용 **고정 링크**다. 최신 파일 탐색/스케줄러 연동은 아직 없다. 출력은 git에서 제외된 `data/private/etf_holdings.json`이다. 과거 링크도 내용이 바뀔 수 있으므로 원자료 내부 날짜를 읽는다. 포트폴리오 데이터나 API 키를 이 모듈에 넣지 않는다.

## 운용사 출처

- [CLOU](https://www.globalxetfs.com/funds/clou/)
- [BUG](https://www.globalxetfs.com/funds/bug/)
- [CRAK](https://www.vaneck.com/us/en/investments/oil-refiners-etf-crak/holdings/)
- [DRAM](https://www.roundhillinvestments.com/etf/dram/)

DRAM 원자료 `Date`는 웹 화면 표시일과 다르다(사이트는 하루 차감). 파일 날짜를 보존하고 이 주의사항을 표시한다. SKHY 상장시장과 CXMT 스왑 매핑은 추가 검증 전까지 자동 평가하지 않는다.

DRAM 가격은 거래소를 명시한 `BATS:DRAM`을 사용한다. 무거래소 티커는 다른 상품의 가격을 반환할 수 있으므로 사용하지 않는다. CLOU/BUG는 NASDAQ, CRAK은 NYSEARCA를 명시한다.

기존 Pepper의 Guide에서 연결된 Journal 복사본을 연다. 기존 Price_US/Price_KR/Added_Stocks와 계산 의존성을 네이티브 복사로 유지했다. 기존 Pepper 안으로 세 탭을 직접 병합한 상태는 아니다. ETF_Review는 전체 구성 자료, Watchlist는 평가 활성화, Orders는 사용자의 수동 계획에 사용한다. 자동 주문은 실행하지 않는다.
