"""Initial schema — all Nexus ERP tables.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("connector_type", sa.String, nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("credentials", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String, nullable=False, server_default="inactive"),
        sa.Column("last_tested_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "schema_versions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("connector_id", sa.String, sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_name", sa.String, nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("schema_json", JSONB, nullable=False),
        sa.Column("schema_hash", sa.String, nullable=False),
        sa.Column("discovered_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_schema_versions_connector_entity", "schema_versions", ["connector_id", "entity_name"])

    op.create_table(
        "schema_diffs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("connector_id", sa.String, sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_name", sa.String, nullable=False),
        sa.Column("from_version", sa.Integer, nullable=False),
        sa.Column("to_version", sa.Integer, nullable=False),
        sa.Column("diff_json", JSONB, nullable=False),
        sa.Column("detected_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "pipelines",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("source_connector_id", sa.String, sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("target_connector_id", sa.String, sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("source_entity", sa.String, nullable=False),
        sa.Column("target_entity", sa.String, nullable=False),
        sa.Column("direction", sa.String, nullable=False, server_default="both"),
        sa.Column("status", sa.String, nullable=False, server_default="inactive"),
        sa.Column("poll_interval_seconds", sa.Integer, server_default="300"),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "field_mappings",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pipeline_id", sa.String, sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_field", sa.String, nullable=True),
        sa.Column("target_field", sa.String, nullable=True),
        sa.Column("transform_name", sa.String, nullable=False, server_default="passthrough"),
        sa.Column("transform_args", JSONB, nullable=True),
        sa.Column("expression", sa.Text, nullable=True),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("ix_field_mappings_pipeline", "field_mappings", ["pipeline_id"])

    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pipeline_id", sa.String, sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("proposed_mappings", JSONB, nullable=False, server_default="[]"),
        sa.Column("human_feedback", sa.Text, nullable=True),
        sa.Column("human_decision", sa.String, nullable=True),
        sa.Column("reviewed_by", sa.String, nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("nnlm_session_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "compiled_transformations",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pipeline_id", sa.String, sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("forward_code", sa.Text, nullable=False),
        sa.Column("reverse_code", sa.Text, nullable=False),
        sa.Column("code_hash", sa.String, nullable=False),
        sa.Column("generated_by", sa.String, nullable=False, server_default="compiler"),
        sa.Column("llm_model", sa.String, nullable=True),
        sa.Column("validation_passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("validation_report", JSONB, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "sync_events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pipeline_id", sa.String, sa.ForeignKey("pipelines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_name", sa.String, nullable=False),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("record_id", sa.String, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("payload_hash", sa.String, nullable=True),
        sa.Column("synced_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_sync_events_pipeline_status", "sync_events", ["pipeline_id", "status"])
    op.create_index("ix_sync_events_synced_at", "sync_events", ["synced_at"])

    op.create_table(
        "external_id_map",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pipeline_id", sa.String, sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.String, nullable=False),
        sa.Column("source_record_id", sa.String, nullable=False),
        sa.Column("target_system", sa.String, nullable=False),
        sa.Column("target_record_id", sa.String, nullable=True),
        sa.Column("entity_name", sa.String, nullable=False),
        sa.Column("payload_hash", sa.String, nullable=True),
        sa.Column("last_synced_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_external_id_map_source",
        "external_id_map",
        ["pipeline_id", "source_system", "source_record_id"],
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pipeline_id", sa.String, sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="running"),
        sa.Column("direction", sa.String, nullable=False, server_default="both"),
        sa.Column("records_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("actor", sa.String, nullable=True),
        sa.Column("diff", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    for table in [
        "audit_log",
        "pipeline_runs",
        "external_id_map",
        "sync_events",
        "compiled_transformations",
        "agent_proposals",
        "field_mappings",
        "pipelines",
        "schema_diffs",
        "schema_versions",
        "connectors",
    ]:
        op.drop_table(table)
