"""상태 배지·사유 코드·안내 코드·화면 한 줄 우선순위 (MVP_SPEC 5.2, 5.4, 5.5).

배지는 규칙 코드가 정한다 (CLAUDE.md 절대 규칙 3). 화면 한 줄 우선순위는 DISPLAY_PRIORITY 하나로 둔다.
"""

from collections.abc import Iterable
from enum import StrEnum


class Badge(StrEnum):
    """결과 상태 배지 4종."""

    UNDETERMINABLE = "❔ 판단 불가"
    NEEDS_REVIEW = "🔍 추가 확인 필요"
    WARNING = "⚠️ 주의 신호"
    CONFIRMED = "✅ 기준 확인"


class FlagCode(StrEnum):
    """❔·🔍·⚠️ 사유 코드 (5.2, 5.4)."""

    # ❔ 판단 불가 (5.2 순서 1~8)
    JUDGMENT_REQUESTED = "JUDGMENT_REQUESTED"
    UNSUPPORTED_INDUSTRY = "UNSUPPORTED_INDUSTRY"
    ACADEMY_LAW = "ACADEMY_LAW"
    WITHDRAWAL = "WITHDRAWAL"
    BUSINESS_FAULT = "BUSINESS_FAULT"
    FORCE_MAJEURE = "FORCE_MAJEURE"
    PERIOD_UNDER_28_DAYS = "PERIOD_UNDER_28_DAYS"
    NO_REFUND_LIMIT_CLAUSE = "NO_REFUND_LIMIT_CLAUSE"
    # 🔍 계산 안 함 (5.2 순서 9~11)
    MISSING_REQUIRED = "MISSING_REQUIRED"
    INVALID_INPUT = "INVALID_INPUT"
    NOTICE_AFTER_VALIDITY = "NOTICE_AFTER_VALIDITY"
    # ⚠️ 강건한 주의 신호
    OFFER_BELOW_B = "OFFER_BELOW_B"
    PENALTY_ABOVE_CAP = "PENALTY_ABOVE_CAP"
    # 🔍 계산함
    SCOPE_UNCERTAIN_PT_ONLY = "SCOPE_UNCERTAIN_PT_ONLY"
    PERIOD_ONE_MONTH_BOUNDARY = "PERIOD_ONE_MONTH_BOUNDARY"
    REFUND_LIMIT_CLAUSE_UNKNOWN = "REFUND_LIMIT_CLAUSE_UNKNOWN"
    WITHDRAWAL_STATUS_UNCONFIRMED = "WITHDRAWAL_STATUS_UNCONFIRMED"
    SESSION_VALIDITY_MISSING = "SESSION_VALIDITY_MISSING"
    REFUND_BASIS_UNKNOWN = "REFUND_BASIS_UNKNOWN"
    RULE_UNVERIFIED = "RULE_UNVERIFIED"
    LIST_PRICE_NOT_USABLE = "LIST_PRICE_NOT_USABLE"
    INTERPRETATION_DEPENDENT = "INTERPRETATION_DEPENDENT"
    USAGE_STARTED = "USAGE_STARTED"
    POSTPONEMENT = "POSTPONEMENT"


class NoticeCode(StrEnum):
    """화면 설명용 안내 코드 (5.5). 배지 판정에 쓰지 않는다."""

    NO_LIST_PRICE = "NO_LIST_PRICE"
    LIST_PRICE_BELOW_TOTAL = "LIST_PRICE_BELOW_TOTAL"
    OFFER_BETWEEN_A_AND_B = "OFFER_BETWEEN_A_AND_B"
    PENALTY_INPUT_MISSING = "PENALTY_INPUT_MISSING"
    STANDARD_TERMS_PENALTY = "STANDARD_TERMS_PENALTY"
    NEGATIVE_REFUND_ZEROED = "NEGATIVE_REFUND_ZEROED"
    POSTPONEMENT_INPUT = "POSTPONEMENT_INPUT"
    PERIOD_CHECK = "PERIOD_CHECK"
    WITHDRAWAL_INFO = "WITHDRAWAL_INFO"
    PT_ONLY_QUESTION = "PT_ONLY_QUESTION"  # 입력 단계 질문. 엔진은 내지 않는다.


