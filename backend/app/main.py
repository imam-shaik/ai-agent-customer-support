"""FastAPI application factory.

Layers (top → bottom):
    API routes   — HTTP contract, validation, status codes
    Services     — business rules and domain events
    Repositories — data access only
    Models       — persistent schema

Middleware adds a request/correlation id and access logging. Exception
handlers guarantee the single safe error envelope for every failure.
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging

logger = get_logger("app.http")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Startup: idempotent knowledge seed (real pipeline ingestion) +
        # a clear warning if someone configured an LLM provider early.
        if settings.environment != "production":
            from app.db.seed import seed_knowledge
            from app.db.session import SessionLocal

            with SessionLocal() as session:
                seed_knowledge(session)
        if settings.llm_provider != "stub" and not settings.nvidia_api_key:
            logger.warning(
                "llm_provider=%s configured but NVIDIA_API_KEY is missing; "
                "live chat turns return 503 until a key is set or Demo mode "
                "is selected in the UI.",
                settings.llm_provider,
            )
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Vilasat AI support platform backend: grounded retrieval and answers "
            "with citations, evidence-aware fallback, escalation tickets, feedback, "
            "knowledge ingestion, and a local Demo/Live provider switch."
        ),
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        # Explicit origins from configuration - never a wildcard.
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        # PUT is required by the provider-settings endpoints (keys);
        # without it the browser rejects their preflight and key saving
        # cannot work from the UI.
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        # Authorization is REQUIRED since staff authentication (Phase 11):
        # every staff-side request carries `Authorization: Bearer <token>`,
        # which makes the browser send a CORS preflight that names the
        # header. Without it in this list the preflight is answered 400
        # ("Disallowed CORS header") and EVERY staff call fails from the
        # browser only — offline pill, empty queue — while API-level
        # clients (curl/TestClient, no preflights) keep working.
        allow_headers=["Accept", "Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        logger.info(
            "request_received method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request_completed method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        """Liveness + provider mode.

        `mode` tells the UI (and operators) which AI providers are
        actually attached: `offline_demo` = the explicit local Demo mode
        (deterministic providers, no network), `live` = real NVIDIA
        providers with keys configured, `partial` = anything mixed or
        incomplete (chat may answer 503).
        """
        from app.services.provider_mode_service import is_demo_mode

        if is_demo_mode():
            return {
                "status": "ok",
                "environment": settings.environment,
                "llm_provider": "stub",
                "embedding_provider": "fake",
                "mode": "offline_demo",
            }

        embedding_provider = settings.embedding_provider
        llm_provider = settings.llm_provider
        llm_live = llm_provider == "nvidia" and bool(settings.nvidia_api_key)
        embedding_live = embedding_provider == "nvidia" and bool(
            settings.embedding_api_key
        )
        if llm_provider == "stub" and embedding_provider == "fake":
            mode = "offline_demo"
        elif llm_live and embedding_live:
            mode = "live"
        else:
            mode = "partial"
        return {
            "status": "ok",
            "environment": settings.environment,
            "llm_provider": llm_provider,
            "embedding_provider": embedding_provider,
            "mode": mode,
        }

    return app


app = create_app()
