"""호출 간격 제한 테스트. 시계·sleep을 가짜로 바꿔 실제로 기다리지 않는다."""

import httpx
import pytest
from pydantic import SecretStr

from llm.client import LLMError, LLMErrorKind, Turn
from llm.gemini import GeminiClient
from llm.ratelimit import MinIntervalLimiter

FAKE_KEY = "FAKE-KEY-ZQX-4444"


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make(rpm: int | None) -> tuple[MinIntervalLimiter, FakeTime]:
    t = FakeTime()
    return MinIntervalLimiter(rpm, clock=t.clock, sleep=t.sleep), t


def test_first_call_does_not_wait() -> None:
    limiter, t = make(12)
    assert limiter.wait() == 0
    assert t.slept == []


def test_back_to_back_calls_wait_interval() -> None:
    limiter, t = make(12)
    for _ in range(4):
        limiter.wait()
    assert t.slept == [5.0, 5.0, 5.0]  # 분당 12건 = 5초 간격


def test_partial_gap_waits_only_remainder() -> None:
    limiter, t = make(12)
    limiter.wait()
    t.now += 3.0
    assert limiter.wait() == pytest.approx(2.0)


def test_long_gap_no_wait() -> None:
    limiter, t = make(15)
    limiter.wait()
    t.now += 60
    assert limiter.wait() == 0


def test_none_disables() -> None:
    limiter, t = make(None)
    for _ in range(3):
        limiter.wait()
    assert t.slept == []


def test_invalid_rpm() -> None:
    with pytest.raises(ValueError):
        MinIntervalLimiter(0)


# ---- Gemini 구현체와의 연결 ----


def ok(req: httpx.Request) -> httpx.Response:
    text = "{}"
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]}
    )


def call(client: GeminiClient) -> str:
    return client.generate_json(
        system="s", turns=[Turn("user", "t")], response_schema={}
    )


def test_gemini_waits_before_each_call() -> None:
    limiter, t = make(12)
    client = GeminiClient(
        api_key=SecretStr(FAKE_KEY),
        model="m",
        limiter=limiter,
        transport=httpx.MockTransport(ok),
    )
    call(client)
    call(client)
    call(client)
    assert t.slept == [5.0, 5.0]


def test_gemini_temperature_none_not_sent() -> None:
    def body(temp: float | None) -> dict[str, object]:
        c = GeminiClient(api_key=SecretStr(FAKE_KEY), model="m", temperature=temp)
        return c.build_body(system="s", turns=[Turn("user", "t")], response_schema={})[
            "generationConfig"
        ]

    assert "temperature" not in body(None)
    assert body(0.0)["temperature"] == 0.0
    assert body(0.3)["temperature"] == 0.3


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "7"}, 7.0),
        ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ({"Retry-After": "-3"}, None),
        ({}, None),
    ],
)
def test_gemini_retry_after(headers: dict[str, str], expected: float | None) -> None:
    client = GeminiClient(
        api_key=SecretStr(FAKE_KEY),
        model="m",
        transport=httpx.MockTransport(
            lambda req: httpx.Response(429, headers=headers, json={})
        ),
    )
    with pytest.raises(LLMError) as exc:
        call(client)
    assert exc.value.kind == LLMErrorKind.RATE_LIMITED
    assert exc.value.retry_after == expected
    assert FAKE_KEY not in str(exc.value)
