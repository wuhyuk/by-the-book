"""LLM 추출값 확인 (CLAUDE.md 절대 규칙 1). 순수 함수, LLM 호출 없음.

LLM은 숫자를 만들지 않는다. 그래서 LLM이 낸 금액·횟수·날짜는 그대로 믿지 않고,
LLM이 함께 낸 근거 구절(evidence)이 (마스킹한) 입력 문장에 그대로 있고 그 구절에서 코드가 읽은
같은 종류의 값이 정확히 그 값 하나일 때만 받는다 (llm/extraction.py). 아니면 버리고 사용자에게 다시 묻는다.

- 금액: "120만원", "1,200,000원", "12만 5천원", "1억 2천만원" 같은 표기. 단위(억·만·천·백)나 "원"이나
  세 자리 쉼표가 있는 수만 금액 후보로 본다. 한글 숫자("백이십만원")는 읽지 않는다.
- 횟수: "20회", "30번".
- 날짜: 연도가 있는 표기만 ("2026-01-01", "2026.1.1", "2026/1/1", "2026년 1월 1일").
  연도 없는 날짜·"1년 계약" 같은 기간에서 날짜를 계산하지 않는다 (해석·계산이므로).
"""

import re
from dataclasses import dataclass
from datetime import date

_WS = re.compile(r"\s+")

_AMOUNT_EXPR = re.compile(
    r"(?<![\d,.])\d[\d,]*(?:\s*(?:억|만|천|백)(?:\s*\d[\d,]*)?)*\s*(?:원)?"
)
_AMOUNT_TOKEN = re.compile(r"\d[\d,]*|억|만|천|백")
_COMMA_INT = re.compile(r"^\d{1,3}(?:,\d{3})+$|^\d+$")
_COUNT = re.compile(r"(?<![\d,.])(\d+)\s*(?:회|번)")
_DATE = re.compile(
    r"(?<!\d)(\d{4})\s*(?:-|\.|/|년)\s*(\d{1,2})\s*(?:-|\.|/|월)\s*(\d{1,2})(?!\d)"
)


def normalize(text: str) -> str:
    """공백을 하나로 줄인다 (근거 구절 대조용)."""
    return _WS.sub(" ", text).strip()


def evidence_in_text(evidence: str | None, text: str) -> bool:
    """근거 구절이 비어 있지 않고 입력 문장에 그대로 들어 있는지."""
    if evidence is None:
        return False
    ev = normalize(evidence)
    return bool(ev) and ev in normalize(text)


def _compound_amount(tokens: list[str]) -> int | None:
    """숫자·단위 토큰열 → 원 단위 정수. 해석할 수 없으면 None."""
    total = 0
    section = 0
    num: int | None = None
    for t in tokens:
        if t[0].isdigit():
            if num is not None or not _COMMA_INT.match(t):
                return None
            num = int(t.replace(",", ""))
        elif t in ("천", "백"):
            section += (1 if num is None else num) * (1000 if t == "천" else 100)
            num = None
        elif t == "만":
            section += 0 if num is None else num
            total += (section or 1) * 10_000
            section, num = 0, None
        elif t == "억":
            section += 0 if num is None else num
            total += (section or 1) * 100_000_000
            section, num = 0, None
    return total + section + (0 if num is None else num)


def amounts_in(text: str) -> set[int]:
    """문장에서 금액 후보를 모두 읽는다."""
    found: set[int] = set()
    for m in _AMOUNT_EXPR.finditer(text):
        expr = m.group(0).strip()
        tokens = [
            t.rstrip(",") for t in _AMOUNT_TOKEN.findall(expr)
        ]  # "150,000," 끝 쉼표
        has_unit = any(t in ("억", "만", "천", "백") for t in tokens)
        has_won = expr.endswith("원")
        has_comma = any("," in t for t in tokens)
        if not (has_unit or has_won or has_comma):
            continue
        value = _compound_amount(tokens)
        if value is not None:
            found.add(value)
    return found


