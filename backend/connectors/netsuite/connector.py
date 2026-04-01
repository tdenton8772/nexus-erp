"""NetSuite connector via SuiteTalk REST API with TBA OAuth 1.0."""
from datetime import datetime
from typing import AsyncIterator
import httpx, hashlib, json, hmac, base64, time, uuid, urllib.parse
from ..base import ERPConnector, ConnectorConfig, ConnectorCapability, ConnectorMeta, EntitySchema, SyncRecord, SchemaField


class NetSuiteConnector(ERPConnector):
    class Meta(ConnectorMeta):
        system_name = "netsuite"
        display_name = "NetSuite"
        version = "1.0.0"
        capabilities = [ConnectorCapability.POLLING, ConnectorCapability.BIDIRECTIONAL]
        supported_entities = ["vendor", "customer", "vendorbill", "invoice", "account", "journalentry"]

    def _auth_header(self, method: str, url: str) -> str:
        c = self.config.credentials
        nonce = uuid.uuid4().hex
        timestamp = str(int(time.time()))
        params = {"oauth_consumer_key": c["consumer_key"], "oauth_nonce": nonce, "oauth_signature_method": "HMAC-SHA256",
                  "oauth_timestamp": timestamp, "oauth_token": c["token_id"], "oauth_version": "1.0"}
        base_str = "&".join([method.upper(), urllib.parse.quote(url, safe=""), urllib.parse.quote("&".join(f"{k}={v}" for k, v in sorted(params.items())), safe="")])
        signing_key = f"{urllib.parse.quote(c['consumer_secret'], safe='')}&{urllib.parse.quote(c['token_secret'], safe='')}"
        sig = base64.b64encode(hmac.new(signing_key.encode(), base_str.encode(), "sha256").digest()).decode()
        params["oauth_signature"] = sig
        header = ", ".join(f'{k}="{v}"' for k, v in params.items())
        return f'OAuth realm="{c["account_id"]}", {header}'

    async def connect(self) -> None:
        account_id = self.config.credentials["account_id"].replace("_", "-").lower()
        self._base = f"https://{account_id}.suitetalk.api.netsuite.com/services/rest/record/v1"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def list_entities(self) -> list[str]:
        return self.Meta.supported_entities

    async def read_schema(self, entity_name: str) -> EntitySchema:
        await self.connect()
        url = f"{self._base}/{entity_name}?limit=1"
        resp = await self._client.get(url, headers={"Authorization": self._auth_header("GET", url), "Content-Type": "application/json"})
        items = resp.json().get("items", [{}]) if resp.is_success else [{}]
        sample = items[0] if items else {}
        fields = [SchemaField(name=k, canonical_name=k.lower(), data_type="string") for k in sample]
        version_hash = hashlib.sha256(json.dumps(sorted(f.name for f in fields)).encode()).hexdigest()
        await self.disconnect()
        return EntitySchema(entity_name=entity_name, system_name=self.Meta.system_name, version_hash=version_hash, fields=fields, fetched_at=datetime.utcnow())

    async def fetch_records(self, entity_name, since=None, page_size=500, cursor=None):
        await self.connect()
        url = f"{self._base}/{entity_name}?limit={page_size}"
        if cursor:
            url += f"&offset={cursor}"
        resp = await self._client.get(url, headers={"Authorization": self._auth_header("GET", url)})
        data = resp.json() if resp.is_success else {"items": []}
        records = [
            SyncRecord(record_id=str(r.get("id", i)), entity_name=entity_name,
                       source_system=self.Meta.system_name, payload=r, updated_at=datetime.utcnow(), operation="update")
            for i, r in enumerate(data.get("items", []))
        ]
        total = data.get("totalResults", 0)
        offset = int(cursor or 0) + page_size
        next_cursor = str(offset) if offset < total else None
        await self.disconnect()
        return records, next_cursor

    async def push_records(self, entity_name, records):
        await self.connect()
        results = []
        for record in records:
            url = f"{self._base}/{entity_name}"
            resp = await self._client.post(url, json=record.payload, headers={"Authorization": self._auth_header("POST", url)})
            results.append({"record_id": record.record_id, "status": "success" if resp.is_success else "error", "erp_id": resp.headers.get("NS_RTIMER_COMPOSITE"), "error": None if resp.is_success else resp.text})
        await self.disconnect()
        return results

    async def subscribe_to_changes(self, entity_name):
        raise NotImplementedError("NetSuite CDC not supported. Use polling.")
