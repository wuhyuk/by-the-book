"""기준대로 백엔드 진입점. 앱 생성과 라우터 등록만 한다."""

from fastapi import FastAPI

from api.health import router as health_router

app = FastAPI(title="기준대로")
app.include_router(health_router)
