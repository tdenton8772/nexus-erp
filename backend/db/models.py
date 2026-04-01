"""
All SQLAlchemy ORM models for Nexus ERP.
All PKs are UUID strings. All timestamps are UTC.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..core.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────────

class ConnectorStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    CONFIGURING = "configuring"


class PipelineStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    ARCHIVED = "archived"


class SyncDirection(str, enum.Enum):
    SOURCE_TO_TARGET = "source_to_target"
    TARGET_TO_SOURCE = "target_to_source"
    BIDIRECTIONAL = "bidirectional"


class SyncEventStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CONFLICT = "conflict"
    SKIPPED = "skipped"


class AgentProposalStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


# ── Connector ──────────────────────────────────────────────────────────────────

class ConnectorRecord(Base):
    """Registered ERP connector instance."""
    __tablename__ = "connectors"

    id = Column(String(36), primary_key=True)
    system_name = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=False)
    status = Column(SAEnum(ConnectorStatus), default=ConnectorStatus.CONFIGURING, nullable=False)
    base_url = Column(String(512), nullable=True)
    credentials_encrypted = Column(Text, nullable=True)     # Fernet-encrypted JSON
    config_json = Column(JSONB, nullable=True)
    last_connected_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    schema_versions = relationship("SchemaVersion", back_populates="connector", cascade="all, delete-orphan")
    source_pipelines = relationship(
        "Pipeline", foreign_keys="Pipeline.source_connector_id", back_populates="source_connector"
    )
    target_pipelines = relationship(
        "Pipeline", foreign_keys="Pipeline.target_connector_id", back_populates="target_connector"
    )


# ── Schema ─────────────────────────────────────────────────────────────────────

class SchemaVersion(Base):
    """Snapshot of an ERP entity's schema captured at a point in time."""
    __tablename__ = "schema_versions"

    id = Column(String(36), primary_key=True)
    connector_id = Column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False)
    entity_name = Column(String(255), nullable=False)
    version_number = Column(Integer, nullable=False)
    version_hash = Column(String(64), nullable=False)
    schema_json = Column(JSONB, nullable=False)
    is_current = Column(Boolean, default=True, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    drift_detected = Column(Boolean, default=False, nullable=False)
    drift_summary = Column(JSONB, nullable=True)

    connector = relationship("ConnectorRecord", back_populates="schema_versions")

    __table_args__ = (
        UniqueConstraint("connector_id", "entity_name", "version_number",
                         name="uq_schema_version"),
    )


class SchemaDiff(Base):
    """Diff between two consecutive schema versions."""
    __tablename__ = "schema_diffs"

    id = Column(String(36), primary_key=True)
    from_version_id = Column(String(36), ForeignKey("schema_versions.id"), nullable=True)
    to_version_id = Column(String(36), ForeignKey("schema_versions.id"), nullable=False)
    diff_json = Column(JSONB, nullable=False)   # {added: [...], removed: [...], changed: [...]}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    agent_triggered = Column(Boolean, default=False, nullable=False)


# ── Pipeline ───────────────────────────────────────────────────────────────────

class Pipeline(Base):
    __tablename__ = "pipelines"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(PipelineStatus), default=PipelineStatus.DRAFT, nullable=False)
    source_connector_id = Column(String(36), ForeignKey("connectors.id"), nullable=False)
    target_connector_id = Column(String(36), ForeignKey("connectors.id"), nullable=False)
    entity_name = Column(String(255), nullable=False)
    direction = Column(SAEnum(SyncDirection), default=SyncDirection.BIDIRECTIONAL, nullable=False)
    poll_interval_seconds = Column(Integer, default=300, nullable=False)
    use_cdc = Column(Boolean, default=False, nullable=False)
    last_sync_at = Column(DateTime, nullable=True)
    config_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    source_connector = relationship(
        "ConnectorRecord", foreign_keys=[source_connector_id], back_populates="source_pipelines"
    )
    target_connector = relationship(
        "ConnectorRecord", foreign_keys=[target_connector_id], back_populates="target_pipelines"
    )
    field_mappings = relationship("FieldMapping", back_populates="pipeline", cascade="all, delete-orphan")
    transformation = relationship(
        "CompiledTransformation", back_populates="pipeline", uselist=False, cascade="all, delete-orphan"
    )
    sync_events = relationship("SyncEvent", back_populates="pipeline")
    agent_proposals = relationship("AgentProposal", back_populates="pipeline")
    runs = relationship("PipelineRun", back_populates="pipeline")


# ── Mapping ────────────────────────────────────────────────────────────────────

