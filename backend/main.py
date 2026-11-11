"""기준대로 백엔드 진입점. 앱 생성과 라우터 등록만 한다."""

from fastapi import FastAPI

from api.analyze import router as analyze_router
from api.calculate import router as calculate_router
from api.config import router as config_router
from api.errors import install_error_handling
from api.guide import router as guide_router
from api.health import router as health_router

app = FastAPI(title="기준대로")
install_error_handling(app)
app.include_router(health_router)
app.include_router(calculate_router)
app.include_router(analyze_router)
app.include_router(guide_router)
app.include_router(config_router)
