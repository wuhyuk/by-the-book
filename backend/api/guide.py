"""설명·업체용 문안 라우터 POST /api/guide (MVP_SPEC 6절, 2026-11-11 결정: LLM 없음).

본문은 /api/calculate와 같다 (item=gym이면 GymInput, laundry면 LaundryInput). 서버가 다시 계산한
결과로 문안을 만들고, 클라이언트가 보낸 계산 결과·숫자는 받지 않는다. 로직은 guide/에 둔다.
요청 본문은 로그에 남기지 않는다.
기능 플래그 offer_gap(설명에 차액 한 줄)·next_steps(다음 행동)는 ENABLED_FEATURES로 켠다 (MVP_SPEC 14절).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from api.calculate import APPLIANCE, RULE_ID, require_appliance, validate_body
from api.settings import AppSettings, get_app_settings
from guide.appliance import build_appliance_guide
from guide.common import Guide, with_next_steps
from guide.gym import build_gym_guide
from guide.laundry import build_laundry_guide
from rules.appliance import ApplianceInput, calculate_appliance
from rules.appliance_rule import load_appliance_rule
from rules.gym import GymInput, calculate_refund
from rules.laundry import LaundryInput, calculate_damage
from rules.laundry_rule import load_laundry_rule
from rules.loader import load_rule

router = APIRouter(prefix="/api")


@router.post(
    "/guide",
    response_model=Guide,
    description="본문은 /api/calculate와 같다. item=gym(기본)이면 GymInput, item=laundry면"
    " LaundryInput (x-laundry-request-schema).",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": GymInput.model_json_schema()}},
        },
        "x-laundry-request-schema": LaundryInput.model_json_schema(),
        "x-appliance-request-schema": ApplianceInput.model_json_schema(),
    },
)
async def guide(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_app_settings)],
    item: Literal["gym", "laundry", "appliance"] = "gym",
) -> Guide:
    """확정된 입력으로 다시 계산해 설명 문장·업체용 문안·근거 조항을 만든다."""
    body = await request.body()
    features = settings.enabled_features
    if item == APPLIANCE:
        require_appliance(settings)
        appliance = validate_body(ApplianceInput, body)
        arule = load_appliance_rule()
        aresult = calculate_appliance(appliance, arule, features)
        aguide = build_appliance_guide(appliance, aresult, arule)
        return with_next_steps(
            aguide,
            "appliance",
            calculated=aresult.calculated,
            flags=aresult.flags,
            features=features,
        )
    if item == "laundry":
        laundry = validate_body(LaundryInput, body)
        lrule = load_laundry_rule()
        lresult = calculate_damage(laundry, lrule, features)
        lguide = build_laundry_guide(laundry, lresult, lrule)
        return with_next_steps(
            lguide,
            "laundry",
            calculated=lresult.calculated,
            flags=lresult.flags,
            features=features,
        )
    inp = validate_body(GymInput, body)
    rule = load_rule(RULE_ID)
    result = calculate_refund(inp, rule, features)
    return with_next_steps(
        build_gym_guide(inp, result, rule),
        "gym",
        calculated=result.calculated,
        flags=result.flags,
        features=features,
    )
