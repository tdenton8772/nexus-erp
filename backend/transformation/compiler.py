"""
MappingCompiler: converts a list of FieldMapping DB records into executable
Python source code for both forward (source→target) and reverse (target→source)
transformation functions.

Generated code is always:
    def transform_forward(record: dict, context: dict) -> dict
    def transform_reverse(record: dict, context: dict) -> dict
"""
import textwrap

BUILTIN_TRANSFORMS: dict[str, str] = {
    "passthrough":              "lambda v, ctx: v",
    "str":                      "lambda v, ctx: str(v) if v is not None else None",
    "int":                      "lambda v, ctx: int(v) if v is not None else None",
    "decimal_to_float":         "lambda v, ctx: float(v) if v is not None else None",
    "float_to_decimal":         "lambda v, ctx: str(round(float(v), 10)) if v is not None else None",
    "intacct_date_to_iso8601":  "lambda v, ctx: v[:10] if v else None",
    "iso8601_to_intacct_date":  "lambda v, ctx: v",
    "upper":                    "lambda v, ctx: v.upper() if v else None",
    "lower":                    "lambda v, ctx: v.lower() if v else None",
    "bool_to_str":              "lambda v, ctx: 'true' if v else 'false'",
    "str_to_bool":              "lambda v, ctx: str(v).lower() in ('true','1','yes')",
}

REVERSE_TRANSFORMS: dict[str, str] = {
    "passthrough":              "passthrough",
    "str":                      "passthrough",
    "decimal_to_float":         "float_to_decimal",
    "float_to_decimal":         "decimal_to_float",
    "intacct_date_to_iso8601":  "iso8601_to_intacct_date",
    "iso8601_to_intacct_date":  "intacct_date_to_iso8601",
    "upper":                    "lower",
    "lower":                    "upper",
    "bool_to_str":              "str_to_bool",
    "str_to_bool":              "bool_to_str",
}


class MappingCompiler:
    def compile(self, field_mappings: list[dict]) -> dict[str, str]:
        """
        Args:
            field_mappings: list of FieldMapping dicts (from DB .as_dict() or Pydantic)
        Returns:
            {"forward": "<python source>", "reverse": "<python source>"}
        """
        forward = self._build_function("transform_forward", field_mappings, forward=True)
        reverse = self._build_function("transform_reverse", field_mappings, forward=False)
        return {"forward": forward, "reverse": reverse}

    def _build_function(self, fn_name: str, mappings: list[dict], forward: bool) -> str:
        lines = ["    result = {}"]

        for m in mappings:
            src = m.get("source_field")
            tgt = m.get("target_field")
            transform_name = m.get("transform_name", "passthrough")
            expression = m.get("expression")

            if forward:
                from_field, to_field = src, tgt
                xform = BUILTIN_TRANSFORMS.get(transform_name, BUILTIN_TRANSFORMS["passthrough"])
            else:
                from_field, to_field = tgt, src
                rev = REVERSE_TRANSFORMS.get(transform_name, "passthrough")
                xform = BUILTIN_TRANSFORMS.get(rev, BUILTIN_TRANSFORMS["passthrough"])

            # Computed field (expression-based, forward only)
            if from_field is None and forward and expression and to_field:
                safe_name = to_field.replace(".", "_").replace("-", "_")
                indented = textwrap.indent(expression.strip(), "        ")
                lines.append(f"    def _compute_{safe_name}(record, context):")
                lines.append(indented)
                lines.append(f"    result['{to_field}'] = _compute_{safe_name}(record, context)")
                continue

            if from_field and to_field and xform:
                lines.append(
                    f"    result['{to_field}'] = ({xform})(record.get('{from_field}'), context)"
                )

        lines.append("    return result")
        body = "\n".join(lines)
        return f"def {fn_name}(record: dict, context: dict) -> dict:\n{body}\n"
