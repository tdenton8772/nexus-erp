"""
LangGraph agent graphs.

Two graphs:
  1. schema_mapping_graph  — initial mapping when a new pipeline is configured
  2. healing_graph         — self-healing after schema drift or sync failure

Both graphs pause at human_checkpoint for human approval before generating code.
The graphs use LangGraph's interrupt_before mechanism so they can be persisted
and resumed across HTTP requests via LangGraph checkpointing.
"""
from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import (
    mapping_proposer,
    code_generator,
    code_validator,
    drift_detector,
    healer,
    human_checkpoint,
)


def _human_decision_router(state: AgentState) -> str:
    decision = state.get("human_decision")
    if decision == "approve":
        return "generate_code"
    if decision == "modify":
        return "repropose"
    return END  # reject


def _validation_router(state: AgentState) -> str:
    result = state.get("code_validation_result") or {}
    if result.get("passed"):
        return END
    errors = result.get("errors", [])
    # Give up after 3 accumulated codegen steps to avoid infinite loops
    steps = state.get("completed_steps", [])
    codegen_attempts = steps.count("code_generator")
    if codegen_attempts >= 3:
        return END
    return "regenerate"


def build_schema_mapping_graph() -> StateGraph:
    """
    Flow:
      propose_mappings → human_checkpoint → [approve] → generate_code
                                          → [modify]  → propose_mappings (with feedback)
                                          → [reject]  → END
      generate_code → validate_code → [pass] → END
                                    → [fail] → generate_code (retry, max 3)
    """
    g = StateGraph(AgentState)

    g.add_node("propose_mappings", mapping_proposer.run)
    g.add_node("human_checkpoint", human_checkpoint.run)
    g.add_node("generate_code", code_generator.run)
    g.add_node("validate_code", code_validator.run)

    g.set_entry_point("propose_mappings")
    g.add_edge("propose_mappings", "human_checkpoint")

    g.add_conditional_edges(
        "human_checkpoint",
        _human_decision_router,
        {
            "generate_code": "generate_code",
            "repropose": "propose_mappings",
            END: END,
        },
    )

    g.add_edge("generate_code", "validate_code")
    g.add_conditional_edges(
        "validate_code",
        _validation_router,
        {"regenerate": "generate_code", END: END},
    )

    return g.compile(interrupt_before=["human_checkpoint"])


def build_healing_graph() -> StateGraph:
    """
    Flow:
      detect_drift → propose_healing → human_checkpoint → [approve] → generate_code
                                                        → [modify]  → propose_healing
                                                        → [reject]  → END
      generate_code → validate_code → [pass] → END
                                    → [fail] → generate_code (retry, max 3)
    """
    g = StateGraph(AgentState)

    g.add_node("detect_drift", drift_detector.run)
    g.add_node("propose_healing", healer.run)
    g.add_node("human_checkpoint", human_checkpoint.run)
    g.add_node("generate_code", code_generator.run)
    g.add_node("validate_code", code_validator.run)

    g.set_entry_point("detect_drift")
    g.add_edge("detect_drift", "propose_healing")
    g.add_edge("propose_healing", "human_checkpoint")

    g.add_conditional_edges(
        "human_checkpoint",
        _human_decision_router,
        {
            "generate_code": "generate_code",
            "repropose": "propose_healing",
            END: END,
        },
    )

    g.add_edge("generate_code", "validate_code")
    g.add_conditional_edges(
        "validate_code",
        _validation_router,
        {"regenerate": "generate_code", END: END},
    )

    return g.compile(interrupt_before=["human_checkpoint"])


# Compiled graph singletons (instantiated once at startup)
schema_mapping_graph = build_schema_mapping_graph()
healing_graph = build_healing_graph()
