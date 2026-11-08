"""호출 간격 제한 (2026-11-08 결정, 무료 한도 대응).

모델별 분당 한도(예: gemini-3.1-flash-lite RPM 15)보다 낮게 LLM_MAX_RPM(기본 12)을 두고,
호출 사이 간격을 60 ÷ max_rpm 초 이상으로 코드가 지킨다. 여러 요청이 동시에 와도 잠금으로 줄을 세운다.
시계와 sleep은 바꿔 끼울 수 있어 테스트는 실제로 기다리지 않는다.
"""

import threading
import time
from collections.abc import Callable


class MinIntervalLimiter:
    """직전 호출에서 최소 간격이 지날 때까지 기다린다. max_rpm이 None이면 기다리지 않는다."""

    def __init__(
        self,
        max_rpm: int | None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_rpm is not None and max_rpm < 1:
            raise ValueError("max_rpm은 1 이상이어야 합니다.")
        self.interval = 0.0 if max_rpm is None else 60.0 / max_rpm
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> float:
        """필요하면 기다린 뒤 이번 호출 시각을 기록한다. 기다린 초를 돌려준다."""
        with self._lock:
            waited = 0.0
            if self.interval and self._last is not None:
                delay = self._last + self.interval - self._clock()
                if delay > 0:
                    self._sleep(delay)
                    waited = delay
            self._last = self._clock()
            return waited
