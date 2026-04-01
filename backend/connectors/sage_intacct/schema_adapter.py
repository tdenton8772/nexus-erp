"""Normalise raw Sage Intacct object definitions into EntitySchema."""
import hashlib, json
from datetime import datetime
from ..base import EntitySchema, SchemaField

DATATYPE_MAP = {
    "TEXT": "string", "INTEGER": "integer", "DECIMAL": "decimal",
    "BOOLEAN": "boolean", "DATE": "datetime", "DATETIME": "datetime",
    "PERCENT": "decimal", "CURRENCY": "decimal",
}

class IntacctSchemaAdapter:
    def adapt(self, entity_name: str, raw: dict) -> EntitySchema:
        fields = [
            SchemaField(
                name=f["id"], canonical_name=f["id"].lower(),
                data_type=DATATYPE_MAP.get(f.get("datatype","TEXT").upper(), "string"),
                nullable=not f.get("required", False),
                erp_native_type=f.get("datatype"),
            )
            for f in raw.get("fields", []) if f.get("id")
        ]
        version_hash = hashlib.sha256(json.dumps(sorted(f.name for f in fields)).encode()).hexdigest()
        return EntitySchema(entity_name=entity_name, system_name="sage_intacct", version_hash=version_hash, fields=fields, fetched_at=datetime.utcnow())
