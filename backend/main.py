"""기준대로 백엔드 진입점. 앱 생성과 라우터 등록만 한다."""

import logging
import sys
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

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
APP_LOGGER = "by_the_book"


def configure_logging() -> None:
    """앱 로그(by_the_book.*)를 표준 출력으로 INFO부터 보낸다 (2026-11-16, Render 로그에 항상 보이게).

    핸들러가 없으면 경고만 Python 기본 출력으로 나가고 INFO는 버려졌다. 두 번 불러도 핸들러는 하나다.
    로그에는 종류·상태·시도·역할·소요 시간만 남긴다 (입력 문장·응답 본문·키 없음, CLAUDE.md 절대 규칙 6).
    """
    logger = logging.getLogger(APP_LOGGER)
    logger.setLevel(logging.INFO)
    if not any(getattr(h, "_by_the_book", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._by_the_book = True  # type: ignore[attr-defined]
        logger.addHandler(handler)


configure_logging()


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
