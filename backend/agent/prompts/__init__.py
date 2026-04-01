MAPPING_SYSTEM_PROMPT = """You are an expert ERP data integration engineer.
Propose field mappings between two ERP schemas using ONLY the grounded context
and schema definitions provided. Do not invent field names.

Available transforms: passthrough, str, int, decimal_to_float, float_to_decimal,
intacct_date_to_iso8601, iso8601_to_intacct_date, upper, lower, bool_to_str, str_to_bool, compute

Return ONLY valid JSON:
{
  "field_mappings": [{"source_field":"X","target_field":"Y","transform":"passthrough","confidence":0.9,"note":""}],
  "unmapped_source_fields": [],
  "unmapped_target_fields": [],
  "confidence_scores": {"overall": 0.87}
}"""

CODEGEN_SYSTEM_PROMPT = """You are an expert Python ETL engineer.
Generate exactly two functions with no import statements:
  transform_forward(record: dict, context: dict) -> dict
  transform_reverse(record: dict, context: dict) -> dict
Allowed builtins: str, int, float, bool, list, dict, round, len, isinstance, sorted, min, max, sum.
Return raw Python source only, no markdown."""

HEALING_SYSTEM_PROMPT = """You are an ERP integration reliability engineer.
A schema drift or sync failure occurred. Using only the grounded context provided,
propose the minimum mapping changes to restore operation. Output JSON in the same
format as a mapping proposal, plus a healing_actions array."""


def build_mapping_user_prompt(source_schema, target_schema, nnlm_context="", human_feedback=""):
    import json
    p = f"Grounded context:\n{nnlm_context}\n\n" if nnlm_context else ""
    p += f"SOURCE ({source_schema.get('system_name')} — {source_schema.get('entity_name')}):\n"
    p += json.dumps(source_schema.get("fields", []), indent=2)
    p += f"\n\nTARGET ({target_schema.get('system_name')} — {target_schema.get('entity_name')}):\n"
    p += json.dumps(target_schema.get("fields", []), indent=2)
    if human_feedback:
        p += f"\n\nHuman feedback:\n{human_feedback}"
    return p


def build_codegen_user_prompt(mappings, source_schema, target_schema, nnlm_context="", prior_errors=None):
    import json
    p = f"Grounded context:\n{nnlm_context}\n\n" if nnlm_context else ""
    p += f"Generate transforms for:\n{json.dumps(mappings, indent=2)}\n"
    p += f"Source: {source_schema.get('system_name')}  Target: {target_schema.get('system_name')}"
    if prior_errors:
        p += "\n\nFix these validation errors:\n" + "\n".join(f"  - {e}" for e in prior_errors)
    return p


def build_healing_user_prompt(schema_diff, failure_details, existing_mappings, nnlm_context=""):
    import json
    p = f"Grounded context:\n{nnlm_context}\n\n" if nnlm_context else ""
    if schema_diff:
        p += f"Schema drift:\n{json.dumps(schema_diff, indent=2)}\n\n"
    if failure_details:
        p += f"Failure details:\n{json.dumps(failure_details, indent=2)}\n\n"
    p += f"Existing mappings:\n{json.dumps(existing_mappings, indent=2)}\n"
    p += "\nPropose minimum changes to restore correct operation."
    return p
