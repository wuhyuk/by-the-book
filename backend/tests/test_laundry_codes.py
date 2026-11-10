"""공통·세탁 사유 코드 구성 (MVP_SPEC 12.4, 9절 Q-S1). 헬스장 코드는 바꾸지 않는다."""

from rules.badge import DISPLAY_PRIORITY, FlagCode
from rules.laundry_codes import (
    LAUNDRY_DISPLAY_PRIORITY,
    LAUNDRY_NO_CALC,
    LAUNDRY_REVIEW,
    LAUNDRY_ROBUST,
    LAUNDRY_UNDETERMINABLE,
    CommonFlag,
    LaundryFlag,
    order_laundry_flags,
)


def test_common_codes_exist_in_gym_with_same_values() -> None:
    gym_values = {f.value for f in FlagCode}
    assert {c.value for c in CommonFlag} <= gym_values


def test_gym_display_priority_unchanged_size() -> None:
    """헬스장 우선순위는 헬스장 코드만 담는다 (세탁 코드가 섞이지 않는다)."""
    assert set(DISPLAY_PRIORITY) == set(FlagCode)
    assert not {f.value for f in LaundryFlag} & {f.value for f in FlagCode}


def test_laundry_groups_partition_all_codes() -> None:
    groups = (LAUNDRY_UNDETERMINABLE, LAUNDRY_NO_CALC, LAUNDRY_ROBUST, LAUNDRY_REVIEW)
    union = set().union(*groups)
    assert sum(len(g) for g in groups) == len(union)
    assert union == set(LaundryFlag) | set(CommonFlag)


def test_laundry_display_priority_is_explicit_list() -> None:
    assert len(LAUNDRY_DISPLAY_PRIORITY) == len(set(LAUNDRY_DISPLAY_PRIORITY))
    assert set(LAUNDRY_DISPLAY_PRIORITY) == set(LaundryFlag) | set(CommonFlag)


def test_display_priority_groups_in_badge_order() -> None:
    """❔ → 🔍 계산 안 함 → ⚠️ → 🔍 순으로 묶여 있다 (12.4)."""
    rank = {
        **dict.fromkeys(LAUNDRY_UNDETERMINABLE, 0),
        **dict.fromkeys(LAUNDRY_NO_CALC, 1),
        **dict.fromkeys(LAUNDRY_ROBUST, 2),
        **dict.fromkeys(LAUNDRY_REVIEW, 3),
    }
    ranks = [rank[c] for c in LAUNDRY_DISPLAY_PRIORITY]
    assert ranks == sorted(ranks)


def test_order_laundry_flags_dedups() -> None:
    got = order_laundry_flags(
        [
            LaundryFlag.DECISION_SENSITIVE,
            LaundryFlag.SPECIAL_AGREEMENT,
            LaundryFlag.SPECIAL_AGREEMENT,
        ]
    )
    assert got == [LaundryFlag.SPECIAL_AGREEMENT, LaundryFlag.DECISION_SENSITIVE]
