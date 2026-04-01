"""APScheduler-based poller for active pipelines.

Each active pipeline gets a job that fires every `poll_interval_seconds`
and enqueues a Celery sync task rather than running inline — keeps the
scheduler lightweight and lets Celery workers handle concurrency.
"""
import logging

from sqlalchemy import select

from ..core.database import AsyncSessionLocal
from ..db.models import Pipeline

logger = logging.getLogger(__name__)


async def schedule_active_pipelines(scheduler) -> None:
    """Read active pipelines from DB and register polling jobs."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Pipeline).where(Pipeline.status == "active")
        )
        pipelines = result.scalars().all()

    for pipeline in pipelines:
        _add_pipeline_job(scheduler, pipeline)

    logger.info("Scheduled %d active pipeline(s) for polling.", len(pipelines))


def _add_pipeline_job(scheduler, pipeline) -> None:
    interval = pipeline.poll_interval_seconds or 300

    scheduler.add_job(
        _enqueue_sync,
        "interval",
        seconds=interval,
        id=f"pipeline_{pipeline.id}",
        args=[pipeline.id],
        replace_existing=True,
    )
    logger.debug("Registered poll job for pipeline %s every %ds", pipeline.id, interval)


async def _enqueue_sync(pipeline_id: str) -> None:
    """Fire-and-forget: enqueue a Celery sync task."""
    try:
        from ..workers.sync_tasks import run_pipeline_sync
        run_pipeline_sync.delay(pipeline_id)
    except Exception as exc:
        logger.error("Failed to enqueue sync for pipeline %s: %s", pipeline_id, exc)
