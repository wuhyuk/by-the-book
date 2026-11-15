"""가전 P2 설명·업체용 문안 (2026-11-15, 세탁과 같은 템플릿 방식, LLM 없음).

입력은 서버가 다시 계산한 ApplianceResult다. 금액·개월은 결과 필드에서만 가져오고, 사유 문구·안내 문구·인용 카드는
rules/appliance_display.py를 그대로 쓴다. ❔·계산 안 함·RULE_UNVERIFIED이면 업체용 문안을 만들지 않는다.
"""

from guide.common import (
    COMPANY_CLOSING,
    DISCLAIMER_LINE,
    Guide,
    basis_line,
    caveat_line,
    company_message_allowed,
    computed_sentence,
    not_calculated_guide,
    offer_gap_lines,
    review_lines,
    undeterminable_guide,
    won,
)
from rules.appliance import ApplianceInput, ApplianceResult
from rules.appliance_codes import ApplianceFlag
from rules.appliance_display import build_appliance_display
from rules.appliance_rule import ApplianceRule
from rules.badge import Badge

A = ApplianceFlag
ROBUST_CODES = frozenset({A.OFFER_BELOW_STANDARD_MIN.value})
FORMULA_CLAUSE_ID = "elec_5"

# 업체용 문안 단서 (🔍 사유 → 불확실성 항목). 설명에 그 사유가 있을 때만 쓴다.
CAVEAT_PHRASES: dict[str, str] = {
    A.PERIOD_BOUNDARY.value: "품질보증기간·부품보유기간이 끝나는 날의 계산 방식",
    A.PARTS_PERIOD_UNCONFIRMED.value: "부품보유기간(제조일 기산) 이내 접수 여부",
    A.CERTIFICATE_UNCONFIRMED.value: "품질보증서에 적힌 품질보증기간·부품보유기간",
}
SENSITIVITY_PHRASES = {
    "partial_month": "고시에 정해져 있지 않은 사용 개월의 1개월 미만 처리",
    "rounding": "원 미만 처리(내림·반올림)",
    "cap": "구입가 한도 적용 여부",
}


def _caveats(codes: list[str], result: ApplianceResult) -> list[str]:
    phrases: list[str] = []
    for code in codes:
        if code == A.DECISION_SENSITIVE.value:
            phrases += [SENSITIVITY_PHRASES[c] for c in result.sensitivity_causes]
        else:
            phrases.append(CAVEAT_PHRASES[code])
    return phrases


def build_appliance_guide(
    inp: ApplianceInput, result: ApplianceResult, rule: ApplianceRule
) -> Guide:
    display = build_appliance_display(result, rule, inp)
    if result.badge == Badge.UNDETERMINABLE:
        return undeterminable_guide(display.screen_line, display.citations)
    if not result.calculated:
        return not_calculated_guide(
            display.screen_line, display.citations, consult=False
        )
    amount = result.amount
    assert amount is not None and inp.item_key is not None
    lo = result.sensitivity_min if result.sensitivity_min is not None else amount
    hi = result.sensitivity_max if result.sensitivity_max is not None else amount
    item = rule.supported(inp.item_key)
    assert item is not None

    lines = [x for x in [display.screen_line, *display.other_flags] if x is not None]
    robust = [x for x in lines if x.code in ROBUST_CODES]
    review = [x for x in lines if x.code not in ROBUST_CODES]
    explanation = [
        (
            f"고시 기준으로 계산한 환급액은 {won(amount)}입니다 (내용연수 {result.life_months}개월, "
            f"사용 {result.used_months}개월, 정액 감가상각 잔여 금액에 구입가의 10% 가산)."
        ),
        *[n.text for n in display.notices],
    ]
    offer = inp.provider_offer
    for line in robust:
        if offer is not None:
            explanation.append(
                f"업체 제시액 {won(offer)}은 고시 기준으로 계산한 가장 작은 기준 금액 {won(lo)}보다 적습니다."
            )
        else:
            explanation.append(line.text)
    explanation += offer_gap_lines(result.offer_gap)
    explanation += review_lines(review)
    if (basis := basis_line(display.citations)) is not None:
        explanation.append(basis)
    explanation.append(DISCLAIMER_LINE)
    if not company_message_allowed(result.flags):
        return Guide(
            explanation=explanation, company_message=None, citations=display.citations
        )

    s = rule.source
    label = next(c.label for c in rule.clauses if c.id == FORMULA_CLAUSE_ID)
    company = [
        (
            f"안녕하세요. 수리를 맡긴 {item.label}의 수리용 부품이 없어 수리할 수 없다는 안내에 따른 "
            "환급 금액에 관해 확인을 부탁드리고자 연락드립니다."
        ),
        computed_sentence(
            f"「{s.name}」({s.notice_number}) {label}의 계산 방식", "환급액", lo, hi
        ),
    ]
    if robust and offer is not None:
        company.append(
            f"안내해 주신 {won(offer)}은 고시 기준으로 계산한 가장 작은 기준 금액({won(lo)})보다 적습니다."
        )
    if (caveat := caveat_line(_caveats([x.code for x in review], result))) is not None:
        company.append(caveat)
    company += [COMPANY_CLOSING, DISCLAIMER_LINE]
    return Guide(
        explanation=explanation,
        company_message="\n".join(company),
        citations=display.citations,
    )
