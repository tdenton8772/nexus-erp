"""
TransformSandbox: safely execute compiler- or LLM-generated Python
transformation code using RestrictedPython + AST validation.

Security model:
  - No imports allowed (ast.Import / ast.ImportFrom are rejected)
  - Only whitelisted builtins available
  - All execution is in-process (low latency, sufficient for transform functions)
"""
import ast
import logging
from typing import Any, Callable

from RestrictedPython import compile_restricted, safe_builtins, safe_globals

logger = logging.getLogger(__name__)

ALLOWED_BUILTINS = {
    **safe_builtins,
    "round": round,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "isinstance": isinstance,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
}


class SandboxViolationError(Exception):
    pass


class TransformSandbox:

    @staticmethod
    def validate_ast(code: str) -> None:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise SandboxViolationError(
                    f"Import statements are not allowed in transformation code"
                )

    @staticmethod
    def compile_transform(code: str) -> dict[str, Callable]:
        """
        Compile and return {fn_name: callable} for all functions in code.
        Raises SandboxViolationError or SyntaxError on invalid code.
        """
        TransformSandbox.validate_ast(code)
        try:
            bytecode = compile_restricted(code, filename="<transform>", mode="exec")
        except SyntaxError as exc:
            raise SyntaxError(f"Transformation code syntax error: {exc}") from exc

        glb: dict[str, Any] = {
            **safe_globals,
            "__builtins__": ALLOWED_BUILTINS,
        }
        exec(bytecode, glb)  # noqa: S102

        return {k: v for k, v in glb.items() if callable(v) and not k.startswith("_")}

    @staticmethod
    def run(fn: Callable, record: dict, context: dict) -> dict:
        result = fn(record, context)
        if not isinstance(result, dict):
            raise ValueError(f"Transform must return dict, got {type(result).__name__}")
        return result


class TransformationEngine:
    """
    Loads compiled transformation code for a pipeline and executes it
    against incoming SyncRecords.
    """

    def __init__(self, forward_code: str, reverse_code: str) -> None:
        self._forward_fns = TransformSandbox.compile_transform(forward_code)
        self._reverse_fns = TransformSandbox.compile_transform(reverse_code)

    def transform_forward(self, record: dict, context: dict | None = None) -> dict:
        fn = self._forward_fns.get("transform_forward")
        if fn is None:
            raise KeyError("transform_forward function not found in compiled code")
        return TransformSandbox.run(fn, record, context or {})

    def transform_reverse(self, record: dict, context: dict | None = None) -> dict:
        fn = self._reverse_fns.get("transform_reverse")
        if fn is None:
            raise KeyError("transform_reverse function not found in compiled code")
        return TransformSandbox.run(fn, record, context or {})
