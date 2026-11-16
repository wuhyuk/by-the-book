# 평가 요약 (2026-11-16)

> 모든 수치는 아래 적은 명령을 2026-11-16에 실제로 실행해 얻은 값이다. LLM·네트워크 호출은 없다 (5절 실서비스 확인은 사용자 제공 사실과 `rag_live_result.md` 기록).
> 실행 환경: Windows, `backend/.venv` Python, 저장소 루트 또는 `backend`에서 실행. 브랜치 `feat/eval-and-docs` 작업 트리 (main `c7ad0c0` 기준, 기능 코드 변경 없음).
> **승인 전 임시값**: 2절(조항 검색)과 3절(판단 보류율)은 평가 문장·정답이 "승인 대기"라 승인 전 임시값이다. pytest 기대값·임계값으로 쓰지 않는다.

## 1. 계산 정확성 (승인 케이스 테스트)

실행 명령 (`backend`에서, 2026-11-16):

```text
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_gym_integration.py::test_case"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_laundry_cases.py::test_approved_case"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_laundry_r2_cases.py::test_r2_case"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_appliance_cases.py::test_appliance_case"
```

케이스 수는 각 테스트 파일의 케이스 목록 길이를 Python으로 센 값이다 (`len(test_gym_calc.CASES)`, `len(test_laundry_cases.CASES)`, `len(test_laundry_r2_cases.CASES)`, `len(test_appliance_cases.CASES)`). 각 테스트는 케이스 하나당 1건으로 매개변수화되어 있다.

| 도메인 | 테스트 | 케이스 수 | 통과 | 승인된 기대값 기준 (승인 문서) |
|---|---|---|---|---|
| 헬스장 | `test_gym_integration.py::test_case` (케이스 목록 `test_gym_calc.CASES`) | 35 | 35 | `docs/sources/gym_cases_draft.md` (사용자 검증 완료(손계산) 7건 + 사용자 승인(보고서 검토) 28건, 2026-10-26. B4는 2026-11-06 재승인) |
| 세탁 (축소 A) | `test_laundry_cases.py::test_approved_case` | 22 | 22 | `docs/sources/vs4_cases_approval.md` (L1~L22, 승인 2026-11-10), 원 케이스 `laundry_cases_draft.md` |
| 세탁 R2 (Set 일부 손상, 플래그 `set_partial`) | `test_laundry_r2_cases.py::test_r2_case` | 41 | 41 | `docs/sources/vs4_restore_r2_cases.md` 2판 (승인 2026-11-15, 제외 4건 R2-14·15·32·44는 테스트 없음) |
| 가전 P2 (플래그 `appliance`) | `test_appliance_cases.py::test_appliance_case` | 34 | 34 | `docs/sources/appliance_cases.md` (A-1~A-34, 승인 2026-11-15) |
| 합계 | | 132 | 132 | |

