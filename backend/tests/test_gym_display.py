"""화면 표시 정보 테스트 (MVP_SPEC 5.4·5.5·5.7, 8.1 VS2).

금액 기대값은 만들지 않는다. 표시 정보가 엔진 결과(GymResult)와 규칙 JSON에서만 나오는지,
문구가 스펙 원문과 같은지 확인한다. 케이스는 test_gym_calc.CASES(검증 완료·승인 35건)다.
"""

import pytest
from test_gym_calc import CASES, Case

from rules.badge import Badge, FlagCode, NoticeCode, order_flags, screen_line
from rules.gym import calculate_refund
from rules.gym_display import (
    CONSULT_CHANNELS,
    DISCLAIMER,
    DRAFT_FLAG_CODES,
    FLAG_TEXTS,
    NOTICE_TEXTS,
    WITHDRAWAL_GUIDE,
    build_display,
    citation_cards,
)
from rules.loader import load_rule

F = FlagCode
N = NoticeCode
RULE = load_rule("gym_refund")

# MVP_SPEC 5.4 표 "화면 한 줄" 원문 (5.2·5.4 문구, 초안)
SPEC_FLAG_TEXTS = {
    F.MISSING_REQUIRED: "계산에 필요한 정보가 빠져 있어 계산하지 않았습니다. 빠진 항목을 입력해 주세요.",
    F.INVALID_INPUT: "입력한 값끼리 맞지 않아 계산하지 않았습니다. 다시 확인해 주세요.",
    F.NOTICE_AFTER_VALIDITY: "해지 의사가 유효기간이 끝난 뒤에 전달되어 이 서비스에서는 계산하지 않습니다. 1372 등 상담 창구에 문의해 주세요.",
    F.OFFER_BELOW_B: "업체 제시액이 정상가 기준으로 계산한 기준 금액보다도 적습니다.",
    F.PENALTY_ABOVE_CAP: "계약서상 위약금이 고시의 위약금 상한(총계약대금의 10%)보다 큽니다. 계산에는 상한을 공제했습니다.",
    F.SCOPE_UNCERTAIN_PT_ONLY: "PT만 계약한 경우 이 기준이 적용되는지 확실하지 않아, 헬스·피트니스 기준으로 계산했습니다.",
    F.PERIOD_ONE_MONTH_BOUNDARY: "계약 기간이 1개월 경계에 있어(날짜를 세는 방식에 따라 28~31일) 이 기준이 적용되는지 확인이 필요합니다.",
    F.REFUND_LIMIT_CLAUSE_UNKNOWN: "계약서에 중도 해지 시 환급 제한이나 위약금 조항이 있는지 확인이 필요합니다.",
    F.WITHDRAWAL_STATUS_UNCONFIRMED: "청약철회 대상이 아니거나 철회 기간이 지났는지 확인되지 않았습니다.",
    F.SESSION_VALIDITY_MISSING: "횟수제 이용권의 유효기간을 입력하지 않아 이 기준의 적용 여부를 확인하지 못했습니다.",
    F.REFUND_BASIS_UNKNOWN: "계약할 때 정한 환급 기준(기간 또는 횟수)을 알 수 없어 두 기준으로 모두 계산했습니다.",
    F.RULE_UNVERIFIED: "계산에 쓴 기준 값 중 원문 확인이 끝나지 않은 값이 있습니다.",
    F.LIST_PRICE_NOT_USABLE: "정상가(할인 전 가격)를 쓸 수 없어 정상가 기준 계산을 하지 못했습니다.",
    F.INTERPRETATION_DEPENDENT: "고시에 이용분 계산 방식이 정해져 있지 않아 금액이 해석에 따라 달라질 수 있습니다.",
    F.USAGE_STARTED: "이용을 시작한 뒤 해지해 이용분 공제가 들어갑니다.",
    F.POSTPONEMENT: "이용 연기 기간이 있어 결과가 달라질 수 있습니다.",
    # 10절 UX 메모 원문
    F.UNSUPPORTED_INDUSTRY: "아직 지원하지 않는 업종입니다. 1372에 문의하세요",
}

