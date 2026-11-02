"""금액 계산 도구 (MVP_SPEC 5.3 반올림 규칙).

금액은 int(원 단위), 비율은 Decimal로만 다룬다. float는 쓰지 않는다.
"""

from decimal import ROUND_FLOOR, Decimal
from fractions import Fraction

_HALF = Fraction(1, 2)


def div_round_half_up(numerator: int, denominator: int) -> int:
    """numerator ÷ denominator를 원 단위 half up으로 한 번만 반올림한다.

    곱셈은 호출하는 쪽에서 먼저 끝내고(예: 총계약대금 × 경과), 여기서 한 번만 나눈다.
    분모는 1 이상, 분자는 0 이상이어야 한다.
    """
    if denominator <= 0:
        raise ValueError("분모는 1 이상이어야 합니다.")
    if numerator < 0:
        raise ValueError("분자는 0 이상이어야 합니다.")
    quotient = Fraction(numerator, denominator)
    floor = quotient.numerator // quotient.denominator
    return floor + 1 if quotient - floor >= _HALF else floor


def penalty_cap(total: int, ratio: Decimal) -> int:
    """위약금 상한 = 총계약대금 × 비율, 원 미만 내림."""
    if not isinstance(ratio, Decimal):
        raise TypeError("비율은 Decimal이어야 합니다.")
    return int((Decimal(total) * ratio).to_integral_value(rounding=ROUND_FLOOR))
