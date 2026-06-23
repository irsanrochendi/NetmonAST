"""NetMon — Network Monitoring System

FastAPI application entry point.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    agent_router,
    alert_router,
    alert_rule_router,
    auth_router,
    dashboard_router,
    device_router,
    export_router,
    maintenance_router,
    metric_router,
)
from app.security import SecurityHeadersMiddleware, api_limiter, auth_limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="NetMon API",
    description="Network Monitoring for Mikrotik, ESXi, and VM Guests",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware (order matters — first added = outermost) ────────────

# 1. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS (restrict in production — set allow_origins to specific domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to dashboard domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Rate Limiting Middleware ────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting based on endpoint path."""
    path = request.url.path
    ip = request.client.host if request.client else "unknown"

    # Choose limiter based on path
    if path.startswith("/api/auth"):
        limiter = auth_limiter
    else:
        limiter = api_limiter

    allowed, headers = limiter.is_allowed(ip)
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Try again later."},
            headers={**headers, "Retry-After": "60"},
        )

    response = await call_next(request)
    # Add rate limit headers to response
    for key, value in headers.items():
        response.headers[key] = value
    return response


# ── Global Exception Handler ───────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler to prevent leaking internal errors."""
    logging.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ── Register Routers ────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api")
app.include_router(device_router, prefix="/api")
app.include_router(metric_router, prefix="/api")
app.include_router(alert_rule_router, prefix="/api")
app.include_router(alert_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(maintenance_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")


# ── Health Check ────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "netmon-api"}


@app.get("/")
async def root():
    return {
        "service": "NetMon",
        "version": "0.1.0",
        "docs": "/docs",
    }
