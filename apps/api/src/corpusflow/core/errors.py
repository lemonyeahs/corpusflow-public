from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
    retryable: bool = False


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    request_id = request.state.request_id
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details or [], retryable=retryable),
        request_id=request_id,
    )
    return JSONResponse(body.model_dump(), status_code=status, headers={"X-Request-ID": request_id})
