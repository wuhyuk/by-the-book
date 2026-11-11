"""세탁 설명·업체용 문안 (2026-11-11, 템플릿 방식).

입력은 서버가 다시 계산한 LaundryResult다. 금액·비율·일수·내용연수는 결과 필드에서만 가져오고,
사유 문구(DECISION_SENSITIVE 범위 문구 포함)·안내 문구·인용 카드는 rules/laundry_display.py를 그대로 쓴다.
"""

from guide.common import (
    COMPANY_CLOSING,
    DISCLAIMER_LINE,
    Guide,
    basis_line,
    caveat_line,
    computed_sentence,
    not_calculated_guide,
    review_lines,
    undeterminable_guide,
    won,
)
from rules.badge import Badge
from rules.laundry import LaundryInput, LaundryResult
from rules.laundry_codes import LaundryFlag, LaundryNotice
from rules.laundry_display import NOTICE_TEXTS, build_laundry_display
from rules.laundry_rule import LaundryRule

ROBUST_CODES = frozenset({LaundryFlag.OFFER_BELOW_STANDARD_MIN.value})
DAMAGE_LABELS = {"defect": "손상", "loss": "분실"}
FORMULA_CLAUSE_IDS = {"ratio": "laundry_1", "fallback": "laundry_5_1"}

# 업체용 문안 단서에 쓰는 말 (🔍 사유 → 불확실성 항목). 설명에 그 사유가 있을 때만 쓴다.
L = LaundryFlag
CAVEAT_PHRASES: dict[str, str] = {
    L.EXEMPTION_CLAIMED.value: "확인서 교부·장기 미회수에 따른 책임 면제 여부",
    L.SPECIAL_AGREEMENT.value: "배상에 관한 특약",
    L.PARTIAL_FAULT_CLAIMED.value: "고객 일부 책임에 따른 공제",
    L.DAMAGED_ITEM_RETURN.value: "손상된 세탁물 인도에 따른 감액",
    "RULE_UNVERIFIED": "원문 확인이 끝나지 않은 기준 값",
}
SENSITIVITY_PHRASES = {
    "use_days": "고시에 정해져 있지 않은 사용일수 산입 방식(구입일을 세는지)",
    "rounding": "원 미만 처리(내림·반올림)",
}


def _caveat_phrases(codes: list[str], result: LaundryResult) -> list[str]:
    phrases: list[str] = []
    for code in codes:
        if code == L.DECISION_SENSITIVE.value:
            phrases += [SENSITIVITY_PHRASES[c] for c in result.sensitivity_causes]
        else:
            phrases.append(CAVEAT_PHRASES[code])
    return phrases


def _clause_label(rule: LaundryRule, clause_id: str) -> str:
    return next(c.label for c in rule.clauses if c.id == clause_id)


def _item_text(inp: LaundryInput, rule: LaundryRule) -> str:
    """사용자가 고른 품목 이름 (표 행 이름 그대로). 고르지 않았으면 일반 표현."""
    if inp.item_key is not None:
        row = next((r for r in rule.lifespan_table.rows if r.id == inp.item_key), None)
        if row is not None:
            return f"맡긴 세탁물({row.item or row.category})"
    return "맡긴 세탁물"


def build_laundry_guide(
    inp: LaundryInput, result: LaundryResult, rule: LaundryRule
) -> Guide:
    """LaundryResult → 설명 문장·업체용 문안·근거 조항."""
    display = build_laundry_display(result, rule, inp)
    if result.badge == Badge.UNDETERMINABLE:
        return undeterminable_guide(display.screen_line, display.citations)
    if not result.calculated:
        return not_calculated_guide(
            display.screen_line, display.citations, consult=False
        )
    amount, method = result.amount, result.method
    assert amount is not None and method is not None
    lo = result.sensitivity_min if result.sensitivity_min is not None else amount
    hi = result.sensitivity_max if result.sensitivity_max is not None else amount

    flag_lines = [display.screen_line, *display.other_flags]
    lines = [line for line in flag_lines if line is not None]
    robust = [line for line in lines if line.code in ROBUST_CODES]
    review = [line for line in lines if line.code not in ROBUST_CODES]

    if method == "ratio":
        explanation = [
            (
                f"고시 기준으로 계산한 배상액은 {won(amount)}입니다 "
                f"(내용연수 {result.life_years}년 품목, 사용일수 {result.use_days}일, "
                f"배상비율 {result.ratio_percent}%)."
            )
        ]
    else:
        explanation = [
            (
                f"{NOTICE_TEXTS[LaundryNotice.UNPROVEN_FALLBACK]} "
                f"이 기준으로 계산한 배상액은 {won(amount)}입니다."
            )
        ]
    offer = inp.provider_offer
    for line in robust:
        explanation.append(line.text)
        if offer is not None:
            explanation.append(
                f"업체 제시액 {won(offer)}은 고시 기준으로 계산한 가장 작은 기준 금액 "
                f"{won(lo)}보다 적습니다."
            )
    explanation += review_lines(review)
    if (basis := basis_line(display.citations)) is not None:
        explanation.append(basis)
    explanation.append(DISCLAIMER_LINE)

    s = rule.source
    damage = DAMAGE_LABELS[inp.damage_type]
    company = [
        (
            f"안녕하세요. {_item_text(inp, rule)}의 {damage} 배상 금액에 관해 "
            "확인을 부탁드리고자 연락드립니다."
        ),
        computed_sentence(
            f"「{s.name}」({s.notice_number}) "
            f"{_clause_label(rule, FORMULA_CLAUSE_IDS[method])}",
            "배상액",
            lo,
            hi,
        ),
    ]
    if robust and offer is not None:
        company.append(
            f"안내해 주신 {won(offer)}은 고시 기준으로 계산한 가장 작은 기준 금액"
            f"({won(lo)})보다 적습니다."
        )
    # 단서: 설명의 확인 목록에 실제로 들어간 불확실성 항목만 (배지와 무관하게)
    if (
        caveat := caveat_line(_caveat_phrases([x.code for x in review], result))
    ) is not None:
        company.append(caveat)
    company += [COMPANY_CLOSING, DISCLAIMER_LINE]
    return Guide(
        explanation=explanation,
        company_message="\n".join(company),
        citations=display.citations,
    )
