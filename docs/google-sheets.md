# Google Sheets 사용 및 연결

[Pepper Workspace 열기](https://docs.google.com/spreadsheets/d/1liWeZKMPFAnSyUPhUVLpmCagA8pv2MoFK7T7ciJ6OyA/edit)

시트 생성, 네이티브 드롭다운 표, 수식, 입력 변경 재계산을 완료했습니다. ChatGPT의 연결된 Google Drive로 읽고 예시 보고서까지 생성해 계산을 대조했습니다. 별도 PC/서버의 Python 실행에는 그 환경의 Google 인증이 추가로 필요합니다. ChatGPT 연결 토큰을 복사하거나 GitHub에 저장하지 않습니다.

## 시트 사용

| 탭 | 수작업 입력 | 자동 계산 |
|---|---|---|
| Settings | B5:B18: 모드, 기준일, 환율·현금·한도·수수료·스트레스 | 전 시트에 적용 |
| Prices | A:I: 티커, 시장, 통화, 가격, 날짜, 출처, Reviewed | 시세 품질 상태 |
| Research | A:L: Swing/Growth, 평가 항목, PASS/FAIL/UNKNOWN, 근거·날짜·출처 | 근거 상태 |
| Financials | A:N: Current/Previous TTM 재무 | DuPont 3요소·ROE·FCF·현금 전환 |
| Valuation | A:G: 기간, 말기 PER, EPS 성장, 요구수익률, 근거·검토일 | 가격이 요구하는 EPS 성장률과 가정 여유 |
| Portfolio | A:J: 보유 수량, 원가, 손절, 계획 수량, 논리·검토일 | 현재/계획 비중·매매 금액·현금·위험 |
| Dashboard | 입력 없음 | 현재/계획 비교 및 평가 현황 |
| Guide | 입력 없음 | 사용 안내 |

노란 셀을 입력합니다. 표의 5행 제목, 탭 이름, Settings B19 스키마는 유지하세요. 숫자로 보이는 한국 티커도 **텍스트**로 입력합니다(예: `005930`). 각 표는 6~105행, 최대 100개 레코드입니다. 106행 이후 입력은 보고서 코드가 오류로 처리합니다. 확장하려면 모든 수식과 스키마 범위를 함께 변경해야 합니다.

1. 가상 DEMO 행과 예시 현금·환율을 실제 값으로 **교체**합니다. 행 전체 삭제 대신 입력 영역의 내용만 지워 수식을 유지합니다.
2. Settings 기준일은 마지막으로 리뷰하려는 거래일을 고정 입력합니다. 가격·평가·공시일의 미래 정보는 배제합니다.
3. Research에 수집한 지표와 사용자의 판단을 기록합니다. 같은 종목·전략·항목의 최신 날짜를 사용하며 같은 날짜의 여러 기록은 충돌로 처리합니다. 날짜를 기입한 UNKNOWN은 이전 PASS/FAIL을 철회하는 데 쓸 수 있습니다.
4. Financials 금액은 한 종목의 두 기간에서 동일 단위(예: 백만 USD)를 사용합니다. EPS만 주당 통화 단위입니다. 평균 자산·자기자본은 동일 방식으로 계산하고 출처에서 확인하세요. 현재 구현은 단위를 자동 변환하지 않습니다.
5. Portfolio의 **계획 수량 G열**을 수정합니다. 빈칸은 보유 유지, `0`은 전량 매도 계획입니다. D열 실제 수량은 자동 변경되지 않습니다. 실제 체결 후 D/E열과 Settings 현금을 사용자가 갱신합니다.
6. 검증 상태를 확인하고 Live 모드로 전환합니다. 과거 리뷰는 Python sync 실행마다 별도 스냅샷으로 남습니다.

Dashboard의 평가 집계는 입력된 행 수이며 최신 종목 점수나 순위가 아닙니다. 시트의 편집 도우미 검증보다 Python의 최종 검증이 더 엄격합니다(출처 URL 형식, 공시 비교 가능성, 같은 날짜 평가 충돌 등). 보고서 `issues`도 확인하세요.

## PC/서버에서 동기화

Python 3.11 이상:

```bash
git clone https://github.com/automata49/pepper.git
cd pepper
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[google]'
python -m pepper review --snapshot examples/demo.json
```

Windows는 `.venv\Scripts\activate`를 사용합니다.

실제 읽기는 Google Application Default Credentials(ADC)를 사용합니다. Google Cloud 프로젝트에서 Sheets API를 활성화하고, 다음 중 실행 환경에 맞는 인증을 설정하세요.

- 서비스 계정 사용 시: 해당 계정 이메일에 **이 시트만 Viewer로 공유**하고, 로컬의 계정 JSON 경로를 `GOOGLE_APPLICATION_CREDENTIALS`에 지정합니다. 계정 키는 저장소 밖에서 관리합니다.
- 사용자 OAuth 사용 시: OAuth 클라이언트를 준비한 뒤 Sheets 읽기 범위가 포함된 ADC를 구성합니다. 조직 정책에 따라 동의 또는 관리자 허용이 필요할 수 있습니다. 일반 Cloud 기본 범위만 있는 ADC는 Sheets 권한을 보장하지 않습니다.

```bash
export GOOGLE_APPLICATION_CREDENTIALS='/absolute/private/path/service-account.json'
pepper sync
```

서비스 계정을 새로 만들거나 사용자 권한을 변경하는 작업은 이번 구현에서 수행하지 않았습니다. 읽기 연결 설정은 `config/workspace.json`에 있으며 시트 ID는 비밀키가 아닙니다. 시트를 복사한 경우 이 ID만 교체하세요.

`pepper sync`는 **읽기 전용**으로 시트를 가져와 아래를 생성합니다.

- `reports/daily.md`, `weekly.md`, `portfolio.md`, `review.json`
- `data/history/demo/` 또는 `live/`: 실행시각별 원본 스냅샷과 계산 결과

두 디렉터리는 Git에서 제외됩니다. 저장소의 `examples/`는 전부 가상 자료입니다. 자동 정기 실행은 아직 등록하지 않았습니다. 사용자가 선택한 PC/서버에서 위 명령을 스케줄링할 수 있습니다.

## 계산과 범위

- DuPont: 순이익/매출 × 매출/평균 자산 × 평균 자산/평균 자본. ROE 변화 원인 기여도는 보고서에서 Shapley 방식으로 계산합니다. 전년 동기 TTM 종료일 간 330~400일·같은 통화·연결 범위를 요구합니다.
- 가격 기대: `(현재가 × (1+요구수익률)^기간 / (EPS × 말기 PER))^(1/기간) - 1`. EPS 양수에 한해 계산하며 배당·세금·FX 수익은 제외합니다.
- 현금: KRW 현금 + USD 현금 × 현재 환율. 계획 현금에서 매수/매도 순금액과 양방향 수수료를 차감합니다. 환전·통화별 결제 여력은 별도 확인합니다.
- 위험: 수량 × max(현재가−손절, 0) × 환율. 손절 미입력은 미산정, 이미 이탈한 경우 별도 경고입니다. 손실 상한을 보장하지 않습니다.
- 현금흐름 추가 검토: 운전자본, 주식보상, 희석·자사주 매입의 질은 Research/CashFlow에 입력합니다.
- 현재는 **수작업 기반**입니다. 시세 자동 수집, 거래내역 장부, 정확한 성과 수익률, 시장 뉴스·실적 일정 수집, 자동 주문은 연결하지 않았습니다.

## 검증 기록

2026-09-20: Google Sheets 네이티브 계산에서 가상 포트폴리오 NAV 7,900,000원, 계획 현금 4,949,350원 확인. DEMO_US 계획 수량 15→20 변경 시 계획 현금 4,298,700원, 0 변경 시 계획 평가액 0원 확인 후 15로 복원했습니다. 같은 원본을 Python으로 재계산하여 일치 확인했습니다. 테스트는 `python -m unittest discover -s tests -v`로 재실행합니다.

공식 문서: [Sheets batchGet](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet), [ADC 설정](https://cloud.google.com/docs/authentication/provide-credentials-adc).
