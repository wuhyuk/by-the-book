# 가전·전자제품 규칙 엔진 명세 초안 (사전 조사, 구현 전)

> 상태: **초안 (2026-11-02)**. 사용자 결정 전에는 구현하지 않는다. 결정이 나면 `docs/MVP_SPEC.md`에 절을 옮긴 뒤 구현한다.
> 틀은 헬스장 `MVP_SPEC.md` 5절과 같다.
> 원문: `appliance_notice.md`, 공통 근거·시행령 별표 1: `dispute_standard_common.md`, 규칙 JSON 초안: `backend/data/rules/appliance_warranty.json`, 케이스: `appliance_cases_draft.md`.
> 표시: **[원문]**, **[해석]**, **[제안]**(사용자 결정 필요), **[미결]**(`stage0_laundry_appliance_report.md` 7절).

## A0. 엔진이 하는 일과 하지 않는 일

가전 기준은 대부분 **표 조회**(상황 → 해결기준 문구)이고, 금액 계산은 "품질보증기간 경과 후" 세 상황(수리 불가, 분실, 부품 미보유)의 감가 환급 하나뿐이다 **[원문]**.

| 한다 | 하지 않는다 |
|---|---|
| 품질보증기간·부품보유기간 조회 (별표 Ⅲ, 보증서가 더 길면 보증서) | 하자가 "정상적인 사용 상태"에서 생겼는지, "중요한 수리"인지 판정 (사용자 응답을 그대로 씀) |
| 보증기간 기산일 결정 (시행령 별표 1 4.라·마) | 소비자 고의·과실 여부 판정 |
| 상황별 해결기준 문구 조회 (별표 Ⅱ ①) | 교환·환급 중 무엇을 받을지 결정 (시행령 제9조 ③: 소비자가 선택) |
| 동일 하자 2회·여러 부위 4회 수리 후 재발 → "수리 불가능으로 봄" 판정 | 수리비 견적의 적정성 |
| 보증기간 경과 후 감가 환급액 계산 | 중고품·설치업·스마트폰 기준 |

## A1. 입력 스키마 (`ApplianceInput`, 이름은 초안)

| 필드 | 타입 | 필수 | 설명·근거 |
|---|---|---|---|
| `judgment_requested` | `bool` | 필수 | 헬스장과 같음 |
| `item_key` | `str \| None` | 필수 | 별표 Ⅲ "5. 1) 완제품" 행 ID (규칙 JSON `items[].id`). 지원 품목 목록은 [미결 Q-A7] |
| `is_used_product` | `bool` | 선택 (기본 `False`) | 중고 구입 → 범위 밖 **[원문]** 별표 Ⅱ ⑫중고전자제품매매업 별도 / 처리 **[제안]** |
| `purchase_price` | `int \| None` | 금액 계산 시 필수 | 구입가 **[원문]** "구입가 환급", 시행령 별표 1 1.바 "영수증 등에 적힌 물품등의 가격" |
| `purchase_date` | `date \| None` | 조건부 필수 | 계약(구입)일 **[원문]** 시행령 별표 1 4.라 |
| `delivery_date` | `date \| None` | 선택 | 인도일. 계약일과 다르면 인도일 기준 **[원문]** 4.라 단서 |
| `exchanged_date` | `date \| None` | 선택 | 교환받은 날. 있으면 그날부터 기산 **[원문]** 4.라 |
| `sale_date_unknown` | `bool` | 선택 (기본 `False`) | 판매일자 확인 곤란 (보증서·영수증 없음 등) **[원문]** 4.마 |
| `manufacture_date` | `date \| None` | `sale_date_unknown`이면 필수 | 제조일(또는 수입통관일). "제조연월만 기재" 처리는 부품보유기간 주석에만 있다 **[원문]** 별표 Ⅲ 머리 주석 |
| `certificate_warranty_months` | `int \| None` | 선택 | 품질보증서 표시 품질보증기간. 별표 Ⅲ보다 짧거나 없으면 별표 Ⅲ **[원문]** 4.가·나 |
| `certificate_parts_years` | `int \| None` | 선택 | 품질보증서 표시 부품보유기간 (내용연수에도 쓰임, 별표 Ⅳ) |
| `situation` | `str` | 필수 | 아래 A3 표의 상황 코드 |
| `received_date` | `date \| None` | 필수 | 하자로 수리 등이 사업자에게 **접수된 날** (보증기간 경과 판단 기준) **[원문]** 비고 "수리 등이 사업자측에 접수된 날을 기준으로 판단함" / 10일·1개월 판단에도 이 날을 쓸지 [미결 Q-A5] |
| `normal_use` | `bool \| None` | 선택 | 정상적인 사용 상태였는지 (사용자 응답) |
| `major_repair` | `bool \| None` | 10일·1개월 상황이면 필수 | "중요한 수리를 요할 때"인지 (사용자 응답) [미결 Q-A8] |
| `same_defect_repairs` | `int \| None` | 선택 | 보증기간 내 동일 하자 수리 횟수 (재발 전까지) **[원문]** 비고 각주 1) |
| `multi_defect_repairs` | `int \| None` | 선택 | 보증기간 내 여러 부위 하자 수리 횟수 |
| `recurred` | `bool \| None` | 선택 | 그 뒤 하자 재발 여부 |
| `settlement_date` | `date \| None` | 감가 계산 시 필수 | 사용연수 끝 날짜 [미결 Q-A1] |
| `provider_offer` | `int \| None` | 선택 | 업체 제시 환급액 |
| `provider_position` | `str \| None` | 선택 | 업체 안내: `paid_repair`(유상수리) / `refund_offer` / `exchange_offer` / `refuse` / `None` |

