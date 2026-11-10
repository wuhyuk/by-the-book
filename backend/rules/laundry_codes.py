"""공통·세탁 사유 코드와 안내 코드 (MVP_SPEC 12.4·12.5, 9절 2026-11-02 Q-S1).

공통 Enum(CommonFlag)과 품목별 Enum(LaundryFlag)을 나누고, 세탁의 코드 집합과 화면 우선순위는
아래 명시 목록으로 둔다. 헬스장 코드(rules/badge.py FlagCode)는 이름·값·순서를 바꾸지 않는다.
헬스장 FlagCode는 공통 코드와 같은 값의 멤버를 그대로 갖는다 (tests/test_laundry_codes.py에서 확인).
"""

from collections.abc import Iterable
from enum import StrEnum


class CommonFlag(StrEnum):
    """모든 품목이 같은 뜻으로 쓰는 사유 코드."""

    JUDGMENT_REQUESTED = "JUDGMENT_REQUESTED"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    INVALID_INPUT = "INVALID_INPUT"
    RULE_UNVERIFIED = "RULE_UNVERIFIED"


class LaundryFlag(StrEnum):
    """세탁 전용 사유 코드 (12.2, 12.4)."""

    # ❔ 판단 불가 (12.2 순서 2~7)
    UNSUPPORTED_SERVICE = "UNSUPPORTED_SERVICE"
    UNSUPPORTED_DAMAGE = "UNSUPPORTED_DAMAGE"
    MANUFACTURING_CAUSE = "MANUFACTURING_CAUSE"
    SET_PARTIAL_UNSUPPORTED = "SET_PARTIAL_UNSUPPORTED"
    ATTACHMENT_UNSUPPORTED = "ATTACHMENT_UNSUPPORTED"
    ITEM_NOT_IN_TABLE = "ITEM_NOT_IN_TABLE"
    # ⚠️ 강건한 주의 신호
    OFFER_BELOW_STANDARD_MIN = "OFFER_BELOW_STANDARD_MIN"
    # 🔍 계산함
    EXEMPTION_CLAIMED = "EXEMPTION_CLAIMED"
    SPECIAL_AGREEMENT = "SPECIAL_AGREEMENT"
    PARTIAL_FAULT_CLAIMED = "PARTIAL_FAULT_CLAIMED"
    DAMAGED_ITEM_RETURN = "DAMAGED_ITEM_RETURN"
    DECISION_SENSITIVE = "DECISION_SENSITIVE"


class LaundryNotice(StrEnum):
    """세탁 안내 코드 (12.5). 배지 판정에 쓰지 않는다."""

    RESTORE_FIRST = "RESTORE_FIRST"
    UNPROVEN_FALLBACK = "UNPROVEN_FALLBACK"
    RECEIPT_BASIS = "RECEIPT_BASIS"
    NO_RECEIPT_LOSS = "NO_RECEIPT_LOSS"
    LAUNDRY_FEE_TERMS = "LAUNDRY_FEE_TERMS"
    CLAIM_PERIOD_TERMS = "CLAIM_PERIOD_TERMS"


LaundryCode = CommonFlag | LaundryFlag

C = CommonFlag
L = LaundryFlag

# 12.2 순서 1~7 (❔), 순서 8~9 (🔍 계산 안 함)
LAUNDRY_UNDETERMINABLE: frozenset[LaundryCode] = frozenset(
    {
        C.JUDGMENT_REQUESTED,
        L.UNSUPPORTED_SERVICE,
        L.UNSUPPORTED_DAMAGE,
        L.MANUFACTURING_CAUSE,
        L.SET_PARTIAL_UNSUPPORTED,
        L.ATTACHMENT_UNSUPPORTED,
        L.ITEM_NOT_IN_TABLE,
    }
)
LAUNDRY_NO_CALC: frozenset[LaundryCode] = frozenset(
    {C.MISSING_REQUIRED, C.INVALID_INPUT}
)
LAUNDRY_ROBUST: frozenset[LaundryCode] = frozenset({L.OFFER_BELOW_STANDARD_MIN})
LAUNDRY_REVIEW: frozenset[LaundryCode] = frozenset(
    {
        L.EXEMPTION_CLAIMED,
        L.SPECIAL_AGREEMENT,
        L.PARTIAL_FAULT_CLAIMED,
        L.DAMAGED_ITEM_RETURN,
        C.RULE_UNVERIFIED,
        L.DECISION_SENSITIVE,
    }
)

# 세탁 결과에 나올 수 있는 코드 전체 = 화면 우선순위 (12.4 표 순서, 초안).
LAUNDRY_DISPLAY_PRIORITY: tuple[LaundryCode, ...] = (
    C.JUDGMENT_REQUESTED,
    L.UNSUPPORTED_SERVICE,
    L.UNSUPPORTED_DAMAGE,
    L.MANUFACTURING_CAUSE,
    L.SET_PARTIAL_UNSUPPORTED,
    L.ATTACHMENT_UNSUPPORTED,
    L.ITEM_NOT_IN_TABLE,
    C.MISSING_REQUIRED,
    C.INVALID_INPUT,
    L.OFFER_BELOW_STANDARD_MIN,
    L.EXEMPTION_CLAIMED,
    L.SPECIAL_AGREEMENT,
    L.PARTIAL_FAULT_CLAIMED,
    L.DAMAGED_ITEM_RETURN,
    C.RULE_UNVERIFIED,
    L.DECISION_SENSITIVE,
)


def order_laundry_flags(flags: Iterable[LaundryCode]) -> list[LaundryCode]:
    """세탁 사유 코드를 화면 우선순위 순으로 정렬한다 (중복 제거)."""
    return sorted(set(flags), key=LAUNDRY_DISPLAY_PRIORITY.index)
