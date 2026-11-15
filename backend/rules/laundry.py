"""세탁물 손상·분실 배상 기준 금액 규칙 엔진 (MVP_SPEC 12절, 축소 A + 복원 R2).

순수 함수만 둔다. LLM을 호출하지 않는다. 금액은 int, 비율은 정수 퍼센트이며 float를 쓰지 않는다.
표 값(배상비율표, 평균 내용연수표, 20배, Set 배분 비율)은 규칙 JSON(LaundryRule)에서 읽는다.

복원 기능은 features로 켠다 (MVP_SPEC 12.10). 지금 아는 이름은 SET_PARTIAL("set_partial", R2 Set 일부
손상·분실 배분 계산)뿐이다. 꺼져 있으면 12.1~12.9(축소 A) 그대로 동작한다 (승인 L4 ❔ 유지).
API는 운영 설정 ENABLED_FEATURES(api/settings.py)를 읽어 넘긴다.
"""

from collections.abc import Collection
from datetime import date
from fractions import Fraction
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
# 복원 기능 이름 (MVP_SPEC 12.10)
SET_PARTIAL = "set_partial"
# 한복류 행 (평균 내용연수표 rows[].id). 한복류 행은 Set 유형 none/hanbok만, 그 밖의 행은
# none/top_bottom/top_mid_bottom만 받는다 (R2 Q5 (c)+(a), 2026-11-15).
HANBOK_ROW_ID = "hanbok"
HANBOK_SET_TYPES = ("none", "hanbok")
OTHER_SET_TYPES = ("none", "top_bottom", "top_mid_bottom")

USE_DAYS_NOTE = "구입일은 세지 않음(고시에 규정 없음)"
FLOOR_NOTE = "원 미만 내림(고시에 규정 없음)"

Method = Literal["ratio", "fallback"]
Decision = Literal["use_days", "rounding", "set_partial_damage"]
UseDays = Literal["D0", "D1"]
Rounding = Literal["floor", "half_up"]
Scope = Literal["allocate", "whole_set"]
SetPart = Literal["top", "mid", "bottom"]
DECISION_ORDER: tuple[Decision, ...] = ("use_days", "rounding", "set_partial_damage")


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
    # R2(set_partial)를 켰을 때만 쓰는 입력 (12.10 R2, 2026-11-15). 폼으로만 받고 문장 분석 대상이 아니다.
    # 꺼져 있을 때 값이 오면 INVALID_INPUT. 켜져 있을 때는 set_part 대신 damaged_parts를 쓴다.
    hanbok_kind: Literal["chima_jeogori", "baji_jeogori"] | None = None
    damaged_parts: list[SetPart] | None = None
    set_partial_request: bool | None = None
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


class SetBasis(_Model):
    """Set 배분 (R2). share_percent는 손상된 벌의 비율 합(규칙 JSON set_allocation), 모든 벌이면 100.

    whole_set_check: 1벌 전체(6.①) 대안을 결정 민감도 검사에 넣는지 (배분을 쓰고 set_partial_request가
    True가 아닐 때만, R2 Q1 (a)·Q2 (a)).
    """

    share_percent: int
    allocated: bool
    whole_set_check: bool


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
    # R2(set_partial) 출력 (보고서 vs4_restore_r2_cases.md 3.2, Q13 (a)). 꺼져 있거나 Set이 아니면 None.
    set_type: str | None = None
    hanbok_kind: str | None = None
    damaged_parts: list[str] | None = None
    set_share_percent: int | None = None
    set_base_raw: str | None = (
        None  # 원 미만 처리 전 배분 기준 가격 (구입가격 × 비율 합 ÷ 100)
    )


# ---- 범위 판정 ----


def _set_part_in_set(inp: LaundryInput) -> bool:
    return inp.set_part in SET_PARTS.get(inp.set_type, ())


def _r2(features: Collection[str]) -> bool:
    return SET_PARTIAL in features


def _r2_fields_given(inp: LaundryInput) -> bool:
    return (
        inp.hanbok_kind is not None
        or inp.damaged_parts is not None
        or inp.set_partial_request is not None
    )


