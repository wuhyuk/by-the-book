"""계산 라우터 (MVP_SPEC 6절, 8.1 VS2, 12.9 VS4). 로직은 rules/에 두고 여기서는 연결만 한다.

품목은 쿼리 item으로 고른다: 없거나 gym이면 헬스장(GymInput, 지금과 같은 응답), laundry면 세탁(LaundryInput).
요청 본문은 입력 모델 그대로다. GymInput은 strict 모델이라 JSON 모드로 검증한다
(날짜는 ISO 문자열로 받고, 숫자 문자열 "100" 같은 값은 자동 변환하지 않는다).
요청 본문은 로그에 남기지 않는다.
세탁 복원 기능(R2 set_partial 등)은 운영 설정 ENABLED_FEATURES로 켠다 (api/settings.py, 2026-11-15).
가전(item=appliance, MVP_SPEC 13절)은 ENABLED_FEATURES에 appliance가 있을 때만 받는다. 꺼져 있으면
지금과 같은 응답(item 쿼리 literal_error 422, /api/appliance/items 404)을 돌려준다.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from api.settings import AppSettings, get_app_settings
from api.spa import NOT_FOUND_MESSAGE
from rules.appliance import ApplianceInput, ApplianceResult, calculate_appliance
from rules.appliance_display import (
    ApplianceDisplay,
    ApplianceItemOption,
    build_appliance_display,
)
from rules.appliance_display import item_options as appliance_options
from rules.appliance_rule import load_appliance_rule
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


class ApplianceCalculateResponse(BaseModel):
    """가전 계산 결과(엔진 출력 그대로)와 화면 표시 정보."""

    model_config = ConfigDict(frozen=True)

    result: ApplianceResult
    display: ApplianceDisplay


APPLIANCE = "appliance"


def require_appliance(settings: AppSettings) -> None:
    """가전이 꺼져 있으면 item 쿼리가 허용 목록 밖일 때와 같은 422를 낸다 (지금 응답과 같게)."""
    if APPLIANCE not in settings.enabled_features:
        raise RequestValidationError(
            [
                {
                    "type": "literal_error",
                    "loc": ("query", "item"),
                    "msg": "",
                    "input": None,
                }
            ]
        )


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
    response_model=CalculateResponse
    | LaundryCalculateResponse
    | ApplianceCalculateResponse,
    description="item=gym(기본)이면 본문은 GymInput, item=laundry면 LaundryInput"
    " (x-laundry-request-schema).",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": GymInput.model_json_schema()}},
        },
        "x-laundry-request-schema": LaundryInput.model_json_schema(),
        "x-appliance-request-schema": ApplianceInput.model_json_schema(),
    },
)
async def calculate(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_app_settings)],
    item: Literal["gym", "laundry", "appliance"] = "gym",
) -> CalculateResponse | LaundryCalculateResponse | ApplianceCalculateResponse:
    """확정된 입력으로 기준 금액을 계산하고 표시 정보를 붙인다."""
    body = await request.body()
    if item == APPLIANCE:
        require_appliance(settings)
        appliance = validate_body(ApplianceInput, body)
        arule = load_appliance_rule()
        aresult = calculate_appliance(appliance, arule)
        return ApplianceCalculateResponse(
            result=aresult, display=build_appliance_display(aresult, arule, appliance)
        )
    if item == "laundry":
        laundry = validate_body(LaundryInput, body)
        lrule = load_laundry_rule()
        lresult = calculate_damage(laundry, lrule, settings.enabled_features)
        return LaundryCalculateResponse(
            result=lresult, display=build_laundry_display(lresult, lrule, laundry)
        )
    inp = validate_body(GymInput, body)
    rule = load_rule(RULE_ID)
    result = calculate_refund(inp, rule)
    return CalculateResponse(result=result, display=build_display(result, rule))


@router.get("/laundry/items", response_model=list[LaundryItemOption])
def laundry_items() -> list[LaundryItemOption]:
    """세탁 품목·소재·용도 선택지 (평균 내용연수표 행 그대로, 내용연수 숫자 없음)."""
    return item_options(load_laundry_rule())


@router.get("/appliance/items", response_model=list[ApplianceItemOption])
def appliance_items(
    settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> list[ApplianceItemOption] | JSONResponse:
    """가전 지원 품목 선택지 (규칙 JSON 순서, 기간 숫자 없음). 가전이 꺼져 있으면 404 (지금과 같게)."""
    if APPLIANCE not in settings.enabled_features:
        # 없는 /api 경로와 같은 응답 (api/spa.py)
        return JSONResponse(status_code=404, content={"message": NOT_FOUND_MESSAGE})
    return appliance_options(load_appliance_rule())
