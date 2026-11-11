"""서버 상태 확인 라우터."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """서버가 응답하는지 확인한다."""
    return {"status": "ok"}


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """배포 호스트 헬스체크 경로 (Render 등). 외부 호출·파일 읽기 없이 바로 답한다."""
    return {"status": "ok"}
