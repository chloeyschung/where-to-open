"""예외 → 공통 에러 JSON.

핸들러가 없으면 에러마다 응답 모양이 다르다 ({"detail": ...}, 평문 "Internal Server Error" 등).
여기서 전부 {"error": {"code", "message"}} 하나로 맞춰서, 프론트는 res.error.message만 보면 된다.
Service는 raise만 하고, Router에는 try/except가 필요 없다.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app")


class AppError(Exception):
    """업무 예외의 부모. 자식 클래스는 status_code와 code만 바꾼다."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


def _error(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    err = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return JSONResponse(status_code=status_code, content={"error": err})


def register_exception_handlers(app: FastAPI) -> None:
    # Service가 던진 업무 예외 (NotFoundError 등)
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError):
        return _error(exc.status_code, exc.code, exc.message)

    # 요청 값 검증 실패 (경로 패턴, 쿼리 범위 등) → 422, details에 어느 값이 틀렸는지
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError):
        return _error(422, "VALIDATION_ERROR", "요청 값이 올바르지 않습니다.", jsonable_encoder(exc.errors()))

    # 없는 URL(404), 허용 안 된 메서드(405)
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "HTTP_ERROR", str(exc.detail))

    # 그 외 전부 (코드 버그, DB 다운) → 500. 원인은 로그에만 남기고 응답에는 내부 정보를 넣지 않는다
    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception("처리하지 못한 예외: %s %s", request.method, request.url.path)
        return _error(500, "INTERNAL_ERROR", "서버 오류가 발생했습니다.")
