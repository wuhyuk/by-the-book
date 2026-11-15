"""가전 P2 환급 기준 금액 규칙 엔진 (MVP_SPEC 13절, docs/sources/appliance_cases.md, 승인 2026-11-15).

별표 Ⅱ ① (2-2) 5) "부품보유기간 이내에 수리용 부품을 보유하고 있지 않아 발생한 피해 / 품질보증기간 경과 후 →
정액 감가 상각한 잔여 금액에 구입가의 10%를 가산하여 환급"만 계산한다.
순수 함수만 둔다. LLM을 호출하지 않는다. 금액은 int, 비율은 Fraction 정수 연산이며 float를 쓰지 않는다.
표 값(품질보증기간, 부품보유기간, 가산 비율)과 지원 품목은 규칙 JSON(ApplianceRule)에서 읽는다.
원문에 없는 결정(D-1~D-10)은 보고서 3.2 기본값이고, D-4·D-6·D-7은 결정 민감도 검사(8조합)에 넣는다.
"""

import calendar
from datetime import date
from fractions import Fraction
from itertools import product
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rules.appliance_codes import (
    APPLIANCE_NO_CALC,
    APPLIANCE_ROBUST,
    APPLIANCE_UNDETERMINABLE,
    ApplianceCode,
    ApplianceFlag,
    ApplianceNotice,
    order_appliance_flags,
)
from rules.appliance_rule import ApplianceRule
from rules.badge import Badge, decide_badge
from rules.laundry_codes import CommonFlag

C = CommonFlag
A = ApplianceFlag
N = ApplianceNotice

Decision = Literal["partial_month", "rounding", "cap"]
DECISION_ORDER: tuple[Decision, ...] = ("partial_month", "rounding", "cap")
PartialMonth = Literal["ceil", "floor"]
Rounding = Literal["floor", "half_up"]
Cap = Literal["cap", "none"]
Combo = tuple[PartialMonth, Rounding, Cap]
BASE_COMBO: Combo = ("ceil", "floor", "cap")
FLOOR_NOTE = "원 미만 내림(고시에 규정 없음)"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ApplianceInput(_Model):
    """입력 (보고서 3.3, 폼으로만 받는다)."""

    judgment_requested: bool
    item_key: str | None = None
    item_unlisted: bool = False
    purchase_price: int | None = None
    purchase_date: date | None = None  # 구입일 (인도일이 다르면 인도일)
    request_date: date | None = None  # 수리 접수일
    manufacture_date: date | None = None
    parts_unavailable: bool | None = None
    certificate_confirmed: bool | None = None
    certificate_warranty_months: int | None = None
    certificate_parts_years: int | None = None
    provider_offer: int | None = None


class ApplianceStep(_Model):
    label: str
    formula: str
    amount: int | None


class ApplianceResult(_Model):
    badge: Badge
    calculated: bool
    item_key: str | None
    row_id: str | None
    warranty_months: int | None
    life_months: int | None
    used_months: int | None  # 결정 값 (끝수 올림)
    used_months_full: int | None  # 완전한 개월 수
    partial_month: bool | None  # 1개월 미만 끝수가 있는지
    amount: int | None
    sensitivity_min: int | None
    sensitivity_max: int | None
    sensitivity_causes: list[Decision]
    steps: list[ApplianceStep]
    flags: list[ApplianceCode]
    missing: list[str]
    notices: list[ApplianceNotice]
    citations: list[str]


# ---- 날짜 (D-5) ----


