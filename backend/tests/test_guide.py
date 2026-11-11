"""설명·업체용 문안 테스트 (guide/, 2026-11-11, LLM 없음).

기대 금액은 새로 만들지 않는다. 헬스장은 test_gym_calc.CASES(검증 완료·승인 35건)의 기대값,
세탁은 test_laundry_cases.CASES(승인 L1~L22)의 기대값을 그대로 쓴다.
확인: (1) 승인 케이스 금액이 문안에 그대로 나온다 (2) 문안의 숫자는 모두 결과 값·규칙 원문 라벨·
고정 문구에서 온다 (3) ❔이면 금액과 업체용 문안이 없다 (4) 금지 표현이 없고 고지 한 줄이 있다
(5) 같은 입력이면 같은 문안이 나온다.
"""

import re
from collections.abc import Iterable
from typing import Any

import pytest
from test_gym_calc import CASES as GYM_CASES
from test_gym_calc import Case as GymCase
from test_laundry_cases import BASE as LAUNDRY_BASE
from test_laundry_cases import CASES as LAUNDRY_CASES
from test_laundry_cases import Case as LaundryCase

from guide.common import (
    CONSULT_1372_LINE,
    DISCLAIMER_LINE,
    FIXED_TEXTS,
    FORBIDDEN_TERMS,
    REVIEW_HEADER,
    Guide,
)
from guide.gym import CAVEAT_PHRASES as GYM_CAVEAT_PHRASES
from guide.gym import FACT_CODES as GYM_FACT_CODES
from guide.gym import build_gym_guide
from guide.laundry import build_laundry_guide
from rules.badge import Badge, order_flags
from rules.badge import FlagCode as F
from rules.gym import RefundKind, calculate_refund
from rules.gym_display import FLAG_TEXTS as GYM_FLAG_TEXTS
from rules.gym_display import NOTICE_TEXTS as GYM_NOTICE_TEXTS
from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_display import FLAG_TEXTS as LAUNDRY_FLAG_TEXTS
from rules.laundry_display import NOTICE_TEXTS as LAUNDRY_NOTICE_TEXTS
from rules.laundry_rule import load_laundry_rule
from rules.loader import load_rule

GYM_RULE = load_rule("gym_refund")
LAUNDRY_RULE = load_laundry_rule()

# 사용자가 지정한 헬스장 케이스 + 배지 대표(✅ C1, ⚠️ N2)
GYM_IDS = ["P1", "N3", "R1", "R2", "R3", "S2", "U1", "C1", "N2"]
# 세탁 배지별 대표: ✅ L1·L5·L6·L20, ⚠️ L8, 🔍 계산 L2·L3·L13·L14·L21, ❔ L4·L9·L11, 🔍 계산 안 함 L7·L19
LAUNDRY_IDS = ["L1", "L5", "L6", "L20", "L8", "L2", "L3", "L13", "L14", "L21"]

NUM = re.compile(r"\d[\d,]*")
AMOUNT = re.compile(r"\d[\d,]*원")


def won(n: int) -> str:
    return f"{n:,}원"


def gym(c: GymCase) -> tuple[Any, Guide]:
    result = calculate_refund(c.inp, GYM_RULE)
    return result, build_gym_guide(c.inp, result, GYM_RULE)


def laundry(c: LaundryCase) -> tuple[Any, Guide]:
    inp = LaundryInput(**{**LAUNDRY_BASE, **c.inp})
    result = calculate_damage(inp, LAUNDRY_RULE)
    return result, build_laundry_guide(inp, result, LAUNDRY_RULE)


def gym_case(cid: str) -> GymCase:
    return next(c for c in GYM_CASES if c.id == cid)


def laundry_case(cid: str) -> LaundryCase:
    return next(c for c in LAUNDRY_CASES if c.id == cid)


def texts(g: Guide) -> list[str]:
    return [*g.explanation, *([g.company_message] if g.company_message else [])]


