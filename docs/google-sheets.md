# Pepper 간략 시트 사용 안내

사용 화면은 Price_US, Price_KR, 보완입력이다. Fundamental 탭은 사용자 요청으로 삭제했고 CAN SLIM C/A/N/S/L/I/M·종합점검·근거/다음 확인을 두 Price 시트 오른쪽에서 관리한다. 시장·뉴스·공시 종합 분석은 ChatGPT가 작성한다.

보완입력 A:J는 요청 정보, K:Q는 값·출처 URL·자료일·기간 시작/끝·통화·메모다. 날짜는 YYYY-MM-DD로 쓰고 단위·회계 범위를 메모에 기록한다. 입력 후 ChatGPT에 재검토를 요청한다. 입력만으로 ROE나 평가에 자동 반영하지 않는다.

거래·보유·주문·복기 탭은 재생성하지 않는다. 이전 Portfolio/Trades/Orders 안내는 폐기한다. 가격 수식에 필요한 계산 탭 6개는 숨김 보존한다. DRAM은 ETF만 유지한다.

## 연결 상태

비공개 실행 환경의 PEPPER_RESEARCH_SHEET_ID에 현재 Journal 파일 ID를 설정한다. ID나 키를 공개 저장소에 쓰지 않는다.

```sh
python -m pepper automate --asof YYYY-MM-DD --research-sheets
```

이 경로는 Price_US·Price_KR의 가격·CAN SLIM 참고값과 보완입력을 읽는다. 대상 종목은 automation config에서 지정하며, 시트 값은 `REFERENCE_ONLY_NOT_INDEPENDENTLY_VERIFIED`로 별도 보관하고 공급자 계산값을 덮어쓰지 않는다. Settings 등 숨김 탭과 삭제된 Fundamental·장부는 읽지 않는다.

자동 수집에서 발견한 미검증 항목을 보완입력에 추가할 때만 다음 옵션을 함께 사용한다.

```sh
python -m pepper automate --asof YYYY-MM-DD --research-sheets --publish-research-sheets
```

게시 범위는 기존 보완입력의 A:J뿐이다. K:Q 수작업 값·출처·날짜·메모는 쓰거나 지우지 않는다. 빈 request_id가 있는 비어 있지 않은 행, 중복 ID·행 위치, 헤더 불일치, 용량 초과는 실패 처리한다. Price_US·Price_KR의 자동 CAN SLIM 갱신은 별도 검증된 작업만 해당 열에 쓴다.

기존 --sheets, --publish-sheets, sync, import-journal, --journal은 CLI에서 차단한다. 서버 ADC는 ChatGPT 연결과 별개다.

GitHub 정기 실행은 간략 스키마 검증 전까지 중지한다. 전체 자동화 완료를 의미하지 않는다. 최신 상태는 BUILD_STATUS.md를 확인한다.
