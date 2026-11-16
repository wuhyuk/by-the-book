"""자연어 분석 라우터 (MVP_SPEC 6절 /api/analyze, 8.1 VS3, 12.9 VS4). 로직은 llm/·rules/에 두고 연결만 한다.

품목은 쿼리 item으로 고른다: 없거나 gym이면 헬스장 추출(지금과 같음), laundry면 세탁 추출.

순서 (2026-11-12 결정): 마스킹 → 규칙 가드레일(외부 호출 없음, 걸리면 ❔, 호출 수에 넣지 않음)
→ 분석 스위치(ANALYZE_ENABLED=false면 ANALYZE_DISABLED) → 하루 상한 확인(ANALYZE_DAILY_LIMIT)
→ LLM 추출·근거 확인 → LLM 판정 가드레일. 분석이 꺼져 있어도 승패 질문은 ❔로 답한다. 하루 호출 수는 실제로 보낸 호출만 센다 (재시도·예비 모델 포함, llm/usage.py).
두 스위치는 /api/analyze에만 걸린다. /api/calculate·/api/guide는 영향을 받지 않는다.
- 입력 문장·마스킹한 문장·LLM 응답은 저장·로그하지 않는다. 로그에는 실패 종류만 남긴다.
- 응답의 fields는 화면 폼을 미리 채우는 값이다. 계산은 사용자가 폼에서 확인한 뒤 /api/calculate가 한다.
- 기능 플래그 rag(MVP_SPEC 15.2, 2026-11-16): 가드레일·스위치·하루 상한을 통과한 뒤 마스킹한 문장으로 조항을
  검색하고(rag/search.py), 기존 추출 호출 한 번에 후보를 넣는다. 응답에 clauses{candidates, selected}를 더한다.
  항목은 저장된 규칙 JSON 값(ID·제목·출처·기준일·확인 여부·본문 앞부분)뿐이고 LLM이 쓴 문장은 넣지 않는다.
  꺼져 있으면 프롬프트·스키마·응답이 지금과 같다 (clauses 키 없음).
- 기능 플래그 llm_resilience(MVP_SPEC 16절, 2026-11-16): 일시 오류(500·502·503·504, 시간 초과, 연결 실패)면
  두 번째 시도를 한 번 한다 (llm/resilience.py). 호출 하나의 시간 제한은 LLM_TIMEOUT_SECONDS(기본 20초).
  모든 시도가 일시 오류로 끝나면 502 문구를 BUSY_MESSAGE로 바꾼다 (code는 그대로). 꺼져 있으면 지금과 같다.
- 기능 플래그 date_year_infer(2026-11-16, 헬스장만): 근거 확인 뒤 연도 없는 종료일·도달일을 코드 규칙으로 보완하고
  extraction.year_inferred에 연도를 적는다 (llm/date_infer.py). 꺼져 있으면 응답이 지금과 같다.
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
from llm.gemini import TIMEOUT_SECONDS as LEGACY_TIMEOUT_SECONDS
from llm.gemini import GeminiClient
from llm.guardrail import detect_judgment_request
from llm.laundry_extraction import analyze_laundry_text
from llm.masking import mask_pii
from llm.ratelimit import MinIntervalLimiter
from llm.resilience import RetryingClient, is_transient
from llm.usage import DailyCallCounter
from rag.search import Candidate, search
from rules.gym_display import GuardrailDisplay, judgment_guardrail_display
from rules.offer_gap import optional_field
from rules.sources import find_clause

logger = logging.getLogger("by_the_book.api")

MAX_TEXT_LENGTH = 2000

NOT_CONFIGURED_MESSAGE = (
    "지금은 문장 분석을 쓸 수 없습니다. 아래 입력 폼에 직접 입력해 주세요."
)
RATE_LIMITED_MESSAGE = "요청이 많아 문장을 분석하지 못했습니다. 잠시 뒤 다시 시도하거나 아래 입력 폼에 직접 입력해 주세요."
FAILED_MESSAGE = "문장을 분석하지 못했습니다. 아래 입력 폼에 직접 입력해 주세요."
# llm_resilience 켜짐 + 일시 오류로 끝난 502 (2026-11-16 승인)
BUSY_MESSAGE = "AI 서비스가 일시적으로 바쁩니다. 잠시 후 다시 시도하거나 아래 입력 폼에 직접 입력해 주세요."
DISABLED_CODE = "ANALYZE_DISABLED"
DISABLED_MESSAGE = "문장 분석은 지금 쓸 수 없습니다. 아래 입력 폼으로 입력해 주세요"
DAILY_LIMIT_CODE = "ANALYZE_DAILY_LIMIT"
DAILY_LIMIT_MESSAGE = (
    "오늘 쓸 수 있는 문장 분석 횟수를 모두 사용했습니다. 아래 입력 폼은 계속 사용할 수 있고, "
    "한국시간 자정 이후 다시 분석할 수 있습니다."
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


RAG_FEATURE = "rag"
RESILIENCE_FEATURE = "llm_resilience"
YEAR_INFER_FEATURE = "date_year_infer"
RAG_K = 5


class ClauseItem(BaseModel):
    """조항 후보 한 줄. 값은 모두 규칙 JSON에 저장된 것이다 (LLM이 쓴 문장 없음)."""

    model_config = ConfigDict(frozen=True)

    clause_id: str
    title: str
    source_name: str
    retrieved_at: str
    verified: bool
    user_checked: bool | None
    excerpt: str


class ClauseSuggestions(BaseModel):
    """자동 검색 후보와 그중 LLM이 고른 조항 (후보 밖 ID·중복은 버린 뒤). 금액 계산에 쓰지 않는다."""

    model_config = ConfigDict(frozen=True)

    candidates: list[ClauseItem]
    selected: list[ClauseItem]


class AnalyzeResponse(BaseModel):
    """status=extracted면 extraction, status=guardrail이면 guardrail이 있다."""

    model_config = ConfigDict(frozen=True)

    status: Literal["extracted", "guardrail"]
    pii_masked: bool
    extraction: AnalyzeResult | None
    guardrail: GuardrailDisplay | None
    # 기능 플래그 rag가 켜져 있고 추출했을 때만 (MVP_SPEC 15.2). 없으면 응답에서 빠진다.
    clauses: ClauseSuggestions | None = optional_field()


def _clause_item(c: Candidate) -> ClauseItem:
    found = find_clause(c.clause_id)
    assert found is not None  # 검색 대상과 조회 색인은 같은 규칙 JSON에서 만든다
    return ClauseItem(
        clause_id=c.clause_id,
        title=c.title,
        source_name=found.source.name,
        retrieved_at=found.retrieved_at,
        verified=found.verified,
        user_checked=found.user_checked,
        excerpt=c.excerpt,
    )


def clause_suggestions(
    candidates: list[Candidate], selected: list[str] | None
) -> ClauseSuggestions:
    items = [_clause_item(c) for c in candidates]
    by_id = {i.clause_id: i for i in items}
    return ClauseSuggestions(
        candidates=items, selected=[by_id[i] for i in selected or [] if i in by_id]
    )


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
    llm_resilience가 켜져 있으면 일시 오류 재시도를 켜고 호출 시간 제한을 LLM_TIMEOUT_SECONDS로 둔다.
    꺼져 있으면 시간 제한 60초, 429만 다룬다 (변경 전과 같다). 설정은 프로세스 시작 때 한 번 읽는다.
    """
    s = load_settings()
    resilient = RESILIENCE_FEATURE in app_settings().enabled_features
    timeout = s.timeout_seconds if resilient else LEGACY_TIMEOUT_SECONDS

    def gemini(model: str) -> GeminiClient:
        return GeminiClient(
            api_key=s.api_key,
            model=model,
            temperature=s.temperature,
            limiter=MinIntervalLimiter(s.max_rpm),
            timeout=timeout,
        )

    fallback = gemini(s.fallback_model) if s.fallback_model else None
    return RetryingClient(
        gemini(s.model),
        fallback,
        counter=daily_counter(),
        transient_retry=resilient,
        call_timeout=timeout,
    )


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
    if not settings.analyze_enabled:
        return _error(503, DISABLED_MESSAGE, DISABLED_CODE)
    if counter.exhausted():
        return _error(429, DAILY_LIMIT_MESSAGE, DAILY_LIMIT_CODE)
    try:
        client = provider()
    except LLMConfigError:
        logger.warning("LLM 설정 없음")
        return _error(503, NOT_CONFIGURED_MESSAGE, "not_configured")
    rag = RAG_FEATURE in settings.enabled_features
    # 검색 입력은 마스킹한 문장만 쓴다 (저장·로그하지 않음)
    candidates = search(masked, item, RAG_K) if rag else []
    try:
        if item == "laundry":
            result = analyze_laundry_text(masked, client, candidates or None)
        else:
            infer = YEAR_INFER_FEATURE in settings.enabled_features
            result = analyze_text(masked, client, candidates or None, infer_year=infer)
    except LLMError as exc:
        logger.warning(
            "LLM 호출 실패: %s (status=%s)",
            exc.kind.value,
            exc.status if exc.status is not None else "-",
        )
        if exc.kind == LLMErrorKind.DAILY_LIMIT:
            return _error(429, DAILY_LIMIT_MESSAGE, DAILY_LIMIT_CODE)
        if exc.kind == LLMErrorKind.RATE_LIMITED:
            return _error(429, RATE_LIMITED_MESSAGE, exc.kind.value)
        busy = RESILIENCE_FEATURE in settings.enabled_features and is_transient(exc)
        return _error(502, BUSY_MESSAGE if busy else FAILED_MESSAGE, exc.kind.value)
    if result.judgment_requested:
        return guardrail
    return AnalyzeResponse(
        status="extracted",
        pii_masked=pii_masked,
        extraction=result,
        guardrail=None,
        clauses=(
            clause_suggestions(candidates, result.selected_clause_ids) if rag else None
        ),
    )