def numbers(text: str) -> set[int]:
    return {int(m.replace(",", "")) for m in NUM.findall(text)}


def ints(value: Any) -> Iterable[int]:
    """결과 객체 안의 정수 값 (문자열 안의 숫자는 넣지 않는다)."""
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from ints(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from ints(v)


def static_numbers() -> set[int]:
    """고정 문구(템플릿·화면 문구)에 원래 들어 있는 숫자 (1372, 28~32일, 10%, 20배 등)."""
    fixed = [
        *FIXED_TEXTS,
        *GYM_FLAG_TEXTS.values(),
        *GYM_NOTICE_TEXTS.values(),
        *LAUNDRY_FLAG_TEXTS.values(),
        *LAUNDRY_NOTICE_TEXTS.values(),
    ]
    return set().union(*(numbers(t) for t in fixed))


STATIC = static_numbers()


def allowed_numbers(result: Any, g: Guide, rule: Any, offer: int | None) -> set[int]:
    """결과 값 + 사용자가 입력한 업체 제시액 + 규칙 원문 라벨 + 고정 문구의 숫자.

    입력값 중에서는 제시액만 인정한다 (⚠️ 문안이 "안내해 주신 ○○원"으로 그대로 옮긴다).
    """
    allowed = set(ints(result.model_dump()))
    allowed |= numbers(rule.source.name) | numbers(rule.source.notice_number)
    for card in g.citations:
        allowed |= numbers(card.label)
    if offer is not None:
        allowed.add(offer)
    return allowed | STATIC


def unexplained_numbers(
    result: Any, g: Guide, rule: Any, offer: int | None = None
) -> set[int]:
    found = set().union(*(numbers(t) for t in texts(g)))
    return found - allowed_numbers(result, g, rule, offer)


def laundry_offer(c: LaundryCase) -> int | None:
    return c.inp.get("provider_offer")


def expected_amount_sentence(kind: str, lo: int, hi: int) -> str:
    if lo == hi:
        return f"계산한 결과 {kind}이 {won(lo)}으로 산정되었습니다."
    return f"계산한 결과 {kind}이 계산 방식에 따라 {won(lo)}~{won(hi)} 범위로 산정되었습니다."


# ---- (1) 승인 케이스의 금액이 그대로 나온다 ----


@pytest.mark.parametrize("cid", GYM_IDS)
def test_gym_approved_amounts_in_text(cid: str) -> None:
    c = gym_case(cid)
    _, g = gym(c)
    exp = c.exp
    assert exp.results is not None and exp.penalty is not None
    explanation = "\n".join(g.explanation)
    refunds: list[int] = []
    for _elapsed, _units, a, b in exp.results.values():
        refunds.append(a[1])
        assert f"실제 부담액 기준(A) {won(a[1])}" in explanation
        if b is not None:
            refunds.append(b[1])
            assert f"정상가 기준(B) {won(b[1])}" in explanation
    assert f"공제한 위약금은 {won(exp.penalty)}" in explanation
    kind = "최소 환급액" if exp.refund_kind == RefundKind.MINIMUM else "환급액"
    assert g.company_message is not None
    sentence = expected_amount_sentence(kind, min(refunds), max(refunds))
    assert sentence in g.company_message


@pytest.mark.parametrize("cid", LAUNDRY_IDS)
def test_laundry_approved_amounts_in_text(cid: str) -> None:
    c = laundry_case(cid)
    _, g = laundry(c)
    assert c.amount is not None
    assert f"배상액은 {won(c.amount)}입니다" in g.explanation[0]
    lo, hi = (c.sens[0], c.sens[1]) if c.sens else (c.amount, c.amount)
    assert g.company_message is not None
    assert expected_amount_sentence("배상액", lo, hi) in g.company_message
    if c.line is not None:  # 범위 문구는 승인된 화면 한 줄 그대로
        assert f"- {c.line}" in g.explanation


def test_company_message_does_not_attribute_amount_to_notice() -> None:
    """금액은 고시가 안내한 값이 아니라 이 서비스가 계산한 값이다 (2026-11-12 지적)."""
    for g in _all_guides():
        for text in texts(g):
            assert "안내되어 있습니다" not in text
            assert "기준상 최소 환급액은" not in text
            assert "기준상 배상액은" not in text


def test_laundry_ratio_details_from_result() -> None:
    """L1: 내용연수·사용일수·배상비율이 승인값 그대로."""
    c = laundry_case("L1")
    _, g = laundry(c)
    assert g.explanation[0] == (
        f"고시 기준으로 계산한 배상액은 {won(280_000)}입니다 "
        f"(내용연수 {c.life_years}년 품목, 사용일수 {c.use_days}일, 배상비율 {c.ratio}%)."
    )


def test_warning_states_fact_with_offer_amount() -> None:
    """⚠️: 사용자가 입력한 제시액과 비교 금액을 사실로만 쓴다.

    N2: 제시액 200,000원 < B 240,000원. L8: 제시액 100,000원 < 160,000원 (승인값).
    """
    _, g = gym(gym_case("N2"))
    assert g.company_message is not None
    assert (
        f"안내해 주신 {won(200_000)}은 정상가 기준으로 계산한 기준 금액"
        f"({won(240_000)})보다 적습니다."
    ) in g.company_message
    assert (
        f"업체 제시액 {won(200_000)}은 정상가 기준(B)으로 계산한 기준 금액 중 "
        f"가장 작은 값 {won(240_000)}보다 적습니다."
    ) in g.explanation
    _, lg = laundry(laundry_case("L8"))
    assert lg.company_message is not None
    assert (
        f"안내해 주신 {won(100_000)}은 고시 기준으로 계산한 가장 작은 기준 금액"
        f"({won(160_000)})보다 적습니다."
    ) in lg.company_message


def test_warning_company_message_has_caveat() -> None:
    """⚠️ N2: 설명의 확인 목록(청약철회·이용분 계산 방식)이 업체용 문안 단서에도 있다."""
    _, g = gym(gym_case("N2"))
    assert g.company_message is not None
    assert (
        "다만 청약철회 해당 여부, 이용분 계산 방식에 따라 금액이 달라질 수 있습니다."
        in g.company_message.splitlines()
    )


def test_usage_started_is_a_fact_line() -> None:
    """N2: '이용을 시작한 뒤 해지…'는 확인 목록이 아니라 별도 줄이다."""
    _, g = gym(gym_case("N2"))
    fact = "이용을 시작한 뒤 해지해 이용분 공제가 들어갑니다."
    assert fact in g.explanation
    assert f"- {fact}" not in g.explanation
    assert g.explanation.index(fact) < g.explanation.index(REVIEW_HEADER)


# ---- (2) 문안의 모든 숫자는 결과 값(과 입력한 제시액)에서 온다 ----


@pytest.mark.parametrize("c", GYM_CASES, ids=lambda c: c.id)
def test_gym_numbers_come_from_result(c: GymCase) -> None:
    result, g = gym(c)
    assert unexplained_numbers(result, g, GYM_RULE, c.inp.provider_offer) == set()


@pytest.mark.parametrize("c", LAUNDRY_CASES, ids=lambda c: c.id)
def test_laundry_numbers_come_from_result(c: LaundryCase) -> None:
    result, g = laundry(c)
    assert unexplained_numbers(result, g, LAUNDRY_RULE, laundry_offer(c)) == set()


def test_number_check_catches_made_up_amount() -> None:
    """검사기 자체가 결과·제시액에 없는 숫자를 잡는지 확인한다 (제시액이 있는 ⚠️ 케이스 포함)."""
    for c in [gym_case("P1"), gym_case("N2")]:
        result, g = gym(c)
        forged = g.model_copy(update={"explanation": [*g.explanation, "123,457원"]})
        found = unexplained_numbers(result, forged, GYM_RULE, c.inp.provider_offer)
        assert found == {123_457}


def test_offer_number_is_only_allowed_as_input() -> None:
    """제시액을 인정하지 않으면 L8 문안의 100,000원이 출처 없는 숫자로 잡힌다.

    (N2의 제시액 200,000원은 A 이용분 200,000원과 우연히 같아 이 확인에 쓸 수 없다.)
    """
    c = laundry_case("L8")
    result, g = laundry(c)
    assert unexplained_numbers(result, g, LAUNDRY_RULE, None) == {100_000}
    assert unexplained_numbers(result, g, LAUNDRY_RULE, laundry_offer(c)) == set()


# ---- (3) ❔·계산 안 함: 금액·업체용 문안 없음, 1372 안내는 한 줄 ----


def _no_calc_checks(g: Guide) -> None:
    assert g.company_message is None
    assert not any(AMOUNT.search(t) for t in g.explanation)
    assert DISCLAIMER_LINE in g.explanation


def _one_1372_line(g: Guide) -> None:
    assert sum("1372" in t for t in g.explanation) == 1


@pytest.mark.parametrize(
    "c",
    [c for c in GYM_CASES if c.exp.badge == Badge.UNDETERMINABLE],
    ids=lambda c: c.id,
)
def test_gym_undeterminable_has_no_amount(c: GymCase) -> None:
    _, g = gym(c)
    _no_calc_checks(g)
    _one_1372_line(g)


@pytest.mark.parametrize(
    "c",
    [c for c in LAUNDRY_CASES if c.badge == Badge.UNDETERMINABLE],
    ids=lambda c: c.id,
)
def test_laundry_undeterminable_has_no_amount(c: LaundryCase) -> None:
    _, g = laundry(c)
    _no_calc_checks(g)
    _one_1372_line(g)


def test_l4_explanation_has_single_1372_line() -> None:
    _, g = laundry(laundry_case("L4"))
    assert CONSULT_1372_LINE not in g.explanation  # 사유 문구에 이미 1372 안내가 있다
    assert len(g.explanation) == 2


def test_not_calculated_review_has_no_amount() -> None:
    """🔍 계산 안 함(L7 누락, L19 입력 오류, 헬스장 누락·유효기간 이후): 금액·업체용 문안 없음."""
    for cid in ["L7", "L19"]:
        _, g = laundry(laundry_case(cid))
        _no_calc_checks(g)
        assert not any("1372" in t for t in g.explanation)  # 다시 입력하면 된다
    for c in GYM_CASES:
        if c.exp.badge == Badge.NEEDS_REVIEW and not c.exp.calculated:
            _, g = gym(c)
            _no_calc_checks(g)
            assert sum("1372" in t for t in g.explanation) <= 1


# ---- (4) 금지 표현 없음, 고지 한 줄, 단서 ----


def _all_guides() -> list[Guide]:
    return [gym(c)[1] for c in GYM_CASES] + [laundry(c)[1] for c in LAUNDRY_CASES]


def test_no_forbidden_terms_and_disclaimer_everywhere() -> None:
    for g in _all_guides():
        for text in texts(g):
            for term in FORBIDDEN_TERMS:
                assert term not in text, term
        assert g.explanation.count(DISCLAIMER_LINE) == 1
        if g.company_message is not None:
            assert g.company_message.splitlines().count(DISCLAIMER_LINE) == 1


def _caveat(g: Guide) -> str | None:
    assert g.company_message is not None
    lines = g.company_message.splitlines()
    return next((x for x in lines if x.startswith("다만 ")), None)


def test_company_caveat_iff_explanation_has_uncertainty() -> None:
    """업체용 문안 단서는 설명에 확인 목록이 있을 때만, 있으면 반드시 붙는다 (⚠️ 포함).

    🔍(계산함)는 확인 목록이 늘 있으므로 단서도 늘 있다. ⚠️는 불확실성이 없으면(L8처럼 범위가
    한 값이고 감액 주장 등이 없으면) 단서를 지어내지 않는다.
    """
    pairs = [gym(c) for c in GYM_CASES] + [laundry(c) for c in LAUNDRY_CASES]
    for result, g in pairs:
        if g.company_message is None:
            continue
        caveat = _caveat(g)
        assert (caveat is not None) == (REVIEW_HEADER in g.explanation)
        if result.badge == Badge.NEEDS_REVIEW:
            assert caveat is not None
    _, l8 = laundry(laundry_case("L8"))
    assert REVIEW_HEADER not in l8.explanation and _caveat(l8) is None


def test_gym_caveat_matches_review_items() -> None:
    """헬스장: 단서 항목은 설명 확인 목록의 사유와 하나씩 대응한다 (없는 불확실성을 만들지 않음)."""
    for c in GYM_CASES:
        result, g = gym(c)
        if g.company_message is None:
            continue
        review = [f for f in order_flags(result.flags) if f.value in GYM_CAVEAT_PHRASES]
        caveat = _caveat(g)
        if not review:
            assert caveat is None
            continue
        assert caveat is not None
        assert caveat == (
            "다만 "
            + ", ".join(GYM_CAVEAT_PHRASES[f.value] for f in review)
            + "에 따라 금액이 달라질 수 있습니다."
        )
        for f in review:
            assert f"- {GYM_FLAG_TEXTS[f]}" in g.explanation


def test_gym_caveat_covers_every_review_code() -> None:
    """계산함 🔍 사유 코드는 단서 말이 있거나 사실 줄로 분류된다 (둘 중 하나만)."""
    review_codes = {
        F.SCOPE_UNCERTAIN_PT_ONLY, F.PERIOD_ONE_MONTH_BOUNDARY,
        F.REFUND_LIMIT_CLAUSE_UNKNOWN, F.WITHDRAWAL_STATUS_UNCONFIRMED,
        F.SESSION_VALIDITY_MISSING, F.REFUND_BASIS_UNKNOWN, F.RULE_UNVERIFIED,
        F.LIST_PRICE_NOT_USABLE, F.INTERPRETATION_DEPENDENT, F.USAGE_STARTED,
        F.POSTPONEMENT,
    }  # fmt: skip
    for code in review_codes:
        assert (code.value in GYM_CAVEAT_PHRASES) != (code.value in GYM_FACT_CODES)


def test_laundry_caveat_matches_sensitivity_causes() -> None:
    """세탁 L2(사용일수)·L3(원 미만)·L21(둘 다)·L13(특약): 단서가 실제 원인만 말한다."""
    days = "고시에 정해져 있지 않은 사용일수 산입 방식(구입일을 세는지)"
    rounding = "원 미만 처리(내림·반올림)"
    tail = "에 따라 금액이 달라질 수 있습니다."
    expected = {
        "L2": f"다만 {days}{tail}",
        "L3": f"다만 {rounding}{tail}",
        "L21": f"다만 {days}, {rounding}{tail}",
        "L13": f"다만 배상에 관한 특약{tail}",
    }
    for cid, line in expected.items():
        _, g = laundry(laundry_case(cid))
        assert _caveat(g) == line, cid
    for cid in ["L1", "L5", "L6", "L8", "L20", "L22"]:
        _, g = laundry(laundry_case(cid))
        assert _caveat(g) is None, cid


# ---- 세탁 표 인용 카드: 적용한 칸 (2026-11-12) ----


def _card(g: Guide, cid: str) -> str:
    return next(c.text for c in g.citations if c.id == cid)


def test_laundry_table_cards_show_applied_cells() -> None:
    """승인값(내용연수·사용일수·배상비율)과 원문 표의 칸 구간이 카드에 그대로 나온다."""
    expected = {
        # L1: 신사정장 동복 4년, 334일 → 4년 행 178~357일 칸 70%
        "L1": ("적용한 품목: 신사정장 (동복) → 내용연수 4년",
               ("적용한 칸: 내용연수 4년 행, 사용일수 178~357일 칸 (이번 사용일수 334일) "
               "→ 배상비율 70%")),
        # L6: 카페트 모 6년, 3,286일 → 6년 행 마지막 칸 10%
        "L6": ("적용한 품목: 카페트 (모) → 내용연수 6년",
               ("적용한 칸: 내용연수 6년 행, 사용일수 3,286일 이상 칸 (이번 사용일수 3,286일) "
               "→ 배상비율 10%")),
        # L20: 한복류 4년, 311일 → 70%
        "L20": ("적용한 품목: 치마, 저고리, 바지, 마고자, 조끼, 두루마기 → 내용연수 4년",
                ("적용한 칸: 내용연수 4년 행, 사용일수 178~357일 칸 (이번 사용일수 311일) "
                "→ 배상비율 70%")),
    }  # fmt: skip
    for cid, (item, cell) in expected.items():
        _, g = laundry(laundry_case(cid))
        assert _card(g, "laundry_lifespan_table").splitlines()[-1] == item, cid
        assert _card(g, "laundry_ratio_table").splitlines()[-1] == cell, cid


def test_laundry_ratio_card_shows_alternative_cell_when_use_days_sensitive() -> None:
    """L2(셔츠류 2년, 28일 95% / 대안 80%)·L14(코트 4년, 357일 70% / 대안 60%)."""
    expected = {
        "L2": [("적용한 칸: 내용연수 2년 행, 사용일수 0~28일 칸 (이번 사용일수 28일) "
               "→ 배상비율 95%"),
               ("사용일수 산입 방식(구입일을 세는지)에 따라 갈리는 칸: 내용연수 2년 행, "
               "사용일수 29~88일 칸 → 배상비율 80%")],
        "L14": [("적용한 칸: 내용연수 4년 행, 사용일수 178~357일 칸 (이번 사용일수 357일) "
                "→ 배상비율 70%"),
                ("사용일수 산입 방식(구입일을 세는지)에 따라 갈리는 칸: 내용연수 4년 행, "
                "사용일수 358~537일 칸 → 배상비율 60%")],
    }  # fmt: skip
    for cid, lines in expected.items():
        _, g = laundry(laundry_case(cid))
        assert _card(g, "laundry_ratio_table").splitlines()[-2:] == lines, cid
    # 원 미만 처리만 원인인 L3은 대안 칸을 적지 않는다 (배상비율이 같다)
    _, g3 = laundry(laundry_case("L3"))
    assert "갈리는 칸" not in _card(g3, "laundry_ratio_table")


def test_laundry_cards_keep_source_line_and_skip_fallback() -> None:
    """원문 한 줄은 그대로 앞에 남는다. 20배(L5)는 표를 쓰지 않아 표 카드가 없다."""
    _, g = laundry(laundry_case("L2"))
    rule_text = {c.id: c.text for c in LAUNDRY_RULE.clauses}
    for cid in ["laundry_ratio_table", "laundry_lifespan_table"]:
        assert _card(g, cid).startswith(rule_text[cid] + "\n")
    _, g5 = laundry(laundry_case("L5"))
    assert not {c.id for c in g5.citations} & {
        "laundry_ratio_table",
        "laundry_lifespan_table",
    }


# ---- (5) 결정성 ----


def test_deterministic() -> None:
    first = [g.model_dump() for g in _all_guides()]
    second = [g.model_dump() for g in _all_guides()]
    assert first == second


def test_citations_are_display_cards() -> None:
    """인용은 표시 단계의 카드를 그대로 쓴다 (새 인용을 만들지 않음)."""
    result, g = gym(gym_case("P1"))
    assert [c.id for c in g.citations] == result.citations
    lresult, lg = laundry(laundry_case("L1"))
    assert [c.id for c in lg.citations] == lresult.citations
