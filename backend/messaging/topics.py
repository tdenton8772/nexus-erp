"""Kafka topic naming conventions and helpers."""

TOPIC_SYNC_INBOUND    = "nexus.sync.{pipeline_id}.inbound"
TOPIC_SYNC_OUTBOUND   = "nexus.sync.{pipeline_id}.outbound"
TOPIC_SYNC_RESULT     = "nexus.sync.{pipeline_id}.result"
TOPIC_DLQ             = "nexus.dlq.{pipeline_id}"
TOPIC_SCHEMA_DRIFT    = "nexus.schema.drift"
TOPIC_AGENT_TRIGGERS  = "nexus.agent.triggers"
TOPIC_AGENT_PROPOSALS = "nexus.agent.proposals"


def sync_inbound(pipeline_id: str) -> str:
    return TOPIC_SYNC_INBOUND.format(pipeline_id=pipeline_id)

def sync_result(pipeline_id: str) -> str:
    return TOPIC_SYNC_RESULT.format(pipeline_id=pipeline_id)

def dlq(pipeline_id: str) -> str:
    return TOPIC_DLQ.format(pipeline_id=pipeline_id)
