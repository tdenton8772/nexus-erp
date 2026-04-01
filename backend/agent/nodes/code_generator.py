"""
Code generator node.
Uses NNLM-grounded context + approved mappings to generate transformation Python code.
"""
import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import AgentState
from ..prompts import CODEGEN_SYSTEM_PROMPT, build_codegen_user_prompt
from ...core.config import settings

logger = logging.getLogger(__name__)


async def run(state: AgentState) -> dict:
    mappings = state.get("approved_mappings") or state.get("proposed_mappings") or []
    source_schema = state.get("source_schema") or {}
    target_schema = state.get("target_schema") or {}
    prior_errors = None

    if state.get("code_validation_result") and not state["code_validation_result"].get("passed"):
        prior_errors = state["code_validation_result"].get("errors", [])

    # Reuse NNLM context retrieved during mapping proposal (already paid for)
    nnlm_context = ""
    nnlm_payload = state.get("nnlm_payload")
    if nnlm_payload:
        retrieved = nnlm_payload.get("query_results", []) + nnlm_payload.get("graph_results", [])
        if retrieved:
            nnlm_context = "\n\n".join(
                f"[{i}] {r.get('text', '')}"
                for i, r in enumerate(retrieved[:6])
            )

    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )
    messages = [
        SystemMessage(content=CODEGEN_SYSTEM_PROMPT),
        HumanMessage(content=build_codegen_user_prompt(
            mappings=mappings,
            source_schema=source_schema,
            target_schema=target_schema,
            nnlm_context=nnlm_context,
            prior_errors=prior_errors,
        )),
    ]

    response = await llm.ainvoke(messages)

    # Strip markdown fences
    code = response.content
    for fence in ("```python", "```"):
        if fence in code:
            code = code.split(fence, 1)[-1].rsplit("```", 1)[0].strip()
            break

    # Split into forward and reverse functions
    forward_code = _extract_function(code, "transform_forward")
    reverse_code = _extract_function(code, "transform_reverse")

    return {
        "generated_code": {"forward": forward_code, "reverse": reverse_code, "full": code},
        "messages": [response],
        "completed_steps": ["code_generator"],
    }


def _extract_function(code: str, fn_name: str) -> str:
    """Extract a single function definition from a source string."""
    lines = code.splitlines()
    collecting = False
    result_lines = []
    for line in lines:
        if line.startswith(f"def {fn_name}("):
            collecting = True
        if collecting:
            result_lines.append(line)
            # Stop at the next top-level def (non-indented) after start
            if result_lines and len(result_lines) > 1 and line.startswith("def ") and not line.startswith(f"def {fn_name}("):
                result_lines.pop()
                break
    return "\n".join(result_lines) if result_lines else code
