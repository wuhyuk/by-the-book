"""세탁 범위 판정·누락·입력 검증·안내·인용·블록 검증 (MVP_SPEC 12.1·12.2·12.4·12.5·12.7).

명세 표의 행마다 구조(사유 코드·배지·계산 여부)만 확인한다. 금액 기대값은 쓰지 않는다
(케이스 금액은 사용자 승인 뒤에 tests/test_laundry_cases.py로 옮긴다).
"""

from datetime import date
from typing import Any

import pytest

from rules.badge import Badge
from rules.laundry import LaundryInput, calculate_damage, check_scope
from rules.laundry_codes import CommonFlag, LaundryFlag, LaundryNotice
from rules.laundry_rule import LaundryRule, load_laundry_rule

C = CommonFlag
L = LaundryFlag
N = LaundryNotice

# 계산 가능한 입력 하나 (구조 확인용, 금액은 비교하지 않는다)
OK: dict[str, Any] = {
    "judgment_requested": False,
    "service_type": "laundry_shop",
    "damage_type": "defect",
    "item_key": "coat",
    "purchase_price": 100_000,
    "purchase_date": date(2026, 1, 1),
    "request_date": date(2026, 3, 1),
    "proof_available": True,
}


def inp(**kw: Any) -> LaundryInput:
    return LaundryInput(**{**OK, **kw})


@pytest.fixture(scope="module")
def rule() -> LaundryRule:
    return load_laundry_rule()


SCOPE_ROWS: list[tuple[str, dict[str, Any], LaundryFlag | CommonFlag]] = [
    ("1 승패", {"judgment_requested": True}, C.JUDGMENT_REQUESTED),
    ("2 무인세탁소", {"service_type": "self_laundromat"}, L.UNSUPPORTED_SERVICE),
    ("2 그 외", {"service_type": "other"}, L.UNSUPPORTED_SERVICE),
    ("3 지체", {"damage_type": "other"}, L.UNSUPPORTED_DAMAGE),
    ("4 제조 불량", {"manufacturing_cause_claimed": True}, L.MANUFACTURING_CAUSE),
    (
        "5 Set 일부",
        {"set_type": "top_bottom", "set_part": "bottom"},
        L.SET_PARTIAL_UNSUPPORTED,
    ),
    (
        "5 한복 상의",
        {"set_type": "hanbok", "set_part": "top"},
        L.SET_PARTIAL_UNSUPPORTED,
    ),
    ("6 부속물", {"attachment_only": True}, L.ATTACHMENT_UNSUPPORTED),
    ("7 표에 없음", {"item_key": None, "item_unlisted": True}, L.ITEM_NOT_IN_TABLE),
]


@pytest.mark.parametrize(
    ("name", "kw", "code"), SCOPE_ROWS, ids=[r[0] for r in SCOPE_ROWS]
)
def test_undeterminable_rows(
    rule: LaundryRule, name: str, kw: dict[str, Any], code: LaundryFlag | CommonFlag
) -> None:
    r = calculate_damage(inp(**kw), rule)
    assert r.flags == [code]
    assert r.badge == Badge.UNDETERMINABLE
    assert not r.calculated and r.amount is None and r.notices == []


def test_order_first_wins(rule: LaundryRule) -> None:
    r = check_scope(
        inp(judgment_requested=True, service_type="x", attachment_only=True), rule
    )
    assert r.stop_code == C.JUDGMENT_REQUESTED
    r = check_scope(
        inp(set_type="top_bottom", set_part="top", attachment_only=True), rule
    )
    assert r.stop_code == L.SET_PARTIAL_UNSUPPORTED


def test_set_partial_checked_before_proof(rule: LaundryRule) -> None:
    """순서 5·6은 입증 여부와 무관하게 먼저 (12.2)."""
    r = check_scope(
        inp(proof_available=False, laundry_fee=5000, attachment_only=True), rule
    )
    assert r.stop_code == L.ATTACHMENT_UNSUPPORTED


