"""배지 판정·화면 한 줄 우선순위 테스트 (MVP_SPEC 5.4)."""

import itertools
from datetime import date
from typing import Any

import pytest

from rules.badge import (
    DISPLAY_PRIORITY,
    NO_CALC_CODES,
    REVIEW_CODES,
    ROBUST_CODES,
    UNDETERMINABLE_CODES,
    Badge,
    FlagCode,
    decide_badge,
    order_flags,
    screen_line,
)
from rules.badge import FlagCode as F
from rules.gym import GymInput, GymResult, calculate_refund
from rules.loader import load_rule

RULE = load_rule("gym_refund")


@pytest.mark.parametrize(
    ("j", "m", "r", "i"), list(itertools.product([False, True], repeat=4))
)
def test_truth_table(j: bool, m: bool, r: bool, i: bool) -> None:
    """16조합 모두 배지가 정확히 하나로 정해지고, 5.4 진리표와 같다."""
    badge = decide_badge(
        judgment_requested=False,
        out_of_scope=j,
        missing_or_invalid=m,
        robust_warnings=[F.OFFER_BELOW_B] if r else [],
        review_flags=[F.INTERPRETATION_DEPENDENT] if i else [],
    )
    assert isinstance(badge, Badge)
    if j:
        assert badge == Badge.UNDETERMINABLE
    elif m:
        assert badge == Badge.NEEDS_REVIEW
    elif r:
        assert badge == Badge.WARNING
    elif i:
        assert badge == Badge.NEEDS_REVIEW
    else:
        assert badge == Badge.CONFIRMED
    # ✅는 사유가 하나도 없을 때만
    assert (badge == Badge.CONFIRMED) == (not (j or m or r or i))


def test_judgment_requested_is_undeterminable() -> None:
    badge = decide_badge(
        judgment_requested=True,
        out_of_scope=False,
        missing_or_invalid=False,
        robust_warnings=[],
        review_flags=[],
    )
    assert badge == Badge.UNDETERMINABLE


def test_badge_values() -> None:
    assert [b.value for b in Badge] == [
        "❔ 판단 불가",
        "🔍 추가 확인 필요",
        "⚠️ 주의 신호",
        "✅ 기준 확인",
    ]


def test_code_groups_partition_flag_codes() -> None:
    """사유 코드는 ❔ / 🔍 계산 안 함 / ⚠️ / 🔍 네 묶음 중 정확히 하나에 속한다."""
    groups = [UNDETERMINABLE_CODES, NO_CALC_CODES, ROBUST_CODES, REVIEW_CODES]
    assert set().union(*groups) == set(FlagCode)
    assert sum(len(g) for g in groups) == len(FlagCode)
    assert ROBUST_CODES == {F.OFFER_BELOW_B, F.PENALTY_ABOVE_CAP}
    assert NO_CALC_CODES == {
        F.MISSING_REQUIRED,
        F.INVALID_INPUT,
        F.NOTICE_AFTER_VALIDITY,
    }


def test_display_priority_covers_every_code_once() -> None:
    assert len(DISPLAY_PRIORITY) == len(set(DISPLAY_PRIORITY)) == len(FlagCode)


def test_display_priority_keeps_grade_order() -> None:
    """등급 순(❔ → 🔍 계산 안 함 → ⚠️ → 🔍 계산함)은 단계 6에서 순서를 바꿔도 지킨다."""
    grade = {
        **{c: 0 for c in UNDETERMINABLE_CODES},
        **{c: 1 for c in NO_CALC_CODES},
        **{c: 2 for c in ROBUST_CODES},
        **{c: 3 for c in REVIEW_CODES},
    }
    grades = [grade[c] for c in DISPLAY_PRIORITY]
    assert grades == sorted(grades)


def test_screen_line_uses_priority_constant() -> None:
    """화면 한 줄은 DISPLAY_PRIORITY에서 가장 앞선 코드다."""
    for size in (1, 2, 3):
        for combo in itertools.combinations(list(FlagCode), size):
            flags = list(reversed(combo))
            expected = min(flags, key=DISPLAY_PRIORITY.index)
            assert screen_line(flags) == expected
            assert order_flags(flags) == sorted(flags, key=DISPLAY_PRIORITY.index)
    assert screen_line([]) is None


# ✅ 조건 ①~⑧을 하나씩 깨는 테스트. 바탕은 C1(사용자 승인 케이스, ✅).
C1: dict[str, Any] = {
    "judgment_requested": False,
    "industry": "fitness",
    "termination_cause": "consumer",
    "contract_type": "period",
    "total_contract_amount": 600_000,
    "paid_amount": 600_000,
    "start_date": date(2026, 3, 1),
    "end_date": date(2026, 8, 31),
    "notice_date": date(2026, 2, 20),
    "has_refund_limit_clause": True,
    "list_price": 600_000,
    "withdrawal_cleared": True,
    "had_postponement": False,
}


def run(**changes: Any) -> GymResult:
    return calculate_refund(GymInput(**{**C1, **changes}), RULE)


def test_c1_is_confirmed() -> None:
    result = run()
    assert result.badge == Badge.CONFIRMED
    assert result.flags == []


