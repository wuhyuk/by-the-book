"""헬스장 환급 계산 라우터 (MVP_SPEC 6절, 8.1 VS2). 로직은 rules/에 두고 여기서는 연결만 한다.

요청 본문은 GymInput 그대로다. GymInput은 strict 모델이라 JSON 모드로 검증한다
(날짜는 ISO 문자열로 받고, 숫자 문자열 "100" 같은 값은 자동 변환하지 않는다).
요청 본문은 로그에 남기지 않는다.
"""

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError

from rules.gym import GymInput, GymResult, calculate_refund
from rules.gym_display import GymDisplay, build_display
from rules.loader import load_rule

RULE_ID = "gym_refund"

router = APIRouter(prefix="/api")


class CalculateResponse(BaseModel):
    """계산 결과(엔진 출력 그대로)와 화면 표시 정보."""

    model_config = ConfigDict(frozen=True)

    result: GymResult
    display: GymDisplay


@router.post(
    "/calculate",
    response_model=CalculateResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": GymInput.model_json_schema()}},
        }
    },
)
async def calculate(request: Request) -> CalculateResponse:
    """확정된 입력으로 기준 금액을 계산하고 표시 정보를 붙인다."""
    body = await request.body()
    try:
        inp = GymInput.model_validate_json(body)
    except ValidationError as exc:
        errors = exc.errors(
            include_input=False, include_context=False, include_url=False
        )
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in errors]
        ) from None
    rule = load_rule(RULE_ID)
    result = calculate_refund(inp, rule)
    return CalculateResponse(result=result, display=build_display(result, rule))
