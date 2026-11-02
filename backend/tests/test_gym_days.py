"""계약 일수·경과 일수·계약 일수 판정 테스트 (MVP_SPEC 5.2, 5.3)."""

from datetime import date

import pytest

from rules.gym import classify_period, contract_days, elapsed_days
from rules.loader import GymRule, load_rule

RULE = load_rule("gym_refund")


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 1, 1), date(2026, 12, 31), 365),  # P1
        (date(2026, 2, 1), date(2026, 2, 28), 28),  # B2
        (date(2026, 3, 1), date(2026, 3, 31), 31),  # B3
        (date(2026, 3, 1), date(2026, 4, 1), 32),  # B4
        (date(2026, 1, 15), date(2027, 1, 14), 365),  # R1 (연도 넘김)
        (date(2028, 2, 1), date(2028, 2, 29), 29),  # 윤년 2월
        (date(2026, 3, 1), date(2026, 3, 1), 1),  # 시작일 = 종료일
    ],
)
def test_contract_days_inclusive(start: date, end: date, expected: int) -> None:
    """계약 일수 = 종료일 − 시작일 + 1 (양끝 포함)."""
    assert contract_days(start, end) == expected


@pytest.mark.parametrize(
    ("notice", "expected"),
    [
        (date(2026, 2, 20), 0),  # 도달일 < 시작일 → 0 (C1)
        (date(2026, 2, 28), 0),  # 시작 하루 전 → 0
        (date(2026, 3, 1), 1),  # 시작일 당일 → 1
        (date(2026, 3, 10), 10),
        (date(2026, 8, 31), 184),  # 종료일 당일 → 계약 일수
        (date(2026, 9, 1), 184),  # 종료일 다음 날 → 계약 일수로 제한
        (date(2027, 5, 1), 184),
    ],
)
def test_elapsed_days_clamped(notice: date, expected: int) -> None:
    """경과 일수 = clamp(도달일 − 시작일 + 1, 0, 계약 일수)."""
    assert elapsed_days(date(2026, 3, 1), notice, 184) == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (None, "unknown"),
        (1, "out_of_scope"),
        (27, "out_of_scope"),
        (28, "needs_review"),
        (31, "needs_review"),
        (32, "ok"),
        (365, "ok"),
    ],
)
def test_classify_period(days: int | None, expected: str) -> None:
    """27 이하 ❔, 28~31 🔍, 32 이상 통과, 날짜 없음은 unknown."""
    assert classify_period(days, RULE) == expected


def test_classify_period_reads_thresholds_from_rule() -> None:
    """경계값은 코드가 아니라 규칙 JSON에서 읽는다."""
    data = RULE.model_dump()
    t = data["params"]["continuous_transaction_criteria"]["period_thresholds_days"]
    t["out_of_scope_below"], t["needs_review_max"] = 30, 35
    other = GymRule.model_validate(data)
    assert classify_period(29, other) == "out_of_scope"
    assert classify_period(30, other) == "needs_review"
    assert classify_period(35, other) == "needs_review"
    assert classify_period(36, other) == "ok"