def test_unlisted_item_ignored_for_fallback(rule: LaundryRule) -> None:
    """20배는 내용연수를 쓰지 않아 표에 없는 품목도 계산한다 (12.2 순서 7)."""
    r = calculate_damage(
        inp(item_key=None, item_unlisted=True, proof_available=False, laundry_fee=5000),
        rule,
    )
    assert r.calculated and r.method == "fallback"


@pytest.mark.parametrize(
    ("kw", "missing"),
    [
        ({"proof_available": None, "purchase_date": None}, ["proof_available"]),
        ({"item_key": None}, ["item_key"]),
        ({"item_key": "mens_suit"}, ["variant_key"]),
        (
            {"purchase_price": None, "purchase_date": None, "request_date": None},
            ["purchase_price", "purchase_date", "request_date"],
        ),
        ({"proof_available": False}, ["laundry_fee"]),
        ({"set_type": "top_bottom"}, ["set_part"]),
        ({"set_type": "top_bottom", "proof_available": None}, ["proof_available"]),
    ],
)
def test_missing_required(
    rule: LaundryRule, kw: dict[str, Any], missing: list[str]
) -> None:
    r = calculate_damage(inp(**kw), rule)
    assert r.flags == [C.MISSING_REQUIRED]
    assert r.missing == missing
    assert r.badge == Badge.NEEDS_REVIEW and not r.calculated


@pytest.mark.parametrize(
    "kw",
    [
        {"purchase_price": 0},
        {"request_date": date(2025, 12, 31)},
        {"item_key": "no_such_item"},
        {"item_key": "blouse", "variant_key": "wool"},
        {"set_type": "top_bottom", "set_part": "mid"},
        {"set_part": "whole"},
        {"provider_offer": -1},
        {"proof_available": False, "laundry_fee": 0},
    ],
)
def test_invalid_input(rule: LaundryRule, kw: dict[str, Any]) -> None:
    r = calculate_damage(inp(**kw), rule)
    assert r.flags == [C.INVALID_INPUT]
    assert r.badge == Badge.NEEDS_REVIEW and not r.calculated


def test_zero_offer_is_valid(rule: LaundryRule) -> None:
    r = calculate_damage(inp(provider_offer=0), rule)
    assert r.calculated and L.OFFER_BELOW_STANDARD_MIN in r.flags


def test_fallback_ignores_ratio_fields(rule: LaundryRule) -> None:
    """20배 경로는 품목·날짜를 검증하지 않는다 (12.1)."""
    r = calculate_damage(
        inp(proof_available=False, laundry_fee=5000, request_date=date(2020, 1, 1)),
        rule,
    )
    assert r.calculated and r.method == "fallback"


def test_set_whole_is_computed_and_cites_6(rule: LaundryRule) -> None:
    r = calculate_damage(inp(set_type="top_bottom", set_part="whole"), rule)
    assert r.calculated and "laundry_6" in r.citations


@pytest.mark.parametrize(
    ("kw", "code", "citation"),
    [
        ({"special_agreement": True}, L.SPECIAL_AGREEMENT, "laundry_1"),
        ({"customer_partial_fault": True}, L.PARTIAL_FAULT_CLAIMED, "laundry_2"),
        ({"wants_damaged_item": True}, L.DAMAGED_ITEM_RETURN, "laundry_2"),
        ({"no_issue_confirmation": True}, L.EXEMPTION_CLAIMED, "laundry_3"),
        ({"uncollected": True}, L.EXEMPTION_CLAIMED, "laundry_3"),
    ],
)
def test_claims_are_review_flags(
    rule: LaundryRule, kw: dict[str, Any], code: LaundryFlag, citation: str
) -> None:
    r = calculate_damage(inp(**kw, provider_offer=0), rule)
    assert r.calculated and code in r.flags
    assert L.OFFER_BELOW_STANDARD_MIN not in r.flags  # 주장이 있으면 ⚠️ 판정 안 함
    assert r.badge == Badge.NEEDS_REVIEW
    assert citation in r.citations


