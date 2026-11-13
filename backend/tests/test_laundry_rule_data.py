"""세탁 규칙 JSON ↔ 고시 원문 값 (MVP_SPEC 12절, docs/sources/laundry_notice.md).

기대값은 고시 원문(소비자분쟁해결기준 [별표 Ⅱ] ⑯세탁업 배상비율표·품목별 평균 내용년수·5-1.③)에서만 가져온다.
"""

import pytest

from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_rule import LaundryRule, load_laundry_rule

# 원문 배상비율표: 내용연수별 칸의 사용일수 하한 (마지막 칸은 상한 없음)과 상한
RATIOS = (95, 80, 70, 60, 50, 45, 40, 35, 30, 20, 10)
SOURCE_UPPER: dict[int, tuple[int, ...]] = {
    1: (14, 44, 89, 134, 179, 224, 269, 314, 365, 547),
    2: (28, 88, 178, 268, 358, 448, 538, 628, 730, 1095),
    3: (43, 133, 268, 403, 538, 673, 808, 943, 1095, 1642),
    4: (57, 177, 357, 537, 717, 897, 1077, 1257, 1460, 2190),
    5: (72, 222, 447, 672, 897, 1122, 1347, 1572, 1825, 2737),
    6: (86, 266, 536, 806, 1076, 1346, 1616, 1886, 2190, 3285),
}

# 원문 평균 내용연수 (표 1·표 2, 행 순서대로). 값이 여럿이면 소재·용도 순서대로.
SOURCE_YEARS: dict[str, tuple[int, ...]] = {
    "mens_suit": (3, 4, 4),
    "coat": (4,),
    "womens_suit": (3, 4, 4),
    "skirt_pants_jacket_jumper": (3, 4, 4),
    "sportswear": (3,),
    "shirts": (2,),
    "blouse": (3, 2),
    "sweater": (3,),
    "jeans": (4, 3),
    "uniform": (2, 2, 3),
    "hanbok": (4,),
    "carpet": (6, 5),
    "leather_bag": (3,),
    "fabric_bag": (2,),
    "scarf": (3, 2),
    "muffler": (3,),
    "necktie": (2,),
    "underwear": (2,),
    "leather_outer": (3, 5),
    "leather_other": (3,),
    "synthetic_leather": (3,),
    "blanket": (5, 4),
    "sofa": (5, 3),
    "curtain": (2, 3),
    "bedding": (3,),
    "shoes_leather_special": (3,),
    "shoes_general": (1,),
    "hat": (1,),
    "fur_outer": (3, 5),
    "fur_other": (3,),
}


@pytest.fixture(scope="module")
def rule() -> LaundryRule:
    return load_laundry_rule()


@pytest.mark.parametrize("life", range(1, 7))
def test_ratio_table_matches_source(rule: LaundryRule, life: int) -> None:
    row = next(r for r in rule.ratio_table.rows if r.life_years == life)
    assert [b.ratio_percent for b in row.bands] == list(RATIOS)
    assert [b.max_days for b in row.bands] == [*SOURCE_UPPER[life], None]
    assert [b.min_days for b in row.bands] == [0] + [u + 1 for u in SOURCE_UPPER[life]]


def test_lifespan_table_matches_source(rule: LaundryRule) -> None:
    got = {
        r.id: (r.years,)
        if r.years is not None
        else tuple(v.years for v in r.variants or [])
        for r in rule.lifespan_table.rows
    }
    assert got == SOURCE_YEARS
    assert [r.id for r in rule.lifespan_table.rows] == list(SOURCE_YEARS)


def test_hanbok_single_value_in_source(rule: LaundryRule) -> None:
    """한복류는 행 전체에 걸친 한 칸, 값 4 (2026-11-06 칸 구조 확인, Q-L8)."""
    row = rule.lifespan_table.row("hanbok")
    assert row is not None
    assert row.years == 4 and row.variants is None
    assert row.years_applies_to_all_materials_in_source is True
    assert row.years_alternative is None
    # 칸 구조(값 하나, 가로선 없음)는 2026-11-13 사용자 표본 대조로도 확인 (시트 2번)
    assert row.years_scope_check is not None
    assert row.years_scope_check.user_checked is True
    assert row.years_scope_check.checked_at == "2026-11-13"


