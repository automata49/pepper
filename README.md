# Pepper

개인 투자 리뷰 프레임워크: 공통 데이터 → Swing Trading / Position Growth 독립 평가 → Daily / Weekly / Portfolio 리뷰.

계산은 코드로 재현하고, 해석은 근거와 함께 작성하며, 최종 매매 결정은 사용자가 내린다.

## 사용 시작

[Google Sheets Workspace 열기](https://docs.google.com/spreadsheets/d/1liWeZKMPFAnSyUPhUVLpmCagA8pv2MoFK7T7ciJ6OyA/edit) · [입력 및 연결 안내](docs/google-sheets.md) · [가상 Portfolio 보고서](examples/reports/portfolio.md)

수작업 데이터·평가 입력과 포트폴리오 시뮬레이션을 구현했습니다. **처음에는 가상 Demo 모드**입니다. 현재 수량과 계획 수량을 분리하고 계획 수량 변경에 따라 거래액·현금·비중·가격 위험이 갱신됩니다.

- 8개 탭: Dashboard, Settings, Portfolio, Research, Financials, Valuation, Prices, Guide.
- Swing/Growth 독립 평가, DuPont ROE 원인 분해, 현금흐름, EPS 성장 기대 역산.
- 읽기 전용 Google Sheets 동기화, 검증, Daily/Weekly/Portfolio Markdown 및 JSON 보고서.
- 시트 생성·연결된 Google Drive를 통한 읽기·예시 재계산까지 검증. 별도 PC/서버의 자동 읽기에는 Google ADC 인증을 한 번 설정해야 합니다.
- 실시간 시세·계좌 연결·자동 주문·정기 실행은 활성화하지 않았습니다.

```bash
python -m pip install -e .
python -m pepper review --snapshot examples/demo.json
python -m unittest discover -s tests -v
```

인증 설정 후 `python -m pip install -e '.[google]'`와 `pepper sync`로 최신 수작업 입력을 읽습니다. 세부 설정은 위 안내를 참고하세요. 개인 자료와 실행 결과는 `data/`, `reports/`에 저장하며 Git에서 제외됩니다.

## 평가 체계

| 영역 | 평가 항목 | 결과 |
| --- | --- | --- |
| Swing Trading | RS, 21/50/200일 이동평균, 돌파·눌림, 20일 평균 대비 거래량, ATR, 무효화 조건 | 후보·진입 조건·과열·위험을 구분 |
| Position Growth | CAN SLIM, DuPont ROE, 현금흐름, 현재 가격에 반영된 기대 | 성장의 질·지속성·밸류에이션 가정·반증 조건 |

두 전략의 평가를 별도로 표시한다. 주도주 여부와 현재 진입 가능 여부도 구분한다.

### Position Growth

1. CAN SLIM: 분기/연간 성장, 신제품·변화, 수급, 주도력, 기관 참여, 시장 방향을 근거별로 평가한다. 정량 지표와 정성 판단을 구분하며 이를 공식 IBD 등급으로 표시하지 않는다.
2. DuPont: ROE = 순이익률 × 자산회전율 × 재무 레버리지. 동일 기간 순이익·매출과 평균 자산·평균 자기자본을 사용한다. 수익성·효율 개선과 레버리지 상승을 분리하고, 비양수 자기자본 등 해석 불가능한 경우는 N/A로 표시한다.
3. 현금흐름: 영업현금흐름, CAPEX, FCF, 이익 대비 현금 전환, 운전자본 변화와 주식보상·희석을 함께 점검한다.
4. 가격에 반영된 기대: 명시적인 할인율·성장률·마진·주식수·말기 가치 가정으로 시나리오 및 역산 평가를 수행한다. 역산된 기대와 실제 전망을 구분한다.

## 리뷰 운영

| 리뷰 | 필수 내용 |
| --- | --- |
| Daily | 데이터 기준시각, 시장 상태, 전일 대비 변화, 신규 트리거, 실적 일정·위험 경고 |
| Weekly | 주도 테마·종목 변화, 두 전략 비교, 후보 순위, 가설 변화, 매매 복기 |
| Portfolio | 전략별 비중, 현금, 종목·테마 중복, 집중도, 손절 기준 위험, 논리 훼손 여부 |

## 구현 구조

- `config/workspace.json`: 연결된 Google Sheets ID
- `pepper/sheets.py`, `schema.json`: 읽기 전용 연결·입력 스키마 검증
- `pepper/engine.py`: 근거·시점 검증, 전략 평가, 재무·가격 기대·포트폴리오 계산
- `pepper/reports.py`: Daily / Weekly / Portfolio 보고서와 스냅샷 비교
- `prompts/review.md`: 선택적 GPT 해석 컨텍스트
- `examples/`: 재현 가능한 가상 자료와 예시 보고서
- `tests/`: 입력 누락·전량 매도·중복·미래 정보·위험·DuPont 검증
- `docs/google-sheets.md`: 사용법·인증·계산 정의·구현 범위

이전 README의 전체 자동 수집 구상 중 현재 구현은 수작업 입력 기반입니다. 시장 일정·뉴스·순위·실제 매매 복기는 수작업 확인 영역으로 명시합니다. Weekly는 7일 이상 전 같은 모드의 스냅샷이 쌓인 후 비교하며, 가격 변화는 배당·분할 조정 총수익률이 아닙니다.

## 검토할 외부 소스

이 목록은 이전 설계에서 제안한 후보이며 아직 연동·라이선스·호환성 검증을 완료하지 않았다.

- FinanceDataReader, pykrx: 가격·한국 시장 데이터 후보
- SEC EDGAR API, OpenDartReader: 미국·한국 공시 데이터 후보
- OpenBB: 데이터 통합 구조 참고 후보
- TradingAgents: 리서치 워크플로우 참고 후보

## 데이터 원칙

- 결측을 0이나 합격으로 대체하지 않는다. 출처와 기준시각이 없는 값은 미검증으로 표시한다.
- 백테스트에는 당시 공개된 정보만 사용한다. 수정주가·배당·분할 처리 기준을 기록한다.
- RS 수익률 비교와 유니버스 내 퍼센타일 순위를 구분한다.
- 계좌 잔고·개인 포지션·API 키는 공개 저장소에 넣지 않는다. 예시는 가상 데이터로 명시한다.
