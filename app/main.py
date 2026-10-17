"""
FastAPI application entry point.

FLOW MAP:
  uvicorn → main.py (lifespan + router mounts) → API routers

LIFESPAN (startup / shutdown):
  startup: init_db() → create tables if not exist
  shutdown: (graceful cleanup)

ROUTER MOUNTS:
  /patients                — Patient CRUD REST API
  /api/voice/webhook       — Vapi voice AI webhook
  /api/voice/tools         — Vapi function call endpoint
  /health                  — Health check
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.patients import router as patients_router
from app.api.voice_webhooks import router as voice_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.responses import error_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ---------------------------------------------------------------------------
# Application lifespan — startup and shutdown hooks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown lifecycle.

    Startup:
      - Initialize database tables (create if not exist)

    Shutdown:
      - Graceful cleanup (reserved for future connection pool cleanup)
    """
    logger.info(
        "Starting %s v%s (APP_ENV=%s)...",
        settings.app_name, settings.app_version, settings.app_env,
    )
    await init_db()
    logger.info("Application ready — accepting requests.")
    yield
    logger.info("Shutting down %s...", settings.app_name)


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------

is_prod = settings.app_env.lower() in ("prod", "production")

app = FastAPI(
    title="Patient Registration Voice Agent API",
    description=(
        "REST API for patient demographic registration with Vapi voice AI integration. "
        "Supports CRUD operations, server-side validation, and automated phone-based intake."
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
)


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

_cors_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]
if not _cors_origins:
    logger.warning(
        "CORS_ORIGINS is empty — browser cross-origin requests will be rejected."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)


# ---------------------------------------------------------------------------
# Router mounts
# ---------------------------------------------------------------------------

app.include_router(patients_router)
app.include_router(voice_router)


# ---------------------------------------------------------------------------
# Health check & Static Dashboard
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "ok",
        "service": "patient-registration-voice-agent",
        "version": settings.app_version,
    }


# Mount static assets and serve dashboard SPA
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/dashboard", include_in_schema=False)
    async def serve_dashboard():
        """Serve the modern Patient Registration & Voice Agent dashboard."""
        return FileResponse(os.path.join(_static_dir, "index.html"))


# ---------------------------------------------------------------------------
# Global exception handlers — enforce envelope format for ALL error responses
# ---------------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Wrap HTTP exceptions in the standard {data, error} envelope."""
    return error_response(
        message=str(exc.detail),
        status_code=exc.status_code,
        code="HTTP_ERROR",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Wrap Pydantic/FastAPI validation errors in the standard envelope.

    Extracts per-field error details for clear API consumer feedback.
    """
    details = []
    for err in exc.errors():
        loc = " → ".join(str(part) for part in err.get("loc", []))
        details.append({
            "field": loc,
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })

    return error_response(
        message="Request validation failed.",
        status_code=422,
        code="VALIDATION_ERROR",
        details=details,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for unhandled exceptions.

    Logs the full traceback and returns a generic 500 error in the
    standard envelope. Never leaks stack traces to the client in production.
    """
    logger.exception(
        "Unhandled error on %s %s: %s",
        request.method, request.url.path, exc,
    )
    message = (
        f"{type(exc).__name__}: {exc}"
        if settings.debug
        else "An unexpected error occurred. Please try again later."
    )
    return error_response(
        message=message,
        status_code=500,
        code="INTERNAL_ERROR",
    )
