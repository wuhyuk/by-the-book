"""가전 P2 기능 플래그·API·문안·규칙 데이터 (2026-11-15 승인, MVP_SPEC 13절).

- 플래그(ENABLED_FEATURES에 appliance)가 꺼져 있으면 지금과 같다: item=appliance는 422 literal_error,
  /api/appliance/items는 404 (2026-11-15 변경 전 응답을 그대로 고정).
- 켜져 있으면 /api/calculate·/api/guide에 가전. 기대값은 docs/sources/appliance_cases.md 4.2.
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_appliance_cases import CASES, inp, rule_for
from test_guide import FORBIDDEN_TERMS, STATIC, ints, numbers, texts

from api.settings import AppSettings, get_app_settings, load_app_settings
from guide.appliance import build_appliance_guide
from guide.common import DISCLAIMER_LINE
from main import app
from rules.appliance import calculate_appliance
from rules.appliance_rule import load_appliance_rule

client = TestClient(app)
RULE = load_appliance_rule()
OFF_422 = {
    "message": "입력 형식이 맞지 않습니다. 표시된 항목을 확인해 주세요.",
    "detail": [{"loc": ["query", "item"], "type": "literal_error"}],
}
OFF_404 = {"message": "요청한 API 경로가 없습니다."}


@pytest.fixture
def features() -> Iterator[Any]:
    def _set(*names: str) -> None:
        app.dependency_overrides[get_app_settings] = lambda: AppSettings(
            enabled_features=names
        )

    yield _set
    app.dependency_overrides.pop(get_app_settings, None)


# ---- 설정 ----


@pytest.mark.parametrize(
    ("value", "expected"),
    [("appliance", ("appliance",)), ("set_partial,appliance", ("set_partial", "appliance")),
     (" appliance , set_partial ", ("set_partial", "appliance")), ("APPLIANCE", ())],
)  # fmt: skip
def test_settings_parse_appliance(value: str, expected: tuple[str, ...]) -> None:
    s = load_app_settings({"ENABLED_FEATURES": value}, env_file=None)
    assert s.enabled_features == expected


def test_config_lists_both(features: Any) -> None:
    features("set_partial", "appliance")
    assert client.get("/api/config").json()["enabled_features"] == [
        "set_partial",
        "appliance",
    ]


# ---- 꺼짐: 지금과 같은 응답 ----


@pytest.mark.parametrize(
    "path", ["/api/calculate?item=appliance", "/api/guide?item=appliance"]
)
def test_off_item_appliance_is_422(features: Any, path: str) -> None:
    features("set_partial")
    body = CASES["A-1"]["input"]
    res = client.post(path, json=body)
    assert (res.status_code, res.json()) == (422, OFF_422)


def test_off_items_is_404(features: Any) -> None:
    features()
    res = client.get("/api/appliance/items")
    assert (res.status_code, res.json()) == (404, OFF_404)


# ---- 켜짐 ----


def test_on_items(features: Any) -> None:
    features("appliance")
    res = client.get("/api/appliance/items")
    assert [i["key"] for i in res.json()] == [
        "tv",
        "fridge",
        "washer",
        "vacuum",
        "laptop",
    ]


def test_on_calculate_a1(features: Any) -> None:
    features("appliance")
    res = client.post("/api/calculate?item=appliance", json=CASES["A-1"]["input"])
    body = res.json()
    assert body["result"]["amount"] == 920_000
    assert body["result"]["badge"] == "✅ 기준 확인"
    cards = {c["id"]: c["text"] for c in body["display"]["citations"]}
    assert "적용한 칸: TV → 'TV, 냉장고' 행" in cards["annex3_items"]
    assert (
        "내용연수 108개월" in cards["annex4"] and "사용 개월 36개월" in cards["annex4"]
    )
    assert [n["code"] for n in body["display"]["notices"]] == [
        "RECEIVED_DATE_BASIS",
        "USED_MONTHS_BASIS",
    ]


def test_on_guide_undeterminable_has_no_company_message(features: Any) -> None:
    features("appliance")
    res = client.post("/api/guide?item=appliance", json=CASES["A-9"]["input"])
    assert res.json()["company_message"] is None


def test_on_rejects_extra_field(features: Any) -> None:
    features("appliance")
    body = {**CASES["A-1"]["input"], "set_part": "top"}
    assert client.post("/api/calculate?item=appliance", json=body).status_code == 422


# ---- 문안: 승인 케이스 전체 ----


@pytest.mark.parametrize("cid", list(CASES))
def test_guide_terms_numbers(cid: str) -> None:
    case = CASES[cid]
    rule = rule_for(case)
    i = inp(case["input"])
    result = calculate_appliance(i, rule)
    g = build_appliance_guide(i, result, rule)
    for text in texts(g):
        for term in (*FORBIDDEN_TERMS, "받을 수 있"):
            assert term not in text, term
    assert g.explanation.count(DISCLAIMER_LINE) == 1
    if g.company_message is not None:
        assert g.company_message.splitlines().count(DISCLAIMER_LINE) == 1
        assert "RULE_UNVERIFIED" not in [f.value for f in result.flags]
    allowed = set(ints(result.model_dump())) | STATIC
    allowed |= numbers(rule.source.name) | numbers(rule.source.notice_number)
    for card in g.citations:
        allowed |= numbers(card.label)
    allowed |= {10}  # 고시 해결기준 "구입가의 10%" (규칙 JSON add_on_percent)
    if i.provider_offer is not None:
        allowed.add(i.provider_offer)
    found = set().union(*(numbers(t) for t in texts(g)))
    assert found <= allowed, found - allowed


# ---- 규칙 데이터 ----


def test_rule_blocks_verified_and_user_checked() -> None:
    for block in (
        RULE.items,
        RULE.resolution_table,
        RULE.lifespan_rule,
        RULE.depreciation,
    ):
        assert block.verified is True
        assert block.verification.user_checked is True
        assert block.verification.checked_at == "2026-11-15"
    assert RULE.verified is False  # 3)·4) 가산 대상 등 미결 블록이 남아 있다
    assert RULE.source.retrieved_at == "2026-11-02"  # 조문 카드 확인일, 바꾸지 않음


def test_rule_table_values_match_verify_sheet() -> None:
    """대조표 S9~S12 (별표 Ⅲ): 품질보증 12개월, 부품보유 TV·냉장고 9, 세탁기·전기청소기 7, 노트북 4년."""
    got = {}
    for s in RULE.params.p2.supported_items:
        row = RULE.items.row(s.row)
        assert row is not None
        got[s.key] = (row.warranty_months, row.parts_years)
    assert got == {
        "tv": (12, 9),
        "fridge": (12, 9),
        "washer": (12, 7),
        "vacuum": (12, 7),
        "laptop": (12, 4),
    }
    assert RULE.depreciation.add_on.add_on_percent == 10  # S3
    assert RULE.lifespan_rule.years_to_months == 12  # D-1


def test_rule_json_raw_decisions() -> None:
    with open("data/rules/appliance_warranty.json", encoding="utf-8") as f:
        raw = json.load(f)
    dep = raw["depreciation"]
    assert dep["used_months"]["partial_month"] == "ceil"
    assert dep["rounding"]["amount"] == "floor_won"
    assert (
        dep["add_on"]["no_parts_after_warranty"]["cap_decision"]["selected"]
        == "purchase_price"
    )
    assert raw["repair_impossible_rule"]["verified"] is False
