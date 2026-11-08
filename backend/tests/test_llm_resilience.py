"""429 처리 테스트: 1회 재시도, Retry-After, 예비 모델 1회, 무한 재시도 없음 (2026-11-08 결정)."""

from dataclasses import dataclass
from typing import Any

import pytest

from llm.client import LLMError, LLMErrorKind, Turn
from llm.resilience import MAX_RETRY_WAIT, RetryingClient


@dataclass
class Scripted:
    """정해 둔 순서대로 성공 문자열 또는 오류를 낸다."""

    model: str
    outcomes: list[str | LLMError]
    calls: int = 0

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, LLMError):
            raise out
        return out


def rl(retry_after: float | None = None) -> LLMError:
    return LLMError(LLMErrorKind.RATE_LIMITED, 429, retry_after=retry_after)


def invoke(
    primary: Scripted, fallback: Scripted | None = None
) -> tuple[Any, list[float]]:
    """성공하면 문자열, 실패하면 LLMError와 sleep 기록을 돌려준다."""
    slept: list[float] = []
    client = RetryingClient(primary, fallback, sleep=slept.append)
    try:
        out: Any = client.generate_json(
            system="s", turns=[Turn("user", "t")], response_schema={}
        )
    except LLMError as exc:
        out = exc
    return out, slept


def test_success_first_try() -> None:
    p = Scripted("a", ["ok"])
    assert invoke(p) == ("ok", [])
    assert p.calls == 1


def test_429_then_retry_success_follows_retry_after() -> None:
    p = Scripted("a", [rl(3.0), "ok"])
    assert invoke(p) == ("ok", [3.0])
    assert p.calls == 2


def test_429_without_retry_after_retries_once() -> None:
    p = Scripted("a", [rl(), "ok"])
    assert invoke(p) == ("ok", [])  # 간격은 기본 모델의 호출 간격 제한이 지킨다
    assert p.calls == 2


def test_429_twice_without_fallback_stops_after_two_calls() -> None:
    p = Scripted("a", [rl(), rl(), "never"])
    err, _ = invoke(p)
    assert isinstance(err, LLMError) and err.kind == LLMErrorKind.RATE_LIMITED
    assert p.calls == 2  # 무한 재시도 없음


def test_long_retry_after_skips_retry() -> None:
    p = Scripted("a", [rl(MAX_RETRY_WAIT + 1), "never"])
    err, slept = invoke(p)
    assert isinstance(err, LLMError) and err.kind == LLMErrorKind.RATE_LIMITED
    assert p.calls == 1
    assert slept == []


def test_fallback_called_once_after_retry() -> None:
    p = Scripted("a", [rl(), rl()])
    f = Scripted("b", ["fallback-ok"])
    assert invoke(p, f)[0] == "fallback-ok"
    assert (p.calls, f.calls) == (2, 1)


def test_fallback_after_skipped_retry() -> None:
    p = Scripted("a", [rl(MAX_RETRY_WAIT + 1)])
    f = Scripted("b", ["fallback-ok"])
    assert invoke(p, f)[0] == "fallback-ok"
    assert (p.calls, f.calls) == (1, 1)


def test_fallback_429_ends_with_rate_limited() -> None:
    p = Scripted("a", [rl(), rl()])
    f = Scripted("b", [rl(), "never"])
    err, _ = invoke(p, f)
    assert isinstance(err, LLMError) and err.kind == LLMErrorKind.RATE_LIMITED
    assert (p.calls, f.calls) == (2, 1)


def test_no_fallback_configured_never_calls_fallback() -> None:
    p = Scripted("a", [rl(), rl()])
    err, _ = invoke(p, None)
    assert isinstance(err, LLMError) and err.status == 429


@pytest.mark.parametrize(
    "kind", [LLMErrorKind.HTTP_ERROR, LLMErrorKind.TIMEOUT, LLMErrorKind.BAD_RESPONSE]
)
def test_other_errors_not_retried(kind: LLMErrorKind) -> None:
    p = Scripted("a", [LLMError(kind), "never"])
    f = Scripted("b", ["never"])
    err, _ = invoke(p, f)
    assert isinstance(err, LLMError) and err.kind == kind
    assert (p.calls, f.calls) == (1, 0)


def test_retry_non_429_error_propagates_without_fallback() -> None:
    p = Scripted("a", [rl(), LLMError(LLMErrorKind.TIMEOUT)])
    f = Scripted("b", ["never"])
    err, _ = invoke(p, f)
    assert isinstance(err, LLMError) and err.kind == LLMErrorKind.TIMEOUT
    assert f.calls == 0


def test_model_is_primary() -> None:
    assert RetryingClient(Scripted("a", []), Scripted("b", [])).model == "a"
