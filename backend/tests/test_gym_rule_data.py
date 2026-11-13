"""규칙 데이터(gym_refund.json) 로드·검증 테스트 (MVP_SPEC 4절, 5.7, 5.8, 5.9)."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from rules.loader import GymRule, load_rule

RULE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "rules" / "gym_refund.json"
)

# MVP_SPEC 5.7 근거 조항 ID 매핑에 나오는 ID 전체
SPEC_CITATION_IDS = {
    "art3_1",
    "art3_2",
    "art2_2",
    "art2_3",
    "art2_4",
    "art4_1",
    "annex_penalty",
    "art5_1",
    "art5_2",
    "art6_1",
    "law32_1",
    "law2_10",
    "yoga_terms_art5_2",
    "gym_terms_art8_2_def",
    "yoga_terms_art9_1_def",
}


@pytest.fixture(scope="module")
def rule() -> GymRule:
    return load_rule("gym_refund")


def raw_rule() -> dict[str, Any]:
    """Decimal로 읽은 원본 dict (변형 테스트용)."""
    return json.loads(RULE_PATH.read_text(encoding="utf-8"), parse_float=Decimal)


def test_loads_required_top_level_fields(rule: GymRule) -> None:
    assert rule.id == "gym_refund"
    assert rule.title
    assert [i.id for i in rule.industries] == ["fitness", "yoga_pilates"]
    assert len(rule.clauses) == 10
    assert len(rule.related_clauses) == 5


def test_source_fields(rule: GymRule) -> None:
    src = rule.source
    assert (
        src.name
        == "계속거래 등의 해지·해제에 따른 위약금 및 대금의 환급에 관한 산정기준"
    )
    assert src.notice_number == "공정거래위원회고시 제2019-9호"
    assert src.url.startswith("https://www.law.go.kr/")
    assert src.effective_date == "2019-11-19"
    assert src.last_amended == "2019-11-19"
    # 사용자 별표 확인일(2026-11-13)은 penalty_rule.verification.checked_at에만 둔다.
    # retrieved_at은 조문 카드 확인일로도 쓰여 이전 값을 유지한다.
    assert src.retrieved_at == "2026-10-26"
    for clause in rule.related_clauses:
        assert clause.source.name
        assert clause.source.url.startswith("https://")
        assert clause.source.retrieved_at == "2026-10-26"


def test_verified_flags(rule: GymRule) -> None:
    """최상위 verified는 false, 결과가 쓰는 블록은 true (MVP_SPEC 4절).

    penalty_rule은 2026-11-13 사용자가 별표 원문과 직접 대조했다 (user_check_sheet.md 5번).
    """
    assert rule.verified is False
    for industry in rule.industries:
        assert industry.penalty_rule.verified is True
        assert industry.penalty_rule.verification.user_checked is True
        assert industry.penalty_rule.verification.checked_at == "2026-11-13"
    assert rule.params.continuous_transaction_criteria.verified is True


def test_ratio_is_decimal_0_10(rule: GymRule) -> None:
    """0.10이 float가 아니라 Decimal("0.10")으로 보존된다."""
    for industry in rule.industries:
        ratio = industry.penalty_rule.ratio
        assert isinstance(ratio, Decimal)
        assert ratio == Decimal("0.10")
        assert str(ratio) == "0.10"


def test_in_source_false_marks(rule: GymRule) -> None:
    """원문에 없는 프로젝트 결정은 in_source: false로 표시되어 있다."""
    p = rule.params
    assert p.rounding.in_source is False
    assert p.day_count.in_source is False
    assert p.refund_basis.in_source is False
    assert p.continuous_transaction_criteria.period_thresholds_days.in_source is False
    assert rule.scenarios.A.in_source is False
    assert rule.scenarios.B.in_source is False


def test_period_thresholds(rule: GymRule) -> None:
    t = rule.params.continuous_transaction_criteria.period_thresholds_days
    assert (t.out_of_scope_below, t.needs_review_max) == (28, 32)


def test_unit_price_method_is_null(rule: GymRule) -> None:
    """단위대금 산정 방식은 미확정(null)이다."""
    assert rule.params.unit_price_method is None
    assert rule.params.list_price_deduction_allowed is None


def test_clause_ids_match_spec_mapping(rule: GymRule) -> None:
    """조항 ID(clauses + related_clauses)가 5.7 매핑과 정확히 같다."""
    ids = [c.id for c in rule.clauses] + [c.id for c in rule.related_clauses]
    assert len(ids) == len(set(ids))
    assert set(ids) == SPEC_CITATION_IDS
    assert rule.clause_ids == SPEC_CITATION_IDS


def test_law2_10_matches_criteria_text(rule: GymRule) -> None:
    """인용용 law2_10과 판정용 계속거래 정의는 같은 문장이다 (5.7)."""
    law = next(c for c in rule.related_clauses if c.id == "law2_10")
    assert law.text == rule.params.continuous_transaction_criteria.text


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("params", "rounding", "used_amount"), "half_even_won"),
        (("params", "rounding", "penalty"), "half_up_won"),
        (("params", "rounding", "order"), "divide_then_multiply"),
        (("params", "day_count", "contract_days"), "end_date - start_date"),
        (("params", "day_count", "elapsed_days"), "notice_date - start_date"),
        (("params", "unit_price_method"), "list_price"),
        (("scenarios", "A", "used_amount_base"), "list_price"),
    ],
)
def test_unexpected_rule_strings_fail_at_load(
    path: tuple[str, ...], bad_value: str
) -> None:
    """반올림·일수 등 문자열 규칙 값이 예상 밖이면 로드 시점에 오류가 난다 (Q9)."""
    data = raw_rule()
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad_value
    with pytest.raises(ValidationError):
        GymRule.model_validate(data)


def test_penalty_rule_type_literal() -> None:
    data = raw_rule()
    data["industries"][0]["penalty_rule"]["applies_as"] = "fixed"
    with pytest.raises(ValidationError):
        GymRule.model_validate(data)


def test_float_ratio_rejected() -> None:
    """parse_float=Decimal 없이 읽은 float 비율은 거부한다."""
    data = json.loads(RULE_PATH.read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        GymRule.model_validate(data)


def test_unknown_key_rejected() -> None:
    data = raw_rule()
    data["params"]["new_rule"] = 1
    with pytest.raises(ValidationError):
        GymRule.model_validate(data)


def test_verified_must_be_bool() -> None:
    data = raw_rule()
    data["industries"][0]["penalty_rule"]["verified"] = "true"
    with pytest.raises(ValidationError):
        GymRule.model_validate(data)


@pytest.mark.parametrize("rule_id", ["../gym_refund", "gym-refund", "GYM", ""])
def test_rule_id_pattern(rule_id: str) -> None:
    with pytest.raises(ValueError):
        load_rule(rule_id)


def test_missing_rule_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_rule("no_such_rule")
