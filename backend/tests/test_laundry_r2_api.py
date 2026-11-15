"""세탁 R2(Set 일부 손상) 기능 플래그·API·문안·추출 경계 (2026-11-15).

- 플래그(ENABLED_FEATURES=set_partial)가 꺼져 있으면 축소 A 그대로: 승인 L4는 ❔ SET_PARTIAL_UNSUPPORTED.
- 켜져 있으면 L4 재승인 값(🔍 136,500~210,000, 원인 Set 배분, 인용 10개)과 R2 승인 케이스.
- 기대값은 docs/sources/vs4_restore_r2_cases.md(2판, 승인 2026-11-15)와 사용자 재승인 L4에서 옮겼다.
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_guide import FORBIDDEN_TERMS, STATIC, ints, numbers, texts
from test_laundry_r2_cases import CASES

from api.settings import AppSettings, get_app_settings
from guide.common import DISCLAIMER_LINE
from guide.laundry import build_laundry_guide
from llm.laundry_extraction import FIELD_NAMES
from main import app
from rules.badge import Badge
from rules.laundry import SET_PARTIAL, LaundryInput, calculate_damage
from rules.laundry_rule import load_laundry_rule

client = TestClient(app)
RULE = load_laundry_rule()
ON = frozenset({SET_PARTIAL})
R2_FIELDS = ("hanbok_kind", "damaged_parts", "set_partial_request")

L4_COMMON: dict[str, Any] = {
    "judgment_requested": False,
    "service_type": "laundry_shop",
    "damage_type": "defect",
    "item_key": "womens_suit",
    "variant_key": "spring_fall",
    "purchase_price": 300_000,
    "purchase_date": "2026-02-22",
    "request_date": "2026-09-10",
    "proof_available": True,
    "set_type": "top_bottom",
}
L4_OFF = {**L4_COMMON, "set_part": "top"}  # 승인 L4 (2026-11-10) 입력
L4_ON = {**L4_COMMON, "damaged_parts": ["top"], "set_partial_request": False}
L4_ON_CITATIONS = [
    "laundry_types",
    "laundry_1",
    "laundry_5_1",
    "cpa16_3",
    "laundry_ratio_table",
    "laundry_lifespan_table",
    "laundry_6",
    "laundry_7",
    "laundry_terms_art9",
    "laundry_terms_art10_3",
]


def inp(data: dict[str, Any]) -> LaundryInput:
    return LaundryInput.model_validate_json(json.dumps(data))


@pytest.fixture
def features() -> Iterator[Any]:
    def _set(*names: str) -> None:
        app.dependency_overrides[get_app_settings] = lambda: AppSettings(
            enabled_features=names
        )

    yield _set
    app.dependency_overrides.pop(get_app_settings, None)


# ---- L4: 꺼짐이면 승인 L4 그대로, 켜짐이면 재승인 값 ----


def test_l4_off_unchanged() -> None:
    r = calculate_damage(inp(L4_OFF), RULE)
    assert r.badge == Badge.UNDETERMINABLE
    assert [f.value for f in r.flags] == ["SET_PARTIAL_UNSUPPORTED"]
    assert r.citations == ["laundry_7"]
    assert (r.set_type, r.damaged_parts, r.set_share_percent) == (None, None, None)


def test_l4_reapproved_on() -> None:
    r = calculate_damage(inp(L4_ON), RULE, ON)
    assert r.badge == Badge.NEEDS_REVIEW
    assert [f.value for f in r.flags] == ["DECISION_SENSITIVE"]
    assert (r.amount, r.sensitivity_min, r.sensitivity_max) == (
        136_500,
        136_500,
        210_000,
    )
    assert r.sensitivity_causes == ["set_partial_damage"]
    assert r.citations == L4_ON_CITATIONS
    # 보고서 4.3 R2-1 배분 줄의 참고 값: 300,000 × 65 ÷ 100 = 195,000
    assert (r.set_type, r.damaged_parts, r.set_share_percent, r.set_base_raw) == (
        "top_bottom",
        ["top"],
        65,
        "195000",
    )


def test_set_base_raw_keeps_fraction() -> None:
    """보고서 4.3 R2-36 배분 줄: 300,001 × 65 ÷ 100 = 195,000.65 (원 미만 처리 전)."""
    r = calculate_damage(inp(CASES["R2-36"]["input"]), RULE, ON)
    assert r.set_base_raw == "195000.65"


def test_old_set_part_with_flag_on() -> None:
    """켜짐: 손상 벌은 damaged_parts로 받는다. set_part만 오면 누락, 둘 다 오면 입력 오류."""
    r = calculate_damage(inp(L4_OFF), RULE, ON)
    assert r.missing == ["damaged_parts"]
    r = calculate_damage(inp({**L4_ON, "set_part": "top"}), RULE, ON)
    assert [f.value for f in r.flags] == ["INVALID_INPUT"]


@pytest.mark.parametrize(
    "extra",
    [{"damaged_parts": ["top"]}, {"set_partial_request": False},
     {"hanbok_kind": "chima_jeogori"}],
)  # fmt: skip
def test_r2_fields_with_flag_off_are_invalid(extra: dict[str, Any]) -> None:
    """꺼져 있을 때 R2 입력이 오면 입력 오류 (R1 Q9와 같은 방식). set_part=whole이라 누락 아님."""
    data = {**L4_COMMON, "set_part": "whole", **extra}
    r = calculate_damage(inp(data), RULE)
    assert [f.value for f in r.flags] == ["INVALID_INPUT"]


def test_flag_on_without_set_matches_off() -> None:
    """Set이 아니면 켜짐·꺼짐 결과가 같다 (R2-30 = 승인 L1 입력)."""
    data = CASES["R2-30"]["input"]
    assert calculate_damage(inp(data), RULE, ON) == calculate_damage(inp(data), RULE)


def test_hanbok_kind_missing_when_hanbok_set() -> None:
    """한복 Set인데 조합(치마저고리·바지저고리)을 고르지 않으면 누락 [이번 구현에서 정한 처리]."""
    data = {**CASES["R2-11"]["input"]}
    data.pop("hanbok_kind")
    r = calculate_damage(inp(data), RULE, ON)
    assert r.missing == ["hanbok_kind"]


# ---- API: 플래그 켜짐/꺼짐 ----


def test_api_calculate_off_keeps_l4(features: Any) -> None:
    features()
    res = client.post("/api/calculate?item=laundry", json=L4_OFF)
    assert res.status_code == 200
    assert res.json()["result"]["flags"] == ["SET_PARTIAL_UNSUPPORTED"]


def test_api_calculate_on_l4(features: Any) -> None:
    features(SET_PARTIAL)
    res = client.post("/api/calculate?item=laundry", json=L4_ON)
    body = res.json()
    assert body["result"]["badge"] == Badge.NEEDS_REVIEW.value
    assert body["result"]["sensitivity_min"] == 136_500
    assert body["result"]["sensitivity_max"] == 210_000
    assert body["display"]["screen_line"]["text"] == (
        "세트 의류 일부 손상의 배분 방식(고시 7.의 비율 적용 여부)에 따라 기준 금액이 "
        "136,500원~210,000원으로 달라질 수 있습니다."
    )


def test_api_guide_on_r2_38(features: Any) -> None:
    features(SET_PARTIAL)
    res = client.post("/api/guide?item=laundry", json=CASES["R2-38"]["input"])
    g = res.json()
    assert "Set 300,000원 × 상의 65%" in "\n".join(g["explanation"])
    assert g["company_message"] is not None
    assert "136,500원" in g["company_message"]


def test_api_guide_new_undeterminable_has_no_company_message(features: Any) -> None:
    features(SET_PARTIAL)
    res = client.post("/api/guide?item=laundry", json=CASES["R2-24"]["input"])
    g = res.json()
    assert g["company_message"] is None
    assert [c["id"] for c in g["citations"]] == ["laundry_5_1", "laundry_7"]


def test_api_guide_off_rejects_r2_input(features: Any) -> None:
    features()
    res = client.post("/api/guide?item=laundry", json=CASES["R2-38"]["input"])
    assert res.json()["company_message"] is None  # 꺼짐: R2 입력은 INVALID_INPUT


def test_items_offer_set_types_by_row() -> None:
    items = {i["key"]: i for i in client.get("/api/laundry/items").json()}
    assert items["hanbok"]["set_types"] == ["none", "hanbok"]
    assert items["mens_suit"]["set_types"] == ["none", "top_bottom", "top_mid_bottom"]


# ---- 문안: 승인 R2 케이스 전체 ----


@pytest.mark.parametrize("cid", list(CASES))
def test_r2_guide_terms_and_numbers(cid: str) -> None:
    data = CASES[cid]["input"]
    i = inp(data)
    result = calculate_damage(i, RULE, ON)
    g = build_laundry_guide(i, result, RULE)
    for text in texts(g):
        for term in (*FORBIDDEN_TERMS, "받을 수 있"):
            assert term not in text, term
    assert g.explanation.count(DISCLAIMER_LINE) == 1
    # 숫자 출처: 결과 필드 + 규칙 라벨 + 고정 문구 + 업체 제시액 + (Set 배분 줄의) 입력 구입가격
    allowed = set(ints(result.model_dump())) | STATIC
    allowed |= numbers(RULE.source.name) | numbers(RULE.source.notice_number)
    for card in g.citations:
        allowed |= numbers(card.label)
    if i.provider_offer is not None:
        allowed.add(i.provider_offer)
    if result.set_share_percent is not None and i.purchase_price is not None:
        allowed.add(i.purchase_price)
    found = set().union(*(numbers(t) for t in texts(g)))
    assert found <= allowed, found - allowed


def test_r2_all_parts_guide_line() -> None:
    i = inp(CASES["R2-3"]["input"])
    g = build_laundry_guide(i, calculate_damage(i, RULE, ON), RULE)
    assert any("모든 벌(상의·하의)" in x for x in g.explanation)


# ---- 문장 분석(LLM) 대상이 아님 ----


def test_r2_fields_not_in_extraction() -> None:
    prompt_dir = "llm/prompts/"
    with open(prompt_dir + "laundry_extract_system.md", encoding="utf-8") as f:
        system = f.read()
    with open(prompt_dir + "laundry_extract_examples.json", encoding="utf-8") as f:
        examples = f.read()
    for name in R2_FIELDS:
        assert name not in FIELD_NAMES
        assert name not in system
        assert name not in examples
