"""
Drift detector node.
Queries NNLM for context about the detected schema drift,
then formats it for the healer node.
"""
import logging
import uuid

from ..state import AgentState
from ...llm.nnlm_client import NNLMClient
from ...core.config import settings

logger = logging.getLogger(__name__)


async def run(state: AgentState) -> dict:
    schema_diff = state.get("schema_diff") or {}
    entity_name = state.get("entity_name", "unknown")
    session_id = state.get("nnlm_session_id") or str(uuid.uuid4())

    nnlm_payload = None
    nnlm_context = ""

    if settings.enable_nnlm and schema_diff:
        added = schema_diff.get("added", [])
        removed = schema_diff.get("removed", [])
        changed = schema_diff.get("changed", [])

        query_parts = [f"Schema drift on {entity_name}."]
        if added:
            query_parts.append(f"New fields: {', '.join(f['name'] for f in added)}")
        if removed:
            query_parts.append(f"Removed fields: {', '.join(f['name'] for f in removed)}")
        if changed:
            query_parts.append(f"Changed fields: {', '.join(c['name'] for c in changed)}")

        query = " ".join(query_parts)

        nnlm = NNLMClient()
        try:
            result = await nnlm.encode(text=query, session_id=session_id)
            nnlm_payload = result
            retrieved = result.get("query_results", []) + result.get("graph_results", [])
            if retrieved:
                nnlm_context = "\n\n".join(
                    f"[{i}] {r.get('text', '')}"
                    for i, r in enumerate(retrieved[:6])
                )
        except Exception as exc:
            logger.warning("NNLM unavailable during drift detection: %s", exc)
        finally:
            await nnlm.close()

    return {
        "nnlm_payload": nnlm_payload,
        "nnlm_session_id": session_id,
        # Store context in messages for healer node to access
        "messages": [{"role": "system", "content": f"NAM context:\n{nnlm_context}"}] if nnlm_context else [],
        "completed_steps": ["drift_detector"],
    }
