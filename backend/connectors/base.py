"""
Abstract base class and shared data models for all ERP connectors.

Every connector—built-in or third-party plugin—must subclass ERPConnector
and implement all abstract methods. The ConnectorRegistry auto-discovers
subclasses on startup without requiring any central registration list.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel


# ── Capabilities ───────────────────────────────────────────────────────────────

class ConnectorCapability(str, Enum):
    CDC = "cdc"                    # Real-time change data capture
    POLLING = "polling"            # Periodic full/delta fetch
    WEBHOOK = "webhook"            # Push from ERP to this platform
    BIDIRECTIONAL = "bidirectional"


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class ConnectorConfig:
    """Serializable config passed to a connector instance at construction time."""
    connector_id: str
    system_name: str
    credentials: dict[str, str]     # Decrypted in memory, never persisted plaintext
    base_url: str
    options: dict[str, Any] = field(default_factory=dict)


# ── Schema Models ──────────────────────────────────────────────────────────────

class SchemaField(BaseModel):
    name: str
    canonical_name: str             # snake_case normalized name
    data_type: str                  # string | decimal | datetime | boolean | object | array | integer
    nullable: bool = True
    max_length: Optional[int] = None
    description: Optional[str] = None
    erp_native_type: Optional[str] = None
    nested_fields: list["SchemaField"] = []


class EntitySchema(BaseModel):
    entity_name: str
    system_name: str
    version_hash: str               # SHA-256 of sorted field names+types
    fields: list[SchemaField]
    fetched_at: datetime


# ── Record Model ───────────────────────────────────────────────────────────────

class SyncRecord(BaseModel):
    """A single record flowing through a pipeline."""
    record_id: str
    entity_name: str
    source_system: str
    payload: dict[str, Any]
    updated_at: datetime            # Used for last-write-wins conflict resolution
    operation: str                  # create | update | delete
    metadata: dict[str, Any] = {}


# ── Connector Metadata ─────────────────────────────────────────────────────────

class ConnectorMeta:
    """
    Declarative metadata for a connector. Subclass this as an inner class
    named `Meta` inside your ERPConnector subclass.

    The ConnectorRegistry reads these attributes without instantiating the connector.
    """
    system_name: str = ""
    display_name: str = ""
    version: str = "1.0.0"
    capabilities: list[ConnectorCapability] = []
    supported_entities: list[str] = []


# ── Abstract Base ──────────────────────────────────────────────────────────────

class ERPConnector(abc.ABC):
    """
    Abstract base class every ERP connector must implement.

    All I/O methods are async. Connectors run inside the asyncio event loop
    and must not block the thread.

    Third-party connectors: create a subclass in plugins/<name>/connector.py
    and the platform will auto-discover it on startup.
    """

    Meta: type[ConnectorMeta]  # Inner class, declared by each subclass

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self._client: Any = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish authenticated session. Raise ConnectorAuthError on failure."""
        ...

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close connections and release resources."""
        ...

    async def health_check(self) -> bool:
        """Ping the ERP API. Default impl: attempt connect/disconnect round-trip."""
        try:
            await self.connect()
            await self.disconnect()
            return True
        except Exception:
            return False

    # ── Schema ─────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def list_entities(self) -> list[str]:
        """Return the names of all syncable entity types."""
        ...

    @abc.abstractmethod
    async def read_schema(self, entity_name: str) -> EntitySchema:
        """
        Introspect the ERP API and return a normalized EntitySchema.
        Must open its own session; do not assume connect() was called.
        """
        ...

    # ── Data ───────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def fetch_records(
        self,
        entity_name: str,
        since: Optional[datetime] = None,
        page_size: int = 500,
        cursor: Optional[str] = None,
    ) -> tuple[list[SyncRecord], Optional[str]]:
        """
        Fetch records with optional delta filter.
        Returns (records, next_cursor). next_cursor is None when exhausted.
        Must be safe to call without a prior connect().
        """
        ...

    @abc.abstractmethod
    async def push_records(
        self,
        entity_name: str,
        records: list[SyncRecord],
    ) -> list[dict[str, Any]]:
        """
        Write records to the ERP system.
        Returns a list of result dicts: {record_id, status, erp_id, error}.
        Must be idempotent—use the ERP's upsert capability where available.
        """
        ...

    # ── CDC / Streaming ────────────────────────────────────────────────────────

    async def subscribe_to_changes(
        self,
        entity_name: str,
    ) -> AsyncIterator[SyncRecord]:
        """
        Yield SyncRecords as changes arrive from the ERP.
        Raise NotImplementedError for ERPs without native CDC;
        the platform will fall back to polling via fetch_records.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support CDC. Use polling mode."
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def supports(self, capability: ConnectorCapability) -> bool:
        return capability in self.Meta.capabilities

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} system={self.Meta.system_name} id={self.config.connector_id}>"


# ── Exceptions ─────────────────────────────────────────────────────────────────

class ConnectorAuthError(Exception):
    """Raised when authentication with the ERP system fails."""


class ConnectorNotFoundError(Exception):
    """Raised when a requested entity or record does not exist."""


class ConnectorRateLimitError(Exception):
    """Raised when the ERP API rate limit is hit. Include retry_after seconds if known."""
    def __init__(self, message: str, retry_after: Optional[int] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