class FieldMapping(Base):
    """Approved canonical field mapping between source and target schemas."""
    __tablename__ = "field_mappings"

    id = Column(String(36), primary_key=True)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False)
    source_field = Column(String(255), nullable=True)   # null for computed/constant fields
    target_field = Column(String(255), nullable=True)   # null for reverse-only fields
    transform_name = Column(String(100), nullable=False, default="passthrough")
    transform_args = Column(JSONB, nullable=True)
    expression = Column(Text, nullable=True)            # inline Python for computed fields
    is_required = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    pipeline = relationship("Pipeline", back_populates="field_mappings")


class AgentProposal(Base):
    """LLM-generated mapping or healing proposal awaiting human review."""
    __tablename__ = "agent_proposals"

    id = Column(String(36), primary_key=True)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id"), nullable=True)
    trigger_type = Column(String(100), nullable=False)  # initial_mapping | drift | failure
    status = Column(SAEnum(AgentProposalStatus), default=AgentProposalStatus.PENDING_REVIEW, nullable=False)
    proposal_json = Column(JSONB, nullable=False)
    human_feedback = Column(Text, nullable=True)
    reviewed_by = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    agent_run_id = Column(String(36), nullable=True)    # LangGraph thread ID
    schema_diff_id = Column(String(36), ForeignKey("schema_diffs.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    pipeline = relationship("Pipeline", back_populates="agent_proposals")


# ── Transformation ─────────────────────────────────────────────────────────────

class CompiledTransformation(Base):
    """Compiled Python transformation functions for a pipeline."""
    __tablename__ = "compiled_transformations"

    id = Column(String(36), primary_key=True)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, unique=True)
    forward_code = Column(Text, nullable=False)         # source -> target
    reverse_code = Column(Text, nullable=False)         # target -> source
    code_hash = Column(String(64), nullable=False)
    generated_by = Column(String(50), nullable=False)   # "compiler" | "llm"
    llm_model = Column(String(100), nullable=True)
    validation_passed = Column(Boolean, default=False, nullable=False)
    validation_report = Column(JSONB, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    pipeline = relationship("Pipeline", back_populates="transformation")


# ── Sync Events ────────────────────────────────────────────────────────────────

class SyncEvent(Base):
    """One record-level sync operation."""
    __tablename__ = "sync_events"

    id = Column(String(36), primary_key=True)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id"), nullable=False)
    record_id = Column(String(255), nullable=False)
    entity_name = Column(String(255), nullable=False)
    source_system = Column(String(100), nullable=False)
    target_system = Column(String(100), nullable=False)
    direction = Column(SAEnum(SyncDirection), nullable=False)
    operation = Column(String(50), nullable=False)       # create | update | delete
    status = Column(SAEnum(SyncEventStatus), default=SyncEventStatus.PENDING, nullable=False)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    source_payload_hash = Column(String(64), nullable=True)
    target_erp_id = Column(String(255), nullable=True)
    conflict_resolution = Column(String(100), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    pipeline = relationship("Pipeline", back_populates="sync_events")

    __table_args__ = (
        Index("ix_sync_events_pipeline_created", "pipeline_id", "created_at"),
        Index("ix_sync_events_record", "record_id", "pipeline_id"),
    )


class ExternalIdMap(Base):
    """Maps source record IDs to target ERP IDs to prevent bidirectional sync loops."""
    __tablename__ = "external_id_map"

    id = Column(String(36), primary_key=True)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False)
    source_system = Column(String(100), nullable=False)
    source_record_id = Column(String(255), nullable=False)
    target_system = Column(String(100), nullable=False)
    target_record_id = Column(String(255), nullable=False)
    last_synced_at = Column(DateTime, nullable=False)
    last_payload_hash = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("pipeline_id", "source_system", "source_record_id",
                         name="uq_external_id_map"),
        Index("ix_external_id_map_lookup", "pipeline_id", "source_system", "source_record_id"),
    )


# ── Pipeline Runs ──────────────────────────────────────────────────────────────

class PipelineRun(Base):
    """One execution batch of a pipeline."""
    __tablename__ = "pipeline_runs"

    id = Column(String(36), primary_key=True)
    pipeline_id = Column(String(36), ForeignKey("pipelines.id"), nullable=False)
    trigger = Column(String(50), nullable=False)         # poll | cdc | manual
    status = Column(String(50), nullable=False)          # running | completed | failed
    records_processed = Column(Integer, default=0, nullable=False)
    records_succeeded = Column(Integer, default=0, nullable=False)
    records_failed = Column(Integer, default=0, nullable=False)
    records_skipped = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    pipeline = relationship("Pipeline", back_populates="runs")


# ── Audit Log ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Immutable audit trail for all user and agent actions."""
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True)
    actor_type = Column(String(50), nullable=False)     # user | agent | system
    actor_id = Column(String(255), nullable=True)
    action = Column(String(255), nullable=False)        # pipeline.created | mapping.approved
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(36), nullable=True)
    before_state = Column(JSONB, nullable=True)
    after_state = Column(JSONB, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )
