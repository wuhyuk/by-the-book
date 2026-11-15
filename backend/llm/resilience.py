"""LLM 호출 실패 처리: 429 재시도·예비 모델(2026-11-08)과 일시 오류 재시도(llm_resilience, 2026-11-16).

429 (기존, 플래그와 무관, 무한 재시도 없음, 호출은 최대 3번):
1. 기본 모델 호출
2. 429면 Retry-After를 따라 기다린 뒤 기본 모델 1회 재시도.
   Retry-After가 MAX_RETRY_WAIT보다 길면 기다리지 않고 재시도를 건너뛴다 (요청을 오래 붙잡지 않는다).
   Retry-After가 없으면 기본 모델의 호출 간격 제한(ratelimit.py)만큼 기다린 뒤 재시도한다.
3. 그래도 429이고 예비 모델(LLM_FALLBACK_MODEL)이 있으면 예비 모델 1회.
4. 그래도 실패하면 LLMError(RATE_LIMITED). API는 "잠시 후 다시 시도하거나 폼에 직접 입력" 안내로 끝낸다.

일시 오류 (transient_retry=True, 기능 플래그 llm_resilience가 켜져 있을 때만, MVP_SPEC 16절):
- 첫 시도가 HTTP 500·502·503·504, 시간 초과(TIMEOUT), 연결 실패(NETWORK)이면 두 번째 시도를 한 번만 한다.
  예비 모델이 있으면 예비 모델, 없으면 같은 모델. 시도 사이 1~2초(지터) 기다린다. 시도는 모두 합쳐 2회까지.
- 두 번째 시도는 전체 대기 상한(TOTAL_BUDGET_SECONDS) 안에 끝날 수 있을 때만 시작한다:
  상한 − 지난 시간 − 대기 − 호출 간격 제한 대기 < 호출 하나의 시간 제한이면 시작하지 않고 첫 오류를 올린다.
- 그 밖의 오류(400·401·403·404 등, BAD_RESPONSE, BLOCKED, DAILY_LIMIT)는 지금처럼 바로 올린다.
- 첫 시도가 429이면 위 429 순서를 그대로 탄다 (일시 오류 재시도와 섞지 않는다).
  두 번째 시도가 429이면 그 429를 그대로 올린다 (429 재시도를 다시 시작하지 않는다).
transient_retry=False(꺼짐)이면 429가 아닌 실패는 재시도하지 않고 그대로 올린다 (변경 전과 같다).

counter(llm/usage.py)가 있으면 실제로 보내는 호출마다(재시도·예비 모델 포함) 호출 직전에 1회씩 센다.
하루 상한에 도달하면 호출을 보내지 않고 LLMError(DAILY_LIMIT)를 그대로 올린다 (재시도하지 않음).

로그 (플래그와 무관): 시도마다 종류(kind)·HTTP 상태·시도 번호·모델 역할(primary/fallback)·소요 시간(초)만 남긴다.
입력 문장·응답 본문·키·모델 이름은 남기지 않는다.
"""

import logging
import random
import time
from collections.abc import Callable
from typing import Any, Literal

from llm.client import LLMClient, LLMError, LLMErrorKind, Turn
from llm.usage import DailyCallCounter

logger = logging.getLogger("by_the_book.llm")

MAX_RETRY_WAIT = 20.0
TOTAL_BUDGET_SECONDS = 50.0  # llm_resilience: 한 요청에서 LLM 시도에 쓰는 시간의 상한
BACKOFF_MIN = 1.0
BACKOFF_MAX = 2.0
TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})

Role = Literal["primary", "fallback"]


def is_transient(exc: LLMError) -> bool:
    """일시 오류인지 (llm_resilience 재시도 대상, 사용자 문구 구분에도 쓴다)."""
    if exc.kind in (LLMErrorKind.TIMEOUT, LLMErrorKind.NETWORK):
        return True
    return exc.kind == LLMErrorKind.HTTP_ERROR and exc.status in TRANSIENT_STATUSES


