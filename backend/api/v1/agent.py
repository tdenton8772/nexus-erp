"""
Agent endpoints.
- Trigger schema mapping or healing runs
- List/review proposals (human-in-the-loop)
- Check run status
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...db.models import AgentProposal, AgentProposalStatus, Pipeline, FieldMapping, CompiledTransformation
from ...transformation.compiler import MappingCompiler
from ...transformation.validator import TransformValidator
from ...llm.schema_indexer import SchemaIndexer
from ...llm.nam_client import NAMClient

router = APIRouter()


class TriggerAgentRun(BaseModel):
    trigger_type: str           # schema_mapping | healing
    pipeline_id: str | None = None
    connector_id: str | None = None
    entity_name: str | None = None


class ReviewProposal(BaseModel):
    decision: str               # approve | reject | modify
    feedback: str | None = None


@router.post("/run", status_code=202)
async def trigger_agent_run(
    body: TriggerAgentRun,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    run_id = str(uuid.uuid4())

    async def _run():
        from ...core.database import AsyncSessionLocal
        from ...agent.graph import schema_mapping_graph, healing_graph
        from ...schema_registry.service import SchemaRegistryService
        from ...connectors.registry import ConnectorRegistry
        from ...connectors.base import ConnectorConfig
        from ...core.security import decrypt_credentials
        from ...db.models import ConnectorRecord

        async with AsyncSessionLocal() as session:
            initial_state: dict = {
                "trigger_type": body.trigger_type,
                "pipeline_id": body.pipeline_id,
                "connector_id": body.connector_id,
                "entity_name": body.entity_name,
                "requires_human_approval": True,
                "messages": [],
                "errors": [],
                "completed_steps": [],
            }

            # Load schemas if pipeline is given
            if body.pipeline_id:
                pipeline_result = await session.execute(
                    select(Pipeline).where(Pipeline.id == body.pipeline_id)
                )
                pipeline = pipeline_result.scalar_one_or_none()
                if pipeline:
                    svc = SchemaRegistryService(session)
                    src_schema = await svc.get_current_schema(pipeline.source_connector_id, pipeline.entity_name)
                    tgt_schema = await svc.get_current_schema(pipeline.target_connector_id, pipeline.entity_name)
                    if src_schema:
                        initial_state["source_schema"] = src_schema.schema_json
                    if tgt_schema:
                        initial_state["target_schema"] = tgt_schema.schema_json

            graph = schema_mapping_graph if body.trigger_type == "schema_mapping" else healing_graph

            # Run until the human checkpoint interrupt
            config = {"configurable": {"thread_id": run_id}}
            async for _ in graph.astream(initial_state, config=config):
                pass  # graph will pause at human_checkpoint

    background_tasks.add_task(_run)
    return {"run_id": run_id, "status": "started"}


@router.get("/proposals")
async def list_proposals(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AgentProposal).order_by(AgentProposal.created_at.desc())
    if status:
        stmt = stmt.where(AgentProposal.status == AgentProposalStatus(status))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"items": [_serialize_proposal(p) for p in rows]}


@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentProposal).where(AgentProposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _serialize_proposal(proposal)


@router.post("/proposals/{proposal_id}/review")
async def review_proposal(
    proposal_id: str,
    body: ReviewProposal,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AgentProposal).where(AgentProposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    proposal.status = AgentProposalStatus(
        "approved" if body.decision == "approve"
        else "rejected" if body.decision == "reject"
        else "pending_review"  # modify keeps it pending
    )
    proposal.human_feedback = body.feedback
    proposal.reviewed_at = datetime.utcnow()
    await db.commit()

    if body.decision == "approve" and proposal.pipeline_id:
        background_tasks.add_task(_apply_approved_proposal, proposal_id, proposal.pipeline_id)

    return {"status": proposal.status.value, "proposal_id": proposal_id}


async def _apply_approved_proposal(proposal_id: str, pipeline_id: str) -> None:
    """
    After human approval: persist FieldMappings, compile transformation code,
    validate it, save CompiledTransformation, and index in NAM.
    """
    from ...core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AgentProposal).where(AgentProposal.id == proposal_id))
        proposal = result.scalar_one_or_none()
        if not proposal:
            return

        mappings_data = proposal.proposal_json.get("field_mappings", [])

        # Persist FieldMappings
        for m in mappings_data:
            fm = FieldMapping(
                id=str(uuid.uuid4()),
                pipeline_id=pipeline_id,
                source_field=m.get("source_field"),
                target_field=m.get("target_field"),
                transform_name=m.get("transform", "passthrough"),
                expression=m.get("expression"),
            )
            db.add(fm)

        await db.commit()

        # Compile and validate transformation code
        compiler = MappingCompiler()
        code = compiler.compile(mappings_data)

        validator = TransformValidator()
        validation = validator.validate(code["forward"], code["reverse"])

        import hashlib, json
        code_hash = hashlib.sha256(
            json.dumps(code, sort_keys=True).encode()
        ).hexdigest()

        # Upsert CompiledTransformation
        existing = await db.execute(
            select(CompiledTransformation).where(CompiledTransformation.pipeline_id == pipeline_id)
        )
        compiled = existing.scalar_one_or_none()

        if compiled:
            compiled.forward_code = code["forward"]
            compiled.reverse_code = code["reverse"]
            compiled.code_hash = code_hash
            compiled.generated_by = "compiler"
            compiled.validation_passed = validation["passed"]
            compiled.validation_report = validation
            compiled.version += 1
            compiled.updated_at = datetime.utcnow()
        else:
            db.add(CompiledTransformation(
                id=str(uuid.uuid4()),
                pipeline_id=pipeline_id,
                forward_code=code["forward"],
                reverse_code=code["reverse"],
                code_hash=code_hash,
                generated_by="compiler",
                validation_passed=validation["passed"],
                validation_report=validation,
            ))

        proposal.status = AgentProposalStatus.APPLIED
        await db.commit()

        # Index approved mapping into NAM
        nam = NAMClient()
        indexer = SchemaIndexer(nam)
        await indexer.index_approved_mapping(pipeline_id, mappings_data)
        await nam.close()


def _serialize_proposal(p: AgentProposal) -> dict:
    return {
        "id": p.id,
        "pipeline_id": p.pipeline_id,
        "trigger_type": p.trigger_type,
        "status": p.status.value if p.status else None,
        "proposal_json": p.proposal_json,
        "human_feedback": p.human_feedback,
        "reviewed_by": p.reviewed_by,
        "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        "agent_run_id": p.agent_run_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