@pytest.mark.parametrize(
    ("changes", "flag"),
    [
        ({"notice_date": date(2026, 3, 1)}, F.USAGE_STARTED),  # ① 시작 전 해지 아님
        (
            {"start_date": date(2026, 3, 1), "end_date": date(2026, 3, 31)},
            F.PERIOD_28_TO_31_DAYS,
        ),  # ② 계약 일수 31
        (
            {"start_date": date(2026, 3, 1), "end_date": date(2026, 4, 1)},
            F.PERIOD_28_TO_31_DAYS,
        ),  # ② 계약 일수 32 (한쪽 끝만 세면 31) [결정 2026-11-06 (a)]
        ({"has_refund_limit_clause": None}, F.REFUND_LIMIT_CLAUSE_UNKNOWN),  # ③
        ({"withdrawal_cleared": None}, F.WITHDRAWAL_STATUS_UNCONFIRMED),  # ④
        ({"withdrawal_cleared": False}, F.WITHDRAWAL_STATUS_UNCONFIRMED),
        ({"list_price": 599_999}, F.LIST_PRICE_NOT_USABLE),  # ⑤ 정상가 < 총계약대금
        ({"is_pt_only": True}, F.SCOPE_UNCERTAIN_PT_ONLY),  # ⑧
    ],
)
def test_breaking_one_confirmed_condition(changes: dict[str, Any], flag: F) -> None:
    result = run(**changes)
    assert result.badge == Badge.NEEDS_REVIEW
    assert flag in result.flags


def test_contract_33_days_is_confirmed() -> None:
    """② 계약 일수 33이면 두 방식(양끝 33, 한쪽 끝 32) 모두 32 이상이라 ✅ (5.2)."""
    result = run(start_date=date(2026, 3, 1), end_date=date(2026, 4, 2))
    assert result.contract_days == 33
    assert result.badge == Badge.CONFIRMED
    assert result.flags == []


def test_breaking_robust_condition() -> None:
    """⑦ 강건한 ⚠️가 있으면 ✅가 아니다."""
    result = run(contract_penalty=60_001)
    assert result.badge == Badge.WARNING
    assert result.flags == [F.PENALTY_ABOVE_CAP]


def test_breaking_verified_condition() -> None:
    """⑥ 쓰는 블록이 verified: false이면 ✅가 아니다."""
    data = RULE.model_dump()
    data["industries"][0]["penalty_rule"]["verified"] = False
    unverified = type(RULE).model_validate(data)
    result = calculate_refund(GymInput(**C1), unverified)
    assert result.badge == Badge.NEEDS_REVIEW
    assert result.flags == [F.RULE_UNVERIFIED]


def test_postponement_not_used_for_confirmed() -> None:
    """had_postponement는 ✅ 판정에 쓰지 않는다 (시작 전 해지, C3)."""
    result = run(had_postponement=True)
    assert result.badge == Badge.CONFIRMED


def test_usage_started_when_dates_missing() -> None:
    """시작일·도달일이 없어 시작 전 해지를 확인하지 못하면 USAGE_STARTED (5.4)."""
    inp = GymInput(
        judgment_requested=False,
        industry="fitness",
        termination_cause="consumer",
        contract_type="session",
        total_contract_amount=600_000,
        paid_amount=600_000,
        total_sessions=10,
        used_sessions=0,
        has_refund_limit_clause=True,
        list_price=600_000,
        withdrawal_cleared=True,
    )
    result = calculate_refund(inp, RULE)
    assert F.USAGE_STARTED in result.flags
    assert result.badge == Badge.NEEDS_REVIEW


def test_penalty_equal_to_cap_is_not_warning() -> None:
    """계약서상 위약금 = 상한이면 PENALTY_ABOVE_CAP이 아니고(5.4 '>'), 그대로 공제한다(5.3 '≤')."""
    result = run(contract_penalty=60_000)
    assert result.badge == Badge.CONFIRMED
    assert result.flags == []
    assert result.penalty == 60_000


def test_both_robust_warnings_screen_line_current_order() -> None:
    """현재 5.4 표 순서: PENALTY_ABOVE_CAP(3) → OFFER_BELOW_B(4).

    N2(사용자 승인 케이스) 입력에 상한을 넘는 계약서상 위약금을 더한 조합이다.
    단계 6에서 DISPLAY_PRIORITY를 바꾸면 이 테스트의 기대값도 함께 바꾼다.
    """
    inp = GymInput(
        judgment_requested=False,
        industry="yoga_pilates",
        termination_cause="consumer",
        contract_type="session",
        refund_basis="session",
        total_contract_amount=600_000,
        paid_amount=600_000,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 8, 31),
        notice_date=date(2026, 5, 1),
        total_sessions=30,
        used_sessions=10,
        has_refund_limit_clause=True,
        list_price=900_000,
        contract_penalty=60_001,
        provider_offer=200_000,
    )
    result = calculate_refund(inp, RULE)
    assert result.badge == Badge.WARNING
    assert result.flags[:2] == [F.PENALTY_ABOVE_CAP, F.OFFER_BELOW_B]
    assert screen_line(result.flags) == F.PENALTY_ABOVE_CAP
