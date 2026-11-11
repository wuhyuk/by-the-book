"""POST /api/guide 테스트 (2026-11-11). 문안은 guide/ 결과와 같아야 하고, 로그 원칙을 지킨다.

로그 원칙: 요청 본문을 로그에 남기지 않음, 422에서 입력 제거, 500은 고정 문구.
"""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_gym_calc import CASES
from test_laundry_cases import BASE as LAUNDRY_BASE
from test_laundry_cases import CASES as LAUNDRY_CASES

import api.guide as guide_module
from api.errors import SERVER_ERROR_MESSAGE
from guide.gym import build_gym_guide
from guide.laundry import build_laundry_guide
from main import app
from rules.gym import calculate_refund
from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_rule import load_laundry_rule
from rules.loader import load_rule

client = TestClient(app)
RULE = load_rule("gym_refund")
LRULE = load_laundry_rule()
MARK_INT = 987654321
MARK_STR = "표지값_ZQX_안내"


@pytest.fixture
def all_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    caplog.set_level(logging.DEBUG)
    yield caplog


def p1() -> dict[str, Any]:
    return next(c for c in CASES if c.id == "P1").inp.model_dump(mode="json")


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.id)
def test_gym_matches_guide_module(c: Any) -> None:
    response = client.post("/api/guide", json=c.inp.model_dump(mode="json"))
    assert response.status_code == 200
    expected = build_gym_guide(c.inp, calculate_refund(c.inp, RULE), RULE)
    assert response.json() == expected.model_dump(mode="json")


@pytest.mark.parametrize("c", LAUNDRY_CASES, ids=lambda c: c.id)
def test_laundry_matches_guide_module(c: Any) -> None:
    inp = LaundryInput(**{**LAUNDRY_BASE, **c.inp})
    response = client.post("/api/guide?item=laundry", json=inp.model_dump(mode="json"))
    assert response.status_code == 200
    expected = build_laundry_guide(inp, calculate_damage(inp, LRULE), LRULE)
    assert response.json() == expected.model_dump(mode="json")


def test_same_body_same_text() -> None:
    first = client.post("/api/guide", json=p1()).json()
    second = client.post("/api/guide", json=p1()).json()
    assert first == second


def test_client_numbers_are_rejected() -> None:
    """계산 결과 숫자를 본문에 넣어 보내면 받지 않는다 (입력 모델 외 필드 금지, 422)."""
    response = client.post("/api/guide", json={**p1(), "refund": MARK_INT})
    assert response.status_code == 422
    assert str(MARK_INT) not in response.text


def test_422_does_not_echo_input(all_logs: Any) -> None:
    response = client.post(
        "/api/guide", json={**p1(), "paid_amount": MARK_STR, "industry": MARK_INT}
    )
    assert response.status_code == 422
    assert all(set(e) == {"loc", "type"} for e in response.json()["detail"])
    assert MARK_STR not in response.text and str(MARK_INT) not in response.text
    assert MARK_STR not in all_logs.text and str(MARK_INT) not in all_logs.text


def test_500_fixed_message(monkeypatch: pytest.MonkeyPatch, all_logs: Any) -> None:
    def boom(*_: Any) -> None:
        raise RuntimeError(f"내부 오류 {MARK_STR}")

    monkeypatch.setattr(guide_module, "build_gym_guide", boom)
    safe = TestClient(app, raise_server_exceptions=False)
    response = safe.post("/api/guide", json=p1())
    assert response.status_code == 500
    assert response.json() == {"message": SERVER_ERROR_MESSAGE}
    assert MARK_STR not in response.text and MARK_STR not in all_logs.text


def test_success_does_not_log_input(all_logs: Any) -> None:
    response = client.post("/api/guide", json={**p1(), "provider_offer": MARK_INT})
    assert response.status_code == 200
    assert str(MARK_INT) not in all_logs.text
    assert f"{MARK_INT:,}" not in all_logs.text


def test_router_has_no_logging() -> None:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(guide_module))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "print" not in names and "logging" not in names
    assert not attrs & {"debug", "info", "warning", "error", "exception", "log"}
