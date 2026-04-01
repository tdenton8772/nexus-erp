"""
FastAPI application entry point for Nexus ERP Integration Platform.

Lifespan:
  - Discovers and registers connector plugins
  - Initialises DB tables (dev mode; prod uses Alembic migrations)
  - Starts Kafka producer
  - Starts APScheduler for pipeline polling
  - Bootstraps NAM/NNLM connectivity check
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.database import engine, Base
from .core.logging import configure_logging
from .connectors.registry import ConnectorRegistry
from .messaging.producer import NexusProducer

configure_logging()
logger = logging.getLogger(__name__)

_producer: NexusProducer | None = None
_registry: ConnectorRegistry = ConnectorRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Nexus ERP starting up…")

    # Auto-create tables in development (Alembic handles production)
    if settings.env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB tables ensured.")

    # Discover connector plugins
    _registry.discover()
    registered = _registry.list_registered()
    logger.info("Connectors registered: %s", registered)

    # Start Kafka producer
    global _producer
    _producer = NexusProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    try:
        await _producer.start()
        logger.info("Kafka producer started.")
    except Exception as exc:
        logger.warning("Kafka producer start failed (non-fatal): %s", exc)

    # NAM/NNLM health ping (non-fatal — system degrades gracefully)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.nam_query_url}/health")
            logger.info("NAM reachable: %s", r.status_code)
    except Exception as exc:
        logger.warning("NAM not reachable at startup (non-fatal): %s", exc)

    # Start APScheduler for active pipeline polling
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from .pipeline.poller import schedule_active_pipelines

        scheduler = AsyncIOScheduler()
        await schedule_active_pipelines(scheduler)
        scheduler.start()
        logger.info("Pipeline poller scheduler started.")
    except Exception as exc:
        logger.warning("Scheduler start failed (non-fatal): %s", exc)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Nexus ERP shutting down…")
    if scheduler:
        scheduler.shutdown(wait=False)
    if _producer:
        try:
            await _producer.stop()
        except Exception:
            pass


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nexus ERP Integration Platform",
    version="0.1.0",
    description="Pluggable, bidirectional ERP integration with AI-driven schema mapping.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

from .api.v1 import (  # noqa: E402  (import after app creation intentional)
    connectors,
    pipelines,
    schemas,
    mappings,
    agent,
    sync_events,
    health,
)

API_PREFIX = "/api/v1"

app.include_router(health.router, tags=["health"])
app.include_router(connectors.router, prefix=API_PREFIX, tags=["connectors"])
app.include_router(pipelines.router, prefix=API_PREFIX, tags=["pipelines"])
app.include_router(schemas.router, prefix=API_PREFIX, tags=["schemas"])
app.include_router(mappings.router, prefix=API_PREFIX, tags=["mappings"])
app.include_router(agent.router, prefix=API_PREFIX, tags=["agent"])
app.include_router(sync_events.router, prefix=API_PREFIX, tags=["sync-events"])