def _partial(inp: LaundryInput) -> bool:
    """손상 벌이 모두 그 Set의 벌이고, 전부는 아님 (보고서 3.3 순서 5-2. 중복은 집합으로 본다)."""
    parts = SET_PARTS.get(inp.set_type)
    if parts is None or not inp.damaged_parts:
        return False
    chosen = set(inp.damaged_parts)
    return chosen < set(parts)


def _all_parts(inp: LaundryInput) -> bool:
    parts = SET_PARTS.get(inp.set_type)
    return (
        parts is not None
        and bool(inp.damaged_parts)
        and set(inp.damaged_parts) == set(parts)
    )


def _missing_r2(inp: LaundryInput, missing: set[str]) -> None:
    """R2 누락 (보고서 3.3 순서 8): 손상 벌, 그리고 입증 가능 + 부분 손상이면 set_partial_request."""
    if inp.set_type == "none":
        return
    if inp.set_type == "hanbok" and inp.hanbok_kind is None:
        missing.add("hanbok_kind")
    if not inp.damaged_parts:
        missing.add("damaged_parts")
    elif inp.proof_available and _partial(inp) and inp.set_partial_request is None:
        missing.add("set_partial_request")


def _missing(
    inp: LaundryInput, rule: LaundryRule, features: Collection[str] = ()
) -> list[str]:
    """12.2 누락 판정. 입증 가능 여부를 모르면 그것만 묻는다."""
    if inp.proof_available is None:
        return ["proof_available"]
    missing: set[str] = set()
    if _r2(features):
        _missing_r2(inp, missing)
    elif inp.set_type != "none" and inp.set_part is None:
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


def _invalid_set_r2(inp: LaundryInput) -> bool:
    """R2 입력 검증 (보고서 3.3 순서 9): set_part 대신 damaged_parts, 중복·Set에 없는 벌."""
    if inp.set_part is not None:
        return True
    if inp.set_type == "none":
        return inp.hanbok_kind is not None or inp.damaged_parts is not None
    if inp.set_type != "hanbok" and inp.hanbok_kind is not None:
        return True
    parts = inp.damaged_parts or []
    if len(parts) != len(set(parts)):
        return True
    return not set(parts) <= set(SET_PARTS[inp.set_type])


def _invalid_set_off(inp: LaundryInput) -> bool:
    """축소 A(R2 꺼짐) 입력 검증. R2 입력이 오면 입력 오류 (R1 Q9와 같은 방식)."""
    if _r2_fields_given(inp):
        return True
    if inp.set_type != "none" and inp.set_part not in (
        *SET_PARTS[inp.set_type],
        "whole",
    ):
        return True
    return inp.set_type == "none" and inp.set_part is not None


def _invalid(
    inp: LaundryInput, rule: LaundryRule, features: Collection[str] = ()
) -> bool:
    """12.1 입력 검증. 계산 경로에서 쓰는 값만 본다."""
    if inp.provider_offer is not None and inp.provider_offer < 0:
        return True
    r2 = _r2(features)
    if _invalid_set_r2(inp) if r2 else _invalid_set_off(inp):
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
    if r2:
        # Set 유형과 품목 행이 맞지 않음 (R2 Q5 (c)+(a))
        allowed = HANBOK_SET_TYPES if row.id == HANBOK_ROW_ID else OTHER_SET_TYPES
        if inp.set_type not in allowed:
            return True
    if row.variants is None:
        # 값이 하나인 행의 variant_key는 무시한다 (결과가 같다, 12.1 Q4 변경)
        return False
    return inp.variant_key is None or row.variant(inp.variant_key) is None


def check_scope(
    inp: LaundryInput, rule: LaundryRule, features: Collection[str] = ()
) -> LaundryScope:
    """MVP_SPEC 12.2 판정 순서 1~9. 먼저 걸리는 것이 이긴다.

    R2를 켜면 순서 5가 바뀐다 (보고서 3.3): 입증 가능 Set 일부는 계산하고, 입증 불가 Set 일부는
    ❔ SET_PARTIAL_FALLBACK_UNDEFINED. ③ 밖 한복 조합(5-1)은 이번 범위 밖이라 입력으로 받지 않는다.
    """

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
    if _r2(features):
        if _partial(inp) and inp.proof_available is False:
            return stop(L.SET_PARTIAL_FALLBACK_UNDEFINED)
    elif inp.set_type != "none" and _set_part_in_set(inp):
        return stop(L.SET_PARTIAL_UNSUPPORTED)
    if inp.attachment_only is True:
        return stop(L.ATTACHMENT_UNSUPPORTED)
    if inp.proof_available is True and inp.item_unlisted:
        return stop(L.ITEM_NOT_IN_TABLE)
    missing = _missing(inp, rule, features)
    if missing:
        return stop(C.MISSING_REQUIRED, missing)
    if _invalid(inp, rule, features):
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


