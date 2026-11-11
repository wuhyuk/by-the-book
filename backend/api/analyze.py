"""자연어 분석 라우터 (MVP_SPEC 6절 /api/analyze, 8.1 VS3, 12.9 VS4). 로직은 llm/·rules/에 두고 연결만 한다.

품목은 쿼리 item으로 고른다: 없거나 gym이면 헬스장 추출(지금과 같음), laundry면 세탁 추출.

순서: 분석 스위치(ANALYZE_ENABLED=false면 바로 ANALYZE_DISABLED) → 마스킹 → 규칙 가드레일(걸리면
LLM을 부르지 않고 ❔, 호출 수에 넣지 않음) → 하루 상한 확인(ANALYZE_DAILY_LIMIT) → LLM 추출·근거 확인
→ LLM 판정 가드레일. 하루 호출 수는 실제로 보낸 호출만 센다 (재시도·예비 모델 포함, llm/usage.py).
두 스위치는 /api/analyze에만 걸린다. /api/calculate·/api/guide는 영향을 받지 않는다.
- 입력 문장·마스킹한 문장·LLM 응답은 저장·로그하지 않는다. 로그에는 실패 종류만 남긴다.
- 응답의 fields는 화면 폼을 미리 채우는 값이다. 계산은 사용자가 폼에서 확인한 뒤 /api/calculate가 한다.
"""

import logging
from collections.abc import Callable
from functools import cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from api.settings import AppSettings, app_settings, get_app_settings
from llm.client import LLMClient, LLMError, LLMErrorKind
from llm.config import LLMConfigError, load_settings
from llm.extraction import AnalyzeResult, analyze_text
from llm.gemini import GeminiClient
from llm.guardrail import detect_judgment_request
from llm.laundry_extraction import analyze_laundry_text
from llm.masking import mask_pii
from llm.ratelimit import MinIntervalLimiter
from llm.resilience import RetryingClient
from llm.usage import DailyCallCounter
from rules.gym_display import GuardrailDisplay, judgment_guardrail_display

logger = logging.getLogger("by_the_book.api")

MAX_TEXT_LENGTH = 2000

NOT_CONFIGURED_MESSAGE = (
    "지금은 문장 분석을 쓸 수 없습니다. 아래 입력 폼에 직접 입력해 주세요."
)
RATE_LIMITED_MESSAGE = "요청이 많아 문장을 분석하지 못했습니다. 잠시 뒤 다시 시도하거나 아래 입력 폼에 직접 입력해 주세요."
FAILED_MESSAGE = "문장을 분석하지 못했습니다. 아래 입력 폼에 직접 입력해 주세요."
DISABLED_CODE = "ANALYZE_DISABLED"
DISABLED_MESSAGE = "문장 분석은 지금 쓸 수 없습니다. 아래 입력 폼으로 입력해 주세요"
DAILY_LIMIT_CODE = "ANALYZE_DAILY_LIMIT"
DAILY_LIMIT_MESSAGE = (
    "오늘 쓸 수 있는 문장 분석 횟수를 모두 써서 지금은 문장 분석을 쓸 수 없습니다. "
    "아래 입력 폼으로 입력해 주세요"
)

router = APIRouter(prefix="/api")


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_TEXT_LENGTH
        ),
    ]


class AnalyzeResponse(BaseModel):
    """status=extracted면 extraction, status=guardrail이면 guardrail이 있다."""

    model_config = ConfigDict(frozen=True)

    status: Literal["extracted", "guardrail"]
    pii_masked: bool
    extraction: AnalyzeResult | None
    guardrail: GuardrailDisplay | None


@cache
def daily_counter() -> DailyCallCounter:
    """프로세스 하나에 카운터 하나 (재시작하면 0부터)."""
    return DailyCallCounter(app_settings().daily_analyze_limit)


def get_daily_counter() -> DailyCallCounter:
    """FastAPI 의존성. 테스트에서 바꿔 끼운다."""
    return daily_counter()


@cache
def default_client() -> LLMClient:
    """설정으로 구현체를 만든다. 설정이 없으면 LLMConfigError.

    기본 모델과 예비 모델(LLM_FALLBACK_MODEL)은 한도가 모델마다 따로라 간격 제한도 따로 둔다.
    429는 RetryingClient가 1회 재시도 → 예비 모델 1회로 처리한다 (llm/resilience.py).
    하루 호출 수는 RetryingClient가 호출마다 센다 (daily_counter).
    """
    s = load_settings()

    def gemini(model: str) -> GeminiClient:
        return GeminiClient(
            api_key=s.api_key,
            model=model,
            temperature=s.temperature,
            limiter=MinIntervalLimiter(s.max_rpm),
        )

    fallback = gemini(s.fallback_model) if s.fallback_model else None
    return RetryingClient(gemini(s.model), fallback, counter=daily_counter())


def get_client_provider() -> Callable[[], LLMClient]:
    """LLM 구현체를 늦게 만든다 (규칙 가드레일에 걸리면 설정 없이도 응답). 테스트에서 바꿔 끼운다."""
    return default_client


def _error(status: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message, "code": code})


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    req: AnalyzeRequest,
    provider: Annotated[Callable[[], LLMClient], Depends(get_client_provider)],
    settings: Annotated[AppSettings, Depends(get_app_settings)],
    counter: Annotated[DailyCallCounter, Depends(get_daily_counter)],
    item: Literal["gym", "laundry"] = "gym",
) -> AnalyzeResponse | JSONResponse:
    """문장 → 폼에 채울 값(근거 확인된 값만)과 되물을 항목. 승패·법적 효력 질문이면 ❔."""
    if not settings.analyze_enabled:
        return _error(503, DISABLED_MESSAGE, DISABLED_CODE)
    masked = mask_pii(req.text)
    pii_masked = masked != req.text
    guardrail = AnalyzeResponse(
        status="guardrail",
        pii_masked=pii_masked,
        extraction=None,
        guardrail=judgment_guardrail_display(),
    )
    if detect_judgment_request(masked):
        return guardrail
    if counter.exhausted():
        return _error(429, DAILY_LIMIT_MESSAGE, DAILY_LIMIT_CODE)
    try:
        client = provider()
    except LLMConfigError:
        logger.warning("LLM 설정 없음")
        return _error(503, NOT_CONFIGURED_MESSAGE, "not_configured")
    try:
        extract = analyze_laundry_text if item == "laundry" else analyze_text
        result = extract(masked, client)
    except LLMError as exc:
        logger.warning("LLM 호출 실패: %s", exc.kind.value)
        if exc.kind == LLMErrorKind.DAILY_LIMIT:
            return _error(429, DAILY_LIMIT_MESSAGE, DAILY_LIMIT_CODE)
        if exc.kind == LLMErrorKind.RATE_LIMITED:
            return _error(429, RATE_LIMITED_MESSAGE, exc.kind.value)
        return _error(502, FAILED_MESSAGE, exc.kind.value)
    if result.judgment_requested:
        return guardrail
    return AnalyzeResponse(
        status="extracted", pii_masked=pii_masked, extraction=result, guardrail=None
    )