입력 검증 (🔍 `INVALID_INPUT`) **[제안]**: 금액 ≤ 0, 날짜 역전(`received_date < 기산일`, `delivery_date < purchase_date`), 수리 횟수 < 0.

## A2. 범위 판정

| 순서 | 조건 | 결과 | 근거 |
|---|---|---|---|
| 1 | `judgment_requested` | ❔ `JUDGMENT_REQUESTED` | CLAUDE.md 4 |
| 2 | `item_key`가 지원 목록 밖 (스마트폰, 자동차, 사무용기기 등) | ❔ `UNSUPPORTED_ITEM` | [미결 Q-A7] |
| 3 | `is_used_product` | ❔ `USED_PRODUCT` | **[원문]** 중고는 ⑫ 별도 기준 |
| 4 | `situation`이 A3 표 밖 (설치업체 하자, 신체 피해 등) | ❔ `UNSUPPORTED_SITUATION` | **[원문]** ⑭가전제품설치업 별도 |
| 5 | `normal_use = False` | ❔ `NOT_NORMAL_USE` (안) | **[원문]** 1)~3)은 모두 "정상적인 사용 상태"가 조건, 시행령 별표 1 1.가 단서 / 소비자 과실이 다툼이면 판정하지 않는다 [제안]. 단, 5) 부품 미보유의 "소비자의 고의·과실로 인한 고장인 경우"는 원문에 해결기준이 있으므로 막지 않는다 |
| 6 | 필수 누락 | 🔍 `MISSING_REQUIRED` | |
| 7 | 입력 검증 실패 | 🔍 `INVALID_INPUT` | |
| 8 | 감가 계산 상황인데 `settlement_date`가 부품보유기간(내용연수) 밖 | 🔍 `OUTSIDE_PARTS_PERIOD` (계산 안 함) | **[원문]** 각주 2) "부품보유기간(내용년수)에 한정하여 적용" / 처리 [미결 Q-A6] |

## A3. 상황 코드와 해결기준 조회 (별표 Ⅱ ①)