def counts_in(text: str) -> set[int]:
    """문장에서 횟수 후보("20회", "30번")를 읽는다."""
    return {int(m.group(1)) for m in _COUNT.finditer(text)}


def dates_in(text: str) -> set[date]:
    """문장에서 연도가 있는 날짜를 읽는다. 없는 날짜(2월 30일 등)는 버린다."""
    found: set[date] = set()
    for m in _DATE.finditer(text):
        try:
            found.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    return found


# ---- 예/아니오 값의 뜻 확인 (2026-11-08 D1 승인, VS3 비교 Q12) ----
#
# 근거 구절이 문장에 있기만 하면 통과하던 구멍을 막는다. 필드마다 단서 낱말이 근거 구절에 있어야 하고,
# 값의 뜻(예/아니오)과 맞는 표현인지 낱말로 확인한다. 통과하지 못하면 채택하지 않고 되묻는다.
# 단서 목록을 바꾸면 tests/test_llm_bool_cues.py와 docs/sources/vs3_report.md 4.6을 같이 고친다.

NEGATION_CUES: tuple[str, ...] = ("없", "않", "안 ", "안했", "아니", "못")


@dataclass(frozen=True)
class BoolRule:
    """cues 중 하나가 근거에 있어야 한다. 값에 따라 추가 조건을 본다."""

    cues: tuple[str, ...]
    true_requires: tuple[str, ...] = ()  # 비어 있지 않으면 하나가 있어야 True를 받는다
    true_forbids: tuple[str, ...] = NEGATION_CUES  # 하나라도 있으면 True를 받지 않는다
    false_requires: tuple[str, ...] = NEGATION_CUES  # 하나가 있어야 False를 받는다
    accept_false: bool = True  # False(기본값과 같음)를 받을지


_PASSED = (
    "지났",
    "지나",
    "넘었",
    "넘어",
    "대상이 아니",
    "대상 아니",
    "해당하지",
    "해당 안",
    "해당 없",
)
_COMBINED = ("같이", "함께", "포함", "패키지", "헬스장 이용", "+")

BOOL_CUE_RULES: dict[str, BoolRule] = {
    # ❔ WITHDRAWAL. "청약철회 기간은 지났어요"는 철회하지 않는다는 뜻이라 True로 받지 않는다.
    # False는 기본값과 같아 정보가 없으므로 받지 않고 되묻는다.
    "is_withdrawal": BoolRule(
        cues=("철회",),
        true_forbids=(*NEGATION_CUES, "지났", "지나"),
        accept_false=False,
    ),
    # ❔ ACADEMY_LAW. False는 기본값과 같아 받지 않고 되묻는다.
    "academy_law_applies": BoolRule(cues=("학원",), accept_false=False),
    # True면 🔍 WITHDRAWAL_STATUS_UNCONFIRMED가 빠진다 (✅ 쪽). "지났다"류 표현이 있어야 한다.
    "withdrawal_cleared": BoolRule(
        cues=("철회",),
        true_requires=_PASSED,
        true_forbids=("안 지", "안지", "않았", "아직"),
        false_requires=(*NEGATION_CUES, "아직"),
    ),
    # True면 🔍 REFUND_LIMIT_CLAUSE_UNKNOWN이 빠지고, False면 ❔ NO_REFUND_LIMIT_CLAUSE.
    "has_refund_limit_clause": BoolRule(
        cues=("위약금", "환불", "환급", "해지", "조항", "약관", "약정", "규정"),
    ),
    # True면 🔍 POSTPONEMENT, False면 안내만 바뀐다.
    "had_postponement": BoolRule(
        cues=("연기", "일시정지", "정지", "홀딩", "미뤘", "미루"),
    ),
    # True면 🔍 SCOPE_UNCERTAIN_PT_ONLY. False를 잘못 받으면 그 🔍가 빠지므로 '함께 쓰는 이용권' 단서가 필요하다.
    # "150만원"의 '만'은 단서가 아니다 ("PT만", "만 계약" 같은 형태만).
    "is_pt_only": BoolRule(
        cues=("PT", "pt", "피티", "퍼스널", "개인 트레이닝", "개인 레슨"),
        true_requires=(
            "PT만",
            "pt만",
            "피티만",
            "단독",
            "만 계약",
            "만 등록",
            "만 끊",
            "만 받",
        ),
        true_forbids=(*NEGATION_CUES, *_COMBINED),
        false_requires=_COMBINED,
    ),
    # True면 반환 가치를 더하고 반환 가치 입력을 요구한다.
    "add_on_returned": BoolRule(cues=("반환", "돌려", "반납")),
}

