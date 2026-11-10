"""Structured error responses.

Every error the API returns has the same envelope, so the frontend can
show safe, understandable messages without parsing exception text:

    {"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}

Never included: stack traces, env vars, API keys, prompts, DB details.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger("app.errors")


class AppError(Exception):
    """Base class for safe, deliberate API errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: list | dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class UnauthorizedError(AppError):
    """Missing, invalid, or expired staff credentials (401).

    The message is safe to display: it never says whether an email
    exists or which part of the credential failed.
    """

    status_code = 401
    code = "UNAUTHORIZED"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"


class InvalidInputError(AppError):
    """Request-level content validation (422, same envelope as schema errors)."""

    status_code = 422
    code = "VALIDATION_ERROR"


class ProcessingError(AppError):
    """The row exists but the pipeline could not process its content.

    The document is persisted as FAILED with a safe reason; the response
    never exposes internal detail — only the document id and reason.
    """

    status_code = 422
    code = "PROCESSING_FAILED"


class EmbeddingUnavailableError(AppError):
    """Embedding provider missing or failed (Phase 7).

    Retrieval/indexing refuse to run instead of inventing vectors — the
    caller gets an explicit, safe error, never fake-but-plausible data.
    """

    status_code = 503
    code = "EMBEDDING_PROVIDER_UNAVAILABLE"


class LLMUnavailableError(AppError):
    """LLM provider missing, unreachable or failed (Phase 8A).

    Generation refuses instead of fabricating an answer — the customer's
    message stays persisted and the turn can be retried safely.
    """

    status_code = 503
    code = "LLM_PROVIDER_UNAVAILABLE"


class GenerationFailedError(AppError):
    """The LLM returned something the application refuses to trust (Phase 8A).

    Malformed structured output or citations that were not part of this
    turn's retrieved evidence. Nothing generated is persisted — no invalid
    answer ever reaches the conversation. 502: the upstream model response
    was invalid, not this request.
    """

    status_code = 502
    code = "GENERATION_FAILED"


def _envelope(request: Request, code: str, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "location": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope(
                request,
                "VALIDATION_ERROR",
                "The request payload failed validation.",
                details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(request, code, message),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback goes to the server log only — never to clients.
        logger.exception(
            "unexpected_error path=%s request_id=%s",
            request.url.path,
            getattr(request.state, "request_id", None),
        )
        return JSONResponse(
            status_code=500,
            content=_envelope(
                request,
                "INTERNAL_ERROR",
                "Something went wrong on our side. Please try again.",
            ),
        )
