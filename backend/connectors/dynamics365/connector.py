"""Microsoft Dynamics 365 connector (Business Central / Finance & Operations via OData)."""
from datetime import datetime
from typing import Any, AsyncIterator, Optional
import httpx
from ..base import ERPConnector, ConnectorConfig, ConnectorCapability, ConnectorMeta, EntitySchema, SyncRecord, SchemaField
import hashlib, json


class Dynamics365Connector(ERPConnector):
    class Meta(ConnectorMeta):
        system_name = "dynamics365"
        display_name = "Microsoft Dynamics 365"
        version = "1.0.0"
        capabilities = [ConnectorCapability.POLLING, ConnectorCapability.BIDIRECTIONAL]
        supported_entities = ["vendors", "customers", "purchaseInvoices", "salesInvoices", "generalLedgerEntries", "accounts"]

    async def connect(self) -> None:
        token = await self._get_token()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def _get_token(self) -> str:
        c = self.config.credentials
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"https://login.microsoftonline.com/{c['tenant_id']}/oauth2/v2.0/token",
                data={"grant_type": "client_credentials", "client_id": c["client_id"],
                      "client_secret": c["client_secret"], "scope": f"{self.config.base_url}/.default"},
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def list_entities(self) -> list[str]:
        return self.Meta.supported_entities

    async def read_schema(self, entity_name: str) -> EntitySchema:
        await self.connect()
        resp = await self._client.get(f"/{entity_name}?$top=1")
        resp.raise_for_status()
        sample = resp.json().get("value", [{}])
        sample_record = sample[0] if sample else {}
        fields = [SchemaField(name=k, canonical_name=k.lower(), data_type=_infer_type(v)) for k, v in sample_record.items()]
        version_hash = hashlib.sha256(json.dumps(sorted(f.name for f in fields)).encode()).hexdigest()
        await self.disconnect()
        return EntitySchema(entity_name=entity_name, system_name=self.Meta.system_name, version_hash=version_hash, fields=fields, fetched_at=datetime.utcnow())

    async def fetch_records(self, entity_name, since=None, page_size=500, cursor=None):
        await self.connect()
        url = f"/{entity_name}?$top={page_size}"
        if since:
            url += f"&$filter=lastModifiedDateTime gt {since.isoformat()}Z"
        if cursor:
            url = cursor
        resp = await self._client.get(url)
        resp.raise_for_status()
        data = resp.json()
        records = [
            SyncRecord(
                record_id=str(r.get("id", i)), entity_name=entity_name,
                source_system=self.Meta.system_name, payload=r,
                updated_at=datetime.fromisoformat(r["lastModifiedDateTime"].rstrip("Z")) if r.get("lastModifiedDateTime") else datetime.utcnow(),
                operation="update",
            )
            for i, r in enumerate(data.get("value", []))
        ]
        next_cursor = data.get("@odata.nextLink")
        await self.disconnect()
        return records, next_cursor

    async def push_records(self, entity_name, records):
        await self.connect()
        results = []
        for record in records:
            erp_id = record.payload.get("id")
            if erp_id:
                resp = await self._client.patch(f"/{entity_name}({erp_id})", json=record.payload)
            else:
                resp = await self._client.post(f"/{entity_name}", json=record.payload)
            ok = resp.status_code in (200, 201, 204)
            result_data = resp.json() if resp.content else {}
            results.append({"record_id": record.record_id, "status": "success" if ok else "error", "erp_id": result_data.get("id"), "error": None if ok else resp.text})
        await self.disconnect()
        return results

    async def subscribe_to_changes(self, entity_name):
        raise NotImplementedError("Dynamics 365 CDC not supported. Use polling.")


def _infer_type(val) -> str:
    if isinstance(val, bool): return "boolean"
    if isinstance(val, int): return "integer"
    if isinstance(val, float): return "decimal"
    return "string"
