# 평가 실행 보고서

실행 ID: `20260924T114423Z`

**자동 실행 및 계약 검사 결과. 의미 채점은 검토 전이며 품질 점수가 아니다.**

- 상태: completed
- 최초 성공: 33/36슬롯
- 최종 성공: 33/36슬롯
- 호출 시도: 36, 재시도: 0, 미실행: 0
- 응답에서 확인 가능한 Token: 입력 78436, 출력 60902
- Usage 미확인 시도: 3. 전체 소비량: 산출 불가

| 슬롯 | 결과 | Requirement 수 | Gap 수 | Blocking Gap 수 | clarification_needed |
| --- | --- | ---: | ---: | ---: | --- |
| L01-1 | success | 4 | 5 | 4 | True |
| L02-1 | success | 25 | 4 | 4 | True |
| L03-1 | success | 31 | 1 | 1 | True |
| L04-1 | success | 4 | 6 | 5 | True |
| L05-1 | success | 10 | 3 | 3 | True |
| L06-1 | success | 18 | 3 | 3 | True |
| R01-1 | success | 3 | 4 | 3 | True |
| R02-1 | success | 19 | 2 | 2 | True |
| E01-1 | success | 9 | 4 | 4 | True |
| S01-1 | success | 19 | 2 | 1 | True |
| A01-1 | success | 10 | 2 | 2 | True |
| D01-1 | success | 12 | 2 | 2 | True |
| L01-2 | success | 2 | 6 | 5 | True |
| L02-2 | success | 19 | 2 | 2 | True |
| L03-2 | success | 28 | 1 | 1 | True |
| L04-2 | success | 4 | 5 | 4 | True |
| L05-2 | other_contract_unknown | N/A | N/A | N/A | N/A |
| L06-2 | success | 18 | 2 | 2 | True |
| R01-2 | success | 3 | 5 | 5 | True |
| R02-2 | success | 18 | 2 | 1 | True |
| E01-2 | success | 13 | 4 | 4 | True |
| S01-2 | success | 14 | 2 | 1 | True |
| A01-2 | success | 9 | 2 | 2 | True |
| D01-2 | success | 11 | 3 | 3 | True |
| L01-3 | success | 4 | 6 | 4 | True |
| L02-3 | success | 24 | 4 | 4 | True |
| L03-3 | success | 29 | 1 | 1 | True |
| L04-3 | success | 5 | 5 | 3 | True |
| L05-3 | other_contract_unknown | N/A | N/A | N/A | N/A |
| L06-3 | success | 14 | 3 | 3 | True |
| R01-3 | success | 3 | 4 | 4 | True |
| R02-3 | other_contract_unknown | N/A | N/A | N/A | N/A |
| E01-3 | success | 7 | 2 | 2 | True |
| S01-3 | success | 12 | 2 | 1 | True |
| A01-3 | success | 9 | 2 | 2 | True |
| D01-3 | success | 8 | 4 | 4 | True |

## 근거

- [전체 시도 및 원본 응답](attempts.jsonl)
- [실행 조건 및 해시](manifest.json)
- [집계 JSON](summary.json)

실패 원인은 API 코드와 메시지만으로 분류했다. 중간 Stage 결과나 서버 로그를 사용하지 않았다. 원본 입력은 manifest에 보존했다. 성공 응답만의 의미 점수는 별도 사람 검토 후 확정한다.
