"""화면 설정 라우터 GET /api/config (2026-11-11). 운영 설정 중 화면에 필요한 값만 돌려준다.

analyze_enabled = 스위치(ANALYZE_ENABLED) 켜짐 그리고 오늘(KST) 하루 상한 미도달 (2026-11-12 결정).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from api.analyze import get_daily_counter
from api.settings import AppSettings, get_app_settings
from llm.usage import DailyCallCounter

router = APIRouter(prefix="/api")


class ConfigResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analyze_enabled: bool
    survey_url: str | None


@router.get("/config", response_model=ConfigResponse)
def config(
    settings: Annotated[AppSettings, Depends(get_app_settings)],
    counter: Annotated[DailyCallCounter, Depends(get_daily_counter)],
) -> ConfigResponse:
    """문장 분석을 지금 쓸 수 있는지와 설문 링크. 키·모델 이름 등 다른 설정은 내보내지 않는다."""
    return ConfigResponse(
        analyze_enabled=settings.analyze_enabled and not counter.exhausted(),
        survey_url=settings.survey_url,
    )
