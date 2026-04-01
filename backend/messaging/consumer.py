"""Async Kafka consumer wrapper."""
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from aiokafka import AIOKafkaConsumer

from ..core.config import settings

logger = logging.getLogger(__name__)


class NexusConsumer:
    def __init__(self, group_id: str, *topics: str) -> None:
        self._topics = topics
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode()),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        if not self._consumer:
            return
        async for msg in self._consumer:
            yield {"topic": msg.topic, "key": msg.key, "value": msg.value, "offset": msg.offset}
            await self._consumer.commit()