# MVP_SPEC 5.5 표·5.3 원문 (결과 화면용)
SPEC_NOTICE_TEXTS = {
    N.NO_LIST_PRICE: "업체가 정상가(할인 전 가격) 기준으로 이용분을 계산하면 환급액이 이보다 적을 수 있습니다.",
    N.LIST_PRICE_BELOW_TOTAL: "정상가를 다시 확인해 주세요.",
    N.OFFER_BETWEEN_A_AND_B: "업체 제시액은 두 계산 방식(실제 부담액 기준 A, 정상가 기준 B)의 결과 사이에 있습니다.",
    N.PENALTY_INPUT_MISSING: "계약서상 위약금을 입력하지 않아 위약금 상한을 공제했습니다. 실제 위약금이 이보다 낮으면 환급액은 더 커집니다.",
    N.STANDARD_TERMS_PENALTY: "표준약관을 사용한 계약이라면 위약금이 이용료의 1/10로 정해져 있어 이 최소 환급액과 실제 환급액이 같거나 가까울 수 있습니다. 계약서의 위약금 조항을 확인해 보세요.",
    N.NEGATIVE_REFUND_ZEROED: "공제 항목의 합계가 지급한 금액보다 커서 기준상 환급액은 0원으로 계산됩니다. 추가로 내야 하는 금액이 있는지는 이 서비스에서 판단하지 않습니다. 1372에 문의해 주세요.",
    N.POSTPONEMENT_INPUT: "연기 기간이 있으면 결과가 달라질 수 있습니다.",
    N.PERIOD_CHECK: "계약서의 이용기간과 연기 내역을 확인해 주세요.",
    N.WITHDRAWAL_INFO: "계약서를 받은 뒤 짧은 기간(방문판매·전화권유판매 14일, 할부계약·통신판매 7일 등) 안이라면 청약철회가 가능할 수 있고, 그 경우에는 이 기준이 적용되지 않습니다.",
    N.PT_ONLY_QUESTION: "PT만 계약하셨나요?",
}

SPEC_WITHDRAWAL_GUIDE = (
    "계약서를 받은 뒤 짧은 기간(방문판매·전화권유판매는 14일, 할부계약·통신판매는 7일 등) "
    "안에 청약을 철회하는 경우에는 이 기준(고시)이 적용되지 않습니다 (고시 제3조 ②). "
    "철회 가능 여부는 1372에 문의해 주세요."
)

# 표현 가드레일 (CLAUDE.md 절대 규칙 5, MVP_SPEC 5.2)
FORBIDDEN_PHRASES = ("무효", "효력이 없", "위법", "받을 수 있")


def all_texts() -> list[str]:
    return [
        *FLAG_TEXTS.values(),
        *NOTICE_TEXTS.values(),
        WITHDRAWAL_GUIDE,
        DISCLAIMER,
        *CONSULT_CHANNELS,
    ]


def test_every_code_has_text() -> None:
    assert set(FLAG_TEXTS) == set(FlagCode)
    assert set(NOTICE_TEXTS) == set(NoticeCode)
    assert all(t.strip() for t in all_texts())


@pytest.mark.parametrize("code", list(SPEC_FLAG_TEXTS), ids=str)
def test_flag_text_matches_spec(code: FlagCode) -> None:
    assert FLAG_TEXTS[code] == SPEC_FLAG_TEXTS[code]


def test_only_undeterminable_codes_are_drafts() -> None:
    """스펙에 문구가 없는 것은 ❔ 사유 7개뿐이다 (승인 대기 보고서)."""
    assert set(FlagCode) - set(SPEC_FLAG_TEXTS) == DRAFT_FLAG_CODES
    assert len(DRAFT_FLAG_CODES) == 7


@pytest.mark.parametrize("code", list(NoticeCode), ids=str)
def test_notice_text_matches_spec(code: NoticeCode) -> None:
    assert NOTICE_TEXTS[code] == SPEC_NOTICE_TEXTS[code]


def test_withdrawal_guide_matches_spec() -> None:
    assert WITHDRAWAL_GUIDE == SPEC_WITHDRAWAL_GUIDE


