"""설명·업체용 문안 라우터 POST /api/guide (MVP_SPEC 6절, 2026-11-11 결정: LLM 없음).

본문은 /api/calculate와 같다 (item=gym이면 GymInput, laundry면 LaundryInput). 서버가 다시 계산한
결과로 문안을 만들고, 클라이언트가 보낸 계산 결과·숫자는 받지 않는다. 로직은 guide/에 둔다.
요청 본문은 로그에 남기지 않는다.
"""

from typing import Literal

from fastapi import APIRouter, Request

from api.calculate import RULE_ID, validate_body
from guide.common import Guide
from guide.gym import build_gym_guide
from guide.laundry import build_laundry_guide
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
    },
)
async def guide(request: Request, item: Literal["gym", "laundry"] = "gym") -> Guide:
    """확정된 입력으로 다시 계산해 설명 문장·업체용 문안·근거 조항을 만든다."""
    body = await request.body()
    if item == "laundry":
        laundry = validate_body(LaundryInput, body)
        lrule = load_laundry_rule()
        return build_laundry_guide(laundry, calculate_damage(laundry, lrule), lrule)
    inp = validate_body(GymInput, body)
    rule = load_rule(RULE_ID)
    return build_gym_guide(inp, calculate_refund(inp, rule), rule)
