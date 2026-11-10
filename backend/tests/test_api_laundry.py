"""세탁 API 분기 (MVP_SPEC 12.9): /api/calculate?item=laundry, /api/laundry/items, /api/analyze?item=laundry.

키 없이 가짜 LLM으로 돈다. 헬스장 기본 경로는 기존 테스트(test_api_calculate, test_api_analyze)가 지킨다.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.analyze import get_client_provider
from llm.client import LLMClient, Turn
from llm.laundry_extraction import FIELD_NAMES
from main import app
from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_display import build_laundry_display
from rules.laundry_rule import load_laundry_rule

client = TestClient(app)

BODY: dict[str, Any] = {
    "judgment_requested": False,
    "service_type": "laundry_shop",
    "damage_type": "defect",
    "item_key": "coat",
    "purchase_price": 100000,
    "purchase_date": "2026-01-01",
    "request_date": "2026-03-01",
    "proof_available": True,
}


def test_laundry_calculate_matches_engine() -> None:
    res = client.post("/api/calculate?item=laundry", json=BODY)
    assert res.status_code == 200
    rule = load_laundry_rule()
    result = calculate_damage(LaundryInput.model_validate_json(json.dumps(BODY)), rule)
    expected = {
        "result": result.model_dump(mode="json"),
        "display": build_laundry_display(result, rule).model_dump(mode="json"),
    }
    assert res.json() == expected


def test_gym_body_rejected_on_laundry_route() -> None:
    res = client.post("/api/calculate?item=laundry", json={"industry": "fitness"})
    assert res.status_code == 422
    assert "input" not in json.dumps(res.json())


def test_laundry_body_rejected_on_default_route() -> None:
    assert client.post("/api/calculate", json=BODY).status_code == 422


def test_unknown_item_is_422() -> None:
    assert client.post("/api/calculate?item=appliance", json=BODY).status_code == 422


def test_422_hides_input_values() -> None:
    marker = 987654321
    res = client.post(
        "/api/calculate?item=laundry", json={**BODY, "purchase_price": str(marker)}
    )
    assert res.status_code == 422
    assert str(marker) not in res.text


def test_items_endpoint() -> None:
    res = client.get("/api/laundry/items")
    assert res.status_code == 200
    data = res.json()
    assert data[0]["key"] == "mens_suit"
    assert "years" not in res.text


# ---- /api/analyze?item=laundry ----


@dataclass
class FakeClient:
    output: str
    model: str = "fake-model"
    received: list[str] = field(default_factory=list)

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.received.append(turns[-1].text)
        assert "item_key" in response_schema["properties"]["fields"]["properties"]
        return self.output


def raw(fields: dict[str, Any], evidence: dict[str, str]) -> dict[str, Any]:
    return {
        "judgment_requested": False,
        "judgment_evidence": None,
        "fields": {n: fields.get(n) for n in FIELD_NAMES},
        "evidence": {n: evidence.get(n) for n in FIELD_NAMES},
    }


@pytest.fixture
def use() -> Iterator[Callable[[Callable[[], LLMClient]], None]]:
    def _use(provider: Callable[[], LLMClient]) -> None:
        app.dependency_overrides[get_client_provider] = lambda: provider

    yield _use
    app.dependency_overrides.clear()


def test_analyze_laundry_grounds_values(use: Any) -> None:
    text = "2026년 1월 5일에 30만원에 산 코트를 세탁소에 맡겼는데 잃어버렸대요. 연락처 010-1234-5678"
    fake = FakeClient(
        json.dumps(
            raw(
                {
                    "service_type": "laundry_shop",
                    "damage_type": "loss",
                    "item_key": "coat",
                    "purchase_price": 300000,
                    "purchase_date": "2026-01-05",
                    "laundry_fee": 999,  # 근거 없음 → 버림
                },
                {
                    "service_type": "세탁소에 맡겼는데",
                    "damage_type": "잃어버렸대요",
                    "item_key": "코트",
                    "purchase_price": "30만원에 산",
                    "purchase_date": "2026년 1월 5일에",
                    "laundry_fee": "세탁비 999원",
                },
            )
        )
    )
    use(lambda: fake)
    res = client.post("/api/analyze?item=laundry", json={"text": text})
    assert res.status_code == 200
    ext = res.json()["extraction"]
    assert ext["fields"]["purchase_price"] == 300000
    assert ext["fields"]["item_key"] == "coat"
    assert "laundry_fee" in ext["unverified"]
    assert "item_key" in ext["confirm"]  # 표 행 선택은 폼에서 확인
    assert "proof_available" in ext["missing"]
    assert "010-1234-5678" not in fake.received[0]


def test_analyze_laundry_rule_guardrail(use: Any) -> None:
    fake = FakeClient("{}")
    use(lambda: fake)
    res = client.post(
        "/api/analyze?item=laundry",
        json={"text": "세탁소 상대로 소송하면 이길 수 있나요?"},
    )
    assert res.json()["status"] == "guardrail"
    assert fake.received == []
