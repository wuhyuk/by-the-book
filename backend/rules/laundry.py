"""세탁물 손상·분실 배상 기준 금액 규칙 엔진 (MVP_SPEC 12절, 축소 A).

순수 함수만 둔다. LLM을 호출하지 않는다. 금액은 int, 비율은 정수 퍼센트이며 float를 쓰지 않는다.
표 값(배상비율표, 평균 내용연수표, 20배)은 규칙 JSON(LaundryRule)에서 읽는다.
"""

from datetime import date
from itertools import product
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rules.badge import Badge, decide_badge
from rules.laundry_codes import (
    LAUNDRY_NO_CALC,
    LAUNDRY_ROBUST,
    LAUNDRY_UNDETERMINABLE,
    CommonFlag,
    LaundryCode,
    LaundryFlag,
    LaundryNotice,
    order_laundry_flags,
)
from rules.laundry_rule import Band, LaundryRule
from rules.money import div_round_half_up

C = CommonFlag
L = LaundryFlag
N = LaundryNotice

LAUNDRY_SHOP = "laundry_shop"
SET_PARTS: dict[str, tuple[str, ...]] = {
    "top_bottom": ("top", "bottom"),
    "top_mid_bottom": ("top", "mid", "bottom"),
    "hanbok": ("top", "bottom"),
}

USE_DAYS_NOTE = "구입일은 세지 않음(고시에 규정 없음)"
FLOOR_NOTE = "원 미만 내림(고시에 규정 없음)"

