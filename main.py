from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Muscar Mail — Model Context Protocol &amp; Email Verification</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Raleway:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #100f11;
      --bg-card: #191b20;
      --bg-card-hover: #2e333a;
      --bg-border: #3d434a;
      --surface-soft: rgba(255, 255, 255, 0.04);
      --accent: #fc946d;
      --accent-dim: #d96a44;
      --accent-glow: rgba(252, 148, 109, 0.15);
      --text-primary: #f5f4f3;
      --text-secondary: #9a9da1;
      --button-ink: #100f11;
    }
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      background: var(--bg);
      color: var(--text-primary);
      font-family: 'Raleway', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
      line-height: 1.5;
    }
    .card {
      background: var(--bg-card);
      border: 1px solid var(--bg-border);
      border-radius: 16px;
      max-width: 560px;
      width: 100%;
      padding: 36px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: var(--surface-soft);
      border: 1px solid var(--bg-border);
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 13px;
      color: var(--text-secondary);
      margin-bottom: 20px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
    }
    h1 {
      font-size: 28px;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 12px;
      letter-spacing: -0.02em;
    }
    p.desc {
      color: var(--text-secondary);
      font-size: 15px;
      margin-bottom: 24px;
    }
    .endpoints {
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid var(--bg-border);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 24px;
    }
    .endpoint-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 0;
      font-size: 13px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .endpoint-row:last-child {
      border-bottom: none;
    }
    .label {
      color: var(--text-secondary);
    }
    .value {
      font-family: 'JetBrains Mono', monospace;
      color: var(--accent);
      background: var(--surface-soft);
      padding: 2px 8px;
      border-radius: 4px;
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.15s ease;
      cursor: pointer;
    }
    .btn-primary {
      background: var(--accent);
      color: var(--button-ink);
      border: 1px solid var(--accent);
    }
    .btn-primary:hover {
      background: var(--accent-dim);
      border-color: var(--accent-dim);
    }
    .btn-secondary {
      background: var(--surface-soft);
      color: var(--text-primary);
      border: 1px solid var(--bg-border);
    }
    .btn-secondary:hover {
      background: var(--bg-card-hover);
      border-color: var(--text-secondary);
    }
    footer {
      margin-top: 24px;
      font-size: 13px;
      color: var(--text-secondary);
      text-align: center;
    }
    footer a {
      color: var(--accent);
      text-decoration: none;
    }
    footer a:hover {
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">
      <span class="dot"></span>
      <span>Stateless MCP Server Online</span>
    </div>
    <h1>Muscar Mail</h1>
    <p class="desc">
      Zero-dependency, stateless Model Context Protocol (MCP) server &amp; email verification engine powered by Verifalia v2.4.
    </p>

    <div class="endpoints">
      <div class="endpoint-row">
        <span class="label">MCP JSON-RPC Endpoint</span>
        <span class="value">POST /mcp/v1/</span>
      </div>
      <div class="endpoint-row">
        <span class="label">REST Verification</span>
        <span class="value">POST /api/v1/verify</span>
      </div>
      <div class="endpoint-row">
        <span class="label">Health Probe</span>
        <span class="value">GET /health</span>
      </div>
      <div class="endpoint-row">
        <span class="label">Protocol Version</span>
        <span class="value">2026-07-28</span>
      </div>
    </div>

    <div class="actions">
      <a href="https://muscar.app" class="btn btn-primary" target="_blank" rel="noopener">
        Visit muscar.app &rarr;
      </a>
      <a href="/docs" class="btn btn-secondary">
        API Documentation
      </a>
    </div>
  </div>

  <footer>
    Part of the <a href="https://muscar.app" target="_blank" rel="noopener">muscar.app</a> ecosystem &bull; Licensed under MIT
  </footer>
</body>
</html>
"""


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

    # 4. Mount branded HTML landing page
    @application.get(
        "/",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def index() -> HTMLResponse:
        """Returns minimal, branded HTML landing page matching muscar.app styles."""
        return HTMLResponse(content=INDEX_HTML)

    # 5. Mount REST API domain router
    application.include_router(verification_router)

    # 6. Mount stateless Model Context Protocol domain router
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