def _amount(
    price: int, ratio_percent: int, rounding: Rounding, share_percent: int = 100
) -> int:
    """구입가격 × 비율 합 × 배상비율 ÷ 10,000. 정수 곱 뒤 마지막에 한 번만 원 미만 처리.

    Set이 아니거나 모든 벌이면 비율 합 100이라 구입가격 × 배상비율 ÷ 100과 같다.
    """
    numerator = price * share_percent * ratio_percent
    if rounding == "floor":
        return numerator // 10_000
    return div_round_half_up(numerator, 10_000)


def set_basis(
    inp: LaundryInput, rule: LaundryRule, features: Collection[str] = ()
) -> SetBasis | None:
    """R2 Set 배분 (보고서 3.1). 비율은 규칙 JSON set_allocation.shares_percent에서만 읽는다.

    R2가 꺼져 있거나 Set이 아니면 None (기존 계산 그대로).
    """
    if not _r2(features) or inp.set_type == "none" or not inp.damaged_parts:
        return None
    if _all_parts(inp):
        # 모든 벌: 1벌 전체(6.①), 범위 결정 없음. set_partial_request는 무시한다 (Q15 (a))
        return SetBasis(share_percent=100, allocated=False, whole_set_check=False)
    shares = rule.set_allocation.shares_percent[inp.set_type]
    return SetBasis(
        share_percent=sum(shares[p] for p in inp.damaged_parts),
        allocated=True,
        whole_set_check=inp.set_partial_request is not True,
    )


def lookup(
    inp: LaundryInput,
    rule: LaundryRule,
    days_mode: UseDays,
    rounding: Rounding,
    share_percent: int = 100,
) -> Lookup:
    """한 조합(사용일수 산입 × 원 미만 처리 × 비율 합)으로 조회하고 배상액을 계산한다."""
    assert inp.purchase_date and inp.request_date and inp.purchase_price
    days = use_days(inp.purchase_date, inp.request_date) + (days_mode == "D1")
    life = life_years(inp, rule)
    band = rule.ratio_table.band(life, days)
    return Lookup(
        life_years=life,
        band=band,
        amount=_amount(inp.purchase_price, band.ratio_percent, rounding, share_percent),
    )


Combo = tuple[UseDays, Rounding, Scope]
_BASE_COMBO: Combo = ("D0", "floor", "allocate")


def _flip(combo: Combo, decision: Decision) -> Combo:
    d, r, s = combo
    if decision == "use_days":
        return ("D1" if d == "D0" else "D0", r, s)
    if decision == "rounding":
        return (d, "half_up" if r == "floor" else "floor", s)
    return (d, r, "whole_set" if s == "allocate" else "allocate")


def _changed(combo: Combo) -> list[Decision]:
    """결정 값 조합과 다른 결정 (DECISION_ORDER 순서)."""
    return [
        x for x, a, b in zip(DECISION_ORDER, combo, _BASE_COMBO, strict=True) if a != b
    ]


