"""가전 P2 사유 코드·안내 코드 (MVP_SPEC 13절, docs/sources/appliance_cases.md 3.4~3.6, 승인 2026-11-15).

공통 코드(CommonFlag)는 세탁과 같은 Enum을 쓰고, 가전 전용 코드는 ApplianceFlag에 둔다.
OFFER_BELOW_STANDARD_MIN·DECISION_SENSITIVE는 세탁과 같은 값을 쓴다 (같은 뜻).
"""

from collections.abc import Iterable
from enum import StrEnum

from rules.laundry_codes import CommonFlag


class ApplianceFlag(StrEnum):
    # ❔ (3.4 순서 2·3·6·7)
    APPLIANCE_ITEM_NOT_SUPPORTED = "APPLIANCE_ITEM_NOT_SUPPORTED"
    PARTS_AVAILABLE = "PARTS_AVAILABLE"
    WITHIN_WARRANTY = "WITHIN_WARRANTY"
    OUTSIDE_PARTS_PERIOD = "OUTSIDE_PARTS_PERIOD"
    # ⚠️
    OFFER_BELOW_STANDARD_MIN = "OFFER_BELOW_STANDARD_MIN"
    # 🔍 계산함
    PERIOD_BOUNDARY = "PERIOD_BOUNDARY"
    PARTS_PERIOD_UNCONFIRMED = "PARTS_PERIOD_UNCONFIRMED"
    CERTIFICATE_UNCONFIRMED = "CERTIFICATE_UNCONFIRMED"
    DECISION_SENSITIVE = "DECISION_SENSITIVE"


class ApplianceNotice(StrEnum):
    RECEIVED_DATE_BASIS = "RECEIVED_DATE_BASIS"
    USED_MONTHS_BASIS = "USED_MONTHS_BASIS"  # 2026-11-15 사용자 지시


ApplianceCode = CommonFlag | ApplianceFlag

C = CommonFlag
A = ApplianceFlag

APPLIANCE_UNDETERMINABLE: frozenset[ApplianceCode] = frozenset(
    {
        C.JUDGMENT_REQUESTED,
        A.APPLIANCE_ITEM_NOT_SUPPORTED,
        A.PARTS_AVAILABLE,
        A.WITHIN_WARRANTY,
        A.OUTSIDE_PARTS_PERIOD,
    }
)
APPLIANCE_NO_CALC: frozenset[ApplianceCode] = frozenset(
    {C.MISSING_REQUIRED, C.INVALID_INPUT}
)
APPLIANCE_ROBUST: frozenset[ApplianceCode] = frozenset({A.OFFER_BELOW_STANDARD_MIN})

# 화면 우선순위 (3.5): ❔ → 🔍 계산 안 함 → ⚠️ → 🔍
APPLIANCE_DISPLAY_PRIORITY: tuple[ApplianceCode, ...] = (
    C.JUDGMENT_REQUESTED,
    A.APPLIANCE_ITEM_NOT_SUPPORTED,
    A.PARTS_AVAILABLE,
    A.WITHIN_WARRANTY,
    A.OUTSIDE_PARTS_PERIOD,
    C.MISSING_REQUIRED,
    C.INVALID_INPUT,
    A.OFFER_BELOW_STANDARD_MIN,
    A.PERIOD_BOUNDARY,
    A.PARTS_PERIOD_UNCONFIRMED,
    A.CERTIFICATE_UNCONFIRMED,
    C.RULE_UNVERIFIED,
    A.DECISION_SENSITIVE,
)


def order_appliance_flags(flags: Iterable[ApplianceCode]) -> list[ApplianceCode]:
    return sorted(set(flags), key=APPLIANCE_DISPLAY_PRIORITY.index)
