"""업체 제시액과 기준 금액의 차액 (기능 플래그 offer_gap, MVP_SPEC 14.1, 2026-11-16).

순수 함수만 둔다. LLM을 호출하지 않는다. 금액은 int, 정수 뺄셈만 한다.
차액은 표시용이며 배지 판정(OFFER_BELOW_B, OFFER_BELOW_STANDARD_MIN 등)에 쓰지 않는다.

- reference_min·reference_max: 엔진이 이미 계산한 기준 금액 범위의 최솟값·최댓값
  (헬스장 = 모든 기준·시나리오 환급액, 세탁·가전 = 결정 민감도 검사 범위). 범위가 없으면 같은 값.
- gap_to_min = reference_min − offer (제시액이 최솟값보다 적으면 양수)
- gap_to_max = offer − reference_max (제시액이 최댓값보다 많으면 양수)
- direction: below_min / within / above_max / equal (min == max == offer)

꺼져 있으면 결과에 필드가 나오지 않는다 (exclude_if, 응답 JSON이 변경 전과 같다).
"""

from collections.abc import Collection
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

OFFER_GAP_FEATURE = "offer_gap"
RULE_UNVERIFIED_CODE = "RULE_UNVERIFIED"

Direction = Literal["below_min", "within", "above_max", "equal"]


def _is_none(value: Any) -> bool:
    return value is None


class OfferGap(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    offer: int
    reference_min: int
    reference_max: int
    gap_to_min: int
    gap_to_max: int
    direction: Direction


def optional_field() -> Any:
    """값이 없으면 응답에서 빠지는 필드 (꺼짐 상태의 응답을 변경 전과 같게 둔다)."""
    return Field(default=None, exclude_if=_is_none)


def compute_offer_gap(offer: int, reference_min: int, reference_max: int) -> OfferGap:
    """정수 뺄셈으로 차액과 위치를 정한다."""
    if reference_min > reference_max:
        raise ValueError("기준 금액 범위가 거꾸로입니다.")
    if offer < reference_min:
        direction: Direction = "below_min"
    elif offer > reference_max:
        direction = "above_max"
    elif reference_min == reference_max:
        direction = "equal"
    else:
        direction = "within"
    return OfferGap(
        offer=offer,
        reference_min=reference_min,
        reference_max=reference_max,
        gap_to_min=reference_min - offer,
        gap_to_max=offer - reference_max,
        direction=direction,
    )


def offer_gap_if_enabled(
    features: Collection[str],
    *,
    offer: int | None,
    amounts: list[int],
    flags: Collection[str],
) -> OfferGap | None:
    """플래그가 켜져 있고, 계산한 금액이 있고, 제시액이 있고, RULE_UNVERIFIED가 아닐 때만 만든다.

    amounts는 엔진 결과 필드의 금액(헬스장 환급액 목록, 세탁·가전 민감도 최솟값·최댓값)이다.
    """
    if OFFER_GAP_FEATURE not in features or offer is None or not amounts:
        return None
    if any(str(f) == RULE_UNVERIFIED_CODE for f in flags):
        return None
    return compute_offer_gap(offer, min(amounts), max(amounts))


def _won(n: int) -> str:
    return f"{n:,}원"


def offer_gap_text(gap: OfferGap) -> str:
    """화면·설명 한 줄 [제안 2026-11-16]. 숫자는 OfferGap 필드에서만 가져온다."""
    offer = _won(gap.offer)
    lo, hi = _won(gap.reference_min), _won(gap.reference_max)
    ranged = gap.reference_min != gap.reference_max
    if gap.direction == "equal":
        return "업체 제시액은 기준 금액과 같습니다."
    if gap.direction == "within":
        return f"업체 제시액 {offer}은 기준 금액 범위({lo}~{hi}) 안에 있습니다."
    if gap.direction == "below_min":
        if ranged:
            return (
                f"업체 제시액 {offer}은 기준 금액 범위({lo}~{hi})의 최솟값보다 "
                f"{_won(gap.gap_to_min)} 적습니다."
            )
        return (
            f"업체 제시액 {offer}은 기준 금액 {lo}보다 {_won(gap.gap_to_min)} 적습니다."
        )
    if ranged:
        return (
            f"업체 제시액 {offer}은 기준 금액 범위({lo}~{hi})의 최댓값보다 "
            f"{_won(gap.gap_to_max)} 많습니다."
        )
    return f"업체 제시액 {offer}은 기준 금액보다 {_won(gap.gap_to_max)} 많습니다."
