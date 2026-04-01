"""Last-write-wins conflict resolution using updated_at timestamps."""
import logging
from datetime import datetime

from ..connectors.base import SyncRecord

logger = logging.getLogger(__name__)


class ConflictResolver:
    async def resolve(
        self,
        incoming: SyncRecord,
        existing_updated_at: datetime | None,
        pipeline_id: str,
    ) -> tuple[bool, str]:
        """
        Returns (should_apply: bool, reason: str).
        Incoming wins if its updated_at is strictly newer.
        """
        if existing_updated_at is None:
            return True, "no_existing_record"

        if incoming.updated_at > existing_updated_at:
            return True, "incoming_is_newer"

        if incoming.updated_at == existing_updated_at:
            # Tie-break: Sage Intacct as hub takes priority
            if incoming.source_system == "sage_intacct":
                return True, "tie_broken_by_hub_priority"
            return False, "tie_broken_defer_to_existing"

        logger.debug(
            "Conflict skip: pipeline=%s record=%s incoming=%s existing=%s",
            pipeline_id, incoming.record_id, incoming.updated_at, existing_updated_at,
        )
        return False, "existing_is_newer"