| `situation` | 원문 분쟁유형 | 기간 조건 | 해결기준 (원문 문구) | 계산 |
|---|---|---|---|---|
| `major_defect_10d` | 1) | 기산일부터 10일 이내 | 제품교환 또는 구입가 환급 | 조회 |
| `major_defect_1m` | 2) | 1개월 이내 | 제품교환 또는 무상수리 | 조회 |
| `defect` | 3) 하자발생 시 | 품질보증기간 이내 | 무상수리 | 조회 |
| `repair_impossible` | 3) 수리불가능 시 | 이내 / 경과 후 | 제품교환 또는 구입가 환급 / 정액 감가상각한 금액에 10%를 가산하여 환급 | 이내 조회 / **경과 후 계산** |
| `exchange_impossible` | 3) 교환불가능 시 | 이내 | 구입가 환급 | 조회 (금액 = 구입가) |
| `exchanged_unit_major_repair_1m` | 3) 교환된 제품이 1개월 이내에 중요한 수리 | 이내 | 구입가 환급 | 조회 |
| `lost_by_business` | 4) | 이내 / 경과 후 | 제품교환 또는 구입가 환급 / 정액 감가상각한 금액에 10%를 가산하여 환급 (한도：구입가격) | 이내 조회 / **경과 후 계산** |
| `no_parts` | 5) | 이내(정상 사용) / 이내(고의·과실) / 경과 후 | 제품교환 또는 구입가 환급 / 유상수리에 해당하는 금액 징수 후 제품교환 / 정액 감가 상각한 잔여 금액에 구입가의 10%를 가산하여 환급 | 이내 조회 / **경과 후 계산** |
| `transport_damage` | 6) | 없음 | 제품교환 (단서 포함) | 조회 |
| `installation_damage` | 7) | 없음 | 제품교환 | 조회 |
| `repair_delay_1m` | 시행령 별표 1 1.나 | 의뢰일부터 1개월 지나도 미인도 | 이내: 같은 종류로 교환 또는 환급 / 경과 후: 정액 감가상각하고 남은 금액에 품목별 기준의 일정금액을 더하여 환급 | 이내 조회 / 경과 후 계산 (일정금액 = ① 3)의 10%로 볼지 [미결 Q-A2에 포함]) |

- 상황 순서: 10일 → 1개월 → 품질보증기간. 10일 안이면 1)이 2)·3)보다 먼저 걸리는지 원문에 우선순위가 없다. 시행령 제9조 ③("두 가지 이상 정하고 있는 경우에는 소비자가 선택")에 따라 걸리는 기준을 **모두** 보여 준다 [해석].
- "수리 불가능으로 봄": `same_defect_repairs ≥ 2`이고 `recurred`, 또는 `multi_defect_repairs ≥ 4`이고 `recurred`이면 `repair_impossible`로 바꾼다 **[원문]** 각주 1). "여러 부위 하자에 대해 4회까지"의 횟수 합산 방식(부위별인지 전체인지)은 [해석: 전체 합산] → 확인 필요 [미결 Q-A8에 포함].
- 리퍼부품 1년 재발 무상수리, 핵심부품 품질보증기간(별표 Ⅲ 2))은 2차 확장 후보로 남긴다 [제안].

## A4. 기간 계산

```text
[기산일]
start = exchanged_date            if 있음                       ← 4.라 "교환받은 날부터"
      = manufacture_date + 3월    if sale_date_unknown          ← 4.마 "3월이 지난 날부터"
      = delivery_date             if 있고 purchase_date와 다름   ← 4.라 단서
      = purchase_date

[품질보증기간]  warranty_months = max(certificate_warranty_months, table_warranty_months)   ← 4.가·나
[만료일]        warranty_end = start + warranty_months (달력 월)            [미결 Q-A5]
[판단]          within = received_date ≤ warranty_end (경계 처리 [미결 Q-A5])
[10일·1개월]    within_10d = received_date − start ≤ 10 (또는 < 10, 첫날 산입 여부 [미결 Q-A5])
```

- 경계 해석 후보끼리 결과가 같으면 그대로 확정, 다르면 두 결과(해결기준 문구)를 함께 보여 주고 🔍 `PERIOD_BOUNDARY` [제안].

## A5. 감가 환급 계산 (보증기간 경과 후 3)·4)·5))

