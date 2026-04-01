"""Celery tasks for agent-driven workflows.

These tasks run LangGraph graphs asynchronously so that HTTP requests
return immediately while long-running LLM calls happen in the background.
"""
import asyncio
import logging

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="backend.workers.agent_tasks.run_schema_mapping_agent",
    max_retries=1,
    default_retry_delay=120,
)
def run_schema_mapping_agent(self, pipeline_id: str, proposal_id: str):
    """Run the schema_mapping_graph for a pipeline.

    Stores intermediate state in LangGraph checkpointer.
    Pauses automatically at human_checkpoint until resumed via API.
    """
    logger.info("Running schema mapping agent for pipeline %s", pipeline_id)
    try:
        _run_async(_async_schema_mapping_agent(pipeline_id, proposal_id))
    except Exception as exc:
        logger.error("Schema mapping agent failed for pipeline %s: %s", pipeline_id, exc)
        raise self.retry(exc=exc)


async def _async_schema_mapping_agent(pipeline_id: str, proposal_id: str):
    from ..core.database import AsyncSessionLocal
    from ..db.models import AgentProposal, Pipeline, SchemaVersion
    from ..agent.graph import schema_mapping_graph
    from ..agent.state import AgentState
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        proposal_result = await db.execute(
            select(AgentProposal).where(AgentProposal.id == proposal_id)
        )
        proposal = proposal_result.scalar_one_or_none()
        if not proposal:
            logger.warning("Proposal %s not found", proposal_id)
            return

        pipeline_result = await db.execute(
            select(Pipeline).where(Pipeline.id == pipeline_id)
        )
        pipeline = pipeline_result.scalar_one_or_none()
        if not pipeline:
            return

        # Fetch latest schemas for source and target connectors
        async def _latest_schema(connector_id, entity_name):
            r = await db.execute(
                select(SchemaVersion)
                .where(
                    SchemaVersion.connector_id == connector_id,
                    SchemaVersion.entity_name == entity_name,
                )
                .order_by(SchemaVersion.version_number.desc())
                .limit(1)
            )
            sv = r.scalar_one_or_none()
            return sv.schema_json if sv else {}

        source_schema = await _latest_schema(
            pipeline.source_connector_id, pipeline.source_entity
        )
        target_schema = await _latest_schema(
            pipeline.target_connector_id, pipeline.target_entity
        )

        initial_state: AgentState = {
            "pipeline_id": pipeline_id,
            "proposal_id": proposal_id,
            "source_schema": source_schema,
            "target_schema": target_schema,
            "source_connector_type": "",
            "target_connector_type": "",
            "proposed_mappings": [],
            "human_feedback": None,
            "human_decision": None,
            "generated_forward_code": None,
            "generated_reverse_code": None,
            "code_validation_result": None,
            "drift_description": None,
            "healing_proposal": None,
            "nnlm_payload": None,
            "nnlm_response": None,
            "nnlm_citations": [],
            "nnlm_session_id": proposal_id,
            "completed_steps": [],
            "errors": [],
        }

        config = {"configurable": {"thread_id": proposal_id}}
        await schema_mapping_graph.ainvoke(initial_state, config=config)

        proposal.status = "awaiting_review"
        await db.commit()
        logger.info("Schema mapping agent paused at human_checkpoint for proposal %s", proposal_id)


@celery_app.task(
    bind=True,
    name="backend.workers.agent_tasks.run_healing_agent",
    max_retries=1,
    default_retry_delay=120,
)
def run_healing_agent(self, pipeline_id: str, proposal_id: str, drift_description: str):
    """Run the healing_graph for a pipeline after schema drift."""
    logger.info("Running healing agent for pipeline %s", pipeline_id)
    try:
        _run_async(_async_healing_agent(pipeline_id, proposal_id, drift_description))
    except Exception as exc:
        logger.error("Healing agent failed for pipeline %s: %s", pipeline_id, exc)
        raise self.retry(exc=exc)


async def _async_healing_agent(pipeline_id: str, proposal_id: str, drift_description: str):
    from ..core.database import AsyncSessionLocal
    from ..db.models import AgentProposal, Pipeline, SchemaVersion
    from ..agent.graph import healing_graph
    from ..agent.state import AgentState
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        pipeline_result = await db.execute(
            select(Pipeline).where(Pipeline.id == pipeline_id)
        )
        pipeline = pipeline_result.scalar_one_or_none()
        if not pipeline:
            return

        async def _latest_schema(connector_id, entity_name):
            r = await db.execute(
                select(SchemaVersion)
                .where(
                    SchemaVersion.connector_id == connector_id,
                    SchemaVersion.entity_name == entity_name,
                )
                .order_by(SchemaVersion.version_number.desc())
                .limit(1)
            )
            sv = r.scalar_one_or_none()
            return sv.schema_json if sv else {}

        source_schema = await _latest_schema(
            pipeline.source_connector_id, pipeline.source_entity
        )
        target_schema = await _latest_schema(
            pipeline.target_connector_id, pipeline.target_entity
        )

        initial_state: AgentState = {
            "pipeline_id": pipeline_id,
            "proposal_id": proposal_id,
            "source_schema": source_schema,
            "target_schema": target_schema,
            "source_connector_type": "",
            "target_connector_type": "",
            "proposed_mappings": [],
            "human_feedback": None,
            "human_decision": None,
            "generated_forward_code": None,
            "generated_reverse_code": None,
            "code_validation_result": None,
            "drift_description": drift_description,
            "healing_proposal": None,
            "nnlm_payload": None,
            "nnlm_response": None,
            "nnlm_citations": [],
            "nnlm_session_id": proposal_id,
            "completed_steps": [],
            "errors": [],
        }

        config = {"configurable": {"thread_id": proposal_id}}
        await healing_graph.ainvoke(initial_state, config=config)

        proposal_result = await db.execute(
            select(AgentProposal).where(AgentProposal.id == proposal_id)
        )
        proposal = proposal_result.scalar_one_or_none()
        if proposal:
            proposal.status = "awaiting_review"
            await db.commit()

        logger.info("Healing agent paused at human_checkpoint for proposal %s", proposal_id)
