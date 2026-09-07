"""
Authentication router — login against Wazuh Indexer credentials.

See api/auth.py for how the credential check itself works. This router
is deliberately the only one NOT protected by get_current_user — it's
where a token is obtained in the first place.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api import auth as auth_core
from api.dependencies import get_current_user, get_db
from database import Database, new_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_WAZUH_HOST = os.getenv("WAZUH_INDEXER_HOST", "localhost")
_WAZUH_PORT = int(os.getenv("WAZUH_INDEXER_PORT", "9200"))
_WAZUH_VERIFY_SSL = os.getenv("WAZUH_INDEXER_VERIFY_SSL", "false").lower() == "true"


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


def _sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    """Never let a password field leak out, even though we don't store
    Wazuh's — belt and suspenders against a future column addition."""
    return {k: v for k, v in user.items() if k != "password"}


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Database = Depends(get_db)) -> LoginResponse:
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required",
        )

    valid = auth_core.verify_wazuh_credentials(
        username,
        payload.password,
        host=_WAZUH_HOST,
        port=_WAZUH_PORT,
        verify_ssl=_WAZUH_VERIFY_SSL,
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    user = db.fetchone("SELECT * FROM users WHERE username = %s", (username,))
    if user is None:
        # First successful Wazuh login for this account — auto-provision
        # an app-side profile. Every authenticated user has full access
        # today (see api/auth.py), so there's no role decision to make
        # here yet beyond the default.
        user_id = new_id()
        db.execute(
            "INSERT INTO users (id, username, email, full_name, role, is_active) "
            "VALUES (%s, %s, %s, %s, 'analyst', TRUE)",
            (user_id, username, f"{username}@wazuh.local", username),
        )
        user = db.fetchone("SELECT * FROM users WHERE id = %s", (user_id,))
        logger.info("Auto-provisioned platform user for Wazuh account %r", username)
    elif not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled",
        )

    assert user is not None
    token = auth_core.create_access_token(user["id"], user["username"])
    return LoginResponse(access_token=token, user=_sanitize_user(user))


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return _sanitize_user(current_user)