def add_months(start: date, months: int) -> date:
    """같은 날짜, 그 날짜가 없는 달은 그 달 말일 (D-5)."""
    y, m = divmod(start.month - 1 + months, 12)
    year, month = start.year + y, m + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def months_between(start: date, end: date) -> tuple[int, bool]:
    """(완전한 개월 수, 1개월 미만 끝수가 있는지)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    while months > 0 and add_months(start, months) > end:
        months -= 1
    return months, add_months(start, months) != end


# ---- 범위 판정 (보고서 3.4) ----

REQUIRED = (
    "item_key",
    "purchase_price",
    "purchase_date",
    "request_date",
    "parts_unavailable",
)


class Periods(_Model):
    warranty_months: int
    life_months: int


def _missing(inp: ApplianceInput) -> list[str]:
    return [
        f
        for f in REQUIRED
        if getattr(inp, f) is None and not (f == "item_key" and inp.item_unlisted)
    ]


def _invalid(inp: ApplianceInput, rule: ApplianceRule) -> bool:
    assert inp.purchase_price is not None
    assert inp.purchase_date is not None and inp.request_date is not None
    return (
        inp.item_key is None
        or rule.supported(inp.item_key) is None
        or inp.purchase_price <= 0
        or inp.request_date < inp.purchase_date
        or (
            inp.manufacture_date is not None
            and inp.manufacture_date > inp.purchase_date
        )
        or (inp.provider_offer is not None and inp.provider_offer < 0)
        or any(
            v is not None and v <= 0
            for v in (inp.certificate_warranty_months, inp.certificate_parts_years)
        )
    )


def periods(inp: ApplianceInput, rule: ApplianceRule) -> Periods:
    """보증서 기간이 고시보다 길면 보증서 기간 (D-10, 별표 Ⅳ, 시행령 별표 1 4.가)."""
    assert inp.item_key is not None
    item = rule.supported(inp.item_key)
    assert item is not None
    row = rule.items.row(item.row)
    assert row is not None
    years = max(row.parts_years, inp.certificate_parts_years or 0)
    return Periods(
        warranty_months=max(row.warranty_months, inp.certificate_warranty_months or 0),
        life_months=rule.lifespan_rule.years_to_months * years,
    )


class Scope(_Model):
    stop_code: ApplianceCode | None
    missing: list[str]
    review: list[ApplianceCode]


def check_scope(inp: ApplianceInput, rule: ApplianceRule) -> Scope:
    def stop(code: ApplianceCode, missing: list[str] | None = None) -> Scope:
        return Scope(stop_code=code, missing=missing or [], review=[])

    if inp.judgment_requested:
        return stop(C.JUDGMENT_REQUESTED)
    if inp.item_unlisted:
        return stop(A.APPLIANCE_ITEM_NOT_SUPPORTED)
    if inp.parts_unavailable is False:
        return stop(A.PARTS_AVAILABLE)
    missing = _missing(inp)
    if missing:
        return stop(C.MISSING_REQUIRED, missing)
    if _invalid(inp, rule):
        return stop(C.INVALID_INPUT)
    assert inp.purchase_date is not None and inp.request_date is not None
    per = periods(inp, rule)
    review: list[ApplianceCode] = []
    warranty_end = add_months(inp.purchase_date, per.warranty_months)
    if inp.request_date < warranty_end:
        return stop(A.WITHIN_WARRANTY)
    if inp.request_date == warranty_end:
        review.append(A.PERIOD_BOUNDARY)
    if inp.manufacture_date is not None:
        parts_end = add_months(inp.manufacture_date, per.life_months)
        if inp.request_date > parts_end:
            return stop(A.OUTSIDE_PARTS_PERIOD)
        if inp.request_date == parts_end:
            review.append(A.PERIOD_BOUNDARY)
    elif inp.request_date > add_months(inp.purchase_date, per.life_months):
        return stop(A.OUTSIDE_PARTS_PERIOD)  # 제조일 ≤ 구입일이라 확실히 지남 (D-9)
    else:
        review.append(A.PARTS_PERIOD_UNCONFIRMED)
    if inp.certificate_confirmed is not True:
        review.append(A.CERTIFICATE_UNCONFIRMED)
    return Scope(stop_code=None, missing=[], review=list(dict.fromkeys(review)))


# ---- 계산 (보고서 3.5) ----


def refund(
    price: int, life_months: int, used_months: int, add_on_percent: int, combo: Combo
) -> int:
    """구입가 − 구입가 × 사용 개월 ÷ 내용연수 + 구입가 × 가산 % ÷ 100, 한도·원 미만 처리 (D-6·D-7)."""
    _, rounding, cap = combo
    exact = (
        Fraction(price)
        - Fraction(price * used_months, life_months)
        + Fraction(price * add_on_percent, 100)
    )
    if cap == "cap":
        exact = min(exact, Fraction(price))
    if rounding == "floor":
        return exact.numerator // exact.denominator
    return (2 * exact.numerator + exact.denominator) // (2 * exact.denominator)


class Sensitivity(_Model):
    min: int
    max: int
    causes: list[Decision]


def _flip(combo: Combo, decision: Decision) -> Combo:
    p, r, c = combo
    if decision == "partial_month":
        return ("floor" if p == "ceil" else "ceil", r, c)
    if decision == "rounding":
        return (p, "half_up" if r == "floor" else "floor", c)
    return (p, r, "none" if c == "cap" else "cap")


def sensitivity(
    price: int, life_months: int, full: int, partial: bool, add_on_percent: int
) -> tuple[int, Sensitivity]:
    """8조합 결정 민감도 검사. 원인은 세탁 12.4 4번 문장과 같은 방식."""

    def value(combo: Combo) -> int:
        used = full + (1 if combo[0] == "ceil" and partial else 0)
        return refund(price, life_months, used, add_on_percent, combo)

    combos: dict[Combo, int] = {
        k: value(k)
        for k in product(("ceil", "floor"), ("floor", "half_up"), ("cap", "none"))
    }
    base = combos[BASE_COMBO]
    causes = [x for x in DECISION_ORDER if combos[_flip(BASE_COMBO, x)] != base]
    if not causes:
        together = {
            name
            for k, v in combos.items()
            if v != base
            for name, a, b in zip(DECISION_ORDER, k, BASE_COMBO, strict=True)
            if a != b
        }
        causes = [x for x in DECISION_ORDER if x in together]
    return base, Sensitivity(
        min=min(combos.values()), max=max(combos.values()), causes=causes
    )


def _blocks_verified(rule: ApplianceRule) -> bool:
    """결과가 쓰는 블록 (보고서 3.5)."""
    return (
        rule.items.verified
        and rule.lifespan_rule.verified
        and rule.depreciation.verified
        and rule.resolution_table.verified
    )


def _citations(
    inp: ApplianceInput, flags: list[ApplianceCode], calculated: bool
) -> list[str]:
    if calculated:
        ids = [
            "elec_5",
            "elec_note_dep",
            "elec_note_received",
            "annex4",
            "annex3_items",
        ]
        if inp.manufacture_date is not None:
            ids.append("annex3_parts_start")
        if inp.certificate_warranty_months or inp.certificate_parts_years:
            ids.append("gen_4_ga")
        return [*ids, "gen_4_ra", "cpa16_3"]
    first = flags[0]
    if first == A.APPLIANCE_ITEM_NOT_SUPPORTED:
        return ["annex4"]
    if first == A.PARTS_AVAILABLE:
        return ["elec_5"]
    if first == A.WITHIN_WARRANTY:
        cert = ["gen_4_ga"] if inp.certificate_warranty_months else []
        return ["elec_5", "annex3_items", *cert, "gen_4_ra"]
    if first == A.OUTSIDE_PARTS_PERIOD:
        return ["elec_5", "annex3_items", "annex3_parts_start"]
    return []


def _won(n: int) -> str:
    return f"{n:,}"


CAUSE_NAMES: dict[str, str] = {
    "partial_month": "사용 개월의 1개월 미만 처리",
    "rounding": "원 미만 처리",
    "cap": "구입가 한도",
}


def _steps(
    inp: ApplianceInput,
    rule: ApplianceRule,
    per: Periods,
    full: int,
    partial: bool,
    used: int,
    amount: int,
    sens: Sensitivity,
) -> list[ApplianceStep]:
    assert (
        inp.item_key and inp.purchase_price and inp.purchase_date and inp.request_date
    )
    item = rule.supported(inp.item_key)
    assert item is not None
    row = rule.items.row(item.row)
    assert row is not None
    price, pct = inp.purchase_price, rule.depreciation.add_on.add_on_percent
    tail = (
        f"완전한 {full}개월 + 1개월 미만 끝수 → 올림 {used}개월 (고시에 규정 없음)"
        if partial
        else f"{used}개월"
    )
    steps = [
        ApplianceStep(
            label="사용 개월",
            formula=f"{inp.purchase_date.isoformat()} → {inp.request_date.isoformat()}, {tail}",
            amount=None,
        ),
        ApplianceStep(
            label="내용연수",
            formula=f"{item.label} (별표 Ⅲ '{row.annex3_label}' 부품보유기간) → "
            f"{per.life_months}개월 (별표 Ⅳ, 월할계산)",
            amount=None,
        ),
        ApplianceStep(
            label="환급액",
            formula=f"{_won(price)} − {_won(price)} × {used} ÷ {per.life_months} + "
            f"{_won(price)} × {pct}%, {FLOOR_NOTE}"
            + (", 구입가 한도 적용(고시에 규정 없음)" if amount == price else ""),
            amount=amount,
        ),
    ]
    if sens.causes:
        cause = "·".join(CAUSE_NAMES[c] for c in sens.causes)
        text = f"고시에 없는 결정({cause})을 바꾸면 결과가 달라집니다: {_won(sens.min)}원~{_won(sens.max)}원"
    else:
        text = "1개월 미만 처리, 원 미만 처리, 구입가 한도를 바꿔도 결과가 같습니다"
    steps.append(ApplianceStep(label="결정 민감도 검사", formula=text, amount=None))
    return steps


def calculate_appliance(inp: ApplianceInput, rule: ApplianceRule) -> ApplianceResult:
    """범위 판정 → 계산 → 결정 민감도 검사 → 제시액 비교 → 배지."""
    scope = check_scope(inp, rule)
    empty = {
        "row_id": None,
        "warranty_months": None,
        "life_months": None,
        "used_months": None,
        "used_months_full": None,
        "partial_month": None,
        "amount": None,
        "sensitivity_min": None,
        "sensitivity_max": None,
        "sensitivity_causes": [],
        "steps": [],
        "notices": [],
    }
    if scope.stop_code is not None:
        flags: list[ApplianceCode] = [scope.stop_code]
        return ApplianceResult(
            badge=decide_badge(
                judgment_requested=inp.judgment_requested,
                out_of_scope=scope.stop_code in APPLIANCE_UNDETERMINABLE,
                missing_or_invalid=scope.stop_code in APPLIANCE_NO_CALC,
                robust_warnings=[],
                review_flags=[],
            ),
            calculated=False,
            item_key=inp.item_key,
            flags=flags,
            missing=scope.missing,
            citations=_citations(inp, flags, calculated=False),
            **empty,  # type: ignore[arg-type]
        )
    assert (
        inp.item_key and inp.purchase_price and inp.purchase_date and inp.request_date
    )
    per = periods(inp, rule)
    full, partial = months_between(inp.purchase_date, inp.request_date)
    used = full + (1 if partial else 0)
    pct = rule.depreciation.add_on.add_on_percent
    amount, sens = sensitivity(inp.purchase_price, per.life_months, full, partial, pct)
    verified = _blocks_verified(rule)
    robust: list[ApplianceCode] = []
    if inp.provider_offer is not None and inp.provider_offer < sens.min and verified:
        robust.append(A.OFFER_BELOW_STANDARD_MIN)
    assert set(robust) <= APPLIANCE_ROBUST
    review: list[ApplianceCode] = list(scope.review)
    if not verified:
        review.append(C.RULE_UNVERIFIED)
    if sens.causes:
        review.append(A.DECISION_SENSITIVE)
    flags = order_appliance_flags(robust + review)
    item = rule.supported(inp.item_key)
    assert item is not None
    return ApplianceResult(
        badge=decide_badge(
            judgment_requested=False,
            out_of_scope=False,
            missing_or_invalid=False,
            robust_warnings=robust,
            review_flags=review,
        ),
        calculated=True,
        item_key=inp.item_key,
        row_id=item.row,
        warranty_months=per.warranty_months,
        life_months=per.life_months,
        used_months=used,
        used_months_full=full,
        partial_month=partial,
        amount=amount,
        sensitivity_min=sens.min,
        sensitivity_max=sens.max,
        sensitivity_causes=sens.causes,
        steps=_steps(inp, rule, per, full, partial, used, amount, sens),
        flags=flags,
        missing=[],
        notices=[N.RECEIVED_DATE_BASIS, N.USED_MONTHS_BASIS],
        citations=_citations(inp, flags, calculated=True),
    )
