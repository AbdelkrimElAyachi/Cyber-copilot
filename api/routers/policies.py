"""
Policies router — CRUD for investigation policies.

Delegates all logic to the existing PolicyEngine, which owns the
policy table and evaluation rules.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from investigation_policy import PolicyEngine
from api.dependencies import get_policy_engine


# ── Schemas ─────────────────────────────────────────────────────────────


class PolicyCreate(BaseModel):
    name: str
    conditions: dict[str, Any]
    description: str = ""
    is_enabled: bool = True
    priority: int = 0


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None
    conditions: Optional[dict[str, Any]] = None


# ── Router ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("")
def list_policies(
    enabled_only: bool = False,
    engine: PolicyEngine = Depends(get_policy_engine),
):
    """List all investigation policies."""
    return engine.list_policies(enabled_only=enabled_only)


@router.get("/{policy_id}")
def get_policy(
    policy_id: str,
    engine: PolicyEngine = Depends(get_policy_engine),
):
    """Retrieve a single policy by ID."""
    policy = engine.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    return policy


@router.post("", status_code=201)
def create_policy(
    body: PolicyCreate,
    engine: PolicyEngine = Depends(get_policy_engine),
):
    """Create a new investigation policy."""
    policy_id = engine.create_policy(
        name=body.name,
        conditions=body.conditions,
        description=body.description,
        is_enabled=body.is_enabled,
        priority=body.priority,
    )
    return {"id": policy_id}


@router.patch("/{policy_id}")
def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    engine: PolicyEngine = Depends(get_policy_engine),
):
    """Update an existing investigation policy."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    affected = engine.update_policy(policy_id, **updates)
    if affected == 0:
        raise HTTPException(status_code=404, detail="Policy not found.")

    return engine.get_policy(policy_id)


@router.delete("/{policy_id}", status_code=204, response_class=Response)
def delete_policy(
    policy_id: str,
    engine: PolicyEngine = Depends(get_policy_engine),
):
    """Delete an investigation policy."""
    affected = engine.delete_policy(policy_id)
    if affected == 0:
        raise HTTPException(status_code=404, detail="Policy not found.")
