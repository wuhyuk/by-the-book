"""/api/analyze 한도 대응 테스트 (2026-11-08 결정). 실제 .env를 읽지 않도록 load_settings를 바꿔 끼운다."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_gym_calc import CASES

import api.analyze as analyze_module
from api.analyze import RATE_LIMITED_MESSAGE, get_client_provider
from llm.client import LLMError, LLMErrorKind, Turn
from llm.config import LLMSettings
from llm.gemini import GeminiClient
from llm.resilience import RetryingClient
from main import app

client = TestClient(app)
FAKE_KEY = "FAKE-KEY-ZQX-5555"


def settings(**kw: Any) -> LLMSettings:
    base: dict[str, Any] = {
        "provider": "gemini",
        "api_key": SecretStr(FAKE_KEY),
        "model": "model-a",
    }
    return LLMSettings(**{**base, **kw})


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    def _build(s: LLMSettings) -> RetryingClient:
        monkeypatch.setattr(analyze_module, "load_settings", lambda: s)
        analyze_module.default_client.cache_clear()
        c = analyze_module.default_client()
        assert isinstance(c, RetryingClient)
        return c

    yield _build
    analyze_module.default_client.cache_clear()


def test_wiring_with_fallback(built: Any) -> None:
    c = built(settings(temperature=None, max_rpm=6, fallback_model="model-b"))
    assert c.model == "model-a"
    assert FAKE_KEY not in repr(c)
    primary, fallback = c._primary, c._fallback
    assert isinstance(primary, GeminiClient) and isinstance(fallback, GeminiClient)
    assert fallback.model == "model-b"
    # 한도가 모델마다 따로라 간격 제한도 따로 둔다
    assert primary._limiter is not fallback._limiter
    assert primary._limiter is not None and primary._limiter.interval == 10.0
    assert primary._temperature is None


def test_wiring_without_fallback(built: Any) -> None:
    c = built(settings())
    assert c._fallback is None
    primary = c._primary
    assert isinstance(primary, GeminiClient)
    assert primary._temperature == 0.0
    assert primary._limiter is not None and primary._limiter.interval == 5.0


class Always429:
    model = "x"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls += 1
        raise LLMError(LLMErrorKind.RATE_LIMITED, 429)


def test_final_429_message_and_form_still_works() -> None:
    primary, fallback = Always429(), Always429()
    retrying = RetryingClient(primary, fallback, sleep=lambda s: None)
    app.dependency_overrides[get_client_provider] = lambda: lambda: retrying
    try:
        r = client.post("/api/analyze", json={"text": "헬스장 120만원 결제했어요"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 429
    assert r.json()["message"] == RATE_LIMITED_MESSAGE
    # 재시도 1회 + 예비 1회, 그 이상 없음
    assert (primary.calls, fallback.calls) == (2, 1)
    # 문장 분석이 막혀도 폼 계산은 그대로 동작한다
    calc = client.post("/api/calculate", json=CASES[0].inp.model_dump(mode="json"))
    assert calc.status_code == 200
