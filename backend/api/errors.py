"""API 오류 응답 처리. 사용자 입력값이 응답·로그에 다시 나오지 않게 한다 (CLAUDE.md 절대 규칙 6).

- 422: 필드 위치(loc)와 오류 종류(type)만 돌려준다. input·ctx·msg·url은 뺀다.
- 500: 고정 문구만 돌려준다. 추적 정보와 입력은 응답에 넣지 않고, 로그에는 예외 종류 이름만 남긴다.
"""

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("by_the_book.api")

VALIDATION_MESSAGE = "입력 형식이 맞지 않습니다. 표시된 항목을 확인해 주세요."
SERVER_ERROR_MESSAGE = "서버에서 오류가 발생했습니다. 잠시 뒤 다시 시도해 주세요."


def sanitize_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """검증 오류에서 위치와 종류만 남긴다."""
    return [{"loc": list(e.get("loc", ())), "type": e.get("type")} for e in errors]


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content={
            "message": VALIDATION_MESSAGE,
            "detail": sanitize_errors(exc.errors()),
        },
    )


class SafeServerErrorMiddleware:
    """처리하지 못한 예외를 고정 문구 500으로 바꾼다.

    Starlette 기본 처리는 예외를 다시 올려 서버 로그에 추적 정보(예외 메시지 포함)를 남긴다.
    예외 메시지에 입력값이 들어갈 수 있으므로 여기서 멈추고 예외 종류 이름만 기록한다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001 - 모든 예외를 고정 문구로 바꾼다
            logger.error("처리하지 못한 오류: %s", type(exc).__name__)
            if started:
                return
            response = JSONResponse(
                status_code=500, content={"message": SERVER_ERROR_MESSAGE}
            )
            await response(scope, receive, send)


def install_error_handling(app: FastAPI) -> None:
    """앱에 422 핸들러와 500 미들웨어를 등록한다."""
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_middleware(SafeServerErrorMiddleware)
