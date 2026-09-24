# Watchlist 보드

ETF 60개(기본)와 관심 주식의 가격 지표와 펀더멘털을 `Watchlist_Board` 탭 한 곳에 보여줍니다.
지표는 Pepper(Python)가 계산하고, 시트는 결과 표시와 수동 입력(총보수·메모)만 맡습니다.

```bash
python -m pepper watchlist --asof 2026-09-22                        # reports/watchlist.json 생성
python -m pepper watchlist --sheets --input data/inputs/latest.json --holdings data/private/etf_holdings.json --publish
```

- `--sheets`: 기존 `Watchlist` 탭에서 enabled 체크한 주식을 추가
- `--input`: 4대가 점수용 펀더멘털 입력(docs/scoring.md 형식) → 장기 점수·PEG·ROE·적정가
- `--holdings`: ETF 구성 종목(etf_holdings 형식) → 상위10 비중·상위 3종목·가중 Forward PER
- `--publish`: 시트에 게시. 기존 수동 입력 열은 Ticker 기준으로 보존하고, 목록에서 빠진 종목의 입력도 맨 아래에 남깁니다.

## 지표 정의 (config/watchlist.yaml에서 변경)

| 지표 | 정의 | 신호 (참고용, 점수 미반영) |
| --- | --- | --- |
| RS 백분위 | 벤치마크 대비 3·6·12개월 수익률 순위, 40·20·40 가중. ETF끼리·주식끼리, 시장별. 레버리지 제외 | — |
| RSI(14) | Wilder 평활 | 70↑ 과열, 30↓ 과매도 |
| MACD | EMA 12·26, 시그널 9 | 히스토그램 0 교차 |
| Stoch Slow | 14·3·3 | %K가 %D를 20 이하에서 상향 / 80 이상에서 하향 교차 |
| Swing Status | Minervini Trend Template (rules/minervini.yaml) | ACTIONABLE·EXTENDED·SETUP·WATCH·AVOID |

ETF는 기업 실적 항목을 N/A로 두고 가격 기준만 평가합니다(rules/exceptions.yaml `etf` 태그).
가중 Forward PER은 상위 10개 중 PER을 아는 종목만으로 계산한 가중 조화평균이며, 그 비중이 상위 10개의 절반 미만이면 비워 둡니다.

## 데이터 출처

| 데이터 | 1순위 (공식) | 예비 (비공식, '비공식 가격' 경고) |
| --- | --- | --- |
| 한국 주식·ETF 일봉, 코스피 지수 | KRX Open API (`KRX_API_KEY`) | FinanceDataReader → 네이버 차트 |
| 미국 주식·ETF 일봉 | — (무료 공식 API 없음) | FinanceDataReader → Yahoo |
| 한국 재무 | OpenDART | — |
| 미국 재무 | SEC Companyfacts | — |
| 한국 목표가 컨센서스 | KIS Open API 종목투자의견 | — (네이버 컨센서스는 쓰지 않음) |

네이버 증권은 공식 공개 API가 없어 직접 크롤링하지 않습니다. KRX Open API는 키 발급 뒤
유가증권·코스닥·ETF 일별매매정보와 KOSPI 시리즈 일별시세정보를 각각 이용 신청해야 합니다.
KRX 가격은 수정주가가 아니므로 상장주식수 변화로 액면분할·병합을 보정합니다(유상증자처럼 가격이 따라 움직이지 않은 경우는 보정하지 않음).
KIS 종목추정실적(추정 EPS)은 응답 구조를 실제 키로 확인한 뒤 연결할 예정이며, 지금은 원자료만 저장합니다.

## 시트 정리 (숨김 탭)

```bash
python -m pepper sheets-clean --spreadsheet <ID>            # 점검만: 삭제 후보와 남길 숨김 탭(이유) 출력
python -m pepper sheets-clean --spreadsheet <ID> --apply    # Drive 전체 사본을 만든 뒤 삭제
```

보이는 탭과 Price_US·Price_KR이 수식·INDIRECT 문자열·차트·피벗·이름 있는 범위로 참조하는 숨김 탭은 연쇄적으로 남깁니다.
사본 생성이 실패하면 아무것도 지우지 않습니다. 삭제 후에도 Google Sheets 버전 기록으로 되돌릴 수 있습니다.
