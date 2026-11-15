"""기준대로 백엔드 진입점. 앱 생성과 라우터 등록만 한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.analyze import router as analyze_router
from api.calculate import router as calculate_router
from api.config import router as config_router
from api.errors import install_error_handling
from api.guide import router as guide_router
from api.health import router as health_router
from api.settings import app_settings
from api.sources import router as sources_router
from api.spa import install_spa
from rag.search import warm_index


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """rag가 켜져 있으면 조항 검색 색인을 서버 시작 때 한 번 만든다 (MVP_SPEC 15.1)."""
    if "rag" in app_settings().enabled_features:
        warm_index()
    yield


app = FastAPI(title="기준대로", lifespan=lifespan)
install_error_handling(app)
app.include_router(health_router)
app.include_router(calculate_router)
app.include_router(analyze_router)
app.include_router(guide_router)
app.include_router(config_router)
app.include_router(sources_router)
# 화면 서빙은 API 라우터를 모두 등록한 뒤에 둔다 (catch-all이 API를 가리지 않게)
install_spa(app)
