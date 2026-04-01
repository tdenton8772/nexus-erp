"""
Healer node.
Uses NNLM-grounded context + schema diff / failure details to propose
the minimum mapping changes that restore correct pipeline operation.
"""
import json
import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import AgentState
from ..prompts import HEALING_SYSTEM_PROMPT, build_healing_user_prompt
from ...core.config import settings

logger = logging.getLogger(__name__)


async def run(state: AgentState) -> dict:
    schema_diff = state.get("schema_diff")
    failure_details = state.get("failure_details")
    existing_mappings = state.get("approved_mappings") or []
    human_feedback = state.get("human_feedback")

    # Extract NNLM context stored by drift_detector
    nnlm_context = ""
    nnlm_payload = state.get("nnlm_payload")
    if nnlm_payload:
        retrieved = nnlm_payload.get("query_results", []) + nnlm_payload.get("graph_results", [])
        nnlm_context = "\n\n".join(
            f"[{i}] {r.get('text', '')}"
            for i, r in enumerate(retrieved[:6])
        )

    if human_feedback:
        nnlm_context = f"Human feedback: {human_feedback}\n\n" + nnlm_context

    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )
    messages = [
        SystemMessage(content=HEALING_SYSTEM_PROMPT),
        HumanMessage(content=build_healing_user_prompt(
            schema_diff=schema_diff,
            failure_details=failure_details,
            existing_mappings=existing_mappings,
            nnlm_context=nnlm_context,
        )),
    ]

    response = await llm.ainvoke(messages)

    try:
        proposal = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        if "```" in content:
            content = content.split("```")[1].lstrip("json").strip()
        try:
            proposal = json.loads(content)
        except Exception:
            logger.error("Healer LLM returned non-JSON")
            return {"errors": ["Healer LLM returned non-JSON"], "completed_steps": ["healer"]}

    return {
        "proposed_mappings": proposal.get("field_mappings", []),
        "healing_actions": proposal.get("healing_actions", []),
        "requires_human_approval": True,
        "messages": [response],
        "completed_steps": ["healer"],
    }
