"""일시 오류 재시도 테스트 (기능 플래그 llm_resilience, MVP_SPEC 16절, 2026-11-16).

가짜 클라이언트·가짜 시계만 쓴다. 실제 Gemini를 부르지 않고 실제로 기다리지 않는다.
꺼짐 동작은 기존 tests/test_llm_resilience.py가 그대로 확인한다 (transient_retry 기본 False).
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import pytest

from llm.client import LLMError, LLMErrorKind, Turn
from llm.resilience import TOTAL_BUDGET_SECONDS, RetryingClient, is_transient
from llm.usage import DailyCallCounter

SECRET_TEXT = "표지문장ZQX 010-9876-5432"
REPLY_BODY = '{"응답본문": "ZQXREPLY"}'


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Scripted:
    """정해 둔 순서대로 (걸린 시간, 성공 문자열 또는 오류)를 낸다. 걸린 시간만큼 가짜 시계를 움직인다."""

    model: str
    clock: Clock
    outcomes: list[tuple[float, str | LLMError]]
    wait_before: float = 0.0  # expected_wait()가 돌려줄 값 (호출 간격 제한 대기)
    calls: int = 0
    seen: list[str] = field(default_factory=list)

    def expected_wait(self) -> float:
        return self.wait_before

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls += 1
        self.seen.append(turns[-1].text)
        took, out = self.outcomes.pop(0)
        self.clock.now += took
        if isinstance(out, LLMError):
            raise out
        return out


def err(status: int) -> LLMError:
    if status == 429:
        return LLMError(LLMErrorKind.RATE_LIMITED, 429)
    return LLMError(LLMErrorKind.HTTP_ERROR, status)


TIMEOUT = LLMError(LLMErrorKind.TIMEOUT)
NETWORK = LLMError(LLMErrorKind.NETWORK)


def run(
    primary: Scripted,
    fallback: Scripted | None,
    clock: Clock,
    *,
    on: bool = True,
    call_timeout: float = 20.0,
    counter: DailyCallCounter | None = None,
) -> tuple[Any, list[float]]:
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        clock.now += s

    client = RetryingClient(
        primary,
        fallback,
        sleep=sleep,
        counter=counter,
        transient_retry=on,
        call_timeout=call_timeout,
        clock=clock,
        backoff=lambda: 1.5,
    )
    try:
        out: Any = client.generate_json(
            system="s", turns=[Turn("user", SECRET_TEXT)], response_schema={}
        )
    except LLMError as exc:
        out = exc
    return out, slept


@pytest.mark.parametrize(
    ("exc", "transient"),
    [
        (err(500), True),
        (err(502), True),
        (err(503), True),
        (err(504), True),
        (TIMEOUT, True),
        (NETWORK, True),
        (err(400), False),
        (err(401), False),
        (err(403), False),
        (err(404), False),
        (err(429), False),
        (LLMError(LLMErrorKind.BAD_RESPONSE), False),
        (LLMError(LLMErrorKind.BLOCKED), False),
        (LLMError(LLMErrorKind.DAILY_LIMIT), False),
        (LLMError(LLMErrorKind.HTTP_ERROR), False),  # 상태 모름
    ],
)
def test_is_transient(exc: LLMError, transient: bool) -> None:
    assert is_transient(exc) is transient


def test_503_then_fallback_success() -> None:
    c = Clock()
    p = Scripted("a", c, [(1.6, err(503))])
    f = Scripted("b", c, [(2.0, "ok")])
    out, slept = run(p, f, c)
    assert out == "ok"
    assert (p.calls, f.calls) == (1, 1)
    assert slept == [1.5]


def test_503_without_fallback_retries_same_model_once() -> None:
    c = Clock()
    p = Scripted("a", c, [(1.0, err(503)), (1.0, "ok")])
    out, slept = run(p, None, c)
    assert out == "ok"
    assert p.calls == 2
    assert slept == [1.5]


def test_503_twice_gives_up_after_two_attempts() -> None:
    c = Clock()
    p = Scripted("a", c, [(1.0, err(503))])
    f = Scripted("b", c, [(1.0, err(503))])
    out, _ = run(p, f, c)
    assert isinstance(out, LLMError) and out.status == 503
    assert (p.calls, f.calls) == (1, 1)


def test_timeout_then_fallback_success() -> None:
    c = Clock()
    p = Scripted("a", c, [(20.0, TIMEOUT)])
    f = Scripted("b", c, [(3.0, "ok")])
    out, _ = run(p, f, c)
    assert out == "ok"
    assert f.calls == 1


def test_network_then_same_model_success() -> None:
    c = Clock()
    p = Scripted("a", c, [(0.1, NETWORK), (1.0, "ok")])
    assert run(p, None, c)[0] == "ok"


@pytest.mark.parametrize(
    "exc",
    [
        err(400),
        err(401),
        err(403),
        err(404),
        LLMError(LLMErrorKind.BAD_RESPONSE),
        LLMError(LLMErrorKind.BLOCKED),
    ],
)
def test_non_transient_not_retried(exc: LLMError) -> None:
    c = Clock()
    p = Scripted("a", c, [(1.0, exc)])
    f = Scripted("b", c, [(1.0, "never")])
    out, slept = run(p, f, c)
    assert out is exc
    assert (p.calls, f.calls) == (1, 0)
    assert slept == []


def test_second_attempt_429_is_raised_without_429_retry() -> None:
    c = Clock()
    p = Scripted("a", c, [(1.0, err(503)), (1.0, "never")])
    f = Scripted("b", c, [(1.0, err(429))])
    out, _ = run(p, f, c)
    assert isinstance(out, LLMError) and out.kind == LLMErrorKind.RATE_LIMITED
    assert (p.calls, f.calls) == (1, 1)


def test_budget_stops_second_attempt() -> None:
    """첫 시도 30초 → 50 − 30 − 1.5 = 18.5 < 20이면 두 번째 시도를 시작하지 않는다."""
    c = Clock()
    p = Scripted("a", c, [(30.0, TIMEOUT)])
    f = Scripted("b", c, [(1.0, "never")])
    out, slept = run(p, f, c)
    assert out is TIMEOUT
    assert f.calls == 0
    assert slept == []


def test_budget_counts_rate_limiter_wait() -> None:
    """첫 시도 25초 → 50 − 25 − 1.5 = 23.5 ≥ 20이지만, 호출 간격 대기 5초를 빼면 18.5 < 20."""
    c = Clock()
    p = Scripted("a", c, [(25.0, TIMEOUT), (1.0, "never")], wait_before=5.0)
    out, _ = run(p, None, c)
    assert out is TIMEOUT
    assert p.calls == 1
    c2 = Clock()
    p2 = Scripted("a", c2, [(25.0, TIMEOUT), (1.0, "ok")], wait_before=0.0)
    assert run(p2, None, c2)[0] == "ok"


def test_budget_includes_limiter_wait_inside_first_attempt() -> None:
    """첫 시도의 걸린 시간(호출 간격 대기 포함)은 시계로 잰다: 시작부터 지난 시간이 상한 계산에 들어간다."""
    assert TOTAL_BUDGET_SECONDS == 50.0
    c = Clock()
    p = Scripted("a", c, [(28.5, err(503))])  # 50 − 28.5 − 1.5 = 20 → 시작
    f = Scripted("b", c, [(20.0, "ok")])
    assert run(p, f, c)[0] == "ok"
    assert c.now == 50.0


def test_429_path_unchanged_when_on() -> None:
    """켜짐에서도 첫 429는 기존 순서(기본 재시도 → 예비 모델)를 그대로 탄다."""
    c = Clock()
    p = Scripted("a", c, [(1.0, err(429)), (1.0, err(429))])
    f = Scripted("b", c, [(1.0, "ok")])
    out, slept = run(p, f, c)
    assert out == "ok"
    assert (p.calls, f.calls) == (2, 1)
    assert slept == []  # Retry-After 없음 → 기다림은 호출 간격 제한(구현체 안)에 맡긴다


def test_429_retry_then_503_is_raised_not_transient_retried() -> None:
    """429 경로 안에서 난 503은 기존처럼 그대로 올린다 (일시 오류 재시도와 섞지 않는다)."""
    c = Clock()
    p = Scripted("a", c, [(1.0, err(429)), (1.0, err(503))])
    f = Scripted("b", c, [(1.0, "never")])
    out, _ = run(p, f, c)
    assert isinstance(out, LLMError) and out.status == 503
    assert f.calls == 0


def test_off_does_not_retry_503() -> None:
    c = Clock()
    p = Scripted("a", c, [(1.0, err(503))])
    f = Scripted("b", c, [(1.0, "never")])
    out, slept = run(p, f, c, on=False)
    assert isinstance(out, LLMError) and out.status == 503
    assert (p.calls, f.calls, slept) == (1, 0, [])


def test_counter_counts_second_attempt() -> None:
    c = Clock()
    counter = DailyCallCounter(10)
    p = Scripted("a", c, [(1.0, err(503))])
    f = Scripted("b", c, [(1.0, "ok")])
    assert run(p, f, c, counter=counter)[0] == "ok"
    assert counter.count == 2


def test_counter_exhausted_on_second_attempt() -> None:
    c = Clock()
    counter = DailyCallCounter(1)
    p = Scripted("a", c, [(1.0, err(503))])
    f = Scripted("b", c, [(1.0, "never")])
    out, _ = run(p, f, c, counter=counter)
    assert isinstance(out, LLMError) and out.kind == LLMErrorKind.DAILY_LIMIT
    assert f.calls == 0


# ---- 로그 (플래그와 무관) ----


def test_logs_kind_status_attempt_role_without_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    c = Clock()
    p = Scripted("model-secret-a", c, [(1.6, err(503))])
    f = Scripted("model-secret-b", c, [(2.25, REPLY_BODY)])
    assert run(p, f, c)[0] == REPLY_BODY
    text = caplog.text
    assert (
        "LLM 시도 실패: kind=http_error status=503 attempt=1 role=primary elapsed=1.60s"
        in text
    )
    assert "LLM 시도 성공: attempt=2 role=fallback elapsed=2.25s" in text
    assert "표지문장" not in text and "010-9876-5432" not in text
    assert "ZQXREPLY" not in text
    assert "model-secret" not in text


def test_logs_timeout_without_status_when_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    c = Clock()
    p = Scripted("a", c, [(20.0, TIMEOUT)])
    run(p, None, c, on=False)
    assert "kind=timeout status=- attempt=1 role=primary elapsed=20.00s" in caplog.text


# ---- 호출 간격 제한 대기 계산 (전체 대기 상한에 들어간다) ----


def test_limiter_pending_does_not_wait() -> None:
    from llm.ratelimit import MinIntervalLimiter

    c = Clock()
    slept: list[float] = []
    lim = MinIntervalLimiter(12, clock=c, sleep=slept.append)
    assert lim.pending() == 0.0
    lim.wait()
    c.now += 2.0
    assert lim.pending() == 3.0
    c.now += 10.0
    assert lim.pending() == 0.0
    assert slept == []
    assert MinIntervalLimiter(None).pending() == 0.0


def test_gemini_expected_wait_uses_limiter() -> None:
    from pydantic import SecretStr

    from llm.gemini import GeminiClient
    from llm.ratelimit import MinIntervalLimiter

    c = Clock()
    lim = MinIntervalLimiter(12, clock=c, sleep=lambda s: None)
    lim.wait()
    g = GeminiClient(api_key=SecretStr("FAKE"), model="m", limiter=lim, timeout=20.0)
    assert g.expected_wait() == 5.0
    assert g.timeout == 20.0
    assert GeminiClient(api_key=SecretStr("FAKE"), model="m").expected_wait() == 0.0
    assert GeminiClient(api_key=SecretStr("FAKE"), model="m").timeout == 60.0
