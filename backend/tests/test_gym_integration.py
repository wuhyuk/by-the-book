"""calculate_refund 통합 테스트 (MVP_SPEC 5.2~5.7).

케이스는 test_gym_calc.CASES(검증 완료·승인 35건)를 그대로 쓴다.
"""

from typing import Any

import pytest
from test_gym_calc import CASES, Case

from rules.badge import Badge, screen_line
from rules.badge import FlagCode as F
from rules.badge import NoticeCode as N
from rules.gym import GymInput, GymResult, calculate_refund
from rules.loader import GymRule, load_rule

RULE = load_rule("gym_refund")
FIRST_STEP = (
    "고시에는 단위대금 산정 방식이 정해져 있지 않아, "
    "실제 부담액 기준(A)과 정상가 기준(B)으로 나누어 계산했습니다."
)


def case(case_id: str) -> Case:
    return next(c for c in CASES if c.id == case_id)


def run(case_id: str, rule: GymRule = RULE) -> GymResult:
    return calculate_refund(case(case_id).inp, rule)


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.id)
def test_case(c: Case) -> None:
    """배지·사유 코드·화면 한 줄·계산 여부·누락 필드·금액·안내 코드."""
    result = calculate_refund(c.inp, RULE)
    exp = c.exp
    assert result.badge == exp.badge
    assert result.calculated is exp.calculated
    assert set(result.flags) == exp.flags
    assert len(result.flags) == len(exp.flags)
    assert screen_line(result.flags) == exp.top  # "현재 순서" 기준 화면 한 줄
    assert result.missing == exp.missing
    if exp.contract_days is not None or exp.calculated:
        assert result.contract_days == exp.contract_days
    if not exp.calculated:
        assert result.results == {}
        assert result.penalty is None and result.penalty_cap is None
        assert result.refund_kind is None
        assert result.notices == []
        assert result.steps == []
        return
    assert result.penalty_cap == exp.penalty_cap
    assert result.penalty == exp.penalty
    assert result.refund_kind == exp.refund_kind
    assert result.deposit_refund == exp.deposit_refund
    assert exp.results is not None
    assert set(result.results) == set(exp.results)
    for basis, (elapsed, units, a, b) in exp.results.items():
        got = result.results[basis]
        assert (got.elapsed, got.units) == (elapsed, units)
        assert (got.A.used_amount, got.A.refund) == a
        assert ((got.B.used_amount, got.B.refund) if got.B else None) == b
    assert set(result.notices) == exp.notices
    assert len(result.notices) == len(exp.notices)


def test_flags_and_notices_are_ordered() -> None:
    """flags는 우선순위 순, notices는 5.5 표 순서다."""
    s3 = run("S3")
    assert s3.flags == [
        F.SCOPE_UNCERTAIN_PT_ONLY,
        F.WITHDRAWAL_STATUS_UNCONFIRMED,
        F.SESSION_VALIDITY_MISSING,
        F.LIST_PRICE_NOT_USABLE,
        F.INTERPRETATION_DEPENDENT,
        F.USAGE_STARTED,
    ]
    assert s3.notices == [
        N.NO_LIST_PRICE,
        N.PENALTY_INPUT_MISSING,
        N.STANDARD_TERMS_PENALTY,
        N.PERIOD_CHECK,
        N.WITHDRAWAL_INFO,
    ]


def test_fixed_steps() -> None:
    """계산 과정 고정 줄 (5.3): 첫 줄, 이용분 반올림 표시, 위약금 내림 표시."""
    for case_id in ("P1", "C1", "U1"):
        steps = run(case_id).steps
        assert steps[0].label == "단위대금 해석"
        assert steps[0].formula == FIRST_STEP
        assert steps[0].amount is None
        used = [s for s in steps if s.label.startswith("이용분")]
        assert used and all(
            "원 단위 반올림(고시에 규정 없음)" in s.formula for s in used
        )
        cap = [s for s in steps if s.label == "위약금 상한"]
        assert len(cap) == 1 and "원 미만 내림(고시에 규정 없음)" in cap[0].formula


def test_steps_amounts_match_results() -> None:
    p1 = run("P1")
    amounts = {s.label: s.amount for s in p1.steps}
    assert amounts["이용분 (일수 기준, A)"] == 295_890
    assert amounts["위약금 상한"] == 120_000
    assert amounts["공제 위약금"] == 120_000
    assert amounts["환급액 (일수 기준, A)"] == 784_110


def test_deposit_separate() -> None:
    """보증금은 환급액과 따로 전액 표시한다 (P5)."""
    p5 = run("P5")
    assert p5.deposit_refund == 100_000
    assert p5.results["period"].A.refund == 455_263
    assert any(s.label == "보증금 환급" and s.amount == 100_000 for s in p5.steps)


