"""계산 라우터 (MVP_SPEC 6절, 8.1 VS2, 12.9 VS4). 로직은 rules/에 두고 여기서는 연결만 한다.

품목은 쿼리 item으로 고른다: 없거나 gym이면 헬스장(GymInput, 지금과 같은 응답), laundry면 세탁(LaundryInput).
요청 본문은 입력 모델 그대로다. GymInput은 strict 모델이라 JSON 모드로 검증한다
(날짜는 ISO 문자열로 받고, 숫자 문자열 "100" 같은 값은 자동 변환하지 않는다).
요청 본문은 로그에 남기지 않는다.
"""

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError

from rules.gym import GymInput, GymResult, calculate_refund
from rules.gym_display import GymDisplay, build_display
from rules.laundry import LaundryInput, LaundryResult, calculate_damage
from rules.laundry_display import (
    LaundryDisplay,
    LaundryItemOption,
    build_laundry_display,
    item_options,
)
from rules.laundry_rule import load_laundry_rule
from rules.loader import load_rule

RULE_ID = "gym_refund"

router = APIRouter(prefix="/api")


class CalculateResponse(BaseModel):
    """계산 결과(엔진 출력 그대로)와 화면 표시 정보."""

    model_config = ConfigDict(frozen=True)

    result: GymResult
    display: GymDisplay


class LaundryCalculateResponse(BaseModel):
    """세탁 계산 결과(엔진 출력 그대로)와 화면 표시 정보."""

    model_config = ConfigDict(frozen=True)

    result: LaundryResult
    display: LaundryDisplay


def validate_body[T: BaseModel](model: type[T], body: bytes) -> T:
    """JSON 모드 검증. 오류에는 위치·종류만 남긴다 (입력값은 api/errors.py가 뺀다)."""
    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        errors = exc.errors(
            include_input=False, include_context=False, include_url=False
        )
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in errors]
        ) from None


@router.post(
    "/calculate",
    response_model=CalculateResponse | LaundryCalculateResponse,
    description="item=gym(기본)이면 본문은 GymInput, item=laundry면 LaundryInput"
    " (x-laundry-request-schema).",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": GymInput.model_json_schema()}},
        },
        "x-laundry-request-schema": LaundryInput.model_json_schema(),
    },
)
async def calculate(
    request: Request, item: Literal["gym", "laundry"] = "gym"
) -> CalculateResponse | LaundryCalculateResponse:
    """확정된 입력으로 기준 금액을 계산하고 표시 정보를 붙인다."""
    body = await request.body()
    if item == "laundry":
        laundry = validate_body(LaundryInput, body)
        lrule = load_laundry_rule()
        lresult = calculate_damage(laundry, lrule)
        return LaundryCalculateResponse(
            result=lresult, display=build_laundry_display(lresult, lrule)
        )
    inp = validate_body(GymInput, body)
    rule = load_rule(RULE_ID)
    result = calculate_refund(inp, rule)
    return CalculateResponse(result=result, display=build_display(result, rule))


@router.get("/laundry/items", response_model=list[LaundryItemOption])
def laundry_items() -> list[LaundryItemOption]:
    """세탁 품목·소재·용도 선택지 (평균 내용연수표 행 그대로, 내용연수 숫자 없음)."""
    return item_options(load_laundry_rule())
