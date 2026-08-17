"""
FastAPI router for the users resource.

Provides endpoints to list, retrieve, create, and update users in the
security investigation platform.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_db
from database import Database, new_id

router = APIRouter(prefix="/users", tags=["users"])


# ── Schemas ─────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    role: str = "analyst"
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("")
def list_users(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all users with optional active status filter and pagination."""
    query = "SELECT * FROM users WHERE 1=1"
    params: list[Any] = []

    if is_active is not None:
        query += " AND is_active = %s"
        params.append(is_active)

    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    return db.fetchall(query, tuple(params))


@router.get("/{user_id}")
def get_user(
    user_id: str,
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve a single user by their ID."""
    row = db.fetchone("SELECT * FROM users WHERE id = %s", (user_id,))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return row


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Create a new user record."""
    # Check for existing username or email
    existing = db.fetchone(
        "SELECT id FROM users WHERE username = %s OR email = %s",
        (user_data.username, user_data.email),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username or email already exists",
        )

    user_id = new_id()
    query = """
        INSERT INTO users (id, username, email, full_name, role, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
    """
    params = (
        user_id,
        user_data.username,
        user_data.email,
        user_data.full_name,
        user_data.role,
        user_data.is_active,
    )
    db.execute(query, params)

    created_user = db.fetchone("SELECT * FROM users WHERE id = %s", (user_id,))
    if not created_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created user",
        )
    return created_user


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    update_data: UserUpdate,
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    """Update an existing user's attributes dynamically."""
    existing = db.fetchone("SELECT * FROM users WHERE id = %s", (user_id,))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        return existing

    # Check for email conflict if email is updated
    if "email" in update_dict:
        conflict = db.fetchone(
            "SELECT id FROM users WHERE email = %s AND id != %s",
            (update_dict["email"], user_id),
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use by another user",
            )

    set_clauses: list[str] = []
    params: list[Any] = []
    for key, value in update_dict.items():
        set_clauses.append(f"{key} = %s")
        params.append(value)

    query = f"UPDATE users SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = %s"
    params.append(user_id)

    db.execute(query, tuple(params))
    return db.fetchone("SELECT * FROM users WHERE id = %s", (user_id,))
