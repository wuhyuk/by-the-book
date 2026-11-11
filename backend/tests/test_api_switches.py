"""운영 스위치 테스트 (2026-11-11): GET /api/config, ANALYZE_ENABLED, DAILY_ANALYZE_LIMIT.

실제 backend/.env와 실제 API를 쓰지 않는다 (conftest가 환경변수로 기본값을 넣고, LLM은 가짜).
확인: 끄면 호출 없음, 하루 상한 도달 시 호출 없음, 가드레일은 호출 수에 넣지 않음, 재시도·예비 모델은
각각 1회, 계산 API는 영향 없음, 로그 원칙(본문 비로깅·키 비노출).
"""

import json
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_api_analyze import FakeClient
from test_gym_calc import CASES
from test_llm_extraction import raw

import api.analyze as analyze_module
from api.analyze import (
    DAILY_LIMIT_CODE,
    DAILY_LIMIT_MESSAGE,
    DISABLED_CODE,
    DISABLED_MESSAGE,
    get_client_provider,
    get_daily_counter,
)
from api.settings import AppSettings, get_app_settings, load_app_settings
from llm.client import LLMError, LLMErrorKind, Turn
from llm.config import LLMSettings
from llm.resilience import RetryingClient
from llm.usage import KST, DailyCallCounter
from main import app

client = TestClient(app)
MARK = "표지문장ZQX스위치"
TEXT = f"{MARK} 헬스장 1년권을 2026-01-01부터 2026-12-31까지 120만원에 결제했어요."
FAKE_KEY = "FAKE-KEY-ZQX-7777"


@pytest.fixture
def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture
def override() -> Iterator[Any]:
    def _set(
        *,
        settings: AppSettings | None = None,
        counter: DailyCallCounter | None = None,
        llm: Any = None,
    ) -> None:
        if settings is not None:
            app.dependency_overrides[get_app_settings] = lambda: settings
        if counter is not None:
            app.dependency_overrides[get_daily_counter] = lambda: counter
        if llm is not None:
            app.dependency_overrides[get_client_provider] = lambda: lambda: llm

    yield _set
    app.dependency_overrides.clear()


def calc_ok() -> None:
    """문장 분석 상태와 상관없이 폼 계산은 그대로 동작한다."""
    r = client.post("/api/calculate", json=CASES[0].inp.model_dump(mode="json"))
    assert r.status_code == 200


def extraction_reply() -> str:
    return json.dumps(raw({}))


# ---- 설정 읽기 ----


def test_settings_defaults() -> None:
    s = load_app_settings({}, env_file=None)
    assert s == AppSettings(
        analyze_enabled=True, daily_analyze_limit=450, survey_url=None
    )


@pytest.mark.parametrize(
    ("value", "enabled"),
    [("", True), ("true", True), ("ON", True), ("false", False), ("0", False),
     ("flase", False)],
)  # fmt: skip
def test_settings_analyze_enabled(value: str, enabled: bool) -> None:
    s = load_app_settings({"ANALYZE_ENABLED": value}, env_file=None)
    assert s.analyze_enabled is enabled


def test_settings_limit_and_survey() -> None:
    s = load_app_settings(
        {"DAILY_ANALYZE_LIMIT": "30", "SURVEY_URL": "https://forms.example/x"},
        env_file=None,
    )
    assert (s.daily_analyze_limit, s.survey_url) == (30, "https://forms.example/x")
    bad = load_app_settings(
        {"DAILY_ANALYZE_LIMIT": "-1", "SURVEY_URL": "javascript:alert(1)"},
        env_file=None,
    )
    assert (bad.daily_analyze_limit, bad.survey_url) == (450, None)


def test_settings_file_values_and_env_first(tmp_path: Any) -> None:
    f = tmp_path / "e.env"
    f.write_text(
        "ANALYZE_ENABLED=false\nDAILY_ANALYZE_LIMIT=7\nLLM_API_KEY=x\n", "utf-8"
    )
    s = load_app_settings({"ANALYZE_ENABLED": "true"}, env_file=f)
    assert (s.analyze_enabled, s.daily_analyze_limit) == (True, 7)


# ---- GET /api/config ----


def test_config_default() -> None:
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == {"analyze_enabled": True, "survey_url": None}


def test_config_reflects_settings(override: Any) -> None:
    override(
        settings=AppSettings(analyze_enabled=False, survey_url="https://s.example")
    )
    assert client.get("/api/config").json() == {
        "analyze_enabled": False,
        "survey_url": "https://s.example",
    }


def test_config_exposes_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", FAKE_KEY)
    r = client.get("/api/config")
    assert FAKE_KEY not in r.text
    assert set(r.json()) == {"analyze_enabled", "survey_url"}


# ---- ANALYZE_ENABLED=false ----


def test_disabled_does_not_call_llm(override: Any, logs: Any) -> None:
    fake = FakeClient(reply=extraction_reply())
    override(settings=AppSettings(analyze_enabled=False), llm=fake)
    r = client.post("/api/analyze", json={"text": TEXT})
    assert r.status_code == 503
    assert r.json() == {"message": DISABLED_MESSAGE, "code": DISABLED_CODE}
    assert fake.received == []
    assert MARK not in logs.text and MARK not in r.text
    calc_ok()


