"""헬스장 설명·업체용 문안 (2026-11-11, 템플릿 방식).

입력은 서버가 다시 계산한 GymResult다. 금액은 결과 필드(환급액·위약금·상한·보증금 환급액)에서만
가져오고, 사유 문구·인용 카드는 rules/gym_display.py의 build_display 결과를 그대로 쓴다.
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
from rules.badge import Badge, FlagCode
from rules.gym import Basis, GymInput, GymResult, RefundKind
from rules.gym_display import build_display
from rules.loader import GymRule

F = FlagCode
ROBUST_CODES = frozenset({F.PENALTY_ABOVE_CAP.value, F.OFFER_BELOW_B.value})
INDUSTRY_LABELS = {"fitness": "헬스·피트니스", "yoga_pilates": "요가·필라테스"}
BASIS_LABELS = {Basis.PERIOD: "일수 기준", Basis.SESSION: "횟수 기준"}
FORMULA_CLAUSE_ID = "art5_1"


def _kind(result: GymResult) -> str:
    return "최소 환급액" if result.refund_kind == RefundKind.MINIMUM else "환급액"


def _refunds(result: GymResult) -> list[int]:
    """모든 기준·시나리오의 환급액 (결과 필드 그대로)."""
    values: list[int] = []
    for br in result.results.values():
        values.append(br.A.refund)
        if br.B is not None:
            values.append(br.B.refund)
    return values


def _min_b(result: GymResult) -> int | None:
    """정상가 기준(B) 환급액 중 가장 작은 값 (OFFER_BELOW_B의 비교 대상, 5.4)."""
    values = [br.B.refund for br in result.results.values() if br.B is not None]
    return min(values) if values else None


def _breakdown(result: GymResult) -> str:
    """기준별로 묶은 금액 (5.3 결과 묶음 표시)."""
    multi = len(result.results) > 1
    parts: list[str] = []
    for basis, br in result.results.items():
        text = f"실제 부담액 기준(A) {won(br.A.refund)}"
        if br.B is not None:
            text += f", 정상가 기준(B) {won(br.B.refund)}"
        parts.append(f"{BASIS_LABELS[basis]}: {text}" if multi else text)
    return " / ".join(parts)


def _formula_label(rule: GymRule) -> str:
    return next(c.label for c in rule.clauses if c.id == FORMULA_CLAUSE_ID)


def build_gym_guide(inp: GymInput, result: GymResult, rule: GymRule) -> Guide:
    """GymResult → 설명 문장·업체용 문안·근거 조항."""
    display = build_display(result, rule)
    if result.badge == Badge.UNDETERMINABLE:
        return undeterminable_guide(display.screen_line, display.citations)
    if not result.calculated:
        return not_calculated_guide(
            display.screen_line, display.citations, consult=display.consult is not None
        )
    assert result.penalty is not None and result.penalty_cap is not None

    flag_lines = [display.screen_line, *display.other_flags]
    lines = [line for line in flag_lines if line is not None]
    robust = [line for line in lines if line.code in ROBUST_CODES]
    review = [line for line in lines if line.code not in ROBUST_CODES]
    refunds = _refunds(result)
    lo, hi = min(refunds), max(refunds)
    kind = _kind(result)
    min_b = _min_b(result)

    explanation = [f"고시 기준으로 계산한 {kind}: {_breakdown(result)}."]
    if lo != hi:
        explanation.append(
            f"계산 방식에 따라 기준 금액은 {amount_or_range(lo, hi)}입니다."
        )
    explanation.append(
        f"공제한 위약금은 {won(result.penalty)}입니다 "
        f"(고시 위약금 상한 {won(result.penalty_cap)})."
    )
    if result.deposit_refund > 0:
        explanation.append(
            f"보증금 {won(result.deposit_refund)}은 환급액과 별도로, 별도 약정이 없으면 "
            "기준상 전액 환급하도록 되어 있습니다."
        )
    for line in robust:
        explanation.append(line.text)
        if line.code == F.OFFER_BELOW_B.value and min_b is not None:
            explanation.append(
                f"정상가 기준(B)으로 계산한 기준 금액 중 가장 작은 값은 {won(min_b)}입니다."
            )
    explanation += review_lines(review)
    if (basis := basis_line(display.citations)) is not None:
        explanation.append(basis)
    explanation.append(DISCLAIMER_LINE)

    s = rule.source
    company = [
        (
            f"안녕하세요. {INDUSTRY_LABELS[inp.industry]} 이용 계약 중도 해지에 따른 "
            "환급 금액에 관해 확인을 부탁드리고자 연락드립니다."
        ),
        (
            f"「{s.name}」({s.notice_number}) {_formula_label(rule)}의 계산 방식으로 계산하면 "
            f"기준상 {kind}은 {amount_or_range(lo, hi)}으로 안내되어 있습니다."
        ),
    ]
    codes = {line.code for line in robust}
    if F.PENALTY_ABOVE_CAP.value in codes:
        company.append(
            f"계약서상 위약금은 고시의 위약금 상한({won(result.penalty_cap)})보다 커서, "
            "위 금액은 상한을 공제해 계산한 것입니다."
        )
    if F.OFFER_BELOW_B.value in codes and min_b is not None:
        company.append(
            f"안내해 주신 금액은 정상가 기준으로 계산한 기준 금액({won(min_b)})보다 적습니다."
        )
    if result.deposit_refund > 0:
        company.append(
            f"보증금 {won(result.deposit_refund)}은 별도 약정이 없으면 기준상 전액 "
            "환급하도록 되어 있습니다."
        )
    if result.badge == Badge.NEEDS_REVIEW:
        company.append(COMPANY_REVIEW_NOTE)
    company += [COMPANY_CLOSING, DISCLAIMER_LINE]
    return Guide(
        explanation=explanation,
        company_message="\n".join(company),
        citations=display.citations,
    )
