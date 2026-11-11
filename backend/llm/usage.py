"""하루 호출 카운터 (2026-11-11 결정, 무료 한도 RPD 대응).

- Gemini로 실제로 보내는 호출만 센다. 재시도와 예비 모델 호출도 각각 1회로 센다 (llm/resilience.py가
  호출 직전에 acquire를 부른다). 규칙 가드레일에 걸려 호출하지 않은 요청은 세지 않는다.
- 날짜는 한국 표준시(KST, UTC+9, 서머타임 없음) 기준이다. 날짜가 바뀌면 0부터 다시 센다.
- 프로세스 메모리에만 둔다. 서버를 다시 시작하면 0으로 초기화되고, 프로세스가 여럿이면 따로 센다.
- 상한에 도달하면 호출을 보내지 않고 LLMError(DAILY_LIMIT)를 올린다. 입력·키는 다루지 않는다.
"""

import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from llm.client import LLMError, LLMErrorKind

KST = timezone(timedelta(hours=9), "KST")


def now_kst() -> datetime:
    return datetime.now(KST)


class DailyCallCounter:
    """KST 날짜별 호출 수. limit이 0이면 호출을 하나도 허용하지 않는다."""

    def __init__(self, limit: int, *, now: Callable[[], datetime] = now_kst) -> None:
        if limit < 0:
            raise ValueError("limit은 0 이상이어야 합니다.")
        self.limit = limit
        self._now = now
        self._day: date | None = None
        self._count = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        today = self._now().astimezone(KST).date()
        if today != self._day:
            self._day = today
            self._count = 0

    @property
    def count(self) -> int:
        """오늘(KST) 센 호출 수."""
        with self._lock:
            self._roll()
            return self._count

    def exhausted(self) -> bool:
        """오늘 상한에 도달했는지."""
        with self._lock:
            self._roll()
            return self._count >= self.limit

    def acquire(self) -> None:
        """호출 1회를 센다. 상한에 도달했으면 세지 않고 LLMError(DAILY_LIMIT)."""
        with self._lock:
            self._roll()
            if self._count >= self.limit:
                raise LLMError(LLMErrorKind.DAILY_LIMIT)
            self._count += 1
