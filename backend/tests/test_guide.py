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
    Guide,
)
from guide.gym import build_gym_guide
from guide.laundry import build_laundry_guide
from rules.badge import Badge
from rules.gym import calculate_refund
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
    """고정 문구(템플릿·화면 문구)에 원래 들어 있는 숫자 (1372, 28~31일, 10%, 20배 등)."""
    fixed = [
        *FIXED_TEXTS,
        *GYM_FLAG_TEXTS.values(),
        *GYM_NOTICE_TEXTS.values(),
        *LAUNDRY_FLAG_TEXTS.values(),
        *LAUNDRY_NOTICE_TEXTS.values(),
    ]
    return set().union(*(numbers(t) for t in fixed))


STATIC = static_numbers()


def allowed_numbers(result: Any, g: Guide, rule: Any) -> set[int]:
    """결과 값 + 규칙 원문 라벨(고시 이름·번호, 인용 조항 라벨) + 고정 문구의 숫자."""
    allowed = set(ints(result.model_dump()))
    allowed |= numbers(rule.source.name) | numbers(rule.source.notice_number)
    for card in g.citations:
        allowed |= numbers(card.label)
    return allowed | STATIC


def unexplained_numbers(result: Any, g: Guide, rule: Any) -> set[int]:
    found = set().union(*(numbers(t) for t in texts(g)))
    return found - allowed_numbers(result, g, rule)


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
    lo, hi = min(refunds), max(refunds)
    expected = won(lo) if lo == hi else f"{won(lo)}~{won(hi)}"
    assert g.company_message is not None
    assert f"{expected}으로 안내되어 있습니다" in g.company_message


@pytest.mark.parametrize("cid", LAUNDRY_IDS)
def test_laundry_approved_amounts_in_text(cid: str) -> None:
    c = laundry_case(cid)
    _, g = laundry(c)
    assert c.amount is not None
    assert f"배상액은 {won(c.amount)}입니다" in g.explanation[0]
    lo, hi = (c.sens[0], c.sens[1]) if c.sens else (c.amount, c.amount)
    expected = won(lo) if lo == hi else f"{won(lo)}~{won(hi)}"
    assert g.company_message is not None
    assert f"배상액은 {expected}으로 안내되어 있습니다" in g.company_message
    if c.line is not None:  # 범위 문구는 승인된 화면 한 줄 그대로
        assert f"- {c.line}" in g.explanation


def test_laundry_ratio_details_from_result() -> None:
    """L1: 내용연수·사용일수·배상비율이 승인값 그대로."""
    c = laundry_case("L1")
    _, g = laundry(c)
    assert g.explanation[0] == (
        f"고시 기준으로 계산한 배상액은 {won(280_000)}입니다 "
        f"(내용연수 {c.life_years}년 품목, 사용일수 {c.use_days}일, 배상비율 {c.ratio}%)."
    )


def test_warning_states_fact_only() -> None:
    """⚠️: 제시액이 기준 미만이라는 사실과 비교 금액만 쓴다 (N2: B 240,000원, L8: 160,000원)."""
    _, g = gym(gym_case("N2"))
    assert g.company_message is not None
    assert (
        f"안내해 주신 금액은 정상가 기준으로 계산한 기준 금액({won(240_000)})보다 적습니다."
        in g.company_message
    )
    _, lg = laundry(laundry_case("L8"))
    assert lg.company_message is not None
    assert f"가장 작은 기준 금액({won(160_000)})보다 적습니다." in lg.company_message


# ---- (2) 문안의 모든 숫자는 결과 값에서 온다 ----


@pytest.mark.parametrize("c", GYM_CASES, ids=lambda c: c.id)
def test_gym_numbers_come_from_result(c: GymCase) -> None:
    result, g = gym(c)
    assert unexplained_numbers(result, g, GYM_RULE) == set()


@pytest.mark.parametrize("c", LAUNDRY_CASES, ids=lambda c: c.id)
def test_laundry_numbers_come_from_result(c: LaundryCase) -> None:
    result, g = laundry(c)
    assert unexplained_numbers(result, g, LAUNDRY_RULE) == set()


def test_number_check_catches_made_up_amount() -> None:
    """검사기 자체가 결과에 없는 숫자를 잡는지 확인한다."""
    result, g = gym(gym_case("P1"))
    forged = g.model_copy(update={"explanation": [*g.explanation, "123,457원"]})
    assert unexplained_numbers(result, forged, GYM_RULE) == {123_457}


# ---- (3) ❔·계산 안 함: 금액·업체용 문안 없음 ----


def _no_calc_checks(g: Guide) -> None:
    assert g.company_message is None
    assert not any(AMOUNT.search(t) for t in g.explanation)
    assert DISCLAIMER_LINE in g.explanation


@pytest.mark.parametrize(
    "c",
    [c for c in GYM_CASES if c.exp.badge == Badge.UNDETERMINABLE],
    ids=lambda c: c.id,
)
def test_gym_undeterminable_has_no_amount(c: GymCase) -> None:
    _, g = gym(c)
    _no_calc_checks(g)
    assert CONSULT_1372_LINE in g.explanation


@pytest.mark.parametrize(
    "c",
    [c for c in LAUNDRY_CASES if c.badge == Badge.UNDETERMINABLE],
    ids=lambda c: c.id,
)
def test_laundry_undeterminable_has_no_amount(c: LaundryCase) -> None:
    _, g = laundry(c)
    _no_calc_checks(g)
    assert CONSULT_1372_LINE in g.explanation


def test_not_calculated_review_has_no_amount() -> None:
    """🔍 계산 안 함(L7 누락, L19 입력 오류, 헬스장 누락·유효기간 이후): 금액·업체용 문안 없음."""
    for cid in ["L7", "L19"]:
        _, g = laundry(laundry_case(cid))
        _no_calc_checks(g)
        assert CONSULT_1372_LINE not in g.explanation  # 다시 입력하면 된다
    for c in GYM_CASES:
        if c.exp.badge == Badge.NEEDS_REVIEW and not c.exp.calculated:
            _, g = gym(c)
            _no_calc_checks(g)


# ---- (4) 금지 표현 없음, 고지 한 줄 ----


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


def test_review_does_not_assert() -> None:
    """🔍(계산함): 금액이 달라질 수 있다는 문장을 붙이고 확인 사항을 밝힌다."""
    for c in GYM_CASES:
        if c.exp.badge == Badge.NEEDS_REVIEW and c.exp.calculated:
            _, g = gym(c)
            assert g.company_message is not None
            assert "금액은 달라질 수 있습니다" in g.company_message
            assert "아래 사항에 따라 금액이 달라질 수 있어 확인이 필요합니다." in (
                g.explanation
            )


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
