import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException
from starlette.responses import Response

from corpusflow.adapters.readiness import DependencyProbe
from corpusflow.api.health import router
from corpusflow.api.v1.business import router as business_router
from corpusflow.core.config import Settings, load_settings
from corpusflow.core.errors import ErrorResponse, error_response
from corpusflow.core.logging import configure_logging
from corpusflow.db.session import build_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(config)
        app.state.config = config
        app.state.sessions = sessionmaker(engine, expire_on_commit=False)
        app.state.probe = DependencyProbe(config, engine)
        try:
            yield
        finally:
            app.state.probe.close()
            engine.dispose()

    app = FastAPI(
        title="CorpusFlow API",
        version="0.1.0",
        lifespan=lifespan,
        description="CorpusFlow modular monolith P0 business loop with server-side policy gates.",
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )

    @app.middleware("http")
    async def correlate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            incoming if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", incoming) else uuid4().hex
        )
        trace = request.headers.get("X-Trace-ID", "")
        request.state.trace_id = (
            trace if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", trace) else request.state.request_id
        )
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger("corpusflow").exception("request_failed")
            response = error_response(request, 500, "INTERNAL_ERROR", "服务内部错误")
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Trace-ID"] = request.state.trace_id
        logging.getLogger("corpusflow").info(
            "http_request",
            extra={
                "request_id": request.state.request_id,
                "trace_id": request.state.trace_id,
                "status_code": response.status_code,
                "duration_ms": round((time.monotonic() - start) * 1000, 2),
                "error_code": "INTERNAL_ERROR" if response.status_code == 500 else None,
            },
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        detail = exc.detail if isinstance(exc.detail, str) else ""
        known = {
            "UNAUTHENTICATED",
            "PERMISSION_DENIED",
            "INVALID_STATE_TRANSITION",
            "RUN_REVIEW_BLOCKED",
            "SELF_APPROVAL_FORBIDDEN",
            "RELEASE_GATE_FAILED",
            "CHECKSUM_MISMATCH",
            "UPLOAD_NOT_VERIFIED",
            "NOT_FOUND",
            "INVALID_ARGUMENT",
            "ADAPTER_UNAVAILABLE",
            "BUILD_SNAPSHOT_CHANGED",
            "SAMPLE_NOT_APPROVED",
            "INVALID_SAMPLE_FORMAT",
            "INVALID_SAMPLE_EVIDENCE",
            "PURPOSE_GRANT_MISSING",
            "VERSION_CONFLICT",
            "MATERIALIZATION_HASH_MISMATCH",
            "DATASET_VERSION_NOT_FOUND",
            "DOWNLOAD_NOT_AUTHORIZED",
            "UPLOAD_SIZE_MISMATCH",
            "IDEMPOTENCY_KEY_REUSED",
            "UNSUPPORTED_PRODUCT_TYPE",
            "PRODUCT_PURPOSE_MISMATCH",
            "NO_VALID_CANDIDATES",
            "INVALID_CHUNK_UNIT",
            "INVALID_CHUNK_CONFIG",
            "INVALID_EVALUATION_CONFIG",
        }
        return error_response(
            request,
            exc.status_code,
            detail if detail in known else codes.get(exc.status_code, "HTTP_ERROR"),
            "请求路径不存在或方法不受支持",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        return error_response(
            request,
            422,
            "VALIDATION_FAILED",
            "请求参数校验失败",
            [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()],
        )

    app.include_router(router)
    app.include_router(business_router)
    return app
