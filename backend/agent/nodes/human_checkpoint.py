"""
Human checkpoint node.
LangGraph interrupts here via interrupt_before. The API layer stores the
proposal to DB, returns the proposal ID to the caller, and the graph
resumes when the human POSTs their decision to /agent/proposals/{id}/review.
"""
import logging
import uuid
from datetime import datetime

from ..state import AgentState

logger = logging.getLogger(__name__)


async def run(state: AgentState) -> dict:
    proposal_id = state.get("proposal_id") or str(uuid.uuid4())
    logger.info(
        "Human checkpoint: pipeline=%s trigger=%s proposal=%s",
        state.get("pipeline_id"),
        state.get("trigger_type"),
        proposal_id,
    )
    # The actual interrupt is configured at the graph level with interrupt_before.
    # This node just ensures the proposal_id is in state so the API layer
    # can persist it before the graph is paused.
    return {
        "proposal_id": proposal_id,
        "completed_steps": ["human_checkpoint"],
    }
