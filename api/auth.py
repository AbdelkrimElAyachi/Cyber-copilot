"""
Authentication core — delegates credential verification to the Wazuh
Indexer instead of maintaining a separate password database.

How it works:
    1. A user submits username/password to POST /auth/login.
    2. We make one HTTP GET to the Wazuh Indexer using those exact
       credentials as HTTP Basic Auth (the same OpenSearch Security realm
       the Wazuh Dashboard itself logs into). 200 = valid Wazuh account,
       401/403 = invalid. The password is never stored — it's forwarded
       once for this check and then discarded.
    3. On success we mint our own short-lived JWT (the Indexer has no
       reusable app token to hand back), which the frontend then sends as
       `Authorization: Bearer <token>` on every subsequent request.

This app has exactly one access tier today (see build_default_tools /
ai_investigator for the one real restriction that exists: no tool can
read the `users` table). Anyone who authenticates gets full access;
per-feature permissions can be layered onto `users.role` later without
touching this module.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from dotenv import load_dotenv
import jwt
import requests

logger = logging.getLogger(__name__)

# Load independently of import order — this module reads env vars at
# import time, and it must not matter whether something else (e.g.
# api/dependencies.py) happens to import it before calling load_dotenv()
# itself. python-dotenv is a no-op if the vars are already set.
load_dotenv()

_JWT_ALGORITHM = "HS256"
_JWT_SECRET = os.getenv("AUTH_JWT_SECRET", "")
_TOKEN_TTL_MINUTES = int(os.getenv("AUTH_TOKEN_TTL_MINUTES", "720"))  # 12h

if not _JWT_SECRET:
    # Fail loud rather than silently signing tokens with an empty/guessable
    # key. A missing secret means every previously issued token becomes
    # invalid on restart anyway, so there's no "safe" default to fall back
    # to — better to say so clearly at startup.
    logger.warning(
        "AUTH_JWT_SECRET is not set — login will be rejected until it is "
        "configured in .env. Generate one with: python3 -c "
        "\"import secrets; print(secrets.token_hex(32))\""
    )


class AuthConfigError(Exception):
    """Raised when auth is used without required configuration."""


def verify_wazuh_credentials(
    username: str,
    password: str,
    *,
    host: str,
    port: int,
    verify_ssl: bool,
    timeout: float = 5.0,
) -> bool:
    """Check a username/password pair against the Wazuh Indexer.

    A single lightweight authenticated GET against the Indexer root is
    enough — OpenSearch answers 200 with cluster info for valid
    credentials and 401 for invalid ones, regardless of security-plugin
    version, so there's no endpoint path to keep in sync with Wazuh
    upgrades.
    """
    try:
        resp = requests.get(
            f"https://{host}:{port}/",
            auth=(username, password),
            verify=verify_ssl,
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Wazuh Indexer unreachable during login check: %s", e)
        return False

    if resp.status_code == 200:
        return True
    if resp.status_code in (401, 403):
        return False
    # Anything else (5xx, unexpected shape) is an Indexer-side problem,
    # not proof the credentials are wrong — treat as a failed check.
    logger.error(
        "Unexpected status %s from Wazuh Indexer during login check", resp.status_code
    )
    return False


def create_access_token(user_id: str, username: str) -> str:
    if not _JWT_SECRET:
        raise AuthConfigError("AUTH_JWT_SECRET is not configured")
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": now + _TOKEN_TTL_MINUTES * 60,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a token. Raises jwt.PyJWTError on any problem
    (expired, bad signature, malformed) — callers turn that into a 401."""
    if not _JWT_SECRET:
        raise AuthConfigError("AUTH_JWT_SECRET is not configured")
    return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])


def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None
