from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

from corpusflow.core.errors import ErrorResponse, error_response

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["alive", "ready"]
    phase: Literal["P0-A"] = "P0-A"
    request_id: str


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(status="alive", request_id=request.state.request_id)


@router.get("/ready", response_model=HealthResponse, responses={503: {"model": ErrorResponse}})
def ready(request: Request) -> HealthResponse | JSONResponse:
    checks = request.app.state.probe.check()
    if any(value != "ok" for value in checks.values()):
        return error_response(
            request,
            503,
            "DEPENDENCY_UNAVAILABLE",
            "依赖未就绪，请检查服务与迁移版本",
            [{"dependency": key, "status": value} for key, value in checks.items()],
            True,
        )
    return HealthResponse(status="ready", request_id=request.state.request_id)