def sensitivity(
    inp: LaundryInput, rule: LaundryRule, basis: SetBasis | None = None
) -> tuple[Lookup, Sensitivity]:
    """결정 민감도 검사 (12.4). 결정 값 결과와 4 또는 8조합 검사 결과를 돌려준다.

    결정: 사용일수 산입(D0/D1) × 원 미만 처리(내림/half up) × 범위(배분/1벌 전체, R2 배분을 쓰고
    set_partial_request가 True가 아닐 때만). 원인은 12.4 4번 문장 그대로: 그 결정 하나만 대안으로
    바꿨을 때 결과가 달라지는 결정. 어느 결정도 혼자서는 바꾸지 않고 함께 바꿀 때만 달라지면,
    결과가 달라지는 조합에서 바꾼 결정을 모두 적는다.
    """
    share = basis.share_percent if basis is not None else 100
    scopes: tuple[Scope, ...] = (
        ("allocate", "whole_set")
        if basis is not None and basis.whole_set_check
        else ("allocate",)
    )
    combos: dict[Combo, Lookup] = {
        (d, r, s): lookup(inp, rule, d, r, share if s == "allocate" else 100)
        for d, r, s in product(("D0", "D1"), ("floor", "half_up"), scopes)
    }
    base = combos[_BASE_COMBO]

    def differs(combo: Combo) -> bool:
        # 내용연수 행·칸·배상액 중 하나라도 다르면 (조합에 없는 대안은 같다고 본다)
        return combo in combos and combos[combo] != base

    causes: list[Decision] = [
        x for x in DECISION_ORDER if differs(_flip(_BASE_COMBO, x))
    ]
    if not causes:
        together = {x for c in combos if differs(c) for x in _changed(c)}
        causes = [x for x in DECISION_ORDER if x in together]
    alt = combos[("D1", "floor", "allocate")].band
    amounts = [x.amount for x in combos.values()]
    return base, Sensitivity(
        min=min(amounts),
        max=max(amounts),
        causes=causes,
        ratio_alt=alt.ratio_percent
        if "use_days" in causes and alt != base.band
        else None,
    )


def _blocks_verified(
    rule: LaundryRule, method: Method, basis: SetBasis | None = None
) -> bool:
    """결과가 쓰는 블록만 본다 (12.4). Set 배분을 쓰면 set_allocation도 본다."""
    if method == "fallback":
        return rule.unproven_fallback.verified
    tables = rule.ratio_table.verified and rule.lifespan_table.verified
    if basis is not None and basis.allocated:
        return tables and rule.set_allocation.verified
    return tables


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
    basis: SetBasis | None = None,
) -> list[str]:
    """근거 조항 ID (12.7). R2: Set이면 laundry_6, 배분을 썼으면 바로 뒤에 laundry_7 (Q12 (a)+(b))."""
    ids: list[str] = []
    if method is not None:
        ids += ["laundry_types", "laundry_1", "laundry_5_1", "cpa16_3"]
        if method == "ratio":
            ids += ["laundry_ratio_table", "laundry_lifespan_table"]
        if basis is not None:
            ids.append("laundry_6")
            if basis.allocated:
                ids.append("laundry_7")
        elif inp.set_type != "none" and inp.set_part == "whole":
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
        by_code: dict[LaundryCode, tuple[str, ...]] = {
            L.UNSUPPORTED_DAMAGE: ("laundry_types",),
            L.SET_PARTIAL_UNSUPPORTED: ("laundry_7",),
            # 20배(5-1.③)와 배분(7.)의 관계가 정해져 있지 않다는 근거 (보고서 3.2, Q19 (a))
            L.SET_PARTIAL_FALLBACK_UNDEFINED: ("laundry_5_1", "laundry_7"),
            L.ATTACHMENT_UNSUPPORTED: ("laundry_8",),
            L.ITEM_NOT_IN_TABLE: ("cpa_dec9_2",),
        }
        ids += [cid for f in flags for cid in by_code.get(f, ())]
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


PART_LABELS: dict[str, str] = {"top": "상의", "mid": "중의", "bottom": "하의"}
# 한복 배정 (보고서 3.1 [해석], Q7 (a)): 저고리 = 상의, 치마·바지 = 하의
HANBOK_PART_LABELS: dict[str, dict[str, str]] = {
    "chima_jeogori": {"top": "저고리(상의)", "bottom": "치마(하의)"},
    "baji_jeogori": {"top": "저고리(상의)", "bottom": "바지(하의)"},
}


def part_labels(inp: LaundryInput) -> list[str]:
    """손상 벌 이름 (입력 순서 그대로). 숫자는 없다."""
    names = (
        HANBOK_PART_LABELS[inp.hanbok_kind]
        if inp.set_type == "hanbok" and inp.hanbok_kind is not None
        else PART_LABELS
    )
    return [names[p] for p in inp.damaged_parts or []]