# 세탁 예/아니오 필드 (MVP_SPEC 12.9, VS4). 헬스장 규칙과 같은 방식이다. 바꾸면
# tests/test_llm_laundry_extraction.py와 docs/sources/vs4_report.md 2절을 같이 고친다.
# 세탁 부정 낱말: '못' 하나만으로는 받지 않는다 ("세탁소 잘못"의 '못'이 부정으로 읽히지 않게).
LAUNDRY_NEG: tuple[str, ...] = (
    "없",
    "않",
    "안 ",
    "안했",
    "아니",
    "못 ",
    "못했",
    "못하",
    "못받",
    "못 받",
)
# "이상 없음 확인서에 서명"의 '없'은 부정이 아니다.
_PLAIN_NEG = tuple(n for n in LAUNDRY_NEG if n != "없")
_SHOP_FAULT = (
    "세탁소 잘못",
    "세탁소 책임",
    "세탁소 과실",
    "업체 잘못",
    "업체 책임",
    "업체 과실",
)
LAUNDRY_BOOL_CUE_RULES: dict[str, BoolRule] = {
    # False면 20배 경로. 인수증·영수증·입증 단서가 있어야 하고, 모른다·없다·잃어버렸다는 False.
    "proof_available": BoolRule(
        cues=(
            "영수증",
            "인수증",
            "입증",
            "증명",
            "구매 내역",
            "결제 내역",
            "구입 내역",
            "기억",
            "얼마에 샀",
            "언제 샀",
        ),
        true_forbids=LAUNDRY_NEG,
        false_requires=(*LAUNDRY_NEG, "모르", "몰라", "잃어", "버렸"),
    ),
    # ❔ MANUFACTURING_CAUSE. "세탁 불량"은 세탁소 과실이라 받지 않는다. False는 받지 않는다.
    "manufacturing_cause_claimed": BoolRule(
        cues=("원단", "제조", "불량", "제품 하자", "제품 자체", "소재 문제"),
        true_forbids=(*LAUNDRY_NEG, "세탁 불량", "세탁불량"),
        accept_false=False,
    ),
    # ❔ ATTACHMENT_UNSUPPORTED. 부속물"만" 손상됐다는 표현이 있어야 True. False는 받지 않는다.
    "attachment_only": BoolRule(
        cues=("부속", "탈부착", "털", "칼라", "카라", "모자", "후드"),
        true_requires=(
            "부속물만",
            "털만",
            "칼라만",
            "카라만",
            "모자만",
            "후드만",
            "만 손상",
            "만 망가",
            "만 상했",
            "만 찢",
            "만 변색",
        ),
        true_forbids=LAUNDRY_NEG,
        accept_false=False,
    ),
    "special_agreement": BoolRule(
        cues=("특약", "별도 약정", "따로 약정", "별도로 정", "따로 정"),
        true_forbids=LAUNDRY_NEG,
        false_requires=LAUNDRY_NEG,
    ),
    # 업체가 고객 책임을 주장. 고객의 잘못·책임을 뜻하는 붙은 표현이 있어야 True
    # ("제 코트"의 '제'만으로는 받지 않는다).
    "customer_partial_fault": BoolRule(
        cues=("책임", "과실", "잘못", "탓"),
        true_requires=(
            "제 잘못",
            "제 책임",
            "제 과실",
            "제 탓",
            "제가 잘못",
            "제게도 책임",
            "저도 책임",
            "저한테도 책임",
            "저에게도 책임",
            "제 잘못도",
            "내 잘못",
            "내 책임",
            "고객 잘못",
            "고객 책임",
            "고객 과실",
            "고객 탓",
            "고객에게도",
            "고객한테도",
            "손님 잘못",
            "손님 책임",
            "손님한테도",
            "소비자 잘못",
            "소비자 책임",
        ),
        true_forbids=(*LAUNDRY_NEG, *_SHOP_FAULT),
        false_requires=LAUNDRY_NEG,
    ),
    "wants_damaged_item": BoolRule(
        cues=("돌려받", "돌려 받", "가져가", "가져오", "찾아오", "받고 싶"),
        true_forbids=LAUNDRY_NEG,
        false_requires=LAUNDRY_NEG,
    ),
    "no_issue_confirmation": BoolRule(
        cues=("확인서", "이상 없", "이상없", "날인", "서명", "사인"),
        true_requires=("확인서", "날인", "서명", "사인"),
        true_forbids=_PLAIN_NEG,
        false_requires=_PLAIN_NEG,
    ),
    # 업체가 장기 미회수를 주장. 기간 낱말은 경과를 뜻하는 형태만 받는다
    # ("구입한 지 3개월", "3월 30일"은 받지 않는다). "안 찾아갔다"는 True 쪽 표현이다.
    "uncollected": BoolRule(
        cues=("미회수", "찾아가", "찾으러", "방치", "3개월", "석 달", "30일"),
        true_requires=(
            "미회수",
            "안 찾아",
            "못 찾아",
            "찾아가지 않",
            "방치",
            "3개월 넘",
            "3개월이 넘",
            "3개월 동안",
            "석 달 넘",
            "석 달이 넘",
            "석 달 동안",
            "30일 넘",
            "30일이 넘",
            "30일 동안",
        ),
        true_forbids=("아니라", "바로 찾", "제때"),
        false_requires=("바로 찾", "제때", "아니"),
    ),
    "receipt_issued": BoolRule(
        cues=("인수증", "보관증", "접수증", "세탁 영수증", "맡긴 영수증"),
        true_forbids=LAUNDRY_NEG,
        false_requires=LAUNDRY_NEG,
    ),
}