F = FlagCode

UNDETERMINABLE_CODES = frozenset(
    {
        F.JUDGMENT_REQUESTED,
        F.UNSUPPORTED_INDUSTRY,
        F.ACADEMY_LAW,
        F.WITHDRAWAL,
        F.BUSINESS_FAULT,
        F.FORCE_MAJEURE,
        F.PERIOD_UNDER_28_DAYS,
        F.NO_REFUND_LIMIT_CLAUSE,
    }
)
NO_CALC_CODES = frozenset(
    {F.MISSING_REQUIRED, F.INVALID_INPUT, F.NOTICE_AFTER_VALIDITY}
)
ROBUST_CODES = frozenset({F.OFFER_BELOW_B, F.PENALTY_ABOVE_CAP})
REVIEW_CODES = frozenset(FlagCode) - UNDETERMINABLE_CODES - NO_CALC_CODES - ROBUST_CODES

# 화면 한 줄 우선순위 (5.4 표, 초안). 단계 6에서 순서를 바꾸면 이 상수만 고친다.
DISPLAY_PRIORITY: tuple[FlagCode, ...] = (
    F.JUDGMENT_REQUESTED,
    F.UNSUPPORTED_INDUSTRY,
    F.ACADEMY_LAW,
    F.WITHDRAWAL,
    F.BUSINESS_FAULT,
    F.FORCE_MAJEURE,
    F.PERIOD_UNDER_28_DAYS,
    F.NO_REFUND_LIMIT_CLAUSE,
    F.MISSING_REQUIRED,
    F.INVALID_INPUT,
    F.NOTICE_AFTER_VALIDITY,
    F.PENALTY_ABOVE_CAP,
    F.OFFER_BELOW_B,
    F.SCOPE_UNCERTAIN_PT_ONLY,
    F.PERIOD_ONE_MONTH_BOUNDARY,
    F.REFUND_LIMIT_CLAUSE_UNKNOWN,
    F.WITHDRAWAL_STATUS_UNCONFIRMED,
    F.SESSION_VALIDITY_MISSING,
    F.REFUND_BASIS_UNKNOWN,
    F.RULE_UNVERIFIED,
    F.LIST_PRICE_NOT_USABLE,
    F.INTERPRETATION_DEPENDENT,
    F.USAGE_STARTED,
    F.POSTPONEMENT,
)


def order_flags(flags: Iterable[FlagCode]) -> list[FlagCode]:
    """사유 코드를 화면 우선순위 순으로 정렬한다 (중복 제거)."""
    return sorted(set(flags), key=DISPLAY_PRIORITY.index)


def screen_line(flags: Iterable[FlagCode]) -> FlagCode | None:
    """배지 옆에 한 줄로 보여 줄 코드. 사유가 없으면 None."""
    ordered = order_flags(flags)
    return ordered[0] if ordered else None


def decide_badge(
    *,
    judgment_requested: bool,
    out_of_scope: bool,
    missing_or_invalid: bool,
    robust_warnings: list[FlagCode],
    review_flags: list[FlagCode],
) -> Badge:
    """배지 결정 순서 (MVP_SPEC 4절, 5.4): ❔ → 🔍(계산 안 함) → ⚠️ → 🔍 → ✅."""
    if judgment_requested or out_of_scope:
        return Badge.UNDETERMINABLE
    if missing_or_invalid:
        return Badge.NEEDS_REVIEW
    if robust_warnings:
        return Badge.WARNING
    if review_flags:
        return Badge.NEEDS_REVIEW
    return Badge.CONFIRMED