def test_unproven_fallback_is_20(rule: LaundryRule) -> None:
    assert rule.unproven_fallback.laundry_fee_multiplier == 20


def test_block_verification_status(rule: LaundryRule) -> None:
    """블록은 기계 대조로 verified: true (Q-S2). 최상위는 false.

    2026-11-13 사용자 표본 대조(user_check_sheet.md 1~4번)로 ratio_table·lifespan_table·
    unproven_fallback은 user_checked: true. set_allocation은 표본에 없어 false 그대로다.
    """
    assert rule.verified is False
    for block in (
        rule.ratio_table,
        rule.lifespan_table,
        rule.set_allocation,
        rule.unproven_fallback,
    ):
        assert block.verified is True
    for block in (rule.ratio_table, rule.lifespan_table, rule.unproven_fallback):
        assert block.verification.user_checked is True
        assert block.verification.checked_at == "2026-11-13"
    assert rule.set_allocation.verification.user_checked is False


def test_decisions_marked_not_in_source(rule: LaundryRule) -> None:
    assert rule.params.use_days.in_source is False
    assert rule.params.rounding.in_source is False
    assert rule.params.decision_sensitivity.in_source is False


def test_source_has_retrieved_at(rule: LaundryRule) -> None:
    # 사용자 표 확인일(2026-11-13)은 블록 verification.checked_at에만 둔다.
    # retrieved_at은 조문 카드 확인일로도 쓰여 이전 값을 유지한다.
    assert rule.source.retrieved_at == "2026-11-02"
    assert rule.source.notice_number == "공정거래위원회고시 제2025-14호"
    for c in rule.related_clauses:
        assert c.source.retrieved_at


def test_engine_citation_ids_exist(rule: LaundryRule) -> None:
    """엔진이 인용할 수 있는 ID가 모두 규칙 JSON에 있다 (12.7)."""
    used = {
        "laundry_types",
        "laundry_1",
        "laundry_2",
        "laundry_3",
        "laundry_5",
        "laundry_5_1",
        "laundry_6",
        "laundry_7",
        "laundry_8",
        "laundry_ratio_table",
        "laundry_lifespan_table",
        "cpa16_3",
        "cpa_dec9_2",
    }
    assert used <= rule.clause_ids


TERMS_IDS = ["laundry_terms_art9", "laundry_terms_art10_3"]


def _terms_input(**kw: object) -> LaundryInput:
    base: dict[str, object] = {
        "judgment_requested": False,
        "service_type": "laundry_shop",
        "damage_type": "loss",
        "proof_available": False,
        "laundry_fee": 1000,
    }
    base.update(kw)
    return LaundryInput.model_validate(base)


def test_terms_clauses_two_paths(rule: LaundryRule) -> None:
    """세탁 표준약관 두 조항은 두 경로로 확인했다 (2026-11-11, Q-L7)."""
    by_id = {c.id: c for c in rule.related_clauses}
    for cid in TERMS_IDS:
        assert by_id[cid].source.verified_paths == 2
        assert by_id[cid].source.usage is None


def test_terms_clauses_cited_when_computed(rule: LaundryRule) -> None:
    """계산한 결과의 표준약관 안내에 맞춰 조항을 인용한다 (12.7)."""
    result = calculate_damage(_terms_input(), rule)
    assert result.calculated
    assert result.citations[-2:] == TERMS_IDS


def test_terms_clauses_not_cited_when_stopped(rule: LaundryRule) -> None:
    result = calculate_damage(_terms_input(damage_type="other"), rule)
    assert not result.calculated
    assert not set(TERMS_IDS) & set(result.citations)


def test_terms_clauses_not_cited_with_one_path(rule: LaundryRule) -> None:
    """한 경로만 확인한 조항은 인용하지 않는다 (verified_paths < 2)."""
    clauses = [
        c.model_copy(
            update={"source": c.source.model_copy(update={"verified_paths": 1})}
        )
        if c.id in TERMS_IDS
        else c
        for c in rule.related_clauses
    ]
    one_path = rule.model_copy(update={"related_clauses": clauses})
    result = calculate_damage(_terms_input(), one_path)
    assert result.calculated
    assert not set(TERMS_IDS) & set(result.citations)
