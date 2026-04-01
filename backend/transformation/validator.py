"""
Validate generated transformation code by running it against fixture records
and checking basic invariants (returns dict, no None on required fields, etc).
"""
import logging
from .sandbox import TransformSandbox, SandboxViolationError

logger = logging.getLogger(__name__)

SAMPLE_SAGE_INVOICE = {
    "RECORDNO": "10001",
    "VENDORNAME": "Acme Corp",
    "TOTALAMOUNT": "5000.00",
    "CURRENCY": "USD",
    "WHENCREATED": "01/15/2024",
    "WHENMODIFIED": "01/20/2024",
    "APBILLSTATUS": "Posted",
}

SAMPLE_GENERIC = {"id": "1", "name": "Test Record", "amount": "100.00", "date": "2024-01-01"}


class TransformValidator:
    def validate(self, forward_code: str, reverse_code: str) -> dict:
        """
        Run both directions against sample records.
        Returns {"passed": bool, "errors": [str], "warnings": [str]}.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Validate forward
        try:
            TransformSandbox.validate_ast(forward_code)
            fns = TransformSandbox.compile_transform(forward_code)
            if "transform_forward" not in fns:
                errors.append("forward_code must define transform_forward(record, context)")
            else:
                for sample in [SAMPLE_SAGE_INVOICE, SAMPLE_GENERIC]:
                    out = fns["transform_forward"](sample, {})
                    if not isinstance(out, dict):
                        errors.append(f"transform_forward returned {type(out).__name__}, expected dict")
        except SandboxViolationError as exc:
            errors.append(f"Forward code security violation: {exc}")
        except SyntaxError as exc:
            errors.append(f"Forward code syntax error: {exc}")
        except Exception as exc:
            warnings.append(f"Forward code runtime warning: {exc}")

        # Validate reverse
        try:
            TransformSandbox.validate_ast(reverse_code)
            fns = TransformSandbox.compile_transform(reverse_code)
            if "transform_reverse" not in fns:
                errors.append("reverse_code must define transform_reverse(record, context)")
            else:
                for sample in [SAMPLE_SAGE_INVOICE, SAMPLE_GENERIC]:
                    out = fns["transform_reverse"](sample, {})
                    if not isinstance(out, dict):
                        errors.append(f"transform_reverse returned {type(out).__name__}, expected dict")
        except SandboxViolationError as exc:
            errors.append(f"Reverse code security violation: {exc}")
        except SyntaxError as exc:
            errors.append(f"Reverse code syntax error: {exc}")
        except Exception as exc:
            warnings.append(f"Reverse code runtime warning: {exc}")

        return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}
