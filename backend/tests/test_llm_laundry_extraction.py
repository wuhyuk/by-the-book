"""세탁 추출 스키마·근거 확인·few-shot (MVP_SPEC 12.9). LLM 호출 없음."""

import json
from typing import Any

import pytest

from llm.grounding import BOOL_CUE_RULES, LAUNDRY_BOOL_CUE_RULES, bool_grounded
from llm.laundry_extraction import (
    BOOL_FIELDS,
    EXAMPLES_FILE,
    FIELD_NAMES,
    ITEM_KEYS,
    SELECTION_FIELDS,
    VARIANT_KEYS,
    RawLaundryExtraction,
    check_extraction,
    few_shot_turns,
    questions,
    response_schema,
)
from rules.laundry import LaundryInput
from rules.laundry_rule import load_laundry_rule


def test_item_keys_match_rule_json() -> None:
    rule = load_laundry_rule()
    assert ITEM_KEYS == tuple(r.id for r in rule.lifespan_table.rows)
    variants = {v.key for r in rule.lifespan_table.rows for v in r.variants or []}
    assert set(VARIANT_KEYS) == variants


def test_fields_are_laundry_input_fields() -> None:
    """추출 필드는 모두 엔진 입력 필드다 (숫자 결과 필드는 없다)."""
    assert set(FIELD_NAMES) <= set(LaundryInput.model_fields)
    for name in ("use_days", "ratio_percent", "amount", "life_years"):
        assert name not in FIELD_NAMES


def test_every_bool_field_has_cue_rule() -> None:
    assert set(LAUNDRY_BOOL_CUE_RULES) == set(BOOL_FIELDS) - set(SELECTION_FIELDS)
    assert not set(LAUNDRY_BOOL_CUE_RULES) & set(BOOL_CUE_RULES)


def test_schema_requires_all_keys() -> None:
    s = response_schema()
    assert s["properties"]["fields"]["required"] == list(FIELD_NAMES)


def test_few_shot_examples_validate_and_ground() -> None:
    examples = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    assert len(few_shot_turns()) == 2 * len(examples)
    for ex in examples:
        raw = RawLaundryExtraction.model_validate(ex["output"])
        result = check_extraction(raw, ex["input"])
        assert result.unverified == []


@pytest.mark.parametrize(
    ("name", "value", "evidence", "ok"),
    [
        ("proof_available", True, "구입 영수증은 가지고 있어요", True),
        ("proof_available", True, "영수증은 없어요", False),
        ("proof_available", False, "영수증은 없어요", True),
        ("proof_available", False, "언제 샀는지 몰라요", True),
        ("manufacturing_cause_claimed", True, "원단 불량이라고 하네요", True),
        ("manufacturing_cause_claimed", False, "원단 불량은 아니래요", False),
        ("attachment_only", True, "털 칼라만 망가졌어요", True),
        ("attachment_only", True, "40만원짜리 코트 모자", False),
        ("no_issue_confirmation", True, "이상 없음 확인서에 서명했어요", True),
        ("no_issue_confirmation", False, "확인서는 안 썼어요", True),
        ("customer_partial_fault", True, "제 잘못도 있다고 하네요", True),
        ("customer_partial_fault", True, "세탁소 잘못이에요", False),
        ("special_agreement", False, "특약은 따로 없었어요", True),
        ("receipt_issued", False, "인수증을 못 받았어요", True),
        ("wants_damaged_item", True, "옷은 돌려받고 싶어요", True),
        # 2026-11-10 리뷰에서 찾은 낱말 오탐 (회귀 방지)
        ("customer_partial_fault", True, "세탁소 잘못으로 제 코트가 망가졌어요", False),
        ("customer_partial_fault", True, "고객 책임도 있다고 하네요", True),
        ("proof_available", False, "세탁소 잘못으로 줄었는데 영수증은 있어요", False),
        ("proof_available", True, "세탁소 잘못으로 줄었는데 영수증은 있어요", True),
        ("proof_available", False, "영수증을 못 찾겠어요", True),
        ("no_issue_confirmation", False, "세탁소 잘못이라 확인서", False),
        ("uncollected", True, "구입한 지 3개월 된 코트", False),
        ("uncollected", True, "2026년 3월 30일에 맡겼는데 보관", False),
        ("uncollected", True, "3개월 넘게 안 찾아갔다고 해요", True),
        ("manufacturing_cause_claimed", True, "세탁 불량 같아요", False),
        ("attachment_only", True, "탈부착 털 달린 패딩 전체가 줄었어요", False),
    ],
)
def test_bool_cues(name: str, value: bool, evidence: str, ok: bool) -> None:
    assert bool_grounded(name, value, evidence) is ok


def _raw(fields: dict[str, Any], evidence: dict[str, str]) -> RawLaundryExtraction:
    return RawLaundryExtraction.model_validate(
        {
            "judgment_requested": False,
            "judgment_evidence": None,
            "fields": {n: fields.get(n) for n in FIELD_NAMES},
            "evidence": {n: evidence.get(n) for n in FIELD_NAMES},
        }
    )


def test_amount_must_be_read_from_evidence() -> None:
    text = "40만원 주고 산 정장이에요"
    r = check_extraction(
        _raw({"purchase_price": 4_000_000}, {"purchase_price": "40만원 주고 산"}), text
    )
    assert "purchase_price" in r.unverified


def test_stop_values_and_selection_are_confirmed() -> None:
    text = "무인세탁소에서 빨았는데 봉제 인형이 찢어졌어요"
    r = check_extraction(
        _raw(
            {"service_type": "self_laundromat", "item_unlisted": True},
            {"service_type": "무인세탁소에서", "item_unlisted": "봉제 인형"},
        ),
        text,
    )
    assert r.confirm == ["item_unlisted", "service_type"]


def test_proof_false_is_confirmed() -> None:
    """입증 불가는 계산식(20배)을 바꾸므로 폼에서 확인받는다 (B13)."""
    text = "영수증은 없어요"
    r = check_extraction(
        _raw({"proof_available": False}, {"proof_available": "영수증은 없어요"}), text
    )
    assert r.confirm == ["proof_available"]


def test_questions_follow_proof_branch() -> None:
    assert questions({}) == [
        "service_type",
        "damage_type",
        "proof_available",
        "item_key",
        "purchase_price",
        "purchase_date",
        "request_date",
        "laundry_fee",
    ]
    assert questions({"proof_available": False}) == [
        "service_type",
        "damage_type",
        "laundry_fee",
    ]
    assert "item_key" not in questions({"proof_available": True, "item_unlisted": True})
    assert "set_part" in questions({"set_type": "top_bottom"})
