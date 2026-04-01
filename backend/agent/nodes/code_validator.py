"""Code validator node — runs generated code through the sandbox validator."""
from ..state import AgentState
from ...transformation.validator import TransformValidator


async def run(state: AgentState) -> dict:
    generated = state.get("generated_code") or {}
    forward_code = generated.get("forward", "")
    reverse_code = generated.get("reverse", "")

    validator = TransformValidator()
    result = validator.validate(forward_code, reverse_code)

    return {
        "code_validation_result": result,
        "completed_steps": ["code_validator"],
    }
