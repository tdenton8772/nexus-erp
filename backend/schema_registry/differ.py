"""Structured diff between two schema snapshots."""


class SchemaDiffer:
    def diff(self, old_schema: dict, new_schema: dict) -> dict:
        """
        Compare two schema dicts (EntitySchema.model_dump() format).
        Returns {added: [...], removed: [...], changed: [...]}.
        """
        old_fields = {f["name"]: f for f in old_schema.get("fields", [])}
        new_fields = {f["name"]: f for f in new_schema.get("fields", [])}

        added = [
            {"name": n, "type": f["data_type"]}
            for n, f in new_fields.items()
            if n not in old_fields
        ]
        removed = [
            {"name": n, "type": f["data_type"]}
            for n, f in old_fields.items()
            if n not in new_fields
        ]
        changed = []
        for name in set(old_fields) & set(new_fields):
            old_f = old_fields[name]
            new_f = new_fields[name]
            if old_f.get("data_type") != new_f.get("data_type") or old_f.get("nullable") != new_f.get("nullable"):
                changed.append({
                    "name": name,
                    "old": {"type": old_f.get("data_type"), "nullable": old_f.get("nullable")},
                    "new": {"type": new_f.get("data_type"), "nullable": new_f.get("nullable")},
                })

        return {"added": added, "removed": removed, "changed": changed}