def test_no_legal_effect_phrases() -> None:
    for text in all_texts():
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in text, text


def test_consult_channels() -> None:
    assert CONSULT_CHANNELS == (
        "1372",
        "한국소비자원 피해구제",
        "대한법률구조공단 ☎132",
    )


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.id)
def test_display_follows_result(c: Case) -> None:
    result = calculate_refund(c.inp, RULE)
    d = build_display(result, RULE)
    assert d.badge == result.badge
    ordered = order_flags(result.flags)
    top = screen_line(result.flags)
    if top is None:
        assert d.screen_line is None and d.other_flags == []
    else:
        assert d.screen_line is not None
        assert d.screen_line.code == top.value
        assert d.screen_line.text == FLAG_TEXTS[top]
        assert [x.code for x in d.other_flags] == [f.value for f in ordered[1:]]
    assert [x.code for x in d.notices] == [n.value for n in result.notices]
    assert [x.id for x in d.citations] == result.citations
    assert d.disclaimer == DISCLAIMER
    assert d.rule_source.notice_number == RULE.source.notice_number
    assert d.rule_source.retrieved_at == RULE.source.retrieved_at
    # 상담 창구: ❔와 계산하지 않은 🔍 중 NOTICE_AFTER_VALIDITY만 (2026-11-06 Q2)
    expect_consult = (
        result.badge == Badge.UNDETERMINABLE or F.NOTICE_AFTER_VALIDITY in result.flags
    )
    assert (d.consult is not None) is expect_consult
    assert (d.withdrawal_guide is not None) is (F.WITHDRAWAL in result.flags)


def test_confirmed_case_has_no_flag_line() -> None:
    c = next(c for c in CASES if c.id == "C1")
    d = build_display(calculate_refund(c.inp, RULE), RULE)
    assert d.badge == Badge.CONFIRMED
    assert d.screen_line is None and d.consult is None


@pytest.mark.parametrize(
    ("case_id", "consult"),
    [("M1", False), ("V1", True), ("V2", True), ("B1", True), ("H1", True)],
)
def test_consult_only_for_undeterminable_and_after_validity(
    case_id: str, consult: bool
) -> None:
    """MISSING_REQUIRED·INVALID_INPUT에는 상담 창구를 붙이지 않는다 (2026-11-06 Q2)."""
    c = next(c for c in CASES if c.id == case_id)
    d = build_display(calculate_refund(c.inp, RULE), RULE)
    assert (d.consult is not None) is consult


def test_invalid_input_has_no_consult() -> None:
    c = next(c for c in CASES if c.id == "P1")
    inp = c.inp.model_copy(update={"paid_amount": c.inp.total_contract_amount + 1})
    result = calculate_refund(inp, RULE)
    assert result.flags == [F.INVALID_INPUT]
    assert build_display(result, RULE).consult is None


def test_disclaimer_is_reference_not_legal_judgment() -> None:
    """고시 원문에 구속력 문구가 없어 '참고 결과이며 법적 판단이 아님'으로 쓴다 (2026-11-06 Q1)."""
    assert "공정거래위원회 고시 기준으로 계산한 참고 결과" in DISCLAIMER
    assert "법적 판단이 아닙니다" in DISCLAIMER
    assert "구속력" not in DISCLAIMER


def test_citation_cards_use_rule_json_text_and_source() -> None:
    ids = sorted(RULE.clause_ids)
    cards = citation_cards(ids, RULE)
    clauses = {c.id: c for c in RULE.clauses}
    related = {c.id: c for c in RULE.related_clauses}
    for card in cards:
        if card.id in clauses:
            assert card.text == clauses[card.id].text
            assert card.label == clauses[card.id].label
            assert card.source.url == RULE.source.url
            assert card.source.retrieved_at == RULE.source.retrieved_at
        else:
            r = related[card.id]
            assert card.text == r.text
            assert card.source.url == r.source.url
            assert card.source.retrieved_at == r.source.retrieved_at


def test_unknown_citation_raises() -> None:
    with pytest.raises(ValueError):
        citation_cards(["no_such_clause"], RULE)
