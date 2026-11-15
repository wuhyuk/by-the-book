"""/api/analyze 일시 오류 처리 (기능 플래그 llm_resilience, MVP_SPEC 16절, 2026-11-16).

가짜 클라이언트만 쓴다 (실제 Gemini·실제 backend/.env 없음). 꺼짐 동작은 기존 tests/test_api_analyze.py가 확인한다.
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_llm_extraction import raw

import api.analyze as analyze_module
from api.analyze import (
    BUSY_MESSAGE,
    FAILED_MESSAGE,
    RATE_LIMITED_MESSAGE,
    get_client_provider,
)
from api.settings import AppSettings, get_app_settings, load_app_settings
from llm.client import LLMError, LLMErrorKind, Turn
from llm.config import DEFAULT_TIMEOUT_SECONDS, LLMSettings, load_settings
from llm.gemini import GeminiClient
from llm.resilience import RetryingClient
from llm.validation_log import failed_fields
from main import APP_LOGGER, app, configure_logging

client = TestClient(app)

MARK = "표지문장ZQX"
TEXT = f"{MARK} 헬스장 1년권을 120만원에 결제했어요"
FAKE_KEY = "FAKE-KEY-ZQX-7777"


@dataclass
class Seq:
    """정해 둔 순서대로 응답하거나 오류를 낸다."""

    outcomes: list[str | LLMError]
    model: str = "fake"
    calls: int = 0
    seen: list[str] = field(default_factory=list)

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls += 1
        self.seen.append(turns[-1].text)
        out = self.outcomes.pop(0)
        if isinstance(out, LLMError):
            raise out
        return out


OK = json.dumps(raw({}))


@pytest.fixture
def setup() -> Iterator[Any]:
    def _setup(
        features: tuple[str, ...], primary: Seq, fallback: Seq | None = None
    ) -> None:
        app.dependency_overrides[get_app_settings] = lambda: AppSettings(
            enabled_features=features
        )
        on = "llm_resilience" in features
        wrapped = RetryingClient(
            primary,
            fallback,
            sleep=lambda s: None,
            transient_retry=on,
            call_timeout=20.0,
            backoff=lambda: 1.0,
        )
        app.dependency_overrides[get_client_provider] = lambda: lambda: wrapped

    yield _setup
    app.dependency_overrides.clear()


def post() -> Any:
    return client.post("/api/analyze", json={"text": TEXT})


ON = ("llm_resilience",)


def test_on_503_then_fallback_200(setup: Any) -> None:
    p, f = Seq([LLMError(LLMErrorKind.HTTP_ERROR, 503)]), Seq([OK])
    setup(ON, p, f)
    r = post()
    assert r.status_code == 200
    assert r.json()["status"] == "extracted"
    assert (p.calls, f.calls) == (1, 1)


def test_on_503_same_model_retry_200(setup: Any) -> None:
    p = Seq([LLMError(LLMErrorKind.HTTP_ERROR, 503), OK])
    setup(ON, p)
    assert post().status_code == 200
    assert p.calls == 2


@pytest.mark.parametrize(
    "exc",
    [
        LLMError(LLMErrorKind.HTTP_ERROR, 503),
        LLMError(LLMErrorKind.HTTP_ERROR, 500),
        LLMError(LLMErrorKind.TIMEOUT),
        LLMError(LLMErrorKind.NETWORK),
    ],
)
def test_on_transient_twice_busy_message(setup: Any, exc: LLMError) -> None:
    p, f = Seq([exc]), Seq([exc])
    setup(ON, p, f)
    r = post()
    assert r.status_code == 502
    assert r.json() == {"message": BUSY_MESSAGE, "code": exc.kind.value}
    assert MARK not in r.text


def test_on_timeout_then_fallback_200(setup: Any) -> None:
    p, f = Seq([LLMError(LLMErrorKind.TIMEOUT)]), Seq([OK])
    setup(ON, p, f)
    assert post().status_code == 200


@pytest.mark.parametrize(
    "exc",
    [
        LLMError(LLMErrorKind.HTTP_ERROR, 400),
        LLMError(LLMErrorKind.HTTP_ERROR, 403),
        LLMError(LLMErrorKind.BAD_RESPONSE),
        LLMError(LLMErrorKind.BLOCKED),
    ],
)
def test_on_non_transient_keeps_failed_message(setup: Any, exc: LLMError) -> None:
    p, f = Seq([exc]), Seq([OK])
    setup(ON, p, f)
    r = post()
    assert r.status_code == 502
    assert r.json() == {"message": FAILED_MESSAGE, "code": exc.kind.value}
    assert (p.calls, f.calls) == (1, 0)


def test_on_schema_failure_not_retried(setup: Any) -> None:
    p, f = Seq(["not json at all"]), Seq([OK])
    setup(ON, p, f)
    r = post()
    assert r.status_code == 502
    assert r.json() == {"message": FAILED_MESSAGE, "code": "bad_response"}
    assert (p.calls, f.calls) == (1, 0)


def test_on_429_path_unchanged(setup: Any) -> None:
    rl = LLMError(LLMErrorKind.RATE_LIMITED, 429)
    p, f = Seq([rl, rl]), Seq([rl])
    setup(ON, p, f)
    r = post()
    assert r.status_code == 429
    assert r.json() == {"message": RATE_LIMITED_MESSAGE, "code": "rate_limited"}
    assert (p.calls, f.calls) == (2, 1)


@pytest.mark.parametrize(
    "exc", [LLMError(LLMErrorKind.HTTP_ERROR, 503), LLMError(LLMErrorKind.TIMEOUT)]
)
def test_off_unchanged_no_retry_old_message(setup: Any, exc: LLMError) -> None:
    p, f = Seq([exc]), Seq([OK])
    setup((), p, f)
    r = post()
    assert r.status_code == 502
    assert r.json() == {"message": FAILED_MESSAGE, "code": exc.kind.value}
    assert (p.calls, f.calls) == (1, 0)


def test_config_lists_llm_resilience() -> None:
    s = load_app_settings({"ENABLED_FEATURES": "llm_resilience,rag"}, env_file=None)
    assert s.enabled_features == ("rag", "llm_resilience")
    app.dependency_overrides[get_app_settings] = lambda: s
    try:
        assert client.get("/api/config").json()["enabled_features"] == [
            "rag",
            "llm_resilience",
        ]
    finally:
        app.dependency_overrides.clear()


# ---- 실제 구성(default_client): 꺼짐 60초·재시도 없음, 켜짐 LLM_TIMEOUT_SECONDS·재시도 ----


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    def _build(features: tuple[str, ...], **kw: Any) -> RetryingClient:
        s = LLMSettings(
            provider="gemini", api_key=SecretStr(FAKE_KEY), model="model-a", **kw
        )
        monkeypatch.setattr(analyze_module, "load_settings", lambda: s)
        monkeypatch.setattr(
            analyze_module,
            "app_settings",
            lambda: AppSettings(enabled_features=features),
        )
        analyze_module.default_client.cache_clear()
        c = analyze_module.default_client()
        assert isinstance(c, RetryingClient)
        return c

    yield _build
    analyze_module.default_client.cache_clear()


def test_default_client_off_keeps_60s_and_no_transient(built: Any) -> None:
    c = built((), fallback_model="model-b", timeout_seconds=15.0)
    assert c._transient_retry is False
    for g in (c._primary, c._fallback):
        assert isinstance(g, GeminiClient) and g.timeout == 60.0


def test_default_client_on_uses_timeout_setting(built: Any) -> None:
    c = built(ON, fallback_model="model-b", timeout_seconds=15.0)
    assert c._transient_retry is True
    assert c._call_timeout == 15.0
    for g in (c._primary, c._fallback):
        assert isinstance(g, GeminiClient) and g.timeout == 15.0
    assert FAKE_KEY not in repr(c)


# ---- LLM_TIMEOUT_SECONDS ----

BASE_ENV = {"LLM_PROVIDER": "gemini", "LLM_API_KEY": FAKE_KEY, "LLM_MODEL": "m"}


@pytest.mark.parametrize(
    ("raw_value", "expected", "warned"),
    [
        (None, 20.0, False),
        ("", 20.0, False),
        ("15", 15.0, False),
        ("12.5", 12.5, False),
        ("1", 1.0, False),
        ("50", 50.0, False),
        ("0", 20.0, True),
        ("-3", 20.0, True),
        ("51", 20.0, True),
        ("abc", 20.0, True),
        ("nan", 20.0, True),
        ("inf", 20.0, True),
    ],
)
def test_timeout_setting(
    caplog: pytest.LogCaptureFixture,
    raw_value: str | None,
    expected: float,
    warned: bool,
) -> None:
    caplog.set_level(logging.DEBUG)
    env = dict(BASE_ENV)
    if raw_value is not None:
        env["LLM_TIMEOUT_SECONDS"] = raw_value
    s = load_settings(env, env_file=None)
    assert s.timeout_seconds == expected
    assert DEFAULT_TIMEOUT_SECONDS == 20.0
    assert ("LLM_TIMEOUT_SECONDS 값이 맞지 않아" in caplog.text) is warned
    if raw_value:
        assert f"={raw_value}" not in caplog.text
    assert FAKE_KEY not in caplog.text


def test_timeout_setting_read_from_env_file(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("LLM_TIMEOUT_SECONDS=30\n", encoding="utf-8")
    assert load_settings(BASE_ENV, env_file=f).timeout_seconds == 30.0


# ---- 로그 ----


def test_api_failure_log_has_kind_status_and_no_content(
    setup: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    exc = LLMError(LLMErrorKind.HTTP_ERROR, 503)
    setup(ON, Seq([exc]), Seq([LLMError(LLMErrorKind.HTTP_ERROR, 503)]))
    assert post().status_code == 502
    text = caplog.text
    assert "kind=http_error status=503 attempt=1 role=primary" in text
    assert "kind=http_error status=503 attempt=2 role=fallback" in text
    assert "LLM 호출 실패: http_error (status=503)" in text
    assert MARK not in text and "120만원" not in text


def test_validation_failure_logs_field_names_only(
    setup: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    bad = raw({})
    bad["fields"]["industry"] = "ZQXVALUE-not-allowed"
    bad["ZQXEXTRAKEY"] = "ZQXEXTRAVALUE"
    setup(ON, Seq([json.dumps(bad)]))
    r = post()
    assert r.status_code == 502
    line = next(
        rec.getMessage()
        for rec in caplog.records
        if rec.getMessage().startswith("LLM 응답 검증 실패")
    )
    assert "fields.industry" in line
    assert "ZQX" not in caplog.text  # 값·낯선 키·입력 문장 없음
    assert "?" in line  # 낯선 키는 '?'로


def test_failed_fields_masks_unknown_names() -> None:
    from pydantic import BaseModel, ConfigDict, ValidationError

    class M(BaseModel):
        model_config = ConfigDict(extra="forbid")
        a: int

    with pytest.raises(ValidationError) as exc:
        M.model_validate({"a": "x", "secret key": 1})
    assert failed_fields(exc.value, ["a"]) == ["a", "?"]


def test_configure_logging_info_stdout_once() -> None:
    configure_logging()
    configure_logging()
    logger = logging.getLogger(APP_LOGGER)
    assert logger.level == logging.INFO
    ours = [h for h in logger.handlers if getattr(h, "_by_the_book", False)]
    assert len(ours) == 1
    fmt = ours[0].formatter
    assert fmt is not None and fmt._fmt is not None
    assert "%(asctime)s" in fmt._fmt and "%(levelname)s" in fmt._fmt