Method = Literal["ratio", "fallback"]
Decision = Literal["use_days", "rounding"]
UseDays = Literal["D0", "D1"]
Rounding = Literal["floor", "half_up"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class LaundryInput(_Model):
    """입력 스키마 (MVP_SPEC 12.1). 필드명은 12.1 그대로다."""

    judgment_requested: bool
    service_type: str
    damage_type: Literal["defect", "loss", "other"]
    manufacturing_cause_claimed: bool | None = None
    item_key: str | None = None
    item_unlisted: bool = False
    variant_key: str | None = None
    purchase_price: int | None = None
    purchase_date: date | None = None
    request_date: date | None = None
    proof_available: bool | None = None
    laundry_fee: int | None = None
    set_type: Literal["none", "top_bottom", "top_mid_bottom", "hanbok"] = "none"
    set_part: Literal["top", "mid", "bottom", "whole"] | None = None
    attachment_only: bool | None = None
    special_agreement: bool | None = None
    customer_partial_fault: bool | None = None
    wants_damaged_item: bool | None = None
    no_issue_confirmation: bool | None = None
    uncollected: bool | None = None
    receipt_issued: bool | None = None
    provider_offer: int | None = None


class LaundryStep(_Model):
    label: str
    formula: str
    amount: int | None


class LaundryScope(_Model):
    """범위 판정 결과 (12.2). stop_code가 있으면 계산하지 않는다."""

    stop_code: LaundryCode | None
    missing: list[str]


class Lookup(_Model):
    """한 조합의 조회 결과와 배상액."""

    life_years: int
    band: Band
    amount: int


class Sensitivity(_Model):
    """결정 민감도 검사 결과 (12.4)."""

    min: int
    max: int
    causes: list[Decision]
    ratio_alt: int | None

    @property
    def sensitive(self) -> bool:
        return bool(self.causes)


class LaundryResult(_Model):
    """출력 (MVP_SPEC 12.6)."""

    badge: Badge
    calculated: bool
    method: Method | None
    use_days: int | None
    life_years: int | None
    ratio_percent: int | None
    band_min_days: int | None
    band_max_days: int | None
    amount: int | None
    fallback_amount: int | None
    sensitivity_min: int | None
    sensitivity_max: int | None
    sensitivity_causes: list[Decision]
    sensitivity_ratio_alt: int | None
    steps: list[LaundryStep]
    flags: list[LaundryCode]
    missing: list[str]
    notices: list[LaundryNotice]
    citations: list[str]


# ---- 범위 판정 ----


def _set_part_in_set(inp: LaundryInput) -> bool:
    return inp.set_part in SET_PARTS.get(inp.set_type, ())


def _missing(inp: LaundryInput, rule: LaundryRule) -> list[str]:
    """12.2 누락 판정. 입증 가능 여부를 모르면 그것만 묻는다."""
    if inp.proof_available is None:
        return ["proof_available"]
    missing: set[str] = set()
    if inp.set_type != "none" and inp.set_part is None:
        missing.add("set_part")
    if inp.proof_available:
        if inp.item_key is None:
            missing.add("item_key")
        else:
            row = rule.lifespan_table.row(inp.item_key)
            if row is not None and row.variants and inp.variant_key is None:
                missing.add("variant_key")
        for name in ("purchase_price", "purchase_date", "request_date"):
            if getattr(inp, name) is None:
                missing.add(name)
    elif inp.laundry_fee is None:
        missing.add("laundry_fee")
    order = list(LaundryInput.model_fields)
    return sorted(missing, key=order.index)


def _invalid(inp: LaundryInput, rule: LaundryRule) -> bool:
    """12.1 입력 검증. 계산 경로에서 쓰는 값만 본다."""
    if inp.provider_offer is not None and inp.provider_offer < 0:
        return True
    if inp.set_type != "none" and inp.set_part not in (
        *SET_PARTS[inp.set_type],
        "whole",
    ):
        return True
    if inp.set_type == "none" and inp.set_part is not None:
        return True
    if not inp.proof_available:
        return inp.laundry_fee is not None and inp.laundry_fee <= 0
    assert inp.item_key is not None and inp.purchase_price is not None
    assert inp.purchase_date is not None and inp.request_date is not None
    if inp.purchase_price <= 0 or inp.request_date < inp.purchase_date:
        return True
    row = rule.lifespan_table.row(inp.item_key)
    if row is None:
        return True
    if row.variants is None:
        # 값이 하나인 행의 variant_key는 무시한다 (결과가 같다, 12.1 Q4 변경)
        return False
    return inp.variant_key is None or row.variant(inp.variant_key) is None


def check_scope(inp: LaundryInput, rule: LaundryRule) -> LaundryScope:
    """MVP_SPEC 12.2 판정 순서 1~9. 먼저 걸리는 것이 이긴다."""

    def stop(
        code: LaundryCode | None, missing: list[str] | None = None
    ) -> LaundryScope:
        return LaundryScope(stop_code=code, missing=missing or [])

    if inp.judgment_requested:
        return stop(C.JUDGMENT_REQUESTED)
    if inp.service_type != LAUNDRY_SHOP:
        return stop(L.UNSUPPORTED_SERVICE)
    if inp.damage_type == "other":
        return stop(L.UNSUPPORTED_DAMAGE)
    if inp.manufacturing_cause_claimed is True:
        return stop(L.MANUFACTURING_CAUSE)
    if inp.set_type != "none" and _set_part_in_set(inp):
        return stop(L.SET_PARTIAL_UNSUPPORTED)
    if inp.attachment_only is True:
        return stop(L.ATTACHMENT_UNSUPPORTED)
    if inp.proof_available is True and inp.item_unlisted:
        return stop(L.ITEM_NOT_IN_TABLE)
    missing = _missing(inp, rule)
    if missing:
        return stop(C.MISSING_REQUIRED, missing)
    if _invalid(inp, rule):
        return stop(C.INVALID_INPUT)
    return stop(None)


# ---- 계산 ----


def use_days(purchase: date, request: date) -> int:
    """사용일수 D0 = 세탁의뢰일 − 구입일 (구입 당일 = 0일)."""
    return (request - purchase).days


def life_years(inp: LaundryInput, rule: LaundryRule) -> int:
    """평균 내용연수표 조회. 행에 값이 여럿이면 소재·용도로 고른다."""
    assert inp.item_key is not None
    row = rule.lifespan_table.row(inp.item_key)
    assert row is not None
    if row.years is not None:
        return row.years
    assert inp.variant_key is not None
    variant = row.variant(inp.variant_key)
    assert variant is not None
    return variant.years


def _amount(price: int, ratio_percent: int, rounding: Rounding) -> int:
    """구입가격 × 배상비율 ÷ 100. 정수 곱 뒤 한 번만 원 미만 처리."""
    numerator = price * ratio_percent
    if rounding == "floor":
        return numerator // 100
    return div_round_half_up(numerator, 100)


def lookup(
    inp: LaundryInput, rule: LaundryRule, days_mode: UseDays, rounding: Rounding
) -> Lookup:
    """한 조합(사용일수 산입 × 원 미만 처리)으로 조회하고 배상액을 계산한다."""
    assert inp.purchase_date and inp.request_date and inp.purchase_price
    days = use_days(inp.purchase_date, inp.request_date) + (days_mode == "D1")
    life = life_years(inp, rule)
    band = rule.ratio_table.band(life, days)
    return Lookup(
        life_years=life,
        band=band,
        amount=_amount(inp.purchase_price, band.ratio_percent, rounding),
    )


def sensitivity(inp: LaundryInput, rule: LaundryRule) -> tuple[Lookup, Sensitivity]:
    """결정 민감도 검사 (12.4). 결정 값 결과와 4조합 검사 결과를 돌려준다."""
    combos: dict[tuple[UseDays, Rounding], Lookup] = {
        (d, r): lookup(inp, rule, d, r)
        for d, r in product(("D0", "D1"), ("floor", "half_up"))
    }
    base = combos[("D0", "floor")]

    def differs(x: Lookup) -> bool:
        return x != base  # 내용연수 행·칸·배상액 중 하나라도 다르면

    causes: list[Decision] = []
    if differs(combos[("D1", "floor")]):
        causes.append("use_days")
    if differs(combos[("D0", "half_up")]):
        causes.append("rounding")
    if not causes and differs(combos[("D1", "half_up")]):
        causes = ["use_days", "rounding"]
    alt = combos[("D1", "floor")].band
    amounts = [x.amount for x in combos.values()]
    return base, Sensitivity(
        min=min(amounts),
        max=max(amounts),
        causes=causes,
        ratio_alt=alt.ratio_percent
        if "use_days" in causes and alt != base.band
        else None,
    )


def _blocks_verified(rule: LaundryRule, method: Method) -> bool:
    """결과가 쓰는 블록만 본다 (12.4)."""
    if method == "fallback":
        return rule.unproven_fallback.verified
    return rule.ratio_table.verified and rule.lifespan_table.verified


def _deduction_claims(inp: LaundryInput) -> list[LaundryCode]:
    """특약·감액·면책 주장 사유 (🔍)."""
    flags: list[LaundryCode] = []
    if inp.no_issue_confirmation is True or inp.uncollected is True:
        flags.append(L.EXEMPTION_CLAIMED)
    if inp.special_agreement is True:
        flags.append(L.SPECIAL_AGREEMENT)
    if inp.customer_partial_fault is True:
        flags.append(L.PARTIAL_FAULT_CLAIMED)
    if inp.wants_damaged_item is True:
        flags.append(L.DAMAGED_ITEM_RETURN)
    return flags


def _notices(inp: LaundryInput, method: Method) -> list[LaundryNotice]:
    """안내 코드 (12.5), 표 순서대로. 계산한 결과에만 붙인다."""
    notices: list[LaundryNotice] = []
    if inp.damage_type == "defect":
        notices.append(N.RESTORE_FIRST)
    if method == "fallback":
        notices.append(N.UNPROVEN_FALLBACK)
    notices.append(N.RECEIPT_BASIS)
    if inp.damage_type == "loss" and inp.receipt_issued is False:
        notices.append(N.NO_RECEIPT_LOSS)
    notices += [N.LAUNDRY_FEE_TERMS, N.CLAIM_PERIOD_TERMS]
    return notices


def _terms_citable(rule: LaundryRule, clause_id: str) -> bool:
    """표준약관 조항은 원문을 두 경로로 확인했을 때만 인용한다 (12.7, Q-L7)."""
    clause = next((c for c in rule.related_clauses if c.id == clause_id), None)
    if clause is None:
        return False
    paths = clause.source.verified_paths
    return paths is not None and paths >= 2 and clause.source.usage != "notice_only"


def _citations(
    inp: LaundryInput,
    rule: LaundryRule,
    flags: list[LaundryCode],
    notices: list[LaundryNotice],
    method: Method | None,
) -> list[str]:
    """근거 조항 ID (12.7)."""
    ids: list[str] = []
    if method is not None:
        ids += ["laundry_types", "laundry_1", "laundry_5_1", "cpa16_3"]
        if method == "ratio":
            ids += ["laundry_ratio_table", "laundry_lifespan_table"]
        if inp.set_type != "none" and inp.set_part == "whole":
            ids.append("laundry_6")
        if L.PARTIAL_FAULT_CLAIMED in flags or L.DAMAGED_ITEM_RETURN in flags:
            ids.append("laundry_2")
        if L.EXEMPTION_CLAIMED in flags:
            ids.append("laundry_3")
        if N.NO_RECEIPT_LOSS in notices:
            ids.append("laundry_5")
        terms = {
            N.LAUNDRY_FEE_TERMS: "laundry_terms_art9",
            N.CLAIM_PERIOD_TERMS: "laundry_terms_art10_3",
        }
        ids += [
            cid
            for code, cid in terms.items()
            if code in notices and _terms_citable(rule, cid)
        ]
    else:
        by_code = {
            L.UNSUPPORTED_DAMAGE: "laundry_types",
            L.SET_PARTIAL_UNSUPPORTED: "laundry_7",
            L.ATTACHMENT_UNSUPPORTED: "laundry_8",
            L.ITEM_NOT_IN_TABLE: "cpa_dec9_2",
        }
        ids += [by_code[f] for f in flags if f in by_code]
    unique = list(dict.fromkeys(ids))
    unknown = set(unique) - rule.clause_ids
    if unknown:
        raise ValueError(f"규칙 JSON에 없는 조항 ID: {sorted(unknown)}")
    return unique


def _won(n: int) -> str:
    return f"{n:,}"


def _band_text(band: Band) -> str:
    upper = "" if band.max_days is None else _won(band.max_days)
    return f"{_won(band.min_days)}~{upper}일"


def _ratio_steps(
    inp: LaundryInput, rule: LaundryRule, base: Lookup, sens: Sensitivity
) -> list[LaundryStep]:
    assert inp.purchase_date and inp.request_date and inp.purchase_price
    assert inp.item_key is not None
    row = rule.lifespan_table.row(inp.item_key)
    assert row is not None
    item = row.label
    if row.variants is not None and inp.variant_key is not None:
        variant = row.variant(inp.variant_key)
        assert variant is not None
        item += f" ({variant.label})"
    days = use_days(inp.purchase_date, inp.request_date)
    steps = [
        LaundryStep(
            label="사용일수",
            formula=f"{inp.request_date.isoformat()} − {inp.purchase_date.isoformat()}, "
            f"{USE_DAYS_NOTE}",
            amount=None,
        ),
        LaundryStep(
            label="내용연수",
            formula=f"{item} → {base.life_years}년 (품목별 평균 내용연수표)",
            amount=None,
        ),
        LaundryStep(
            label="배상비율",
            formula=f"내용연수 {base.life_years}년 행, 사용일수 {_won(days)}일 → "
            f"{_band_text(base.band)} 칸 {base.band.ratio_percent}% (배상비율표)",
            amount=None,
        ),
        LaundryStep(
            label="배상액",
            formula=f"{_won(inp.purchase_price)} × {base.band.ratio_percent}%, {FLOOR_NOTE}",
            amount=base.amount,
        ),
    ]
    if sens.sensitive:
        names = {"use_days": "사용일수 산입", "rounding": "원 미만 처리"}
        cause = "·".join(names[c] for c in sens.causes)
        steps.append(
            LaundryStep(
                label="결정 민감도 검사",
                formula=f"고시에 없는 결정({cause})을 바꾸면 결과가 달라집니다: "
                f"{_won(sens.min)}원~{_won(sens.max)}원",
                amount=None,
            )
        )
    else:
        steps.append(
            LaundryStep(
                label="결정 민감도 검사",
                formula="구입일 산입 여부와 원 미만 처리 방식을 바꿔도 결과가 같습니다",
                amount=None,
            )
        )
    return steps


def calculate_damage(inp: LaundryInput, rule: LaundryRule) -> LaundryResult:
    """범위 판정 → 계산 → 민감도 검사 → 제시액 비교 → 배지 (MVP_SPEC 12.2~12.7)."""
    scope = check_scope(inp, rule)
    if scope.stop_code is not None:
        flags: list[LaundryCode] = [scope.stop_code]
        return LaundryResult(
            badge=decide_badge(
                judgment_requested=inp.judgment_requested,
                out_of_scope=scope.stop_code in LAUNDRY_UNDETERMINABLE,
                missing_or_invalid=scope.stop_code in LAUNDRY_NO_CALC,
                robust_warnings=[],
                review_flags=[],
            ),
            calculated=False,
            method=None,
            use_days=None,
            life_years=None,
            ratio_percent=None,
            band_min_days=None,
            band_max_days=None,
            amount=None,
            fallback_amount=None,
            sensitivity_min=None,
            sensitivity_max=None,
            sensitivity_causes=[],
            sensitivity_ratio_alt=None,
            steps=[],
            flags=flags,
            missing=scope.missing,
            notices=[],
            citations=_citations(inp, rule, flags, [], None),
        )

    method: Method = "ratio" if inp.proof_available else "fallback"
    base: Lookup | None = None
    if method == "ratio":
        base, sens = sensitivity(inp, rule)
        amount = base.amount
        assert inp.purchase_date and inp.request_date
        days: int | None = use_days(inp.purchase_date, inp.request_date)
        fallback_amount = None
        steps = _ratio_steps(inp, rule, base, sens)
    else:
        assert inp.laundry_fee is not None
        multiplier = rule.unproven_fallback.laundry_fee_multiplier
        amount = inp.laundry_fee * multiplier
        sens = Sensitivity(min=amount, max=amount, causes=[], ratio_alt=None)
        days = None
        fallback_amount = amount
        steps = [
            LaundryStep(
                label="입증 불가 시 배상액",
                formula=f"세탁요금 {_won(inp.laundry_fee)} × {multiplier} (고시 5-1.③)",
                amount=amount,
            )
        ]

    claims = _deduction_claims(inp)
    verified = _blocks_verified(rule, method)
    robust: list[LaundryCode] = []
    if (
        inp.provider_offer is not None
        and inp.provider_offer < sens.min
        and not claims
        and verified
    ):
        robust.append(L.OFFER_BELOW_STANDARD_MIN)
    assert set(robust) <= LAUNDRY_ROBUST
    review: list[LaundryCode] = list(claims)
    if not verified:
        review.append(C.RULE_UNVERIFIED)
    if sens.sensitive:
        review.append(L.DECISION_SENSITIVE)
    flags = order_laundry_flags(robust + review)
    notices = _notices(inp, method)
    return LaundryResult(
        badge=decide_badge(
            judgment_requested=False,
            out_of_scope=False,
            missing_or_invalid=False,
            robust_warnings=robust,
            review_flags=review,
        ),
        calculated=True,
        method=method,
        use_days=days,
        life_years=base.life_years if base else None,
        ratio_percent=base.band.ratio_percent if base else None,
        band_min_days=base.band.min_days if base else None,
        band_max_days=base.band.max_days if base else None,
        amount=amount,
        fallback_amount=fallback_amount,
        sensitivity_min=sens.min,
        sensitivity_max=sens.max,
        sensitivity_causes=sens.causes,
        sensitivity_ratio_alt=sens.ratio_alt,
        steps=steps,
        flags=flags,
        missing=[],
        notices=notices,
        citations=_citations(inp, rule, flags, notices, method),
    )
