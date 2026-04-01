"""Connector CRUD and test-connection endpoints."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.security import encrypt_credentials, decrypt_credentials
from ...connectors.base import ConnectorConfig
from ...connectors.registry import ConnectorRegistry
from ...db.models import ConnectorRecord, ConnectorStatus

router = APIRouter()


class ConnectorCreate(BaseModel):
    system_name: str
    display_name: str
    base_url: str = ""
    credentials: dict[str, Any] = {}
    config_json: dict[str, Any] = {}


class ConnectorUpdate(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    credentials: dict[str, Any] | None = None
    config_json: dict[str, Any] | None = None


@router.get("/types")
async def list_connector_types():
    return ConnectorRegistry.list_registered()


@router.get("")
async def list_connectors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ConnectorRecord).order_by(ConnectorRecord.created_at.desc()))
    rows = result.scalars().all()
    return {"items": [_serialize(c) for c in rows]}


@router.get("/{connector_id}")
async def get_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    row = await _get_or_404(connector_id, db)
    return _serialize(row)


@router.post("", status_code=201)
async def create_connector(body: ConnectorCreate, db: AsyncSession = Depends(get_db)):
    encrypted = encrypt_credentials(body.credentials) if body.credentials else None
    record = ConnectorRecord(
        id=str(uuid.uuid4()),
        system_name=body.system_name,
        display_name=body.display_name,
        base_url=body.base_url,
        credentials_encrypted=encrypted,
        config_json=body.config_json or {},
        status=ConnectorStatus.CONFIGURING,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize(record)


@router.put("/{connector_id}")
async def update_connector(connector_id: str, body: ConnectorUpdate, db: AsyncSession = Depends(get_db)):
    record = await _get_or_404(connector_id, db)
    if body.display_name is not None:
        record.display_name = body.display_name
    if body.base_url is not None:
        record.base_url = body.base_url
    if body.credentials is not None:
        record.credentials_encrypted = encrypt_credentials(body.credentials)
    if body.config_json is not None:
        record.config_json = body.config_json
    record.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(record)
    return _serialize(record)


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    record = await _get_or_404(connector_id, db)
    await db.delete(record)
    await db.commit()


@router.post("/{connector_id}/test")
async def test_connector(connector_id: str, db: AsyncSession = Depends(get_db)):
    record = await _get_or_404(connector_id, db)
    creds = decrypt_credentials(record.credentials_encrypted) if record.credentials_encrypted else {}
    config = ConnectorConfig(
        connector_id=record.id,
        system_name=record.system_name,
        credentials=creds,
        base_url=record.base_url or "",
    )
    try:
        connector = ConnectorRegistry.create(config)
        healthy = await connector.health_check()
        record.status = ConnectorStatus.ACTIVE if healthy else ConnectorStatus.ERROR
        record.last_connected_at = datetime.utcnow() if healthy else record.last_connected_at
        record.last_error = None if healthy else "Health check failed"
    except KeyError:
        healthy = False
        record.last_error = f"No connector registered for '{record.system_name}'"
    except Exception as exc:
        healthy = False
        record.last_error = str(exc)
        record.status = ConnectorStatus.ERROR

    await db.commit()
    return {"healthy": healthy, "message": "Connection successful" if healthy else record.last_error}


async def _get_or_404(connector_id: str, db: AsyncSession) -> ConnectorRecord:
    result = await db.execute(select(ConnectorRecord).where(ConnectorRecord.id == connector_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Connector not found")
    return row


def _serialize(c: ConnectorRecord) -> dict:
    return {
        "id": c.id,
        "system_name": c.system_name,
        "display_name": c.display_name,
        "status": c.status.value if c.status else None,
        "base_url": c.base_url,
        "config_json": c.config_json,
        "last_connected_at": c.last_connected_at.isoformat() if c.last_connected_at else None,
        "last_error": c.last_error,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
