"""조항 조회 라우터 GET /api/sources/{clause_id} (MVP_SPEC 14.3, 2026-11-16, 기능 플래그 없음).

규칙 JSON의 조항 ID로 원문·출처·기준일·확인 여부를 돌려준다. 로직은 rules/sources.py에 둔다.
ID는 영문 소문자·숫자·밑줄(64자 이하)만 받는다 (그 밖은 422). 없는 ID는 404 한국어 메시지.
"""

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

from rules.sources import CLAUSE_ID_PATTERN, NOT_FOUND_TEXT, ClauseSource, find_clause

router = APIRouter(prefix="/api")


@router.get(
    "/sources/{clause_id}",
    response_model=ClauseSource,
    responses={404: {"description": NOT_FOUND_TEXT}},
)
def source(
    clause_id: Annotated[str, Path(pattern=CLAUSE_ID_PATTERN.pattern)],
) -> ClauseSource | JSONResponse:
    """조항 원문과 출처. 근거 카드의 '원문 보기'에 쓴다."""
    found = find_clause(clause_id)
    if found is None:
        return JSONResponse(status_code=404, content={"message": NOT_FOUND_TEXT})
    return found
