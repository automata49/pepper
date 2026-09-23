# Pepper 간략 시트 사용 안내

사용 화면은 Price_US, Price_KR, Fundamental, 보완입력이다. 가격·펀더멘털 상세 근거는 시트에서 확인하고 시장·뉴스·공시 종합 분석은 ChatGPT가 작성한다.

보완입력 A:J는 요청 정보, K:Q는 값·출처 URL·자료일·기간 시작/끝·통화·메모다. 날짜는 YYYY-MM-DD로 쓰고 단위·회계 범위를 메모에 기록한다. 입력 후 ChatGPT에 재검토를 요청한다. 입력만으로 ROE나 평가에 자동 반영하지 않는다.

거래·보유·주문·복기 탭은 재생성하지 않는다. 이전 Portfolio/Trades/Orders 안내는 폐기한다. 가격 수식에 필요한 계산 탭 6개는 숨김 보존한다. DRAM은 ETF만 유지한다.

## 연결 상태

비공개 실행 환경의 PEPPER_RESEARCH_SHEET_ID에 현재 Journal 파일 ID를 설정한다. ID나 키를 공개 저장소에 쓰지 않는다.

```sh
python -m pepper automate --asof YYYY-MM-DD --research-sheets
```

이 경로는 보완입력만 읽어 보고서에 독립 검증 전 근거로 첨부한다. 대상 종목은 automation config에서 지정한다. Price/Fundamental 직접 읽기 및 새 스키마 게시 경로는 전환 중이다. 기존 --sheets, --publish-sheets, sync, import-journal, --journal은 CLI에서 차단한다. 서버 ADC는 ChatGPT 연결과 별개다.

GitHub 정기 실행은 간략 스키마 검증 전까지 중지한다. 전체 자동화 완료를 의미하지 않는다. 최신 상태는 BUILD_STATUS.md를 확인한다.
