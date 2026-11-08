"""LLM 호출 인터페이스 (MVP_SPEC 9절 확정 3).

제공자별 구현체(gemini.py)는 이 인터페이스만 맞춘다. 프롬프트·스키마·검증은 제공자와 무관하게
extraction.py에 두므로, 제공자 교체는 구현체 교체로 끝난다.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol


class LLMErrorKind(StrEnum):
    """호출 실패 종류. API는 종류별 고정 문구로만 응답한다."""

    RATE_LIMITED = "rate_limited"  # 429
    TIMEOUT = "timeout"
    NETWORK = "network"
    HTTP_ERROR = "http_error"  # 429 외 4xx·5xx
    BAD_RESPONSE = "bad_response"  # 응답이 JSON이 아니거나 스키마와 다름
    BLOCKED = "blocked"  # 제공자가 응답을 막음 (안전 필터 등)


class LLMError(Exception):
    """LLM 호출 실패. 메시지에 입력 원문·응답 본문·키를 넣지 않는다 (종류와 상태 코드만)."""

    def __init__(
        self,
        kind: LLMErrorKind,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.kind = kind
        self.status = status
        self.retry_after = retry_after  # 429 응답의 Retry-After(초). 없으면 None
        super().__init__(
            f"LLM 호출 실패: {kind.value}" + (f" ({status})" if status else "")
        )


@dataclass(frozen=True)
class Turn:
    """대화 한 턴. role은 사용자 입력(user) 또는 모델 응답 예시(model)."""

    role: Literal["user", "model"]
    text: str


class LLMClient(Protocol):
    """텍스트 → JSON 문자열. 구현체는 temperature 0과 JSON 출력 강제를 지킨다."""

    @property
    def model(self) -> str: ...

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        """system 지시와 대화 턴을 보내고 response_schema에 맞춘 JSON 문자열을 돌려준다."""
        ...
