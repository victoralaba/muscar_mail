from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from core.config import get_settings
from core.logging import get_logger, setup_logging
from core.telemetry import init_telemetry
from domains.mcp.routes import router as mcp_router
from domains.verification.routes import router as verification_router
from domains.verification.service import verifalia_service
from shared.exceptions import register_exception_handlers
from shared.redis import redis_client

logger = get_logger("muscar_mail.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and graceful shutdown for Render serverless containers.

    Enforces Invariants:
    - INV-BOOT-FAST: Zero synchronous blocking I/O or external network queries on boot (<2s).
    - INV-CLEAN-LIFESPAN: Explicitly closes httpx2 connection pools and async Redis connections on teardown.
    """
    settings = get_settings()

    # 1. Initialize structured logging & telemetry
    setup_logging(environment=settings.ENVIRONMENT, debug=settings.DEBUG)
    init_telemetry(dsn=settings.SENTRY_DSN, environment=settings.ENVIRONMENT)

    logger.info(
        "Starting muscar_mail application.",
        app=settings.MCP_SERVER_NAME,
        version=settings.MCP_SERVER_VERSION,
        mcp_protocol=settings.MCP_PROTOCOL_VERSION,
        environment=settings.ENVIRONMENT,
    )

    yield

    # Teardown logic on SIGTERM / instance sleep
    logger.info("Shutting down muscar_mail application. Releasing connection pools...")
    try:
        await verifalia_service.close()
    except Exception as exc:
        logger.warning("Error releasing Verifalia HTTP client connection pool.", error=str(exc))

    try:
        await redis_client.close()
    except Exception as exc:
        logger.warning("Error releasing Redis connection pool.", error=str(exc))

    logger.info("Application teardown complete. Ready for clean sleep/exit.")


def create_app() -> FastAPI:
    """Application factory building and configuring the muscar_mail FastAPI instance."""
    settings = get_settings()

    # Eagerly wire structured logging for initialization and startup safety
    setup_logging(environment=settings.ENVIRONMENT, debug=settings.DEBUG)

    application = FastAPI(
        title="muscar_mail",
        description=(
            "Custom, zero-dependency, stateless Model Context Protocol (MCP) server "
            "and REST API for email deliverability verification via Verifalia v2.4."
        ),
        version=settings.MCP_SERVER_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. Mount global domain exception handlers
    register_exception_handlers(application)

    # 2. Configure CORS middleware for distributed AI agent sandboxes & browser clients
    # Note: allow_credentials is intentionally False because muscar_mail is completely
    # stateless and uses header-based Bearer/X-API-Key auth, preventing OWASP API8 origin reflection.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Mount zero-network health check probe (Invariant INV-HEALTH-ZERO-NET)
    @application.get(
        "/health",
        status_code=status.HTTP_200_OK,
        tags=["system"],
        summary="Zero-network health check",
        description="Instantaneous (<5ms) probe confirming container uptime without external network dispatch.",
    )
    async def health_check() -> Dict[str, str]:
        """Returns instantaneous healthy status for container orchestrators."""
        return {
            "status": "healthy",
            "app": settings.MCP_SERVER_NAME,
            "version": settings.MCP_SERVER_VERSION,
            "protocol_version": settings.MCP_PROTOCOL_VERSION,
        }

    # 4. Mount REST API domain router
    application.include_router(verification_router)

    # 5. Mount stateless Model Context Protocol domain router
    application.include_router(mcp_router)

    return application


# ASGI entrypoint for uvicorn (e.g. uvicorn main:app)
app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
