"""Gemini 구현체 테스트 (httpx.MockTransport, 가짜 키). 실제 API를 부르지 않는다."""

import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from llm.client import LLMError, LLMErrorKind, Turn
from llm.gemini import GeminiClient, extract_text

FAKE_KEY = "FAKE-KEY-ZQX-1111"
SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def ok_body(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def make(handler: Any) -> GeminiClient:
    return GeminiClient(
        api_key=SecretStr(FAKE_KEY),
        model="model-x",
        transport=httpx.MockTransport(handler),
    )


def call(client: GeminiClient) -> str:
    return client.generate_json(
        system="시스템",
        turns=[Turn("user", "예시 입력"), Turn("model", "{}"), Turn("user", "입력")],
        response_schema=SCHEMA,
    )


def test_request_shape() -> None:
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["headers"] = dict(req.headers)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=ok_body('{"a": 1}'))

    assert call(make(handler)) == '{"a": 1}'
    assert seen["url"].endswith("/v1beta/models/model-x:generateContent")
    assert FAKE_KEY not in seen["url"]  # 키는 URL이 아니라 헤더로
    assert seen["headers"]["x-goog-api-key"] == FAKE_KEY
    body = seen["body"]
    assert body["systemInstruction"] == {"parts": [{"text": "시스템"}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    cfg = body["generationConfig"]
    assert cfg["temperature"] == 0
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["responseJsonSchema"] == SCHEMA


def test_repr_hides_key() -> None:
    client = make(lambda req: httpx.Response(200, json=ok_body("{}")))
    assert FAKE_KEY not in repr(client)
    assert FAKE_KEY not in str(client.__dict__)


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (429, LLMErrorKind.RATE_LIMITED),
        (400, LLMErrorKind.HTTP_ERROR),
        (403, LLMErrorKind.HTTP_ERROR),
        (500, LLMErrorKind.HTTP_ERROR),
    ],
)
def test_http_errors(
    status: int, kind: LLMErrorKind, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": f"echo {FAKE_KEY}"}})

    with pytest.raises(LLMError) as exc:
        call(make(handler))
    assert exc.value.kind == kind
    assert exc.value.status == status
    assert FAKE_KEY not in str(exc.value)
    assert exc.value.__cause__ is None
    assert FAKE_KEY not in caplog.text
    assert "입력" not in caplog.text


def test_timeout_and_network() -> None:
    def timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=req)

    def network(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=req)

    with pytest.raises(LLMError) as exc:
        call(make(timeout))
    assert exc.value.kind == LLMErrorKind.TIMEOUT
    with pytest.raises(LLMError) as exc:
        call(make(network))
    assert exc.value.kind == LLMErrorKind.NETWORK
    assert exc.value.__cause__ is None


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        (b"not json", LLMErrorKind.BAD_RESPONSE),
        (b"[]", LLMErrorKind.BAD_RESPONSE),
        (b'{"candidates": []}', LLMErrorKind.BAD_RESPONSE),
        (b'{"promptFeedback": {"blockReason": "SAFETY"}}', LLMErrorKind.BLOCKED),
        (b'{"candidates": [{"finishReason": "SAFETY"}]}', LLMErrorKind.BLOCKED),
        (b'{"candidates": [{"content": {"parts": []}}]}', LLMErrorKind.BAD_RESPONSE),
    ],
)
def test_extract_text_errors(raw: bytes, kind: LLMErrorKind) -> None:
    with pytest.raises(LLMError) as exc:
        extract_text(raw)
    assert exc.value.kind == kind


def test_extract_text_skips_thoughts() -> None:
    raw = json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "생각", "thought": True},
                            {"text": '{"a":'},
                            {"text": " 1}"},
                        ]
                    }
                }
            ]
        }
    ).encode()
    assert extract_text(raw) == '{"a": 1}'
