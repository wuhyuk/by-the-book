"""LLM 응답의 스키마 검증 실패 로그 (2026-11-16). 필드 이름만 남긴다.

검증 오류의 위치(loc) 중 알려진 이름(스키마의 키)만 쓰고, 그 밖의 값(LLM이 만든 낯선 키 등)은 "?"로 바꾼다.
입력 문장·응답 본문·오류 메시지(값이 들어갈 수 있음)는 남기지 않는다.
"""

import logging
from collections.abc import Iterable

from pydantic import ValidationError

logger = logging.getLogger("by_the_book.llm")


def failed_fields(exc: ValidationError, known: Iterable[str]) -> list[str]:
    """검증에 실패한 위치를 'fields.industry'처럼 이름만으로. 목록 번호는 그대로, 모르는 이름은 '?'."""
    allowed = set(known)
    out: list[str] = []
    for err in exc.errors():
        parts = [
            str(p) if isinstance(p, int) or p in allowed else "?"
            for p in err.get("loc", ())
        ]
        path = ".".join(parts) or "?"
        if path not in out:
            out.append(path)
    return out


def log_validation_failure(exc: ValidationError, known: Iterable[str]) -> None:
    logger.warning("LLM 응답 검증 실패: fields=%s", ",".join(failed_fields(exc, known)))
