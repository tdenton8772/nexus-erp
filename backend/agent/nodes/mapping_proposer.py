"""
Mapping proposer node.
Queries NNLM for grounded schema context, then asks the LLM to propose
field mappings using that context — not raw hallucination.
"""
import json
import logging
import uuid

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import AgentState
from ..prompts import MAPPING_SYSTEM_PROMPT, build_mapping_user_prompt
from ...llm.nnlm_client import NNLMClient
from ...core.config import settings

logger = logging.getLogger(__name__)


async def run(state: AgentState) -> dict:
    source_schema = state.get("source_schema") or {}
    target_schema = state.get("target_schema") or {}
    human_feedback = state.get("human_feedback")
    session_id = state.get("nnlm_session_id") or str(uuid.uuid4())

    # Step 1: Query NNLM for grounded context about these schemas
    nnlm_context = ""
    nnlm_payload = None
    if settings.enable_nnlm:
        nnlm = NNLMClient()
        try:
            query = (
                f"Field mappings between {source_schema.get('system_name', 'source')} "
                f"{source_schema.get('entity_name', 'entity')} and "
                f"{target_schema.get('system_name', 'target')} "
                f"{target_schema.get('entity_name', 'entity')}"
            )
            nnlm_result = await nnlm.encode(
                text=query,
                history=state.get("messages", [])[-6:],  # last 3 turns
                session_id=session_id,
            )
            nnlm_payload = nnlm_result

            # Build context string from retrieved records
            retrieved = nnlm_result.get("query_results", []) + nnlm_result.get("graph_results", [])
            if retrieved:
                nnlm_context = "\n\n".join(
                    f"[{i}] {r.get('text', '')}"
                    for i, r in enumerate(retrieved[:8])
                )
        except Exception as exc:
            logger.warning("NNLM unavailable, proceeding without grounded context: %s", exc)
        finally:
            await nnlm.close()

    # Step 2: LLM mapping proposal grounded in NNLM context
    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )
    messages = [
        SystemMessage(content=MAPPING_SYSTEM_PROMPT),
        HumanMessage(content=build_mapping_user_prompt(
            source_schema=source_schema,
            target_schema=target_schema,
            nnlm_context=nnlm_context,
            human_feedback=human_feedback or "",
        )),
    ]

    response = await llm.ainvoke(messages)

    try:
        proposal = json.loads(response.content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown fences if present
        content = response.content
        if "```" in content:
            content = content.split("```")[1].lstrip("json").strip()
        try:
            proposal = json.loads(content)
        except Exception:
            logger.error("LLM returned non-JSON mapping proposal")
            return {"errors": ["LLM mapping proposal was not valid JSON"], "completed_steps": ["mapping_proposer"]}

    return {
        "proposed_mappings": proposal.get("field_mappings", []),
        "requires_human_approval": True,
        "nnlm_payload": nnlm_payload,
        "nnlm_session_id": session_id,
        "messages": [response],
        "completed_steps": ["mapping_proposer"],
    }