```text
[내용연수]  life_years = max(certificate_parts_years, table_parts_years)     ← 별표 Ⅳ 병합 칸 + 별표 Ⅲ
            life_months = life_years × 12                                   [해석, Q-A3]
[사용연수]  used_months = months_between(start, settlement_date)            [미결 Q-A1: 시작·끝·1개월 미만]
[감가상각비]  dep = purchase_price × used_months ÷ life_months              ← 원문 비고 "(사용연수/내용연수)×구입가"
[잔여금]     resid = purchase_price − dep                                   ← 원문 비고 "구입가-감가상각비"

[환급액 후보]
3) 수리 불가 / 4) 분실:  "정액 감가상각한 금액에 10%를 가산"               [미결 Q-A2]
   후보 X: resid + purchase_price × 10%     (5)의 명시 문구와 같은 구조)
   후보 Y: resid × 110%
   4)만:   min(후보, purchase_price)        ← 원문 "(한도：구입가격)"
5) 부품 미보유:  resid + purchase_price × 10%                                ← 원문 명시
원 미만: [미결 Q-C1]
```

| 항목 | 내용 | 표시 |
|---|---|---|
| 감가 방법 | 정액법, 월할계산 | [원문] |
| 감가상각비·잔여금 식 | 원문 비고 그대로 | [원문] |
| 내용연수 | 별표 Ⅳ: 보증서 부품보유기간, 별표 Ⅲ보다 짧거나 없으면 별표 Ⅲ | [원문] / 년→월 환산 [해석] |
| 사용연수 시작·끝·1개월 미만 | 원문에 없음 | [미결 Q-A1] |
| 10% 가산 대상 | 3)·4) 문구 불명확, 5) 명시 | [미결 Q-A2] |
| 한도 | 4)에만 "(한도：구입가격)" | [원문] / 3)·5)에도 적용할지 원문에 없음 → 후보 X는 사용 개월이 내용연수의 10% 미만일 때만 구입가를 넘는다 [기계 확인: resid + 0.1P > P ⇔ used/life < 0.1] |
| 부품보유기간 한정 | 3) 경과 후 수리 불가에 각주 2) | [원문] / 4)·5)에도 적용할지 [미결 Q-A6] |

## A6. 배지 결정

결정 순서는 헬스장과 같다. 블록 단위 검증: 결과가 쓰는 블록은 `items`(별표 Ⅲ), `resolution_table`(별표 Ⅱ ①), `general_rules`(시행령 별표 1 4.), 감가 계산이면 `depreciation`·`lifespan_rule`(별표 Ⅳ). 초안은 모두 `false`.

강건한 ⚠️ 후보:

| 코드 | 조건 | 해석과 무관한 이유 |
|---|---|---|
| `PAID_REPAIR_IN_WARRANTY` | `provider_position = paid_repair`, `situation = defect`, `normal_use = True`, 모든 기간 해석 후보에서 보증기간 이내 | 원문 3) "무상수리"와 시행령 별표 1 1.가 "사업자가 부담"이 기간 해석과 무관하게 성립 |
| `OFFER_BELOW_STANDARD_MIN` | `provider_offer` < 감가 환급 후보(X·Y × 사용연수 후보 × 반올림) 최솟값 | 세탁과 같은 방식 |

🔍 사유 (계산·조회는 함): `PERIOD_BOUNDARY`(기간 해석에 따라 해결기준이 바뀜), `USED_MONTHS_DEPENDENT`(Q-A1 결정 전), `ADD_ON_DEPENDENT`(Q-A2 결정 전, 3)·4)), `ROUNDING_DEPENDENT`, `NORMAL_USE_UNCONFIRMED`(`normal_use is None`), `MAJOR_REPAIR_UNCONFIRMED`, `CERTIFICATE_UNKNOWN`(보증서 기간 미입력 → 별표 Ⅲ 최소 기간으로 판단, "보증서 기간이 더 길면 결과가 달라질 수 있음"), `LIFESPAN_ITEM_NOT_LISTED`(별표 Ⅳ에 없는 품목, Q-A4), `SALE_DATE_ESTIMATED`(4.마 적용), `RULE_UNVERIFIED`, `INTERPRETATION_DEPENDENT`.

