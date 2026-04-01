"""Async Kafka producer wrapper."""
import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from ..core.config import settings

logger = logging.getLogger(__name__)


class NexusProducer:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode(),
            key_serializer=lambda k: k.encode() if k else None,
            compression_type="gzip",
            acks="all",
            enable_idempotence=True,
        )
        await self._producer.start()
        logger.info("Kafka producer started")

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def publish(self, topic: str, value: Any, key: str | None = None) -> None:
        if not self._producer:
            logger.warning("Producer not started; skipping publish to %s", topic)
            return
        await self._producer.send_and_wait(topic, value=value, key=key)
