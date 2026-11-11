"""세탁 설명·업체용 문안 (2026-11-11, 템플릿 방식).

입력은 서버가 다시 계산한 LaundryResult다. 금액·비율·일수·내용연수는 결과 필드에서만 가져오고,
사유 문구(DECISION_SENSITIVE 범위 문구 포함)·안내 문구·인용 카드는 rules/laundry_display.py를 그대로 쓴다.
"""

from guide.common import (
    COMPANY_CLOSING,
    COMPANY_REVIEW_NOTE,
    DISCLAIMER_LINE,
    Guide,
    amount_or_range,
    basis_line,
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
    display = build_laundry_display(result, rule)
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
    for line in robust:
        explanation.append(line.text)
        explanation.append(
            f"고시 기준으로 계산한 가장 작은 기준 금액은 {won(lo)}입니다."
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
        (
            f"「{s.name}」({s.notice_number}) {_clause_label(rule, FORMULA_CLAUSE_IDS[method])}"
            f"에 따라 계산하면 기준상 배상액은 {amount_or_range(lo, hi)}으로 안내되어 있습니다."
        ),
    ]
    if robust:
        company.append(
            f"안내해 주신 금액은 고시 기준으로 계산한 가장 작은 기준 금액({won(lo)})보다 적습니다."
        )
    if result.badge == Badge.NEEDS_REVIEW:
        company.append(COMPANY_REVIEW_NOTE)
    company += [COMPANY_CLOSING, DISCLAIMER_LINE]
    return Guide(
        explanation=explanation,
        company_message="\n".join(company),
        citations=display.citations,
    )
