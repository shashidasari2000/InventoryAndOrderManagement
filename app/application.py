import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.database import Base, engine
from app.db_bootstrap import ensure_inventory_uom_schema
from app.api.routes import auth, whatsapp, transactions, messages, admin
from app.api.routes import inventory, suppliers, orders, pnl

settings = get_settings()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered accounting assistant for Indian MSMEs via WhatsApp",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    """Keep startup minimal on serverless — every ms here is felt as app lag."""
    logger = structlog.get_logger()
    if not settings.RUN_DB_BOOTSTRAP:
        logger.info("db_bootstrap_skipped", reason="RUN_DB_BOOTSTRAP=false")
        return
    try:
        Base.metadata.create_all(bind=engine)
        ensure_inventory_uom_schema(engine)
        logger.info("db_startup_ok")
    except Exception as exc:
        logger.error("db_startup_failed", error=str(exc))


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = structlog.get_logger()
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_type=type(exc).__name__)
    # Surface detail in non-production for easier Vercel debugging
    detail = str(exc) if settings.DEBUG or settings.APP_ENV == "development" else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


PREFIX = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=PREFIX)
app.include_router(whatsapp.router, prefix=PREFIX)
app.include_router(transactions.router, prefix=PREFIX)
app.include_router(messages.router, prefix=PREFIX)
app.include_router(admin.router, prefix=PREFIX)
app.include_router(inventory.router, prefix=PREFIX)
app.include_router(suppliers.router, prefix=PREFIX)
app.include_router(orders.router, prefix=PREFIX)
app.include_router(pnl.router, prefix=PREFIX)


@app.get("/")
def root():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "docs": "/api/docs",
        "health": "/health",
        "ping": "/ping",
        "api": settings.API_V1_PREFIX,
    }


@app.get("/ping")
def ping():
    """Ultra-light keep-warm endpoint (no DB). Use with an external cron every 5 min."""
    return {"ok": True}


@app.get("/health")
def health_check():
    db_ok = False
    db_error = None
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "database": "connected" if db_ok else "error",
        "database_error": db_error,
    }
