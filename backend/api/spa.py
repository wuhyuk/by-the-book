"""화면(frontend/dist) 서빙 (2026-11-12, 컨테이너 한 개 배포). 새 의존성 없이 Starlette FileResponse만 쓴다.

- dist 안에 있는 파일이면 그 파일을 돌려준다 (/assets/… 등).
- 그 밖의 경로는 index.html (SPA 폴백). 단 /api로 시작하는 경로는 폴백하지 않고 404 JSON.
- dist 밖을 가리키는 경로(.. 등)는 파일로 내주지 않고 index.html로 돌린다.
- dist가 없으면(백엔드만 개발할 때) 아무것도 등록하지 않는다.
dist 위치는 환경변수 FRONTEND_DIST, 없으면 저장소의 frontend/dist.
요청 경로·본문은 로그에 남기지 않는다.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response

DEFAULT_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
NOT_FOUND_MESSAGE = "요청한 API 경로가 없습니다."


def dist_dir() -> Path:
    raw = os.environ.get("FRONTEND_DIST", "").strip()
    return Path(raw) if raw else DEFAULT_DIST


def install_spa(app: FastAPI, dist: Path | None = None) -> bool:
    """dist가 있으면 화면 서빙 경로를 등록하고 True. API 라우터를 모두 등록한 뒤 부른다."""
    root = (dist or dist_dir()).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"message": NOT_FOUND_MESSAGE})
        if full_path:
            candidate = (root / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        # index.html은 새 배포가 바로 반영되도록 캐시하지 않는다
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return True