def test_disabled_env_var_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """환경변수로 끄는 실제 경로 (의존성 바꿔 끼우기 없이)."""
    monkeypatch.setenv("ANALYZE_ENABLED", "false")
    import api.settings as settings_module

    settings_module.app_settings.cache_clear()
    r = client.post("/api/analyze", json={"text": TEXT})
    assert r.json()["code"] == DISABLED_CODE
    assert client.get("/api/config").json()["analyze_enabled"] is False
    calc_ok()


# ---- 하루 호출 카운터 ----


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def test_counter_kst_day_rollover() -> None:
    # 2026-11-11 23:59 KST → 같은 날, 00:00 KST → 다음 날 (UTC 15:00 경계)
    clock = Clock(datetime(2026, 11, 11, 23, 59, tzinfo=KST))
    c = DailyCallCounter(2, now=clock)
    c.acquire()
    c.acquire()
    assert c.exhausted()
    with pytest.raises(LLMError) as exc:
        c.acquire()
    assert exc.value.kind == LLMErrorKind.DAILY_LIMIT
    assert c.count == 2  # 막힌 호출은 세지 않는다
    clock.at = clock.at + timedelta(minutes=1)
    assert c.count == 0 and not c.exhausted()


def test_counter_uses_kst_not_utc() -> None:
    """UTC 14:59(KST 23:59)와 UTC 15:00(KST 다음 날 00:00)은 다른 날이다."""
    from datetime import UTC

    clock = Clock(datetime(2026, 11, 11, 14, 59, tzinfo=UTC))
    c = DailyCallCounter(1, now=clock)
    c.acquire()
    assert c.exhausted()
    clock.at = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
    assert not c.exhausted()


def test_limit_reached_returns_code_without_call(override: Any, logs: Any) -> None:
    counter = DailyCallCounter(1)
    fake = FakeClient(reply=extraction_reply())
    override(counter=counter, llm=RetryingClient(fake, counter=counter))
    first = client.post("/api/analyze", json={"text": TEXT})
    assert first.status_code == 200 and len(fake.received) == 1
    second = client.post("/api/analyze", json={"text": TEXT})
    assert second.status_code == 429
    assert second.json() == {"message": DAILY_LIMIT_MESSAGE, "code": DAILY_LIMIT_CODE}
    assert len(fake.received) == 1  # 상한 도달 뒤에는 호출하지 않는다
    assert MARK not in logs.text
    calc_ok()


def test_guardrail_is_not_counted(override: Any) -> None:
    counter = DailyCallCounter(5)
    fake = FakeClient(reply=extraction_reply())
    override(counter=counter, llm=RetryingClient(fake, counter=counter))
    r = client.post(
        "/api/analyze", json={"text": "헬스장 환불 소송하면 이길 수 있나요?"}
    )
    assert r.json()["status"] == "guardrail"
    assert counter.count == 0 and fake.received == []


def test_guardrail_still_answers_at_limit(override: Any) -> None:
    """상한에 도달해도 규칙 가드레일(호출 없음)은 ❔로 답한다."""
    counter = DailyCallCounter(0)
    override(counter=counter, llm=FakeClient(reply=extraction_reply()))
    r = client.post(
        "/api/analyze", json={"text": "헬스장 환불 소송하면 이길 수 있나요?"}
    )
    assert r.json()["status"] == "guardrail"


class Always429:
    model = "x"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls += 1
        raise LLMError(LLMErrorKind.RATE_LIMITED, 429)


def test_retry_and_fallback_each_counted(override: Any) -> None:
    counter = DailyCallCounter(10)
    primary, fallback = Always429(), Always429()
    retrying = RetryingClient(primary, fallback, sleep=lambda s: None, counter=counter)
    override(counter=counter, llm=retrying)
    r = client.post("/api/analyze", json={"text": TEXT})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    assert (primary.calls, fallback.calls) == (2, 1)
    assert counter.count == 3


def test_limit_hit_mid_retry(override: Any) -> None:
    """재시도 도중 상한에 닿으면 더 호출하지 않고 ANALYZE_DAILY_LIMIT."""
    counter = DailyCallCounter(1)
    primary, fallback = Always429(), Always429()
    retrying = RetryingClient(primary, fallback, sleep=lambda s: None, counter=counter)
    override(counter=counter, llm=retrying)
    r = client.post("/api/analyze", json={"text": TEXT})
    assert r.status_code == 429 and r.json()["code"] == DAILY_LIMIT_CODE
    assert (primary.calls, fallback.calls) == (1, 0)
    assert counter.count == 1


def test_default_client_shares_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """실제 구성(default_client)이 엔드포인트와 같은 카운터를 쓰고 키를 드러내지 않는다."""
    s = LLMSettings(provider="gemini", api_key=SecretStr(FAKE_KEY), model="model-a")
    monkeypatch.setattr(analyze_module, "load_settings", lambda: s)
    analyze_module.default_client.cache_clear()
    try:
        c = analyze_module.default_client()
        assert isinstance(c, RetryingClient)
        assert c._counter is analyze_module.daily_counter()
        assert c._counter.limit == 450
        assert FAKE_KEY not in repr(c)
    finally:
        analyze_module.default_client.cache_clear()
