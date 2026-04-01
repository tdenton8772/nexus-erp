"""LangGraph agent state definition."""
from typing import Annotated, Any, Optional
import operator
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # Trigger context
    trigger_type: str               # schema_mapping | drift | failure | manual
    pipeline_id: Optional[str]
    connector_id: Optional[str]
    entity_name: Optional[str]

    # Schema context
    source_schema: Optional[dict]
    target_schema: Optional[dict]
    schema_diff: Optional[dict]

    # NNLM grounded context
    nnlm_payload: Optional[dict]    # Full EncodeResponse from NNLM
    nnlm_response: Optional[str]    # Decoded grounded synthesis
    nnlm_citations: Optional[list]  # Citation indices into query_results
    nnlm_session_id: Optional[str]  # Conversation session for multi-turn

    # Proposals (pre-approval)
    proposed_mappings: Optional[list[dict]]
    approved_mappings: Optional[list[dict]]

    # Code generation
    generated_code: Optional[dict]              # {forward: str, reverse: str}
    code_validation_result: Optional[dict]      # {passed, errors, warnings}

    # Self-healing
    failure_details: Optional[dict]
    healing_actions: Optional[list[dict]]

    # Human-in-the-loop
    requires_human_approval: bool
    human_decision: Optional[str]               # approve | reject | modify
    human_feedback: Optional[str]
    proposal_id: Optional[str]                  # DB AgentProposal.id

    # Accumulated fields
    messages: Annotated[list[Any], operator.add]
    errors: Annotated[list[str], operator.add]
    completed_steps: Annotated[list[str], operator.add]
