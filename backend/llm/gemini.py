"""Gemini API 구현체 (REST, httpx). MVP_SPEC 9절 확정 3·4.

- 엔드포인트: POST {BASE_URL}/models/{model}:generateContent
- 키는 x-goog-api-key 헤더로만 보낸다. URL 쿼리에 넣지 않아 httpx 로그·예외 메시지의 URL에 키가 나오지 않는다.
- JSON 출력: generationConfig.responseMimeType = application/json, responseJsonSchema = 추출 스키마.
- temperature: 기본 0 (CLAUDE.md 3절). LLM_TEMPERATURE를 비우면 보내지 않는다 (llm/config.py).
  공식 문서상 Gemini 3.6 Flash 이후 모델은 이 값을 무시한다 (docs/sources/vs3_report.md 1.4).
- 호출 간격: limiter(ratelimit.py)가 호출 전에 기다린다. 429의 Retry-After(초)는 LLMError에 담는다.
  재시도·예비 모델은 resilience.py가 한다 (이 클래스는 재시도하지 않는다).
- 요청·응답 본문과 키를 로그·예외 메시지에 넣지 않는다. 실패는 LLMError(종류, 상태 코드)로만 알린다.
"""

import json
from typing import Any

import httpx
from pydantic import SecretStr

from llm.client import LLMError, LLMErrorKind, Turn
from llm.ratelimit import MinIntervalLimiter

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT_SECONDS = 60.0
DEFAULT_TEMPERATURE = 0.0


class GeminiClient:
    """LLMClient 구현체. transport는 테스트에서 httpx.MockTransport를 넣는다."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        temperature: float | None = DEFAULT_TEMPERATURE,
        limiter: MinIntervalLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._limiter = limiter
        self._transport = transport
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"GeminiClient(model={self._model!r})"

    @property
    def model(self) -> str:
        return self._model

    def build_body(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> dict[str, Any]:
        """generateContent 요청 본문. temperature가 None이면 넣지 않는다."""
        config: dict[str, Any] = {
            "responseMimeType": "application/json",
            "responseJsonSchema": response_schema,
        }
        if self._temperature is not None:
            config["temperature"] = self._temperature
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": t.role, "parts": [{"text": t.text}]} for t in turns],
            "generationConfig": config,
        }

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        body = self.build_body(
            system=system, turns=turns, response_schema=response_schema
        )
        url = f"{BASE_URL}/models/{self._model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key.get_secret_value(),
        }
        if self._limiter is not None:
            self._limiter.wait()
        try:
            with httpx.Client(
                transport=self._transport, timeout=self._timeout
            ) as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            raise LLMError(LLMErrorKind.TIMEOUT) from None
        except httpx.HTTPError:
            raise LLMError(LLMErrorKind.NETWORK) from None
        if response.status_code == 429:
            raise LLMError(
                LLMErrorKind.RATE_LIMITED,
                429,
                retry_after=parse_retry_after(response.headers.get("retry-after")),
            )
        if response.status_code >= 400:
            raise LLMError(LLMErrorKind.HTTP_ERROR, response.status_code)
        return extract_text(response.content)


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After 헤더의 초 값. 없거나 초 형식이 아니면(HTTP 날짜 등) None."""
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def extract_text(raw: bytes) -> str:
    """응답 본문에서 모델 출력 텍스트를 꺼낸다. 생각(thought) 부분은 뺀다."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise LLMError(LLMErrorKind.BAD_RESPONSE) from None
    if not isinstance(data, dict):
        raise LLMError(LLMErrorKind.BAD_RESPONSE)
    feedback = data.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise LLMError(LLMErrorKind.BLOCKED)
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise LLMError(LLMErrorKind.BAD_RESPONSE)
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    if first.get("finishReason") in {
        "SAFETY",
        "PROHIBITED_CONTENT",
        "BLOCKLIST",
        "SPII",
    }:
        raise LLMError(LLMErrorKind.BLOCKED)
    parts = (first.get("content") or {}).get("parts") or []
    texts = [
        p["text"]
        for p in parts
        if isinstance(p, dict)
        and isinstance(p.get("text"), str)
        and not p.get("thought")
    ]
    if not texts:
        raise LLMError(LLMErrorKind.BAD_RESPONSE)
    return "".join(texts)
