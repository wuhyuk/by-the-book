# MVP_SPEC — 기준대로

> 상태: **초안**. 현재 단계에 필요한 결정이 끝나기 전에는 그 단계를 구현하지 않는다. 결정이 나면 이 문서를 먼저 갱신한다.
> **현재 단계: 0 (고시 원문 확인, 미완료)**
> 완료한 단계: 1 (저장소 뼈대, 2026-10-19). 단계 0과 병행해 먼저 끝냈으며, 단계 0이 끝나기 전에는 단계 2로 넘어가지 않는다.

## 1. MVP 한 줄

헬스장 중도 해지 상황을 입력하면, 고시 기준의 환급액을 코드로 계산해 계산 과정·근거·상태 배지와 함께 보여 준다. (세탁·가전은 같은 구조에 규칙만 추가)

## 2. 왜 헬스장 하나로 시작하는가

- 계산식이 가장 단순해 "추출 → 규칙 엔진 → 근거 표시" 전체 흐름을 먼저 끝까지 연결할 수 있다.
- 세탁(배상비율표)·가전(내용연수·부품보유기간 표)은 원문 표 정리에 시간이 더 든다. 구조가 검증된 뒤에 얹는다.
- 이 순서는 결정 사항이며 바꾸려면 아래 9절에서 변경한다.

## 3. 범위

**포함**: 자유 문장 입력, 정보 추출(LLM, JSON 스키마), 헬스장 환급 계산(규칙 엔진), 근거 카드(조항 원문·출처·기준일), 상태 배지 4종, 판단 가드레일, 업체용 요약 문안, 결과 화면.
**제외**: 로그인, 사진·영수증 입력, 법률 문서 생성, 세탁·가전(MVP 이후), 데이터 저장.

## 4. 규칙 데이터 형식 (`backend/data/rules/gym_refund.json`)

```json
{
  "id": "gym_refund",
  "title": "체육시설업 중도 해지 환급",
  "source": {
    "name": "계속거래 등의 해지·해제에 따른 위약금 및 대금의 환급에 관한 산정기준",
    "notice_number": "공정거래위원회고시 제2019-9호",
    "url": "https://www.law.go.kr/행정규칙/계속거래등의해지·해제에따른위약금및대금의환급에관한산정기준",
    "effective_date": "2019-11-19",
    "last_amended": "2019-11-19",
    "retrieved_at": "2026-10-26"
  },
  "verified": false,
  "industries": [
    {
      "id": "fitness",
      "name": "헬스·피트니스업",
      "scope_basis": "제3조 ① 3호",
      "penalty_rule": {
        "type": "ratio_of_total",
        "ratio": 0.10,
        "applies_as": "upper_limit",
        "basis": "별표 위약금 기준 (상한: 제4조 ①)",
        "verified": true,
        "verification": { "method": "공식 HWP 텍스트 추출 ↔ 법제처 별표 이미지 판독 일치", "user_checked": false, "checked_at": "2026-10-26" }
      }
    }
  ],
  "params": {
    "unit_price_method": null,
    "list_price_deduction_allowed": null,
    "rounding": { "used_amount": "half_up_won", "penalty": "floor_won", "in_source": false },
    "day_count": { "contract_days": "end_date - start_date + 1", "in_source": false },
    "refund_basis": { "fitness": "contract_type", "yoga_pilates": "agreed", "in_source": false },
    "continuous_transaction_criteria": { "text": "법 제2조 제10호 원문", "verified": true }
  },
  "scenarios": {
    "A": { "name": "실제 부담액 기준", "used_amount_base": "total_contract_amount", "in_source": false },
    "B": { "name": "정상가 기준", "used_amount_base": "list_price", "in_source": false }
  },
  "notes": ["원문에 없는 값과 그 근거"],
  "clauses": [
    { "id": "art5_1", "label": "제5조 ①", "text": "고시 원문 그대로" }
  ],
  "related_clauses": [
    { "id": "law32_1", "label": "방문판매법 제32조 ①", "source": { "name": "…", "url": "…", "retrieved_at": "…" }, "text": "원문 그대로" }
  ]
}
```

위는 구조 예시다. 실제 파일에는 업종 2행(`fitness`, `yoga_pilates`), `params`의 나머지 키, 고시 조문 10개(`clauses`), 고시 밖 원문 5개(`related_clauses`)가 있다.

- `source`: 출처 이름·고시번호·URL·시행일·최근 개정일·확인일. 확인하지 못한 값은 `null`.
- `verified`(최상위): 파일 전체가 원문으로 확정되었는지. 단위대금 산정 방식이 미확정이므로 `false`.
- 블록별 `verified`: 그 블록의 값만 원문과 대조했는지. 배지는 블록 단위로 판정한다: 강건한 `⚠️`와 `✅`는 결과가 쓰는 블록(`penalty_rule`, `continuous_transaction_criteria`)이 모두 `true`일 때만 켠다 (5.4, CLAUDE.md 절대 규칙 2).
- `verification`: 블록을 어떻게 확인했는지 (`method`, `user_checked`, `checked_at`). 사용자가 직접 대조하지 않았으면 `user_checked: false`.
- `industries[].penalty_rule.applies_as`: `"upper_limit"`이면 별표 금액은 상한이다 (제4조 ①).
- `params`의 `null`은 "원문에 없음 또는 미확정"이다. 추측으로 채우지 않는다. 원문에 없는 프로젝트 결정(반올림 등)은 `"in_source": false`로 표시한다.
- `scenarios`: 이용분 계산 시나리오 A·B (5.3). 둘 다 원문에 없는 해석이다.
- `related_clauses[]`: 고시 밖 원문(방문판매법, 표준약관). 각 항목에 `source`가 있다.
- `clauses[]`: 근거 카드와 인용 검증(절대 규칙 7)에 쓰는 조문 원문. `id`가 인용 ID다.

값은 모두 원문 확인 후 채운다. `retrieved_at`은 `source` 안에 둔다. 결과가 쓰는 블록이 `verified=false`이면 계산은 하되 결과 배지는 `✅ 기준 확인`이 될 수 없다 (아래 배지 결정 순서 4번).

MVP(품목 1개)에서는 조항 검색 없이 품목 ID(`gym_refund`)로 이 파일을 직접 조회한다. 업종 필터 + 키워드 → 임베딩 검색은 품목이 2개 이상이 되는 단계 7에서 도입한다.

### 배지 결정 순서

위에서부터 판정하며 먼저 걸리는 것이 이긴다.

1. 판단 불가 조건(승패·법적 효력 질문, 5.2의 범위 밖)이면 `❔ 판단 불가`
2. 필수 정보가 누락되었으면 `🔍 추가 확인 필요` (계산하지 않음). 입력 오류, 횟수 기준의 유효기간 이후 도달(5.2 순서 11)도 여기에 든다
3. 강건한 주의 신호(5.4)가 있으면 `⚠️ 주의 신호`
4. 해석 의존 계산이거나 규칙 값이 `verified=false`이면 `🔍 추가 확인 필요`
5. 그 외에는 `✅ 기준 확인`

## 5. 규칙 엔진 계약 (`backend/rules/`)

> 이 절이 단계 2 구현의 **단일 기준 문서**다. 다른 문서와 다르면 이 절을 먼저 고친 뒤 구현한다.
> 근거 원문: 고시 `docs/sources/gym_penalty_notice.md`, 조문 정리 `gym_penalty_review.md`, 계속거래 `continuous_transaction_definition.md`, 표준약관 `gym_standard_terms.md`(요가·필라테스 표준약관은 같은 파일 부록), 관련 법 `related_laws.md`.
> 표시: **[원문]** 원문 확인, **[해석]** 원문에 근거한 해석, **[결정]** 원문에 없는 프로젝트 결정(사용자 승인, 날짜 표기), **[미결]** 아직 정하지 않음.