# 판단 질문 플래그: 근거 구절에 이 낱말 중 하나가 있어야 받는다.
JUDGMENT_CUES: tuple[str, ...] = (
    "판정",
    "판단",
    "맞는지",
    "맞는 건지",
    "이길",
    "이기",
    "승소",
    "패소",
    "승산",
    "소송",
    "재판",
    "고소",
    "무효",
    "효력",
    "불법",
    "위법",
    "합법",
    "적법",
    "법적",
    "내용증명",
    "내용 증명",
    "소장",
    "따져",
)


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def bool_grounded(name: str, value: bool, evidence: str) -> bool:
    """예/아니오 값이 근거 구절의 낱말과 맞는지 (근거 구절이 문장에 있는지는 따로 본다)."""
    rule = (
        BOOL_CUE_RULES[name] if name in BOOL_CUE_RULES else LAUNDRY_BOOL_CUE_RULES[name]
    )
    if not _has(evidence, rule.cues):
        return False
    if value:
        if rule.true_requires and not _has(evidence, rule.true_requires):
            return False
        return not _has(evidence, rule.true_forbids)
    return rule.accept_false and _has(evidence, rule.false_requires)


def judgment_grounded(evidence: str | None, text: str) -> bool:
    """판단 질문 근거가 문장에 있고 판단 단서 낱말을 담고 있는지."""
    return evidence_in_text(evidence, text) and _has(evidence or "", JUDGMENT_CUES)