def default_backoff() -> float:
    return random.uniform(BACKOFF_MIN, BACKOFF_MAX)


def _expected_wait(client: LLMClient) -> float:
    """구현체가 호출 간격 제한 대기를 알려 주면 그 값, 아니면 0."""
    fn = getattr(client, "expected_wait", None)
    return float(fn()) if callable(fn) else 0.0


class RetryingClient:
    """LLMClient를 감싸 429(항상)와 일시 오류(transient_retry일 때)를 다룬다. 제공자와 무관하다."""

    def __init__(
        self,
        primary: LLMClient,
        fallback: LLMClient | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_retry_wait: float = MAX_RETRY_WAIT,
        counter: DailyCallCounter | None = None,
        transient_retry: bool = False,
        call_timeout: float = 0.0,
        total_budget: float = TOTAL_BUDGET_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        backoff: Callable[[], float] = default_backoff,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._sleep = sleep
        self._max_retry_wait = max_retry_wait
        self._counter = counter
        self._transient_retry = transient_retry
        self._call_timeout = call_timeout
        self._total_budget = total_budget
        self._clock = clock
        self._backoff = backoff

    def __repr__(self) -> str:
        return f"RetryingClient(primary={self._primary!r}, fallback={self._fallback!r})"

    @property
    def model(self) -> str:
        return self._primary.model

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        attempt = 0

        def call(client: LLMClient, role: Role) -> str:
            nonlocal attempt
            attempt += 1
            if self._counter is not None:
                self._counter.acquire()
            started = self._clock()
            try:
                out = client.generate_json(
                    system=system, turns=turns, response_schema=response_schema
                )
            except LLMError as exc:
                logger.warning(
                    "LLM 시도 실패: kind=%s status=%s attempt=%d role=%s elapsed=%.2fs",
                    exc.kind.value,
                    exc.status if exc.status is not None else "-",
                    attempt,
                    role,
                    self._clock() - started,
                )
                raise
            logger.info(
                "LLM 시도 성공: attempt=%d role=%s elapsed=%.2fs",
                attempt,
                role,
                self._clock() - started,
            )
            return out

        begin = self._clock()
        try:
            return call(self._primary, "primary")
        except LLMError as exc:
            if exc.kind == LLMErrorKind.RATE_LIMITED:
                wait = exc.retry_after
            elif self._transient_retry and is_transient(exc):
                return self._transient_second(call, exc, begin)
            else:
                raise
        if wait is None or wait <= self._max_retry_wait:
            if wait:
                self._sleep(wait)
            logger.warning("LLM 429: 기본 모델 재시도")
            try:
                return call(self._primary, "primary")
            except LLMError as exc:
                if exc.kind != LLMErrorKind.RATE_LIMITED:
                    raise
        else:
            logger.warning("LLM 429: 대기 시간이 길어 재시도 건너뜀")
        if self._fallback is not None:
            logger.warning("LLM 429: 예비 모델 호출")
            return call(self._fallback, "fallback")
        raise LLMError(LLMErrorKind.RATE_LIMITED, 429)

    def _transient_second(
        self, call: Callable[[LLMClient, Role], str], first: LLMError, begin: float
    ) -> str:
        """일시 오류 뒤 두 번째 시도 (한 번만). 상한 안에 끝날 수 없으면 시작하지 않고 첫 오류를 올린다."""
        client, role = (
            (self._fallback, "fallback")
            if self._fallback is not None
            else (self._primary, "primary")
        )
        delay = self._backoff()
        remaining = (
            self._total_budget
            - (self._clock() - begin)
            - delay
            - _expected_wait(client)
        )
        if remaining < self._call_timeout:
            logger.warning(
                "LLM 일시 오류: 전체 대기 상한(%.0fs)을 넘어 두 번째 시도를 하지 않음",
                self._total_budget,
            )
            raise first
        logger.warning("LLM 일시 오류: %.1fs 뒤 %s 모델로 두 번째 시도", delay, role)
        self._sleep(delay)
        return call(client, role)
