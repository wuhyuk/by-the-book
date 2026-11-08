"""POST /api/analyze 테스트 (가짜 LLMClient, 가짜 키). 실제 API·실제 backend/.env를 쓰지 않는다.

확인: 마스킹 후 호출, 규칙 가드레일은 LLM 없이 ❔, 근거 확인된 값만 응답, 오류는 고정 문구,
입력 문장이 로그·오류 응답에 나오지 않음 (CLAUDE.md 절대 규칙 4·6).
"""

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_llm_extraction import raw

from api.analyze import (
    FAILED_MESSAGE,
    NOT_CONFIGURED_MESSAGE,
    RATE_LIMITED_MESSAGE,
    get_client_provider,
)
from llm.client import LLMClient, LLMError, LLMErrorKind, Turn
from llm.config import LLMConfigError
from main import app
from rules.badge import Badge

client = TestClient(app)

MARK = "표지문장ZQX"
PHONE = "010-9876-5432"
TEXT = (
    f"{MARK} 헬스장 1년권을 2026-01-01부터 2026-12-31까지 120만원에 결제했어요. "
    f"연락처 {PHONE}"
)


@dataclass
class FakeClient:
    reply: str | None = None
    error: LLMError | None = None
    model: str = "fake-model"
    received: list[str] = field(default_factory=list)

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.received.append(turns[-1].text)
        if self.error:
            raise self.error
        assert self.reply is not None
        return self.reply


@pytest.fixture
def use() -> Iterator[Callable[[Any], None]]:
    def _use(provider: Callable[[], LLMClient]) -> None:
        app.dependency_overrides[get_client_provider] = lambda: provider

    yield _use
    app.dependency_overrides.clear()


@pytest.fixture
def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


def post(text: str = TEXT) -> Any:
    return client.post("/api/analyze", json={"text": text})


def test_extracts_grounded_values_and_masks(use: Any, logs: Any) -> None:
    fake = FakeClient(
        json.dumps(
            raw(
                {
                    "industry": ("fitness", "헬스장 1년권"),
                    "contract_type": ("period", "헬스장 1년권"),
                    "total_contract_amount": (1_200_000, "120만원에 결제했어요"),
                    "start_date": ("2026-01-01", "2026-01-01부터"),
                    "paid_amount": (1_000_000, "120만원에 결제했어요"),  # 근거와 다름
                }
            )
        )
    )
    use(lambda: fake)
    r = post()
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "extracted"
    assert data["pii_masked"] is True
    ext = data["extraction"]
    assert ext["fields"] == {
        "industry": "fitness",
        "contract_type": "period",
        "total_contract_amount": 1_200_000,
        "start_date": "2026-01-01",
    }
    assert ext["unverified"] == ["paid_amount"]
    assert ext["missing"] == [
        "termination_cause",
        "paid_amount",
        "end_date",
        "notice_date",
    ]
    assert PHONE not in fake.received[0]  # 마스킹 후 호출
    assert "[전화번호]" in fake.received[0]
    assert MARK not in logs.text and PHONE not in logs.text


def test_rule_guardrail_skips_llm(use: Any) -> None:
    def never() -> LLMClient:
        raise AssertionError("LLM을 부르면 안 된다")

    use(never)
    r = post("헬스장 120만원 냈는데 소송하면 이길 수 있을까요?")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "guardrail"
    assert data["extraction"] is None
    g = data["guardrail"]
    assert g["badge"] == Badge.UNDETERMINABLE.value
    assert g["screen_line"]["code"] == "JUDGMENT_REQUESTED"
    assert "1372" in g["consult"]["channels"]


def test_rule_guardrail_works_without_llm_settings(use: Any) -> None:
    def not_configured() -> LLMClient:
        raise LLMConfigError("LLM 설정이 비어 있습니다: LLM_API_KEY")

    use(not_configured)
    assert post("내용증명 써 주세요").json()["status"] == "guardrail"
    r = post()
    assert r.status_code == 503
    assert r.json() == {"message": NOT_CONFIGURED_MESSAGE, "code": "not_configured"}


def test_llm_judgment_with_evidence_is_guardrail(use: Any) -> None:
    text = "헬스장 위약금이 너무 많은데 업체 말이 맞는 건지 따져 보고 싶어요"
    fake = FakeClient(json.dumps(raw({}, judgment="업체 말이 맞는 건지 따져 보고")))
    use(lambda: fake)
    data = post(text).json()
    assert data["status"] == "guardrail"
    assert data["guardrail"]["badge"] == Badge.UNDETERMINABLE.value


@pytest.mark.parametrize(
    ("kind", "status", "message"),
    [
        (LLMErrorKind.RATE_LIMITED, 429, RATE_LIMITED_MESSAGE),
        (LLMErrorKind.TIMEOUT, 502, FAILED_MESSAGE),
        (LLMErrorKind.HTTP_ERROR, 502, FAILED_MESSAGE),
        (LLMErrorKind.BAD_RESPONSE, 502, FAILED_MESSAGE),
        (LLMErrorKind.BLOCKED, 502, FAILED_MESSAGE),
    ],
)
def test_llm_errors_fixed_messages(
    use: Any, logs: Any, kind: LLMErrorKind, status: int, message: str
) -> None:
    use(lambda: FakeClient(error=LLMError(kind)))
    r = post()
    assert r.status_code == status
    assert r.json() == {"message": message, "code": kind.value}
    assert MARK not in r.text and MARK not in logs.text
    assert PHONE not in logs.text


def test_bad_llm_json_is_502(use: Any) -> None:
    use(lambda: FakeClient("not json"))
    r = post()
    assert r.status_code == 502
    assert MARK not in r.text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": ""},
        {"text": "   "},
        {"text": "가" * 2001},
        {"text": MARK, "extra": 1},
        {"text": 123},
    ],
)
def test_invalid_request_422_without_input(use: Any, body: dict[str, Any]) -> None:
    use(lambda: FakeClient(json.dumps(raw({}))))
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 422
    assert MARK not in r.text
    assert "가가가" not in r.text


def test_openapi_lists_analyze() -> None:
    assert "/api/analyze" in app.openapi()["paths"]