def set_base_raw(price: int, share_percent: int) -> str:
    """원 미만 처리 전 배분 기준 가격 = 구입가격 × 비율 합 ÷ 100 (정확한 소수 문자열, 정수 연산)."""
    value = Fraction(price * share_percent, 100)
    whole, rem = divmod(value.numerator, value.denominator)
    if rem == 0:
        return str(whole)
    cents = (
        rem * 100 // value.denominator
    )  # 분모가 100의 약수라 소수 둘째 자리에서 끝난다
    return f"{whole}.{cents:02d}".rstrip("0")


def _set_step(inp: LaundryInput, basis: SetBasis) -> LaundryStep:
    assert inp.purchase_price is not None
    names = "·".join(part_labels(inp))
    if not basis.allocated:
        formula = (
            f"Set 구입가격 {_won(inp.purchase_price)} 전체 (모든 벌 {names}, 고시 6.①)"
        )
    else:
        formula = (
            f"Set 구입가격 {_won(inp.purchase_price)} × {names} {basis.share_percent}% "
            "(고시 7. 배분 비율, 원 미만 처리는 마지막에 한 번)"
        )
    return LaundryStep(label="Set 배분", formula=formula, amount=None)


def _ratio_steps(
    inp: LaundryInput,
    rule: LaundryRule,
    base: Lookup,
    sens: Sensitivity,
    basis: SetBasis | None = None,
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
    ]
    if basis is not None and basis.allocated:
        steps.append(_set_step(inp, basis))
        formula = (
            f"{_won(inp.purchase_price)} × {basis.share_percent}% × "
            f"{base.band.ratio_percent}%, {FLOOR_NOTE}"
        )
    else:
        if basis is not None:
            steps.append(_set_step(inp, basis))
        formula = (
            f"{_won(inp.purchase_price)} × {base.band.ratio_percent}%, {FLOOR_NOTE}"
        )
    steps.append(LaundryStep(label="배상액", formula=formula, amount=base.amount))
    if sens.sensitive:
        names = {
            "use_days": "사용일수 산입",
            "rounding": "원 미만 처리",
            "set_partial_damage": "Set 배분",
        }
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


def _set_outputs(
    inp: LaundryInput, basis: SetBasis | None, features: Collection[str]
) -> dict[str, object]:
    """R2 출력 필드 (보고서 3.2). R2가 꺼져 있거나 Set이 아니면 모두 None."""
    if not _r2(features) or inp.set_type == "none":
        return {}
    out: dict[str, object] = {
        "set_type": inp.set_type,
        "hanbok_kind": inp.hanbok_kind,
        "damaged_parts": list(inp.damaged_parts) if inp.damaged_parts else None,
    }
    if basis is not None and inp.purchase_price is not None and inp.proof_available:
        out["set_share_percent"] = basis.share_percent
        out["set_base_raw"] = set_base_raw(inp.purchase_price, basis.share_percent)
    return out


def calculate_damage(
    inp: LaundryInput, rule: LaundryRule, features: Collection[str] = ()
) -> LaundryResult:
    """범위 판정 → 계산 → 민감도 검사 → 제시액 비교 → 배지 (MVP_SPEC 12.2~12.7, R2 12.10).

    features에 SET_PARTIAL이 있으면 Set 일부 손상을 배분으로 계산한다. 없으면 축소 A 그대로.
    """
    scope = check_scope(inp, rule, features)
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
            **_set_outputs(inp, None, features),  # type: ignore[arg-type]
        )

    method: Method = "ratio" if inp.proof_available else "fallback"
    basis = set_basis(inp, rule, features)
    base: Lookup | None = None
    if method == "ratio":
        base, sens = sensitivity(inp, rule, basis)
        amount = base.amount
        assert inp.purchase_date and inp.request_date
        days: int | None = use_days(inp.purchase_date, inp.request_date)
        fallback_amount = None
        steps = _ratio_steps(inp, rule, base, sens, basis)
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
    verified = _blocks_verified(rule, method, basis)
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
        citations=_citations(inp, rule, flags, notices, method, basis),
        **_set_outputs(inp, basis, features),  # type: ignore[arg-type]
    )
