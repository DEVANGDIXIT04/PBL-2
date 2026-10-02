"""FastAPI application."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import anomalies, auth, budgets, categories, forecast, reports, transactions
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_db

logger = logging.getLogger(__name__)
settings = get_settings()

ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the optional nightly retrain job. Migrations run in the container entrypoint."""
    configure_logging(settings.log_level)
    scheduler = None
    if settings.enable_scheduler:
        from apscheduler.schedulers.background import BackgroundScheduler

        from app.services.anomaly_service import train_all_users

        scheduler = BackgroundScheduler()
        scheduler.add_job(train_all_users, "cron", hour=2, minute=15, id="nightly-retrain")
        scheduler.start()
        logger.info("nightly retrain scheduled")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Personal finance tracker with Isolation Forest anomaly detection "
        "and anomaly-adjusted exponential smoothing forecasts."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log method, path, and status. The Authorization header is never logged."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "%s %s -> %s (%sms)", request.method, request.url.path, response.status_code, elapsed_ms
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "code": ERROR_CODES.get(exc.status_code, "error")},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    parts = []
    for item in exc.errors():
        loc = ".".join(str(piece) for piece in item.get("loc", []) if piece != "body")
        parts.append(f"{loc}: {item.get('msg')}" if loc else str(item.get("msg")))
    return JSONResponse(
        status_code=422,
        content={"detail": "; ".join(parts) or "Invalid request", "code": "validation_error"},
    )


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)) -> dict:
    """Liveness probe. Confirms the process can reach the database."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/", tags=["health"])
def root() -> dict:
    return {"app": settings.app_name, "docs": "/docs", "health": "/health"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(budgets.router, prefix="/api/v1")
app.include_router(anomalies.router, prefix="/api/v1")
app.include_router(forecast.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