def test_notices_by_condition(rule: LaundryRule) -> None:
    r = calculate_damage(inp(), rule)
    assert r.notices == [
        N.RESTORE_FIRST,
        N.RECEIPT_BASIS,
        N.LAUNDRY_FEE_TERMS,
        N.CLAIM_PERIOD_TERMS,
    ]
    r = calculate_damage(
        inp(
            damage_type="loss",
            proof_available=False,
            laundry_fee=1,
            receipt_issued=False,
        ),
        rule,
    )
    assert r.notices == [
        N.UNPROVEN_FALLBACK,
        N.RECEIPT_BASIS,
        N.NO_RECEIPT_LOSS,
        N.LAUNDRY_FEE_TERMS,
        N.CLAIM_PERIOD_TERMS,
    ]
    assert "laundry_5" in r.citations
    r = calculate_damage(inp(damage_type="loss", receipt_issued=True), rule)
    assert N.NO_RECEIPT_LOSS not in r.notices


def test_citations_for_computed_and_stopped(rule: LaundryRule) -> None:
    r = calculate_damage(inp(), rule)
    assert r.citations[:6] == [
        "laundry_types",
        "laundry_1",
        "laundry_5_1",
        "cpa16_3",
        "laundry_ratio_table",
        "laundry_lifespan_table",
    ]
    fb = calculate_damage(inp(proof_available=False, laundry_fee=1), rule)
    assert "laundry_ratio_table" not in fb.citations
    stopped = {
        L.UNSUPPORTED_DAMAGE: ({"damage_type": "other"}, ["laundry_types"]),
        L.SET_PARTIAL_UNSUPPORTED: (
            {"set_type": "top_bottom", "set_part": "top"},
            ["laundry_7"],
        ),
        L.ATTACHMENT_UNSUPPORTED: ({"attachment_only": True}, ["laundry_8"]),
        L.ITEM_NOT_IN_TABLE: (
            {"item_key": None, "item_unlisted": True},
            ["cpa_dec9_2"],
        ),
        L.UNSUPPORTED_SERVICE: ({"service_type": "self_laundromat"}, []),
    }
    for kw, ids in stopped.values():
        assert calculate_damage(inp(**kw), rule).citations == ids


def _unverified(rule: LaundryRule, block: str) -> LaundryRule:
    b = getattr(rule, block)
    return rule.model_copy(update={block: b.model_copy(update={"verified": False})})


@pytest.mark.parametrize("block", ["ratio_table", "lifespan_table"])
def test_unverified_ratio_blocks(rule: LaundryRule, block: str) -> None:
    """쓰는 블록이 미검증이면 RULE_UNVERIFIED 🔍, ⚠️는 켜지 않는다 (12.4)."""
    r = calculate_damage(inp(provider_offer=0), _unverified(rule, block))
    assert C.RULE_UNVERIFIED in r.flags
    assert L.OFFER_BELOW_STANDARD_MIN not in r.flags
    assert r.badge == Badge.NEEDS_REVIEW
    # 20배는 표 블록을 쓰지 않는다
    fb = calculate_damage(
        inp(proof_available=False, laundry_fee=1), _unverified(rule, block)
    )
    assert C.RULE_UNVERIFIED not in fb.flags


def test_unverified_fallback_block(rule: LaundryRule) -> None:
    bad = _unverified(rule, "unproven_fallback")
    assert (
        C.RULE_UNVERIFIED
        in calculate_damage(inp(proof_available=False, laundry_fee=1), bad).flags
    )
    assert C.RULE_UNVERIFIED not in calculate_damage(inp(), bad).flags


def test_top_level_verified_not_used(rule: LaundryRule) -> None:
    assert rule.verified is False
    assert C.RULE_UNVERIFIED not in calculate_damage(inp(), rule).flags


def test_hanbok_has_no_review_flag(rule: LaundryRule) -> None:
    """한복류는 원문 칸 구조로 확인한 값이라 🔍를 붙이지 않는다 (Q-L8)."""
    r = calculate_damage(inp(item_key="hanbok"), rule)
    assert r.life_years == 4
    assert all(f not in r.flags for f in (C.RULE_UNVERIFIED,))


def test_steps_never_empty_when_computed(rule: LaundryRule) -> None:
    r = calculate_damage(inp(), rule)
    assert [s.label for s in r.steps][:4] == [
        "사용일수",
        "내용연수",
        "배상비율",
        "배상액",
    ]
    assert r.steps[3].amount == r.amount
