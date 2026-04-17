"""Supabase JWT verification.

If SUPABASE_JWT_SECRET is unset, runs in single-user dev mode (returns a fixed
local user id) so you can run the whole stack without provisioning Supabase.
"""

from __future__ import annotations

import os

import jwt
from fastapi import Depends, HTTPException, Request

DEV_USER_ID = "00000000-0000-0000-0000-000000000000"


def _secret() -> str | None:
    return os.environ.get("SUPABASE_JWT_SECRET") or None


def _audience() -> str:
    return os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization") or request.headers.get("Authorization")
    if not h:
        return None
    parts = h.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def current_user(request: Request) -> str:
    """Return the user_id (Supabase auth.users.id) for this request."""
    secret = _secret()
    if not secret:
        return DEV_USER_ID

    token = _bearer(request)
    if not token:
        raise HTTPException(401, "Missing bearer token")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], audience=_audience())
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(401, "Token missing 'sub'")
    return sub


CurrentUser = Depends(current_user)
