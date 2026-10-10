"""Error envelope: `{"error": {"code", "message", "details"}}` for every non-2xx response."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def not_found(resource: str, id_: object) -> ApiError:
    return ApiError(404, "not_found", f"{resource} {id_} not found", {"resource": resource, "id": str(id_)})


def _envelope(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorEnvelope, "description": "Resource not found"},
    422: {"model": ErrorEnvelope, "description": "Invalid path or query parameter"},
}


def install_error_handlers(app: FastAPI) -> None:
    async def api_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return _envelope(exc.status, exc.code, exc.message, exc.details)

    async def validation_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        errors = [
            {"location": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        return _envelope(422, "invalid_request", "Request parameters are invalid", {"errors": errors})

    async def http_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        return _envelope(exc.status_code, _HTTP_CODES.get(exc.status_code, "http_error"), str(exc.detail))

    async def unhandled(_: Request, __: Exception) -> JSONResponse:
        return _envelope(500, "internal_error", "Internal server error")

    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(Exception, unhandled)
