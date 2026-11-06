"""POST /api/calculate 테스트 (MVP_SPEC 6절, 8.1 VS2).

금액 기대값은 새로 만들지 않는다. API 결과가 엔진 calculate_refund 결과와 같은지만 본다.
케이스는 test_gym_calc.CASES(검증 완료·승인 35건)다.
로그·보안 기준: 입력값이 로그·422·500 응답에 다시 나오지 않는다 (CLAUDE.md 절대 규칙 6).
"""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_gym_calc import CASES, Case

import api.calculate as calculate_module
from api.errors import SERVER_ERROR_MESSAGE, VALIDATION_MESSAGE
from main import app
from rules.gym import calculate_refund
from rules.gym_display import build_display
from rules.loader import load_rule

RULE = load_rule("gym_refund")
client = TestClient(app)

# 다른 값과 겹치지 않는 표지값. 응답·로그에 나오면 입력이 새어 나간 것이다.
MARK_INT = 987654321
MARK_STR = "표지값_ZQX_업종"


def body(c: Case) -> dict[str, Any]:
    return c.inp.model_dump(mode="json")


def p1() -> dict[str, Any]:
    return body(next(c for c in CASES if c.id == "P1"))


@pytest.fixture
def all_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    caplog.set_level(logging.DEBUG)
    yield caplog


# ---- 정상 경로 ----


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.id)
def test_matches_engine(c: Case) -> None:
    response = client.post("/api/calculate", json=body(c))
    assert response.status_code == 200
    data = response.json()
    expected = calculate_refund(c.inp, RULE)
    assert data["result"] == expected.model_dump(mode="json")
    assert data["display"] == build_display(expected, RULE).model_dump(mode="json")


def test_judgment_requested_false_path() -> None:
    """폼 입력은 judgment_requested=false로 보낸다 (8.1 VS2 기본값)."""
    data = client.post("/api/calculate", json=p1()).json()
    assert data["result"]["badge"] != "❔ 판단 불가"
    assert "JUDGMENT_REQUESTED" not in data["result"]["flags"]


def test_dates_are_iso_strings() -> None:
    b = p1()
    assert isinstance(b["start_date"], str)
    assert client.post("/api/calculate", json=b).status_code == 200


def test_openapi_documents_request_body() -> None:
    spec = client.get("/openapi.json").json()
    schema = spec["paths"]["/api/calculate"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert "total_contract_amount" in schema["properties"]


# ---- 422: 위치와 종류만 ----


@pytest.mark.parametrize(
    ("change", "loc", "kind"),
    [
        ({"paid_amount": str(MARK_INT)}, ["body", "paid_amount"], "int_type"),
        ({"industry": MARK_INT}, ["body", "industry"], "string_type"),
        ({"start_date": MARK_STR}, ["body", "start_date"], "date_parsing"),
        ({"contract_type": MARK_STR}, ["body", "contract_type"], "literal_error"),
        ({"unknown_field": MARK_STR}, ["body", "unknown_field"], "extra_forbidden"),
    ],
)
def test_422_has_only_loc_and_type(
    change: dict[str, Any], loc: list[str], kind: str, all_logs: Any
) -> None:
    response = client.post("/api/calculate", json={**p1(), **change})
    assert response.status_code == 422
    data = response.json()
    assert data["message"] == VALIDATION_MESSAGE
    assert {"loc": loc, "type": kind} in data["detail"]
    for err in data["detail"]:
        assert set(err) == {"loc", "type"}
    assert str(MARK_INT) not in response.text
    assert MARK_STR not in response.text
    assert MARK_STR not in all_logs.text and str(MARK_INT) not in all_logs.text


def test_422_missing_required_field() -> None:
    b = p1()
    del b["total_contract_amount"]
    data = client.post("/api/calculate", json=b).json()
    assert {"loc": ["body", "total_contract_amount"], "type": "missing"} in data[
        "detail"
    ]


def test_422_invalid_json_does_not_echo_body() -> None:
    raw = '{"industry": "' + MARK_STR + '", '
    response = client.post(
        "/api/calculate",
        content=raw.encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert MARK_STR not in response.text
    assert all(set(e) == {"loc", "type"} for e in response.json()["detail"])


# ---- 500: 고정 문구만 ----


def test_500_returns_fixed_message(
    monkeypatch: pytest.MonkeyPatch, all_logs: Any
) -> None:
    def boom(*_: Any) -> None:
        raise RuntimeError(f"내부 오류 {MARK_STR} {MARK_INT}")

    monkeypatch.setattr(calculate_module, "calculate_refund", boom)
    safe_client = TestClient(app, raise_server_exceptions=False)
    response = safe_client.post("/api/calculate", json=p1())
    assert response.status_code == 500
    assert response.json() == {"message": SERVER_ERROR_MESSAGE}
    assert "Traceback" not in response.text
    assert MARK_STR not in response.text
    # 로그에는 예외 종류 이름만 남는다
    assert "RuntimeError" in all_logs.text
    assert MARK_STR not in all_logs.text and str(MARK_INT) not in all_logs.text


# ---- 정상 요청도 입력을 로그에 남기지 않는다 ----


def test_success_does_not_log_input(all_logs: Any) -> None:
    b = {**p1(), "provider_offer": MARK_INT}
    response = client.post("/api/calculate", json=b)
    assert response.status_code == 200
    assert str(MARK_INT) not in all_logs.text
    assert f"{MARK_INT:,}" not in all_logs.text


def test_router_has_no_logging() -> None:
    """라우터는 입력을 logger로 출력하지 않는다 (logging·print 사용 자체가 없다)."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(calculate_module))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imports = {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    assert "logging" not in imports
    assert "print" not in names
    assert not attrs & {"debug", "info", "warning", "error", "exception", "log"}
