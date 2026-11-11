"""429 처리: 1회 재시도와 예비 모델 1회 (2026-11-08 결정).

순서 (무한 재시도 없음, 호출은 최대 3번):
1. 기본 모델 호출
2. 429면 Retry-After를 따라 기다린 뒤 기본 모델 1회 재시도.
   Retry-After가 MAX_RETRY_WAIT보다 길면 기다리지 않고 재시도를 건너뛴다 (요청을 오래 붙잡지 않는다).
   Retry-After가 없으면 기본 모델의 호출 간격 제한(ratelimit.py)만큼 기다린 뒤 재시도한다.
3. 그래도 429이고 예비 모델(LLM_FALLBACK_MODEL)이 있으면 예비 모델 1회.
4. 그래도 실패하면 LLMError(RATE_LIMITED). API는 "잠시 후 다시 시도하거나 폼에 직접 입력" 안내로 끝낸다.
429가 아닌 실패는 재시도하지 않고 그대로 올린다. 로그에는 단계 이름만 남긴다 (입력·키 없음).
counter(llm/usage.py)가 있으면 실제로 보내는 호출마다(재시도·예비 모델 포함) 호출 직전에 1회씩 센다.
하루 상한에 도달하면 호출을 보내지 않고 LLMError(DAILY_LIMIT)를 그대로 올린다 (재시도하지 않음).
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from llm.client import LLMClient, LLMError, LLMErrorKind, Turn
from llm.usage import DailyCallCounter

logger = logging.getLogger("by_the_book.llm")

MAX_RETRY_WAIT = 20.0


class RetryingClient:
    """LLMClient를 감싸 429만 다룬다. 제공자와 무관하다."""

    def __init__(
        self,
        primary: LLMClient,
        fallback: LLMClient | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_retry_wait: float = MAX_RETRY_WAIT,
        counter: DailyCallCounter | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._sleep = sleep
        self._max_retry_wait = max_retry_wait
        self._counter = counter

    def __repr__(self) -> str:
        return f"RetryingClient(primary={self._primary!r}, fallback={self._fallback!r})"

    @property
    def model(self) -> str:
        return self._primary.model

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        def call(client: LLMClient) -> str:
            if self._counter is not None:
                self._counter.acquire()
            return client.generate_json(
                system=system, turns=turns, response_schema=response_schema
            )

        try:
            return call(self._primary)
        except LLMError as exc:
            if exc.kind != LLMErrorKind.RATE_LIMITED:
                raise
            wait = exc.retry_after
        if wait is None or wait <= self._max_retry_wait:
            if wait:
                self._sleep(wait)
            logger.warning("LLM 429: 기본 모델 재시도")
            try:
                return call(self._primary)
            except LLMError as exc:
                if exc.kind != LLMErrorKind.RATE_LIMITED:
                    raise
        else:
            logger.warning("LLM 429: 대기 시간이 길어 재시도 건너뜀")
        if self._fallback is not None:
            logger.warning("LLM 429: 예비 모델 호출")
            return call(self._fallback)
        raise LLMError(LLMErrorKind.RATE_LIMITED, 429)
