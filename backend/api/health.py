"""서버 상태 확인 라우터."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """서버가 응답하는지 확인한다."""
    return {"status": "ok"}