BASE_CITATIONS = [
    "art2_2",
    "art2_3",
    "art2_4",
    "art3_1",
    "art4_1",
    "annex_penalty",
    "art5_1",
    "law32_1",
]


@pytest.mark.parametrize(
    ("case_id", "expected"),
    [
        ("P1", BASE_CITATIONS + ["gym_terms_art8_2_def"]),
        ("E2", BASE_CITATIONS),  # 계약서상 위약금 있음 → 표준약관 안내 없음
        ("P5", BASE_CITATIONS + ["art5_2", "gym_terms_art8_2_def"]),
        ("S2", BASE_CITATIONS + ["art6_1", "yoga_terms_art9_1_def"]),
        ("U1", BASE_CITATIONS + ["yoga_terms_art9_1_def"]),
        ("B2", BASE_CITATIONS + ["gym_terms_art8_2_def", "law2_10"]),
        ("B4", BASE_CITATIONS + ["gym_terms_art8_2_def", "law2_10"]),  # 32일
        ("P4", BASE_CITATIONS + ["gym_terms_art8_2_def", "law2_10"]),
        ("B1", ["law2_10"]),
        ("H1", ["law2_10"]),
        ("V1", ["yoga_terms_art5_2"]),
        ("V4", ["yoga_terms_art5_2"]),
        ("V2", []),  # 헬스·피트니스는 해당 원문 없음
        ("M1", []),
    ],
)
def test_citations(case_id: str, expected: list[str]) -> None:
    """5.7 부여 규칙."""
    result = run(case_id)
    assert result.citations == expected
    assert set(result.citations) <= RULE.clause_ids


def test_withdrawal_citation() -> None:
    inp = case("C1").inp.model_copy(update={"is_withdrawal": True})
    result = calculate_refund(inp, RULE)
    assert result.badge == Badge.UNDETERMINABLE
    assert result.flags == [F.WITHDRAWAL]
    assert result.citations == ["art3_2"]


def unverified(path: str) -> GymRule:
    """JSON은 그대로 두고, 모델 복사본에서 블록 verified만 false로 바꾼다."""
    data: dict[str, Any] = RULE.model_dump()
    if path == "penalty_rule":
        for industry in data["industries"]:
            industry["penalty_rule"]["verified"] = False
    else:
        data["params"]["continuous_transaction_criteria"]["verified"] = False
    return GymRule.model_validate(data)


@pytest.mark.parametrize("block", ["penalty_rule", "continuous_transaction_criteria"])
@pytest.mark.parametrize(
    ("case_id", "robust"), [("N2", F.OFFER_BELOW_B), ("K1", F.PENALTY_ABOVE_CAP)]
)
def test_robust_warning_needs_verified_blocks(
    block: str, case_id: str, robust: F
) -> None:
    """블록이 미검증이면 ⚠️ 코드를 flags에서 빼고 RULE_UNVERIFIED만 남긴다 (Q6)."""
    assert robust in run(case_id).flags
    result = run(case_id, unverified(block))
    assert result.badge == Badge.NEEDS_REVIEW
    assert robust not in result.flags
    assert F.RULE_UNVERIFIED in result.flags
    assert set(result.flags) == (case(case_id).exp.flags - {robust}) | {
        F.RULE_UNVERIFIED
    }
    # 금액은 그대로
    assert result.results == run(case_id).results


@pytest.mark.parametrize("block", ["penalty_rule", "continuous_transaction_criteria"])
@pytest.mark.parametrize("case_id", ["C1", "C3", "C4"])
def test_confirmed_needs_verified_blocks(block: str, case_id: str) -> None:
    result = run(case_id, unverified(block))
    assert result.badge == Badge.NEEDS_REVIEW
    assert result.flags == [F.RULE_UNVERIFIED]


def test_unverified_does_not_change_scope_results() -> None:
    """❔·계산 안 함 결과는 블록 검증과 무관하다."""
    for case_id in ("B1", "H1", "M1", "V1"):
        assert run(case_id, unverified("penalty_rule")) == run(case_id)


def test_judgment_requested_overrides_everything() -> None:
    inp = case("N2").inp.model_copy(update={"judgment_requested": True})
    result = calculate_refund(inp, RULE)
    assert result.badge == Badge.UNDETERMINABLE
    assert result.flags == [F.JUDGMENT_REQUESTED]
    assert result.calculated is False


def test_input_is_strict() -> None:
    """금액에 float를 넣으면 모델 생성에서 거부한다."""
    with pytest.raises(ValueError):
        GymInput(**{**case("C1").inp.model_dump(), "paid_amount": 600_000.0})