- 위 표에 넣지 않은 것: L4의 R2 재승인 값(`test_laundry_r2_api.py`), 같은 헬스장 케이스를 다른 각도로 보는 `test_gym_calc.py`의 위약금·기준별 결과 테스트, 오라클 비교 테스트(`test_gym_oracle.py`, `test_laundry_oracle.py`). R1(소재·용도 미상)은 코드가 없어 승인 케이스 6건도 테스트에 없다 (MVP_SPEC 12.10).
- 전체 백엔드 테스트 (`backend`에서 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_rag_live_check.py`): **1779 passed**, 경고 1건(Starlette `TestClient`의 httpx 사용 경고). `test_rag_live_check.py`는 이전 작업의 추적하지 않는 파일이라 제외했다.

계산에 LLM이 관여하지 않는다는 구조 근거: `backend/tests/test_import_direction.py`(AST로 `rules/*.py`가 `llm`·`api`를 import하지 않는지 검사)가 **41 passed**, 그리고 저장소 루트에서 `grep -rnE "^\s*(import|from)\s+(llm|api)\b" backend/rules` 결과 **일치 0줄**(종료 코드 1).

## 2. 조항 검색 (rag, BM25) — 승인 전 임시값

실행 명령 (저장소 루트에서): `backend/.venv/Scripts/python.exe -X utf8 eval/run_retrieval_eval.py --misses`
평가 세트 `docs/sources/rag_eval_set.md` 30문장 (정답 승인 대기 30건). 기준선 = 업종 필터만 쓰고 조항 앞쪽 k개. 실제 서비스는 후보 5개를 LLM에 넘기므로(MVP_SPEC 15.2) **hit@5가 핵심 수치**다. 검색 알고리즘·토큰화·파라미터는 바꾸지 않았다 (튜닝 없음).

| 업종 | 문장 수 | BM25 hit@1 | BM25 hit@3 | BM25 hit@5 | 기준선 hit@1 | 기준선 hit@3 | 기준선 hit@5 |
|---|---|---|---|---|---|---|---|
| gym | 10 | 6/10 (60%) | 7/10 (70%) | 9/10 (90%) | 1/10 (10%) | 1/10 (10%) | 2/10 (20%) |
| laundry | 10 | 4/10 (40%) | 8/10 (80%) | 9/10 (90%) | 1/10 (10%) | 2/10 (20%) | 4/10 (40%) |
| appliance | 10 | 3/10 (30%) | 5/10 (50%) | 6/10 (60%) | 0/10 (0%) | 1/10 (10%) | 1/10 (10%) |
| 전체 | 30 | 13/30 (43%) | 20/30 (67%) | 24/30 (80%) | 2/30 (7%) | 4/30 (13%) | 7/30 (23%) |

BM25 hit@5를 놓친 문장 (6건):

| ID | 정답 | BM25 상위 5 |
|---|---|---|
| G7 | art6_1 | art2_4, yoga_terms_art5_2, art2_2, yoga_terms_art9_1_def, gym_terms_art8_2_def |
| L8 | laundry_7 | laundry_2, laundry_1, laundry_6, laundry_5_1, laundry_types |
| A1 | elec_5 | elec_3, elec_note_refurb, elec_note_fn2, annex4, annex3_items |
| A2 | elec_1 | gen_1_da, gen_1_na, gen_4_ra, elec_5, gen_1_ga |
| A4 | elec_4 | gen_1_da, elec_note_refurb, elec_2, elec_3, elec_1 |
| A8 | elec_6 | gen_4_ra, gen_1_da (점수 > 0인 후보가 2개뿐) |

hit@3은 놓쳤고 hit@5에서 맞힌 문장 (4건): G2(art2_2, 4위), G3(art5_2, 4위), L7(laundry_6, 5위), A3(elec_note_fn1, 5위).

가전은 문장 분석이 없어(MVP_SPEC 13.1) 검색만 평가한 값이며 실제 서비스 흐름에는 쓰이지 않는다.

## 3. 판단 보류율 (규칙 가드레일만) — 승인 전 임시값

실행 명령 (저장소 루트에서): `backend/.venv/Scripts/python.exe -X utf8 eval/run_guardrail_eval.py`
평가 세트 `docs/sources/guardrail_eval_set.md` 40문장 (보류 대상 20, 정상 20, 모두 승인 대기). 대상은 `backend/llm/guardrail.py`의 `detect_judgment_request`이며 실제 흐름과 같게 마스킹한 문장을 넣었다. LLM 판정(`judgment_requested` 추출값, 근거 구절이 있을 때 OR로 합침)은 이 평가에 들어가지 않는다. 가드레일 패턴은 바꾸지 않았다.

| 지표 | 값 |
|---|---|
| 보류 재현율 (보류 대상 20개 중 잡음) | 6/20 (30%) |
| 오탐률 (정상 20개 중 막음) | 1/20 (5%) |

놓친 보류 대상 문장 (14건): J3, J4, J5, J8, J9, J10, J11, J12, J14, J15, J16, J17, J18, J19 (문장은 `guardrail_eval_set.md`).
잡은 보류 대상 문장 (6건): J1, J2, J6, J7, J13, J20.
오탐한 정상 문장 (1건): N13 "세탁 맡긴 니트가 늘어났어요. 승소 이런 건 관심 없고 배상 기준만 알려 주세요".

## 4. 일반 챗봇 비교

`docs/sources/eval_compare_sheet.md`: 승인 케이스 10건(헬스장 4, 세탁 3, 가전 3, ✅ 3·⚠️ 2·🔍 3·❔ 2)의 질문문과 이 서비스의 엔진 실행 결과. 10건 모두 엔진 결과가 승인 문서의 정답과 같았다. 일반 챗봇 열은 사용자가 채운다 (아직 빈칸).

## 5. 실서비스 확인 (2026-11-16)

사용자 제공 사실:

1. 기능 플래그 `rag`만 켠 첫 실행에서 문장 7건 중 6건이 502였다. Gemini 쪽 일시 오류로 추정하며, 같은 날 Gemini 대시보드의 503 약 5건과 건수가 맞는다.
2. `llm_resilience`와 `rag`를 함께 켠 뒤 같은 7문장을 실행했을 때 7건 모두 성공했다 (응답 2.1~2.9초). 후보가 일치했고, 후보 밖 ID 0개, 숫자 오염 의심 0건이었다.
3. 세탁 7번 문장에서 세트 단서를 폼에 자동 입력하도록 수정했다 (`fix/set-autofill`).

`rag_live_result.md`(2번 실행의 기록) 표와 요약:

| 번호 | 업종 | 보류 | 후보 일치 | AI 선택 | 후보 밖 ID | 폼 채움 값 | 숫자 오염 의심 | 시간(초) | 오류 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 헬스장 | 아니오 | 일치: gym_terms_art8_2_def, law2_10, art4_1, art5_1, law32_1 | (없음) (기대 art4_1, 다름) | 없음 | industry=fitness, contract_type=period, total_contract_amount=1200000, paid_amount=1200000 | 없음 | 2.9 | - |
| 2 | 헬스장 | 아니오 | 일치: yoga_terms_art5_2, yoga_terms_art9_1_def, art5_2, annex_penalty, art2_2 | art5_2 (기대 art5_2, 포함) | 없음 | industry=yoga_pilates, deposit=100000 | 없음 | 2.1 | - |
| 3 | 헬스장 | 아니오 | 일치: yoga_terms_art5_2, yoga_terms_art9_1_def, annex_penalty, art2_2, gym_terms_art8_2_def | yoga_terms_art5_2 (기대 yoga_terms_art5_2, 포함) | 없음 | industry=yoga_pilates, contract_type=session | 없음 | 2.2 | - |
| 4 | 세탁 | 아니오 | 일치: laundry_5, laundry_5_1, laundry_4, laundry_3, laundry_terms_art9 | laundry_5 (기대 laundry_5, 포함) | 없음 | service_type=laundry_shop, damage_type=loss, item_key=coat, receipt_issued=False | 없음 | 2.6 | - |
| 5 | 세탁 | 아니오 | 일치: laundry_3, laundry_4, laundry_terms_art9, laundry_6, laundry_5 | laundry_3 (기대 laundry_3, 포함) | 없음 | damage_type=defect, no_issue_confirmation=True | 없음 | 2.4 | - |
| 6 | 세탁 | 아니오 | 일치: laundry_7, laundry_2, laundry_ratio_table, laundry_terms_art9, laundry_1 | laundry_7 (기대 laundry_7, 포함) | 없음 | - | 없음 | 2.1 | - |
| 7 | 세탁 | 아니오 | 기대 없음: laundry_7, laundry_1, laundry_ratio_table, laundry_2, laundry_types | laundry_7 | 없음 | damage_type=defect, item_key=mens_suit, set_type=top_bottom, set_part=top | 없음 | 2.3 | - |

요약 (`rag_live_result.md` 그대로): 호출 7건, 실패 0건, 후보 밖 ID 0개, 오염 의심 0건.
`rag_live_result.md`의 정의: 숫자 오염 의심은 후보 조항 원문에 나오는 숫자가 폼 채움 값에 있고 입력 문장에는 그 숫자가 없을 때 붙인 표시이며, 판정이 아니라 사람이 확인할 표시다.
