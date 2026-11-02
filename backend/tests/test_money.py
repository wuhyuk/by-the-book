"""금액 반올림·내림 함수 테스트 (MVP_SPEC 5.3 반올림, 5.9)."""

from decimal import Decimal

import pytest

from rules.money import div_round_half_up, penalty_cap


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (300_003, 6, 50_001),  # R2: 50,000.5 → 50,001 (정확히 .5는 올림)
        (100_001, 2, 50_001),  # .5 → 올림
        (4_999, 10, 500),  # 499.9 → 500
        (4_949, 10, 495),  # 494.9 → 495
        (49, 100, 0),  # .49 → 내림
        (51, 100, 1),  # .51 → 올림
        (50, 100, 1),  # .50 → 올림
        (0, 365, 0),  # 분자 0
        (12_345, 1, 12_345),  # 분모 1
        (1_200_000 * 90, 365, 295_890),  # P1: 295,890.41… → 295,890
    ],
)
def test_div_round_half_up(numerator: int, denominator: int, expected: int) -> None:
    """곱셈 결과를 한 번만 나눠 원 단위 half up으로 반올림한다."""
    assert div_round_half_up(numerator, denominator) == expected


def test_div_round_half_up_returns_int() -> None:
    """결과는 int다 (float 금지)."""
    assert type(div_round_half_up(7, 2)) is int


@pytest.mark.parametrize(("numerator", "denominator"), [(1, 0), (1, -3), (-1, 3)])
def test_div_round_half_up_rejects_out_of_domain(
    numerator: int, denominator: int
) -> None:
    """분모가 0 이하이거나 분자가 음수이면 오류를 낸다."""
    with pytest.raises(ValueError):
        div_round_half_up(numerator, denominator)


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (999_999, 99_999),  # R3: 99,999.9 → 99,999 (원 미만 내림)
        (1_200_000, 120_000),
        (9, 0),  # 0.9 → 0
        (10, 1),
        (0, 0),
        (300_003, 30_000),  # R2: 30,000.3 → 30,000
    ],
)
def test_penalty_cap_floors(total: int, expected: int) -> None:
    """위약금 상한은 총계약대금 × 비율을 원 미만 내림한다."""
    assert penalty_cap(total, Decimal("0.10")) == expected


def test_penalty_cap_returns_int() -> None:
    """결과는 int다."""
    assert type(penalty_cap(999_999, Decimal("0.10"))) is int


def test_penalty_cap_rejects_float_ratio() -> None:
    """비율은 Decimal만 받는다 (float 금지)."""
    with pytest.raises(TypeError):
        penalty_cap(1_000, 0.1)  # type: ignore[arg-type]
