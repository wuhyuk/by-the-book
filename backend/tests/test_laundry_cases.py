"""세탁 승인 케이스 L1~L22 (사용자 승인(보고서 검토) 2026-11-10).

기대값은 docs/sources/laundry_cases_draft.md·vs4_cases_approval.md의 승인 케이스에 적힌 값만 쓴다
(배지·금액·사용일수·내용연수·배상비율·민감도 범위·원인·사유 코드·누락 항목·안내 코드·화면 한 줄).
새 기대 숫자를 만들지 않는다. 안내 코드는 기대값에 넣는다 (Q2 승인).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

from rules.badge import Badge
from rules.laundry import LaundryInput, LaundryResult, calculate_damage
from rules.laundry_codes import CommonFlag, LaundryFlag, LaundryNotice
from rules.laundry_display import build_laundry_display
from rules.laundry_rule import LaundryRule, load_laundry_rule

C = CommonFlag
L = LaundryFlag
N = LaundryNotice
D = date

OK, REVIEW, WARN, NONE = (
    Badge.CONFIRMED,
    Badge.NEEDS_REVIEW,
    Badge.WARNING,
    Badge.UNDETERMINABLE,
)
DEFECT_NOTICES = [
    N.RESTORE_FIRST,
    N.RECEIPT_BASIS,
    N.LAUNDRY_FEE_TERMS,
    N.CLAIM_PERIOD_TERMS,
]

BASE: dict[str, Any] = {
    "judgment_requested": False,
    "service_type": "laundry_shop",
    "damage_type": "defect",
    "proof_available": True,
}
L1_IN: dict[str, Any] = {
    "item_key": "mens_suit",
    "variant_key": "winter",
    "purchase_price": 400_000,
    "purchase_date": D(2025, 11, 1),
    "request_date": D(2026, 10, 1),
}


@dataclass(frozen=True)
class Case:
    id: str
    inp: dict[str, Any]
    badge: Badge
    amount: int | None = None
    flags: list[Any] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notices: list[LaundryNotice] = field(default_factory=list)
    use_days: int | None = None
    life_years: int | None = None
    ratio: int | None = None
    sens: tuple[int, int, list[str], int | None] | None = (
        None  # min, max, 원인, 대안 비율
    )
    line: str | None = None  # 화면 한 줄
    citations: list[str] | None = None


CASES: list[Case] = [
    Case("L1", L1_IN, OK, 280_000, notices=DEFECT_NOTICES, use_days=334, life_years=4, ratio=70,
         sens=(280_000, 280_000, [], None)),
    Case("L2", {"item_key": "shirts", "purchase_price": 50_000, "purchase_date": D(2026, 9, 1),
                "request_date": D(2026, 9, 29)},
         REVIEW, 47_500, [L.DECISION_SENSITIVE], notices=DEFECT_NOTICES, use_days=28, life_years=2,
         ratio=95, sens=(40_000, 47_500, ["use_days"], 80),
         line="고시에 정해져 있지 않은 사용일수 산입 방식(구입일을 세는지)에 따라 배상비율이 95%에서 "
              "80%로 바뀌어, 기준 금액이 40,000원~47,500원으로 달라질 수 있습니다."),
    Case("L3", {"item_key": "blouse", "variant_key": "silk", "purchase_price": 123_457,
                "purchase_date": D(2025, 5, 20), "request_date": D(2026, 10, 2)},
         REVIEW, 61_728, [L.DECISION_SENSITIVE], notices=DEFECT_NOTICES, use_days=500, life_years=3,
         ratio=50, sens=(61_728, 61_729, ["rounding"], None),
         line="고시에 정해져 있지 않은 원 미만 처리(내림·반올림)에 따른 1원 차이가 있습니다 "
              "(61,728원~61,729원)."),
    Case("L4", {"item_key": "womens_suit", "variant_key": "spring_fall", "set_type": "top_bottom",
                "set_part": "top", "purchase_price": 300_000, "purchase_date": D(2026, 2, 22),
                "request_date": D(2026, 9, 10)},
         NONE, flags=[L.SET_PARTIAL_UNSUPPORTED],
         line="세트 의류의 일부만 손상·분실된 경우는 소비자분쟁해결기준의 기준표에 배상액 배분 규정이 "
              "있으나, 이번 버전에서는 지원하지 않습니다. 1372 또는 한국소비자원에 문의해 주세요."),
    Case("L5", {"damage_type": "loss", "proof_available": False, "laundry_fee": 8_000},
         OK, 160_000,
         notices=[N.UNPROVEN_FALLBACK, N.RECEIPT_BASIS, N.LAUNDRY_FEE_TERMS, N.CLAIM_PERIOD_TERMS]),
    Case("L6", {"damage_type": "loss", "item_key": "carpet", "variant_key": "wool",
                "purchase_price": 1_000_000, "purchase_date": D(2017, 10, 16),
                "request_date": D(2026, 10, 15)},
         OK, 100_000, notices=[N.RECEIPT_BASIS, N.LAUNDRY_FEE_TERMS, N.CLAIM_PERIOD_TERMS],
         use_days=3_286, life_years=6, ratio=10),
    Case("L7", {"item_key": "mens_suit", "purchase_price": 500_000, "purchase_date": D(2025, 11, 24),
                "request_date": D(2026, 9, 20)},
         REVIEW, flags=[C.MISSING_REQUIRED], missing=["variant_key"]),
    Case("L8", {"item_key": "sweater", "purchase_price": 200_000, "purchase_date": D(2026, 4, 27),
                "request_date": D(2026, 8, 5), "provider_offer": 100_000},
         WARN, 160_000, [L.OFFER_BELOW_STANDARD_MIN], notices=DEFECT_NOTICES, use_days=100,
         life_years=3, ratio=80, sens=(160_000, 160_000, [], None)),
    Case("L9", {**L1_IN, "judgment_requested": True}, NONE, flags=[C.JUDGMENT_REQUESTED]),
    Case("L10", {"item_key": "coat", "purchase_price": 300_000, "request_date": D(2026, 10, 20),
                 "proof_available": None},
         REVIEW, flags=[C.MISSING_REQUIRED], missing=["proof_available"]),
    Case("L11", {"item_unlisted": True, "purchase_price": 50_000, "purchase_date": D(2026, 3, 1),
                 "request_date": D(2026, 10, 1)},
         NONE, flags=[L.ITEM_NOT_IN_TABLE], citations=["cpa_dec9_2"]),
    Case("L12", {**L1_IN, "manufacturing_cause_claimed": True}, NONE, flags=[L.MANUFACTURING_CAUSE],
         line="의복류 등 다른 품목 기준의 대상일 수 있습니다. 1372에 문의해 주세요."),
    Case("L13", {**L1_IN, "special_agreement": True}, REVIEW, 280_000, [L.SPECIAL_AGREEMENT],
         notices=DEFECT_NOTICES, sens=(280_000, 280_000, [], None)),
    Case("L14", {"item_key": "coat", "purchase_price": 300_000, "purchase_date": D(2025, 10, 1),
                 "request_date": D(2026, 9, 23)},
         REVIEW, 210_000, [L.DECISION_SENSITIVE], notices=DEFECT_NOTICES, use_days=357, life_years=4,
         ratio=70, sens=(180_000, 210_000, ["use_days"], 60),
         line="고시에 정해져 있지 않은 사용일수 산입 방식(구입일을 세는지)에 따라 배상비율이 70%에서 "
              "60%로 바뀌어, 기준 금액이 180,000원~210,000원으로 달라질 수 있습니다."),
    Case("L15", {"item_key": "coat", "purchase_price": 300_000, "purchase_date": D(2025, 10, 1),
                 "request_date": D(2026, 9, 22)},
         OK, 210_000, notices=DEFECT_NOTICES, use_days=356, life_years=4, ratio=70),
    Case("L16", {**L1_IN, "service_type": "self_laundromat"}, NONE, flags=[L.UNSUPPORTED_SERVICE]),
    Case("L17", {**L1_IN, "damage_type": "other"}, NONE, flags=[L.UNSUPPORTED_DAMAGE]),
    Case("L18", {"item_key": "coat", "purchase_price": 300_000, "purchase_date": D(2025, 12, 1),
                 "request_date": D(2026, 10, 1), "attachment_only": True},
         NONE, flags=[L.ATTACHMENT_UNSUPPORTED],
         line="탈부착 부속물(털, 칼라, 모자 등)이 손상된 경우는 소비자분쟁해결기준의 기준표에 규정이 "
              "있으나, 이번 버전에서는 지원하지 않습니다. 1372 또는 한국소비자원에 문의해 주세요."),
    Case("L19", {"item_key": "sweater", "purchase_price": 150_000, "purchase_date": D(2026, 10, 5),
                 "request_date": D(2026, 9, 5)},
         REVIEW, flags=[C.INVALID_INPUT]),
    Case("L20", {"item_key": "hanbok", "purchase_price": 250_000, "purchase_date": D(2025, 3, 15),
                 "request_date": D(2026, 1, 20)},
         OK, 175_000, notices=DEFECT_NOTICES, use_days=311, life_years=4, ratio=70,
         sens=(175_000, 175_000, [], None)),
    Case("L21", {"item_key": "sweater", "purchase_price": 98_765, "purchase_date": D(2026, 7, 1),
                 "request_date": D(2026, 8, 13)},
         REVIEW, 93_826, [L.DECISION_SENSITIVE], notices=DEFECT_NOTICES, use_days=43, life_years=3,
         ratio=95, sens=(79_012, 93_827, ["use_days", "rounding"], 80),
         line="고시에 정해져 있지 않은 사용일수 산입 방식과 원 미만 처리에 따라 기준 금액이 "
              "79,012원~93,827원으로 달라질 수 있습니다."),
    Case("L22", {"item_key": "sweater", "purchase_price": 200_000, "purchase_date": D(2026, 4, 27),
                 "request_date": D(2026, 8, 5), "provider_offer": 160_000},
         OK, 160_000, notices=DEFECT_NOTICES, sens=(160_000, 160_000, [], None)),
]  # fmt: skip


@pytest.fixture(scope="module")
def rule() -> LaundryRule:
    return load_laundry_rule()


def run(rule: LaundryRule, inp: dict[str, Any]) -> LaundryResult:
    return calculate_damage(LaundryInput(**{**BASE, **inp}), rule)


def case(case_id: str) -> Case:
    return next(c for c in CASES if c.id == case_id)


@pytest.mark.parametrize("c", CASES, ids=[c.id for c in CASES])
def test_approved_case(rule: LaundryRule, c: Case) -> None:
    case = c
    r = run(rule, case.inp)
    assert r.badge == case.badge
    assert r.amount == case.amount
    assert r.calculated == (case.amount is not None)
    assert r.flags == case.flags
    assert r.missing == case.missing
    assert r.notices == case.notices
    if case.use_days is not None:
        assert (r.use_days, r.life_years, r.ratio_percent) == (
            case.use_days,
            case.life_years,
            case.ratio,
        )
    if case.sens is not None:
        lo, hi, causes, alt = case.sens
        assert (r.sensitivity_min, r.sensitivity_max) == (lo, hi)
        assert r.sensitivity_causes == causes
        assert r.sensitivity_ratio_alt == alt
    if case.line is not None:
        display = build_laundry_display(r, rule)
        assert display.screen_line is not None
        assert display.screen_line.text == case.line
    if case.citations is not None:
        assert r.citations == case.citations
    if case.badge == NONE:
        assert build_laundry_display(r, rule).consult is not None


def test_l5_fallback_amount(rule: LaundryRule) -> None:
    r = run(rule, case("L5").inp)
    assert r.method == "fallback" and r.fallback_amount == 160_000


def test_l19_no_consult(rule: LaundryRule) -> None:
    """입력 오류는 다시 입력하면 되므로 상담 창구를 붙이지 않는다 (L19)."""
    assert build_laundry_display(run(rule, case("L19").inp), rule).consult is None


def test_l20_variant_key_is_ignored(rule: LaundryRule) -> None:
    """값이 하나인 행(한복류)에 소재(견)가 와도 무시하고 L20과 같은 결과 (Q4 변경, 2026-11-10)."""
    base = run(rule, case("L20").inp)
    with_variant = run(rule, {**case("L20").inp, "variant_key": "silk"})
    assert with_variant.model_dump() == base.model_dump()