### 5.1 입력 스키마 (`GymInput`)

필드명은 단계 2에서 확정한다. 아래 이름으로 구현하고, 바꾸려면 이 표를 먼저 고친다.

| 필드 | 타입 | 필수 | 설명·근거 |
|---|---|---|---|
| `judgment_requested` | `bool` | 필수 | 승패·법적 효력 질문 여부. 단계 4 API가 정해 넘긴다 [결정 2026-10-26 #8] |
| `industry` | `str` | 필수 | `fitness` / `yoga_pilates` / 그 외 문자열. 체력단련장 외 시설(수영장, 골프연습장 등)은 그 외로 넘긴다 [원문] 고시 제3조 ① 3호 |
| `academy_law_applies` | `bool` | 선택 (기본 `False`) | 학원법 시행령 제18조 적용 여부 [원문] 고시 제3조 ① 단서 |
| `is_withdrawal` | `bool` | 선택 (기본 `False`) | 청약철회로 해지하는지 [원문] 고시 제3조 ② |
| `withdrawal_cleared` | `bool \| None` | 선택 | "청약철회 대상이 아니거나 기간이 지났음을 확인"했는지 (확인 항목 하나). `True`가 아니면 ✅ 불가 [결정 2026-10-26 보충 2, 질문 답 2]. 항목 옆 풀이: "계약서 수령일부터 7일·14일이 지났거나, 권유 없이 직접 매장을 찾아가 일시불로 계약한 경우 (법적 판정이 아닌 참고 풀이입니다). 전화·길거리 권유나 무료 체험 안내를 받고 방문해 계약했다면 1372에 확인해 주세요." [결정 2026-10-26 Q1, 후속 Q1]. 전화 권유 뒤 매장 계약이 청약철회 대상인지는 [미결] (5.2 미결) |
| `termination_cause` | `str` | 필수 | `consumer` / `business` / `force_majeure` / `unknown` |
| `contract_type` | `str` | 필수 | `period`(기간제) / `session`(횟수제) [원문] 고시 제2조 3호 "1월, 1일, 1회 또는 1시간 등" |
| `refund_basis` | `str \| None` | 요가·필라테스 필수 | `period` / `session` / `unknown`. 요가·필라테스만 쓴다. 헬스·피트니스는 입력과 상관없이 `contract_type`을 쓴다 [원문] 요가·필라테스 표준약관 제9조 ①, 체력단련장 표준약관에는 선택 규정 없음 [결정 2026-10-26 #4] |
| `total_contract_amount` | `int` | 필수 | 총계약대금. 가입비·입회금 포함, 보증금 제외 [원문] 고시 제2조 2호. 가입비 별도 필드 없음 |
| `paid_amount` | `int` | 필수 | 지급한 계약대금 [원문] 고시 제5조 ① |
| `start_date` | `date \| None` | 기간 기준이면 필수 | 이용 기간 시작일. 횟수제는 유효기간 시작일 [결정 2026-10-26 결정 9] |
| `end_date` | `date \| None` | 기간 기준이면 필수 | 이용 기간 종료일. 연기가 있었으면 **연장된 종료일**. 횟수제는 유효기간 종료일 |
| `notice_date` | `date \| None` | 기간 기준이면 필수. 횟수 기준은 `end_date`(유효기간 종료일)가 있으면 필수, 없으면 필수 아님(`SESSION_VALIDITY_MISSING`) [결정 2026-10-26 후속 Q3] | 해지 의사표시가 사업자에게 도달한 날 [원문] 고시 제5조 ① |
| `total_sessions` | `int \| None` | 횟수 기준이면 필수 | 계약상 총 횟수 |
| `used_sessions` | `int \| None` | 횟수 기준이면 필수 | 도달일까지 이용한 횟수. 요가·필라테스 표준약관을 쓴 계약이면 받지 않은 보강수업도 이용 횟수에 넣는다 [원문] 요가·필라테스 표준약관 제9조 ② |
| `add_on_value` | `int` | 선택 (기본 0) | 부가상품 가액 [원문] 고시 제5조 ① |
| `add_on_returned` | `bool` | 선택 (기본 `False`) | 부가상품 반환 여부 [원문] 고시 제6조 ① |
| `returned_add_on_value` | `int` | 반환 시 필수 | 반환한 부가상품등의 가치 상당액 (계약서 기재 금액 등, 사용자 입력) |
| `deposit` | `int` | 선택 (기본 0) | 보증금 [원문] 고시 제5조 ② |
| `has_refund_limit_clause` | `bool \| None` | 선택 | 중도 해지 시 환급 제한·위약금 약정 유무 [원문] 법 제2조 제10호 |
| `list_price` | `int \| None` | 선택 | 정상가: 같은 계약의 정상가 총액(할인·프로모션 적용 전, 같은 기간·같은 이용권 기준) [결정 2026-10-26 #3, #5 선택 입력] |
| `contract_penalty` | `int \| None` | 선택 | 계약서상 위약금 |
| `provider_offer` | `int \| None` | 선택 | 사업자 제시액 |
| `had_postponement` | `bool \| None` | 선택 | 이용 연기(일시정지) 여부 [원문] 체력단련장 표준약관 제7조, 요가·필라테스 표준약관 제8조. 경과 일수 반영 방식은 원문에 없음 [결정 2026-10-26 #8] |
| `is_pt_only` | `bool \| None` | 선택 (기본 `None`) | PT(퍼스널 트레이닝)만 계약했는지. 헬스·피트니스 + 횟수제일 때 입력 단계에서 묻는다 (5.5 `PT_ONLY_QUESTION`, 예 → `True` / 아니오 → `False` / 모름 → `None`). `True`이면 헬스·피트니스 규칙으로 계산하고 `SCOPE_UNCERTAIN_PT_ONLY`(🔍)를 붙인다 [결정 2026-10-26 질문 답 4, Q3] |

필수 판정에 쓰는 "환급 기준(`basis`)": 헬스·피트니스는 `contract_type`, 요가·필라테스는 `refund_basis`(없으면 `unknown`). `unknown`이면 기간 기준과 횟수 기준 입력을 모두 요구한다.

입력 검증 (실패하면 `🔍` 계산 안 함, `INVALID_INPUT`): 금액이 음수, `total_contract_amount` ≤ 0, `paid_amount` > `total_contract_amount`, `end_date` < `start_date`, `total_sessions` ≤ 0, `used_sessions`가 0 미만이거나 `total_sessions` 초과.

### 5.2 범위 판정

위에서부터 판정하며 먼저 걸리는 것이 이긴다. ❔이면 계산하지 않고 상담 창구(1372, 한국소비자원 피해구제, 대한법률구조공단 ☎132)를 안내한다.

| 순서 | 조건 | 결과 | 근거 |
|---|---|---|---|
| 1 | `judgment_requested` | ❔ `JUDGMENT_REQUESTED` | CLAUDE.md 절대 규칙 4 |
| 2 | `industry`가 `fitness`·`yoga_pilates`가 아님 (미용업, 이러닝, 학습지, 결혼중개, 체력단련장 외 시설 포함) | ❔ `UNSUPPORTED_INDUSTRY` | [원문] 고시 제3조 ①, MVP 범위 |
| 3 | `academy_law_applies` | ❔ `ACADEMY_LAW` | [원문] 고시 제3조 ① 단서 |
| 4 | `is_withdrawal` | ❔ `WITHDRAWAL` + 청약철회 안내 문구 (아래) | [원문] 고시 제3조 ② |
| 5 | `termination_cause = business` | ❔ `BUSINESS_FAULT` | [원문] 고시 제4조 ① |
| 6 | `termination_cause = force_majeure` | ❔ `FORCE_MAJEURE` (확장 후보) | [원문] 체력단련장 표준약관 제11조, 요가·필라테스 표준약관 제11조 |
| 7 | 계약 일수 < 28 (날짜가 있을 때) | ❔ `PERIOD_UNDER_28_DAYS` | [원문] 법 제2조 제10호 "1개월 이상", 경계값은 [결정 2026-10-26 #2] |
| 8 | `has_refund_limit_clause = False` | ❔ `NO_REFUND_LIMIT_CLAUSE` | [원문] 법 제2조 제10호 |
| 9 | 필수 입력 누락, `termination_cause = unknown` | 🔍 `MISSING_REQUIRED` (계산 안 함) | 배지 순서 2 |
| 10 | 입력 검증 실패 | 🔍 `INVALID_INPUT` (계산 안 함) | 배지 순서 2 |
| 11 | 횟수 기준을 계산해야 하고(`basis`가 `session` 또는 `unknown`) `notice_date` > `end_date`(유효기간 종료일) | 🔍 `NOTICE_AFTER_VALIDITY` (계산 안 함, 기준 전체) + 상담 창구 안내 | 배지 순서 2 [결정 2026-10-26 질문 답 3, Q2] |

유효기간 이후 도달 (순서 11) [결정 2026-10-26 질문 답 3, Q2]:

- 횟수 기준 계산에만 적용한다. 기간 기준은 지금대로 경과 일수를 계약 일수로 제한해 계산한다 (케이스 X1, 0원).
- 도달일이 유효기간 종료일과 같은 날이면 계산한다 (`notice_date = end_date` → 통과, 케이스 V3).
- 요가·필라테스 `refund_basis = unknown`이면 기간 기준도 계산하지 않는다 (결과 전체 계산 안 함, 케이스 V4).
- 계산하지 않고 5.2 머리말의 상담 창구(1372, 한국소비자원 피해구제, 대한법률구조공단 ☎132)를 안내한다.
- 요가·필라테스는 아래 원문을 근거로 인용한다 (`yoga_terms_art5_2`). 평가 문구(소멸이 정당한지 등)는 붙이지 않는다. 헬스·피트니스는 해당 원문이 없어 인용하지 않는다.

  > 요가ㆍ필라테스 표준약관 (표준약관 제10083호, 2026. 7. 16. 제정) 제5조(사업자의 서비스 제공) ② 등록기간이 만료되면 아직 수강하지 않은 수업횟수는 모두 소멸하며, 회원은 이에 대해 환불이나 보강을 요청할 수 없습니다.

  원문 재확인 (2026-10-26): 공정위 첨부 hwpx(`atchmnflNo=54236`)를 다시 내려받아 `Contents/section0.xml` 본문에서 조 제목 "제5조(사업자의 서비스 제공)"와 항 번호 "②", 문장을 글자 단위로 대조했다. `gym_standard_terms.md` 부록의 옮김과 같다. 같은 조 ③(재등록 시 잔여 횟수 소멸, 사업자 허용 시 이월)은 인용하지 않는다.

계약 일수 판정 (`contract_days = end_date − start_date + 1`):

| 계약 일수 | 판정 |
|---|---|
| 27 이하 | ❔ (순서 7) |
| 28~31 | 🔍 `PERIOD_28_TO_31_DAYS` (계산은 함) |
| 32 이상 | 통과 |
| 날짜 없음 (횟수제 유효기간 미입력) | 🔍 `SESSION_VALIDITY_MISSING` (계산은 함) |

- 28·31·32일 경계는 [결정 2026-10-19·2026-10-26 유지]. 민법 제160조 역 계산은 쓰지 않는다 (`related_laws.md`).
- 1372 답변 1은 "1개월 이상의 헬스장 이용계약은 … 계속거래"라고 안내했다. 원문은 약정 요건(③)이 더 있어 더 엄격하다. 엔진은 원문을 따른다.
- 시행령 제37조(10만원·3개월)는 계속거래 정의가 아니다. 쓰지 않는다.

청약철회 ❔ 안내 문구 (`WITHDRAWAL`): "계약서를 받은 뒤 짧은 기간(방문판매·전화권유판매는 14일, 할부계약·통신판매는 7일 등) 안에 청약을 철회하는 경우에는 이 기준(고시)이 적용되지 않습니다 (고시 제3조 ②). 철회 가능 여부는 1372에 문의해 주세요." [원문] 기간은 방문판매법 제8조 ①, 할부거래법 제8조 ①, 전자상거래법 제17조 ①

미결:
- [미결] 고시 제3조 ① 3호의 "체육시설법…에 해당하는"이 요가·필라테스업에도 걸리는지. 참고 원문: 소비자분쟁해결기준 별표 Ⅱ 비고 "요가․필라테스업은 체육시설업법상 체육시설업에는 포함되지 않음" (`related_laws.md`). 해석이 정해지기 전에는 요가·필라테스업의 시설 요건을 판정 조건으로 쓰지 않는다.
- [미결] 전화 권유를 받고 매장에서 계약한 경우가 전화권유판매(방문판매법 제2조 3호, 장소를 정하지 않음)로 청약철회 대상인지. 풀이 문구는 이 경우를 "1372에 확인"으로 안내만 하고 판단하지 않는다. 방문 권유 뒤 매장 계약은 제2조 1호 괄호와 시행규칙 제3조에 따라 방문판매에 들어갈 수 있어, 풀이에서 "권유 없이 직접 찾아간 경우"로 좁혔다 [결정 2026-10-26 후속 Q1]. 원문 `related_laws.md`.

해결한 질문 (2026-10-26 사용자 답):
- 계약일 기준 14일 규칙은 만들지 않는다. 청약철회 기간을 확인하지 못하면 🔍(`WITHDRAWAL_STATUS_UNCONFIRMED`)를 유지한다.
- 청약철회권이 없는 계약: "청약철회 대상이 아니거나 기간이 지났음"을 하나의 확인 항목(`withdrawal_cleared`)으로 받는다 (5.1).
- 유효기간이 지난 뒤 남은 횟수: 순서 11.
- PT 단독 계약: 헬스·피트니스 규칙으로 계산하고 🔍 `SCOPE_UNCERTAIN_PT_ONLY` (5.1 `is_pt_only`, 5.4).
- 방문판매법 제2조 제10호: `related_clauses`에 `law2_10`으로 넣는다 (5.7).
- 후속 (2026-10-26): 시작 전 해지는 `NO_LIST_PRICE`를 표시하지 않는다 (5.3). 횟수 기준에서 유효기간 종료일이 있으면 `notice_date` 필수 (5.1). `USAGE_STARTED`로 이름 변경 (5.4 이름 변경 기록).

표현 가드레일 (범위 판정·설명 공통):

- "무효", "효력이 없다", "위법" 같은 법적 효력 판단 표현을 화면 문구로 쓰지 않는다. 법 조문은 출처와 함께 원문을 인용만 한다.
- 1372 답변 1의 "무효로 볼 수 있으며" 같은 문장도 화면에 옮기지 않는다.

### 5.3 계산식

```text
[기준 단위]
기간 기준: elapsed = clamp(notice_date − start_date + 1, 0, contract_days), units = contract_days
횟수 기준: elapsed = used_sessions, units = total_sessions
(요가·필라테스 refund_basis = unknown이면 두 기준을 모두 계산)

[이용분]  (시나리오별, 원 단위 half up, 곱셈 먼저·한 번만 반올림)
used_A = round_half_up(total_contract_amount × elapsed ÷ units)
used_B = round_half_up(list_price × elapsed ÷ units)          ← list_price ≥ total_contract_amount일 때만

[위약금]  (두 시나리오 공통, 총계약대금 기준)
cap      = floor(total_contract_amount × ratio)               ← ratio = Decimal("0.10"), 원 미만 내림
penalty  = contract_penalty             (contract_penalty ≤ cap → refund_kind = computed)
         = cap                          (contract_penalty > cap 또는 없음 → refund_kind = minimum, "최소 환급액")

[환급액]
raw_X    = paid_amount − used_X − add_on_value − penalty + (add_on_returned ? returned_add_on_value : 0)
refund_X = max(raw_X, 0)                                       ← 음수면 0 + 안내
deposit_refund = deposit                                       ← 별도 약정 없으면 전액, 환급액과 따로 표시
```

| 항목 | 내용 | 표시 |
|---|---|---|
| 공제 구조 | 지급한 계약대금 − 공급받은 단위의 단위대금 − 부가상품 가액 − 위약금 | [원문] 고시 제5조 ① |
| 미이용 간주 | 기한 도래로 이용할 수 있었던 기간은 공급된 것으로 본다 → 기간 기준은 날짜로 계산 | [원문] 고시 제5조 ① 후단 |
| 위약금 상한 | 별표 금액(총계약대금의 10%)을 초과하지 못한다 | [원문] 고시 제4조 ①, 별표 |
| 결과 표시 (`refund_kind`) | 공제한 위약금이 상한이면 "최소 환급액"(계약서상 위약금이 없거나 상한보다 큰 경우), 계약서상 위약금을 그대로 공제했으면 "환급액" | [결정 2026-10-26 추가 수정 1] |
| 단위대금 산정 | 원문에 없음. 시나리오 A(총계약대금 기준)·B(정상가 기준)를 함께 계산 | [미결] `unit_price_method: null` |
| 기간 기준 일수 | 시작일·도달일 모두 산입. 도달일이 시작일보다 이르면 0, 계약 일수를 넘으면 계약 일수 | [결정 2026-10-26 #1, 보충 1] |
| 기간을 일수로 계산 | 표준약관 계산식 "이용료 × 이미 경과한 기간(일수) ÷ 계약상 이용기간(일수)" | [원문] 표준약관 제10048호 제8조 ②, 제10083호 제9조 ① / 고시 적용은 [결정 2026-10-26 결정 9] |
| 부가상품 반환 | 환급금에 더하는 방식 (원문은 위약금 감액도 허용) | [원문] 고시 제6조 ① / 방식 선택은 [결정] |
| 보증금 | 별도 약정이 없으면 전액 환급 | [원문] 고시 제5조 ② |

반올림 [결정 2026-10-26 #1]:
- 이용분: 원 단위 half up. `Fraction` 정수 연산으로 `total × elapsed`를 먼저 곱하고 `units`로 한 번 나눈 뒤 반올림한다. 계산 과정에 "원 단위 반올림(고시에 규정 없음)"을 표시한다.
- 위약금 상한: `Decimal(total) × Decimal("0.10")`을 원 미만 내림 (`ROUND_FLOOR`). 계산 과정에 "원 미만 내림(고시에 규정 없음)"을 표시한다.
- 금액은 `int`, 비율은 `Decimal`. `float` 금지. 규칙 JSON은 `json.loads(parse_float=Decimal)`로 읽는다.

시나리오 B 처리:

| `list_price` | 처리 |
|---|---|
| 없음 | A만 계산. 안내 `NO_LIST_PRICE`: "업체가 정상가(할인 전 가격) 기준으로 이용분을 계산하면 환급액이 이보다 적을 수 있습니다." (반드시 표시). ✅ 불가 [결정 2026-10-26 보충 5]. 단, 시작 전 해지(`notice_date < start_date`이고 모든 기준의 이용분 0)이면 ✅ 판정에 정상가를 요구하지 않는다 [결정 2026-10-26 추가 수정 2]. 이때는 `NO_LIST_PRICE`도 표시하지 않는다 (이용분이 0이면 정상가 기준으로도 금액이 같다) [결정 2026-10-26 후속 Q2] |
| < 총계약대금 | B 계산·판정 생략. flag `LIST_PRICE_BELOW_TOTAL`: "정상가를 다시 확인해 주세요." ✅ 불가 [결정 2026-10-26 #2] |
| ≥ 총계약대금 | A·B 모두 계산 |

결과 묶음 표시 (`refund_basis = unknown`): 기준별로 묶어 "일수 기준: A … / B …", "횟수 기준: A … / B …"로 보여 준다. 숫자를 한 줄에 나열하지 않는다 [결정 2026-10-26 보충 6].

계산 과정(`steps`) 고정 줄:
1. 첫 줄 (항상): "고시에는 단위대금 산정 방식이 정해져 있지 않아, 실제 부담액 기준(A)과 정상가 기준(B)으로 나누어 계산했습니다." 경과가 0이어도 표시한다.
2. 이용분 줄: 계산식과 "원 단위 반올림(고시에 규정 없음)"
3. 위약금 줄: 상한 계산식과 "원 미만 내림(고시에 규정 없음)"

### 5.4 배지 결정

결정 순서 (4절과 같음, 먼저 걸리는 것이 이긴다): ❔ → 🔍(필수 정보 누락·입력 오류·유효기간 이후 도달, 계산 안 함) → ⚠️(강건) → 🔍(해석 의존·미검증·확인 필요) → ✅.

블록 단위 검증: 강건한 ⚠️와 ✅는 결과가 쓰는 블록 `industries[].penalty_rule`, `params.continuous_transaction_criteria`가 모두 `verified: true`일 때만 켠다. 최상위 `verified`(현재 `false`)는 배지 판정에 쓰지 않는다. 블록이 `false`이면 `RULE_UNVERIFIED`(🔍)가 붙는다.

강건한 ⚠️ (해석과 무관하게 성립하는 신호만):

| 코드 | 조건 | 해석과 무관한 이유 | 화면 한 줄 |
|---|---|---|---|
| `OFFER_BELOW_B` | `provider_offer` < 시나리오 B 환급액의 최솟값 (기준이 여럿이면 그중 최소). B가 없으면 판정하지 않음 | B(정상가 기준)는 두 해석 중 환급액을 가장 작게 잡는다 (정상가 ≥ 총계약대금일 때만 성립). 위약금도 상한을 썼으므로 실제 위약금이 낮으면 환급액은 더 커진다. 일수를 양끝 산입하면 경과 일수가 가장 길게 잡혀 환급액이 가장 작다 [해석] | "업체 제시액이 정상가 기준으로 계산한 기준 금액보다도 적습니다." |
| `PENALTY_ABOVE_CAP` | `contract_penalty` > 상한(총계약대금 × 0.10) | 이용분 계산을 쓰지 않는다 [원문] 고시 제4조 ① | "계약서상 위약금이 고시의 위약금 상한(총계약대금의 10%)보다 큽니다. 계산에는 상한을 공제했습니다." |

🔍 사유 (계산은 함, 하나라도 있으면 ✅ 불가). 화면 한 줄 문구는 초안이며 사용자 검토 대상이다:

| 코드 | 짧은 이름 | 조건 | 화면 한 줄 |
|---|---|---|---|
| `SCOPE_UNCERTAIN_PT_ONLY` | 범위 불확실 (PT 단독) | `is_pt_only = True` | "PT만 계약한 경우 이 기준이 적용되는지 확실하지 않아, 헬스·피트니스 기준으로 계산했습니다." |
| `PERIOD_28_TO_31_DAYS` | 1개월 경계 구간 | 계약 일수 28~31 | "계약 기간이 1개월 경계(28~31일)에 있어 이 기준이 적용되는지 확인이 필요합니다." |
| `REFUND_LIMIT_CLAUSE_UNKNOWN` | 약정 미확인 | `has_refund_limit_clause is None` | "계약서에 중도 해지 시 환급 제한이나 위약금 조항이 있는지 확인이 필요합니다." |
| `WITHDRAWAL_STATUS_UNCONFIRMED` | 청약철회 미확인 | `withdrawal_cleared`가 `True`가 아님 | "청약철회 대상이 아니거나 철회 기간이 지났는지 확인되지 않았습니다." |
| `SESSION_VALIDITY_MISSING` | 유효기간 미입력 | 횟수제인데 유효기간 날짜 없음 | "횟수제 이용권의 유효기간을 입력하지 않아 이 기준의 적용 여부를 확인하지 못했습니다." |
| `REFUND_BASIS_UNKNOWN` | 기준 미상 | 요가·필라테스 `refund_basis = unknown` | "계약할 때 정한 환급 기준(기간 또는 횟수)을 알 수 없어 두 기준으로 모두 계산했습니다." |
| `RULE_UNVERIFIED` | 규칙 미검증 | 쓰는 블록이 `verified: false` | "계산에 쓴 기준 값 중 원문 확인이 끝나지 않은 값이 있습니다." |
| `LIST_PRICE_NOT_USABLE` | 정상가 미입력·확인 필요 | 정상가 없음 또는 정상가 < 총계약대금. 단, 시작 전 해지(`notice_date < start_date`이고 모든 기준의 이용분 0)에서 정상가가 없는 것은 사유가 아니다 [결정 2026-10-26 추가 수정 2] | "정상가(할인 전 가격)를 쓸 수 없어 정상가 기준 계산을 하지 못했습니다." |
| `INTERPRETATION_DEPENDENT` | 해석 의존 계산 | 어느 기준·시나리오든 이용분 > 0 | "고시에 이용분 계산 방식이 정해져 있지 않아 금액이 해석에 따라 달라질 수 있습니다." |
| `USAGE_STARTED` | 이용 시작 후 해지 | 도달일이 시작일보다 이르지 않음 (시작 전 해지가 아님). `start_date` 또는 `notice_date`가 없어 시작 전 해지를 확인하지 못하면 `True`로 본다 (예: S3). 그래서 ✅는 시작 전 해지가 확인될 때만 나온다 [결정 2026-10-26 추가 1]. 이름은 아래 변경 기록 [결정 2026-10-26 후속 Q4] | "이용을 시작한 뒤 해지해 이용분 공제가 들어갑니다." |
| `POSTPONEMENT` | 연기 입력 | `had_postponement = True` (시작 전 해지는 제외) | "이용 연기 기간이 있어 결과가 달라질 수 있습니다." |

🔍 사유 (계산 안 함, 5.2 순서 9~11, 먼저 걸린 하나만 붙는다):

| 코드 | 짧은 이름 | 화면 한 줄 |
|---|---|---|
| `MISSING_REQUIRED` | 필수 정보 누락 | "계산에 필요한 정보가 빠져 있어 계산하지 않았습니다. 빠진 항목을 입력해 주세요." |
| `INVALID_INPUT` | 입력 오류 | "입력한 값끼리 맞지 않아 계산하지 않았습니다. 다시 확인해 주세요." |
| `NOTICE_AFTER_VALIDITY` | 유효기간 이후 도달 (횟수 기준 계산에만 적용, 5.2 순서 11. 기간 기준의 종료일 이후 도달에는 붙지 않는다) | "해지 의사가 유효기간이 끝난 뒤에 전달되어 이 서비스에서는 계산하지 않습니다. 1372 등 상담 창구에 문의해 주세요." |

코드 이름 변경 기록 (2026-10-26, 조건은 같음. 이전 이름은 이 목록에만 남긴다):
- `NOT_BEFORE_START` → `USED_AMOUNT_NONZERO` → `USAGE_STARTED`
- `WITHDRAWAL_PERIOD_UNCONFIRMED` → `WITHDRAWAL_STATUS_UNCONFIRMED`, 입력 필드 `withdrawal_period_passed` → `withdrawal_cleared`
- 안내 코드 `MINIMUM_REFUND` → `PENALTY_INPUT_MISSING` (결과 라벨 `refund_kind = minimum` "최소 환급액"은 그대로)
- 안내 코드 `OFFER_NEAR_LIST_PRICE_BASIS` → `OFFER_BETWEEN_A_AND_B` (문구도 조건에 맞춰 바꿈)

화면 표시 우선순위 [결정 2026-10-26 추가 수정 3]: 결과의 `flags` 중 아래 표에서 가장 위에 있는 코드 1개만 배지 옆에 한 줄로 보여 주고, 나머지는 "다른 확인 사항 n개" 아래에 접어서 우선순위 순으로 보여 준다. 배지 판정에는 쓰지 않는다 (배지는 결정 순서로만 정한다). 배지와 같은 등급의 코드가 항상 먼저 오도록 등급 순(❔ → 🔍 계산 안 함 → ⚠️ → 🔍 계산함)으로 묶었다. 등급 안의 순서는 초안이다: 고시 적용 여부를 흔드는 사유 → 계산 기준을 흔드는 사유 → 금액 해석 사유 → 참고 사유.

| 우선순위 | 코드 | 등급 |
|---|---|---|
| 1 | 5.2 순서 1~8의 ❔ 코드 (먼저 걸린 하나) | ❔ |
| 2 | `MISSING_REQUIRED` / `INVALID_INPUT` / `NOTICE_AFTER_VALIDITY` (먼저 걸린 하나) | 🔍 계산 안 함 |
| 3 | `PENALTY_ABOVE_CAP` | ⚠️ |
| 4 | `OFFER_BELOW_B` | ⚠️ |
| 5 | `SCOPE_UNCERTAIN_PT_ONLY` | 🔍 |
| 6 | `PERIOD_28_TO_31_DAYS` | 🔍 |
| 7 | `REFUND_LIMIT_CLAUSE_UNKNOWN` | 🔍 |
| 8 | `WITHDRAWAL_STATUS_UNCONFIRMED` | 🔍 |
| 9 | `SESSION_VALIDITY_MISSING` | 🔍 |
| 10 | `REFUND_BASIS_UNKNOWN` | 🔍 |
| 11 | `RULE_UNVERIFIED` | 🔍 |
| 12 | `LIST_PRICE_NOT_USABLE` | 🔍 |
| 13 | `INTERPRETATION_DEPENDENT` | 🔍 |
| 14 | `USAGE_STARTED` | 🔍 |
| 15 | `POSTPONEMENT` | 🔍 |

✅ 조건 [결정 2026-10-26 #6, 보충 2·4·5, 추가 수정 2]: 위 ❔·🔍·⚠️ 사유가 하나도 없을 때. 풀어 쓰면 ① 시작 전 해지(`notice_date < start_date`, 모든 기준의 이용분 0) ② 계약 일수 32 이상 ③ `has_refund_limit_clause = True` ④ `withdrawal_cleared = True` ⑤ 정상가가 있으면 `list_price ≥ total_contract_amount` (시작 전 해지이므로 정상가가 없어도 된다) ⑥ 쓰는 블록 모두 `verified: true` ⑦ 강건한 ⚠️ 없음 ⑧ `is_pt_only`가 `True`가 아님. `had_postponement`는 ✅ 판정에 쓰지 않는다.

진리표 (J = ❔ 조건, M = 계산 안 함 🔍 사유(필수 정보 누락·입력 오류·유효기간 이후 도달), R = 강건한 ⚠️ 신호, I = 🔍 사유):

| J | M | R | I | 배지 | 도달 가능 |
|---|---|---|---|---|---|
| 1 | * | * | * | ❔ | 예 (8조합 모두 ❔) |
| 0 | 1 | 0 | 0 | 🔍 계산 안 함 | 예 |
| 0 | 1 | 0 | 1 | 🔍 계산 안 함 | 예 (I는 계산하지 않아 평가하지 않음) |
| 0 | 1 | 1 | * | 🔍 계산 안 함 | **아니오** (계산하지 않으면 R을 만들 수 없음) |
| 0 | 0 | 1 | 0 | ⚠️ | 이론상 (R이 있으면 보통 I도 있음) |
| 0 | 0 | 1 | 1 | ⚠️ | 예 (N2, K1) |
| 0 | 0 | 0 | 1 | 🔍 | 예 |
| 0 | 0 | 0 | 0 | ✅ | 예 (C1, C3, C4) |

검사 결과 (2026-10-26, scratchpad 스크립트, 저장소에 두지 않음): 16조합 모두 배지가 하나로 정해진다. ✅는 J=M=R=I=0일 때만, ❔는 J=1일 때만, ⚠️는 J=0·M=0·R=1일 때만 나온다. 케이스 30건의 기대 배지가 이 표와 모두 일치한다. 2026-10-26 추가한 5건(V1~V4, C4)과 바뀐 사유 코드(P2, S3)도 이 표와 맞는다 (M에 `NOTICE_AFTER_VALIDITY`를 넣은 것 외에 표는 그대로).

제시액 위치 (강건하지 않은 비교는 배지를 바꾸지 않는다):

| 제시액 위치 | 처리 |
|---|---|
| 제시액 < B 최솟값 | ⚠️ `OFFER_BELOW_B` |
| B 최솟값 ≤ 제시액 < A 최댓값 | 안내 `OFFER_BETWEEN_A_AND_B`: "업체 제시액은 두 계산 방식(실제 부담액 기준 A, 정상가 기준 B)의 결과 사이에 있습니다." |
| 제시액 ≥ A 최댓값, 또는 B 없음 | 안내 없음 |

가드레일 위치: 승패·법적 효력 질문 감지는 단계 4 API(`/api/calculate` 앞단)에 둔다. 엔진의 `decide_badge`는 `judgment_requested: bool`만 받는다 [결정 2026-10-26 #8].

### 5.5 안내 문구 (`notices`)

배지 판정의 입력이 아니다. 화면 설명용이다.

| 코드 | 조건 | 문구 |
|---|---|---|
| `NO_LIST_PRICE` | 정상가 없음. 단, 시작 전 해지(`notice_date < start_date`이고 모든 기준의 이용분 0)이면 표시하지 않음 [결정 2026-10-26 후속 Q2] | 5.3 표 |
| `LIST_PRICE_BELOW_TOTAL` | 정상가 < 총계약대금 | "정상가를 다시 확인해 주세요." |
| `OFFER_BETWEEN_A_AND_B` | 5.4 제시액 표 | "업체 제시액은 두 계산 방식(실제 부담액 기준 A, 정상가 기준 B)의 결과 사이에 있습니다." |
| `PENALTY_INPUT_MISSING` | `contract_penalty` 없음 | "계약서상 위약금을 입력하지 않아 위약금 상한을 공제했습니다. 실제 위약금이 이보다 낮으면 환급액은 더 커집니다." (계약서상 위약금이 상한보다 커서 상한을 공제한 경우는 `PENALTY_ABOVE_CAP` 화면 한 줄이 설명한다. 2026-10-26 조건을 `refund_kind = minimum`에서 바꿈, 기존 케이스의 표시는 같음) |
| `STANDARD_TERMS_PENALTY` | `contract_penalty` 없음 | "표준약관을 사용한 계약이라면 위약금이 이용료의 1/10로 정해져 있어 이 최소 환급액과 실제 환급액이 같거나 가까울 수 있습니다. 계약서의 위약금 조항을 확인해 보세요." [원문] 표준약관 제10048호 제8조 ②, 제10083호 제9조 ① / 문구는 [결정 2026-10-26 #7, 보충 3]. `refund_kind`는 그대로 "최소 환급액" |
| `NEGATIVE_REFUND_ZEROED` | 시나리오별 `raw_X < 0` | "공제 항목의 합계가 지급한 금액보다 커서 기준상 환급액은 0원으로 계산됩니다. 추가로 내야 하는 금액이 있는지는 이 서비스에서 판단하지 않습니다. 1372에 문의해 주세요." |
| `POSTPONEMENT_INPUT` | `had_postponement = True` | 입력 안내: "이용을 연기했다면 종료일에는 연장된 종료일을 입력해 주세요." 결과 안내: "연기 기간이 있으면 결과가 달라질 수 있습니다." |
| `PERIOD_CHECK` | `had_postponement`가 `None`·`False` | 고정 안내: "계약서의 이용기간과 연기 내역을 확인해 주세요." |
| `WITHDRAWAL_INFO` | `withdrawal_cleared`가 `True`가 아님 | "계약서를 받은 뒤 짧은 기간(방문판매·전화권유판매 14일, 할부계약·통신판매 7일 등) 안이라면 청약철회가 가능할 수 있고, 그 경우에는 이 기준이 적용되지 않습니다." |
| `PT_ONLY_QUESTION` | 입력 단계, `industry = fitness`이고 `contract_type = session` | 입력 질문: "PT만 계약하셨나요?" 응답 예 / 아니오 / 모름 → `is_pt_only` = `True` / `False` / `None` [결정 2026-10-26 Q3] |

### 5.6 출력 (`GymResult`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `badge` | `Badge` | ❔ / 🔍 / ⚠️ / ✅ |
| `calculated` | `bool` | 계산했는지 |
| `results` | `dict[Basis, BasisResult]` | 기준(`period`/`session`)별 결과. `BasisResult = {elapsed, units, A: ScenarioResult, B: ScenarioResult \| None}` |
| `ScenarioResult` | — | `used_amount: int`, `raw_refund: int`, `refund: int` |
| `penalty` | `int` | 공제한 위약금 |
| `penalty_cap` | `int` | 상한 (내림 후) |
| `refund_kind` | `str` | `minimum`(최소 환급액) / `computed`(환급액) |
| `deposit_refund` | `int` | 보증금 환급액 (환급액과 별도) |
| `contract_days` | `int \| None` | 계약 일수 |
| `steps` | `list[Step]` | 항목명·계산식·금액, 고정 줄 포함 (5.3) |
| `flags` | `list[str]` | ❔·🔍·⚠️ 사유 코드 (5.2·5.4) |
| `missing` | `list[str]` | 누락 필드 |
| `notices` | `list[str]` | 안내 코드 (5.5) |
| `citations` | `list[str]` | 근거 조항 ID (5.7) |

### 5.7 근거 조항 ID 매핑

근거 카드에는 원문을 확인한 조문만 인용한다 (10절). ID는 규칙 JSON `clauses[].id`(고시)와 `related_clauses[].id`(고시 밖 원문).

| 결과 요소 | 인용 ID |
|---|---|
| 적용 범위 (업종) | `art3_1` |
| 청약철회 ❔ | `art3_2` |
| 총계약대금 정의 (가입비 포함, 보증금 제외) | `art2_2` |
| 단위·단위대금 | `art2_3`, `art2_4` |
| 위약금 상한 | `art4_1`, `annex_penalty` |
| 환급 공식·미이용 간주 | `art5_1` |
| 보증금 | `art5_2` |
| 부가상품 반환 | `art6_1` |
| 위약금·환급 일반 원칙 (방문판매법) | `law32_1` |
| 계속거래 요건 (`PERIOD_UNDER_28_DAYS`, `PERIOD_28_TO_31_DAYS`, `NO_REFUND_LIMIT_CLAUSE`, `REFUND_LIMIT_CLAUSE_UNKNOWN`) | `law2_10` [결정 2026-10-26 질문 답 5] |
| 유효기간 이후 도달 (`NOTICE_AFTER_VALIDITY`, 요가·필라테스만) | `yoga_terms_art5_2` [결정 2026-10-26 질문 답 3] |
| 표준약관 위약금 안내 (`STANDARD_TERMS_PENALTY`) | `gym_terms_art8_2_def` (헬스·피트니스), `yoga_terms_art9_1_def` (요가·필라테스) |
| 환급 기준 합의 (`refund_basis`) | `yoga_terms_art9_1_def` |

인용하지 않는 조문: 약관법 제9조 (위약금 과다를 직접 다루지 않음, `related_laws.md`), 방문판매법 제52조, 민법 기간 조문. 계속거래 정의(법 제2조 제10호)는 판정용 `params.continuous_transaction_criteria`와 인용용 `related_clauses[law2_10]`에 같은 문장으로 둔다.

### 5.8 함수 시그니처 (단계 2)

```python
# backend/rules/money.py
def div_round_half_up(numerator: int, denominator: int) -> int
def penalty_cap(total: int, ratio: Decimal) -> int                     # 원 미만 내림

# backend/rules/loader.py
def load_rule(rule_id: str) -> GymRule                                  # json.loads(parse_float=Decimal) + Pydantic 검증

# backend/rules/gym.py
def contract_days(start: date, end: date) -> int                        # end − start + 1
def elapsed_days(start: date, notice: date, total_days: int) -> int      # clamp(notice − start + 1, 0, total_days)
def classify_period(days: int | None) -> Literal["out_of_scope", "needs_review", "ok", "unknown"]
def resolve_basis(inp: GymInput) -> Literal["period", "session", "unknown"]
def check_scope(inp: GymInput, rule: GymRule) -> ScopeResult           # ❔ 코드, 누락 필드, 입력 오류
def calc_penalty(total: int, cap: int, contract_penalty: int | None) -> tuple[int, RefundKind]
def calc_basis(inp: GymInput, basis: Basis, penalty: int) -> BasisResult
def compare_offer(offer: int | None, results: dict[Basis, BasisResult]) -> OfferComparison
def collect_review_flags(inp: GymInput, rule: GymRule, results: dict[Basis, BasisResult]) -> list[str]
def calculate_refund(inp: GymInput, rule: GymRule) -> GymResult

# backend/rules/badge.py
def decide_badge(*, judgment_requested: bool, out_of_scope: bool, missing_or_invalid: bool,
                 robust_warnings: list[str], review_flags: list[str]) -> Badge
```

`rules/`는 `llm/`을 import하지 않는다. 새 의존성 없음 (표준 라이브러리 `datetime`, `decimal`, `fractions`, `json` + 기존 `pydantic`, `pytest`).

### 5.9 테스트 구성 (단계 2, 테스트 먼저)

| 파일 | 내용 |
|---|---|
| `tests/test_money.py` | half up .5 경계 (R2: 50,000.5 → 50,001), 위약금 내림 (R3: 99,999.9 → 99,999) |
| `tests/test_gym_rule_data.py` | `ratio`가 `Decimal("0.10")`, `in_source: false` 표시, 블록 `verified` 값, 조항 ID 존재 |
| `tests/test_gym_days.py` | 계약 일수·경과 일수 (도달일 < 시작일 → 0, 종료일 이후 → 계약 일수) |
| `tests/test_gym_scope.py` | 5.2 표의 행마다 1건, 경계 27/28/31/32일 (B1~B4) |
| `tests/test_gym_calc.py` | `gym_cases_draft.md`의 계산 케이스 (사용자 검증 후) |
| `tests/test_gym_badge.py` | 5.4 진리표 16조합, ✅ 조건 각각을 하나씩 깨는 케이스 |
| `tests/test_import_direction.py` | `rules/`가 `llm/`을 import하지 않는지 (AST) |

테스트 기대값은 사용자가 검증한 `gym_cases_draft.md`에서만 가져온다.

### 5.10 구현 순서 (단계 2)

1. `money.py` 테스트 → 구현
2. `loader.py` + 규칙 데이터 테스트
3. 일수 함수 테스트 → 구현
4. 범위 판정 테스트 → 구현
5. 계산 테스트 → 구현
6. 배지 진리표 테스트 → 구현
7. `calculate_refund` 통합 테스트 (케이스 전체) → 구현
8. `ruff check`, `ruff format`, `pytest` 통과 확인 후 보고

### 5.11 단계 0 확인 결과

| 항목 | 결과 |
|---|---|
| 입력 단위 | [원문] 계약으로 정한 1월/1일/1회/1시간 등 (제2조 3호). 기간제는 날짜로 입력 [결정 2026-10-26] |
| 이용분 계산 방식 | [원문] 공급받은 단위 수 × 단위대금 (제5조 ①). 단위대금 산정은 [미결], 시나리오 A·B 병기 |
| 이용분 기준 금액 | 고시 원문에 없음. 1372 답변 1(비구속)은 정상가 기준을 언급. 표준약관은 "계약 시 납부한 총 금액"(제10048호), "실 결제금액"(제10083호) |
| 반올림 | [결정] 이용분 half up, 위약금 원 미만 내림 |
| 일수 계산 | [결정] 시작일·도달일 모두 산입, 0~계약 일수로 제한 |
| 계속거래 요건 | [원문] 법 제2조 제10호. 기간 경계 28/31/32일은 [결정] |
| 별표 | [원문] 공식 HWP 재추출·별표 이미지 판독 일치 (2026-10-26). `penalty_rule.verified: true`, `user_checked: false` |
| 표준약관 | [원문] 제10048호(2025-05-23 개정) 최신, 요가·필라테스 제10083호(2026-07-16 제정) 별도 존재 |
| 고시 현행성 | [원문] 제2019-9호 이후 개정 없음 (2026-10-26) |
| 방문판매법 2026-09-29 개정 | 인용 조문(제2조 제10호, 제31조, 제32조)에 개정 표시 없음 [해석] |

## 6. API (MVP)

| 엔드포인트 | 역할 |
|---|---|
| `POST /api/analyze` | 문장 → 추출 결과(`item`, `fields`, `missing`, `evidence`) |
| `POST /api/calculate` | 확정된 필드 → 계산 결과(`refund`, `steps`, `badge`, `source`) |
| `POST /api/guide` | 계산 결과 → 설명·업체용 문안·다음 행동 (인용 검증 포함) |

`/api/ask`(자유 질의)는 MVP 범위 밖이다.

## 7. 완료 기준 (MVP)

- [ ] 규칙 파일의 모든 값에 원문 출처가 있고 `verified=true`
- [ ] 규칙 엔진 pytest 케이스 10건 이상 전부 통과 (정답은 손계산)
- [ ] 입력 → 결과 화면이 끝까지 동작 (가상 사례 5건)
- [ ] 승패·법적 효력 질문 5건이 모두 `❔ 판단 불가`로 처리
- [ ] 결과 화면에 기준일·출처·"권고 기준" 고지 표시

## 8. 구현 순서

| 단계 | 내용 | 산출물 |
|---|---|---|
| 0 | 헬스장 관련 고시·위약금 산정기준 원문 확인 (사람이 확인, Claude Code는 정리 보조) | 규칙 JSON 초안, 출처 목록 |
| 1 | 저장소 뼈대: 폴더, `backend/pyproject.toml`, FastAPI health, Vite react-ts 앱, `.env.example`(`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`), CI 없이 pytest 1건 | 실행 확인 — ✅ 완료 (2026-10-19) |
| 2 | 규칙 엔진 + 테스트 (LLM 없음) | `rules/gym.py`, tests |
| 3 | 정보 추출 (LLM 어댑터, JSON 스키마, few-shot, temperature 0) | `/api/analyze` |
| 4 | 계산 API + 상태 배지 + 가드레일 | `/api/calculate` |
| 5 | 근거 카드·설명·업체용 문안 + 인용 검증 | `/api/guide` |
| 6 | 화면 3개 연결 (UI 예시 v0.1 기준) | 동작하는 MVP |
| 7 | 세탁·가전 규칙 추가, 조항 검색 도입(업종 필터 + 키워드 → 임베딩), 평가 30건, 범용 LLM 비교 | 평가 결과 |

단계 0이 끝나기 전에는 단계 2의 숫자를 확정하지 않는다. 단계 1은 0과 병행 가능.

### 단계 0 체크리스트

상태: 완료 / 사용자 대기 / 외부 답변 대기 / 차단. 기준일 2026-10-26.

| 항목 | 상태 | 담당 | 메모 |
|---|---|---|---|
| 별표 대조 | 완료 (사용자 육안 대조 안 함) | Claude Code | 공식 HWP 재추출·별표 이미지 판독·기존 표 세 가지가 전 행 일치. `penalty_rule.verified: true`, `verification.user_checked: false` |
| 고시번호·시행일·개정이력·현행성 | 완료 | Claude Code | 제2019-9호 이후 개정 없음 (2026-10-26 재확인) |
| 고시 본문 현행본 대조 (제1~8조) | 완료 | Claude Code | 글자 단위 일치 |
| 계속거래 정의 원문 | 완료 | Claude Code | 기간 경계 28/31/32일 유지 (2026-10-26 결정) |
| 1372 답변 | 완료 (부분 답변, 추가 문의 없음) | 사용자 | 접수번호·문의 2 질문 원문 TODO |
| 단위대금 해석 | 완료 (미확정 유지, A·B 병기) | 사용자 (결정) | |
| 표준약관 (제10048호) 계산식 2중 검증 | 완료 | Claude Code | 수식 스크립트 ↔ 공정위 문서뷰어 렌더링 일치 |
| 요가·필라테스 표준약관 (제10083호) | 완료 | Claude Code | 환급 기준 합의 → `refund_basis` |
| 청약철회 조문, 환급 기한, 소비자분쟁해결기준 위치 | 완료 | Claude Code | `related_laws.md` |
| 입력 방식·일수·배지 결정 (질문 8건 + 보충 7건) | 완료 | 사용자 (결정) | 5절 반영 |
| 새 질문 (청약철회 14일 ❔ 방안, 청약철회권 없는 계약, 유효기간 후 잔여 횟수, PT 단독 범위, 법 제2조 제10호 인용) | 완료 (2026-10-26) | 사용자 (결정) | 5절 반영, 5.2 "해결한 질문" |
| 후속 질문 5건 (권유 뒤 매장 계약 풀이, 횟수 기준 `notice_date`, 시작 전 해지 `NO_LIST_PRICE`, `USAGE_STARTED`, CLAUDE.md 배지 문구) | 완료 (2026-10-26), 전화 권유 뒤 매장 계약만 [미결] | 사용자 (결정) | 5절 반영 |
| 손계산 케이스 검증 (`gym_cases_draft.md`, 35건: 사용자 검증 완료 7, 재계산 일치(Claude) 20, 검증 대기 8) | 사용자 대기 | 사용자 | 검증 전에는 테스트 코드로 옮기지 않는다 |

## 9. 결정 사항과 남은 결정

**확정 (2026-10-19)**

1. MVP 첫 품목: 헬스장(체육시설업)
2. 프론트: TypeScript (`strict`, Vite react-ts 기본 템플릿, 라우터·UI·상태관리 라이브러리 없음)
3. 백엔드 배치: `backend/pyproject.toml`, `backend/.venv`, `backend/.env`. 실행은 `backend`에서 `uvicorn main:app --reload`
4. 단계 1 의존성: `fastapi`, `uvicorn`, `pydantic`, `pytest`, `httpx`, `ruff`(lint·format, black 미사용)

**남은 결정**

1. 사용할 무료 LLM API (키 발급 가능한 것) — 단계 3 전에 결정
2. 배포 대상 — 미정이면 6주차에 결정

## 10. UX 요구 메모 (단계 6용)

- 첫 화면에 지원 업종(헬스·피트니스업, 요가·필라테스업)을 안내한다.
- 예시 상황 버튼 3개: 헬스장, 필라테스, 기타.
- 미지원 업종 입력 시: "아직 지원하지 않는 업종입니다. 1372에 문의하세요" + 상담 창구 링크 (링크 URL은 단계 6에서 공식 페이지로 확인).
- 사업자 귀책·폐업은 `❔ 판단 불가` 결과에 "다음 확장 예정"으로 안내한다.
- 근거 카드에는 원문을 확인한 조문(고시, 방문판매법 제32조 ①, 체력단련장·요가·필라테스 표준약관)만 인용한다. ID 매핑은 5.7. 약관법 제9조 제5호는 위약금 과다를 직접 다루지 않으므로 인용하지 않는다. "무효" 같은 법적 효력 표현은 쓰지 않는다 [결정 2026-10-26 #7].
- 결과 화면 고정 안내: 정상가 미입력 안내(5.3), 표준약관 위약금 안내(5.5 `STANDARD_TERMS_PENALTY`), 기간·연기 확인 안내(5.5 `PERIOD_CHECK`).
- 입력 화면: 연기했다고 답하면 종료일 입력란에 "연장된 종료일을 입력" 안내를 붙인다 (5.5 `POSTPONEMENT_INPUT`).
- `refund_basis = unknown` 결과는 "일수 기준", "횟수 기준"으로 묶어서 보여 준다 (5.3).
- 사유 한 줄 표시 문제: 케이스 기준으로 계산한 🔍 24건 중 20건의 화면 한 줄이 `WITHDRAWAL_STATUS_UNCONFIRMED`라 화면에 같은 문구만 보인다. 단계 6에서 결정: 사유 상위 2개와 "외 N개" 펼침, 또는 확인 체크리스트. 단계 2에서는 5.4 우선순위 규칙(1개 표시)을 바꾸지 않는다 [2026-10-26 기록].

## 11. 평가 메모 (단계 7)

- 교수님 조언: AI Hub 대화 데이터(감정 태그 '부정')를 구어체 견고성 시험에 보조로 사용할 수 있음. 이용 승인·조건 확인 전이며, 원문은 저장소에 올리지 않는다. 정확도 지표의 정답 데이터는 직접 만든 가상 사례로 한다.
