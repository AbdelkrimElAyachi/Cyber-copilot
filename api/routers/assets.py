"""
FastAPI router for the assets resource.

Provides endpoints to list, retrieve, create, update, and delete monitored
assets (endpoints, servers, cloud instances, network devices, etc.) tracked
by the security investigation platform.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.dependencies import get_db
from database import Database, new_id

router = APIRouter(prefix="/assets", tags=["assets"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class AssetCreate(BaseModel):
    """Payload schema for creating a new asset."""

    hostname: str
    ip_address: Optional[str] = None
    asset_type: str = "endpoint"
    os: Optional[str] = None
    wazuh_agent_id: Optional[str] = None
    criticality: str = "medium"
    notes: Optional[str] = None


class AssetUpdate(BaseModel):
    """Payload schema for updating an existing asset."""

    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    asset_type: Optional[str] = None
    os: Optional[str] = None
    wazuh_agent_id: Optional[str] = None
    criticality: Optional[str] = None
    notes: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ensure_asset_exists(db: Database, asset_id: str) -> dict[str, Any]:
    """Retrieve an asset by ID or raise HTTP 404 if not found."""
    row = db.fetchone("SELECT * FROM assets WHERE id = %s", (asset_id,))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    return row


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("")
def list_assets(
    asset_type: Optional[str] = None,
    criticality: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Database = Depends(get_db),
) -> list[dict[str, Any]]:
    """List assets with optional filtering by asset_type and criticality."""
    query = "SELECT * FROM assets WHERE 1=1"
    params: list[Any] = []

    if asset_type:
        query += " AND asset_type = %s"
        params.append(asset_type)
    if criticality:
        query += " AND criticality = %s"
        params.append(criticality)

    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    return db.fetchall(query, tuple(params))


@router.get("/{asset_id}")
def get_asset(
    asset_id: str,
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve a single asset by its unique ID."""
    return _ensure_asset_exists(db, asset_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_asset(
    asset: AssetCreate,
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Create a new asset record."""
    asset_id = new_id()

    query = """
        INSERT INTO assets (
            id, hostname, ip_address, asset_type, os,
            wazuh_agent_id, criticality, notes, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
    """
    params = (
        asset_id,
        asset.hostname,
        asset.ip_address,
        asset.asset_type,
        asset.os,
        asset.wazuh_agent_id,
        asset.criticality,
        asset.notes,
    )
    db.execute(query, params)
    return db.fetchone("SELECT * FROM assets WHERE id = %s", (asset_id,))  # type: ignore[return-value]


@router.patch("/{asset_id}")
def update_asset(
    asset_id: str,
    update_data: AssetUpdate,
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Update fields of an existing asset."""
    _ensure_asset_exists(db, asset_id)

    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        return _ensure_asset_exists(db, asset_id)

    set_clauses: list[str] = []
    params: list[Any] = []
    for key, value in update_dict.items():
        set_clauses.append(f"{key} = %s")
        params.append(value)

    query = f"UPDATE assets SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = %s"
    params.append(asset_id)

    db.execute(query, tuple(params))
    return db.fetchone("SELECT * FROM assets WHERE id = %s", (asset_id,))  # type: ignore[return-value]


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Database = Depends(get_db),
) -> None:
    """Delete an asset by ID."""
    _ensure_asset_exists(db, asset_id)
    db.execute("DELETE FROM assets WHERE id = %s", (asset_id,))