✅ 조건: 위 사유가 하나도 없음. 예: 냉장고, 보증서 기간 입력, 정상 사용, 접수일이 모든 해석에서 보증기간 안 → "무상수리" 조회 결과는 ✅ 가능 (블록 검증 후).

## A7. 안내 코드 (초안)

| 코드 | 조건 | 문구 (초안) | 근거 |
|---|---|---|---|
| `CONSUMER_CHOICE` | 해결기준이 "A 또는 B" | "기준에 두 가지 방법이 있으면 소비자가 선택하는 기준에 따릅니다." | [원문] 시행령 제9조 ③ |
| `RECEIVED_DATE_BASIS` | 보증기간 판단 | "품질보증기간 안에 수리를 접수했다면, 사업자 사정으로 늦게 끝나도 접수한 날을 기준으로 판단합니다." | [원문] 비고 |
| `REPAIR_DELAY` | 수리 의뢰 후 1개월 | 시행령 별표 1 1.나 인용 | [원문] |
| `PAID_REPAIR_RECURRENCE` | 유상수리 이력 | "유상으로 수리한 날부터 2개월 안에 같은 고장이 다시 생기면 무상수리하도록 되어 있습니다." | [원문] 시행령 별표 1 1.다 |
| `DISCOUNT_EXCHANGE` | 할인 구매 + 교환 | 시행령 별표 1 1.마 인용 | [원문] |
| `SHIPPING_COST` | 사업자 귀책 | "처리 과정의 운반비용 등은 사업자가 부담하도록 되어 있습니다." | [원문] 시행령 별표 1 6. |

## A8. 출력 (`ApplianceResult`, 초안)

공통 필드(`badge`, `calculated`, `steps`, `flags`, `missing`, `notices`, `citations`) +

| 필드 | 타입 | 설명 |
|---|---|---|
| `warranty` | `{start, months, end_candidates: list[date], source: "table" \| "certificate"}` | 보증기간 |
| `period_status` | `list[str]` | 해석 후보별 `within_10d` / `within_1m` / `within_warranty` / `after_warranty` |
| `resolutions` | `list[{clause_id, text}]` | 해당 해결기준 원문 문구 (여럿이면 모두) |
| `depreciation` | `{life_months, used_months_candidates, candidates: list[{rule, amount_exact, floor, half_up}], cap} \| None` | 감가 환급 |

## A9. 인용 ID (규칙 JSON)

| 결과 요소 | 인용 ID |
|---|---|
| 해결기준 1)~7) | `elec_1` ~ `elec_7` |
| 비고 (감가 방법, 수리 불가 간주, 접수일 기준, 부품보유기간 한정, 리퍼) | `elec_note_dep`, `elec_note_fn1`, `elec_note_received`, `elec_note_fn2`, `elec_note_refurb` |
| 품질보증·부품보유기간 | `annex3_items`, `annex3_parts_start` |
| 내용연수 | `annex4` |
| 보증기간 기산·연장 | `gen_4_ga`, `gen_4_na`, `gen_4_ra`, `gen_4_ma` (related) |
| 비용 부담·수리 지연·유상수리 재발·교환·환급금액 | `gen_1_ga`, `gen_1_na`, `gen_1_da`, `gen_1_ra`, `gen_1_ma`, `gen_1_ba` (related) |
| 선택 | `cpa_dec9_3` (related) |
| 권고 기준 고지 | `cpa16_3` (related) |

## A10. 이 초안의 미결 질문

Q-A1 사용연수, Q-A2 10% 가산, Q-A3 내용연수 환산·기산, Q-A4 별표 Ⅳ에 없는 품목, Q-A5 기간 계산, Q-A6 부품보유기간 경과, Q-A7 지원 품목·상황, Q-A8 사용자 응답 항목(중요한 수리, 수리 횟수), Q-C1 원 미만, Q-S1·Q-S2.
