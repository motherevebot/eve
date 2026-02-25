"""Shared API dependencies — auth, DB session."""

import uuid

from fastapi import HTTPException, Header

from app.services.jwt_auth import decode_access_token


async def get_current_user_id(
    authorization: str = Header(..., description="Bearer <JWT>"),
) -> str:
    """Extract and validate JWT from Authorization header. Returns user_id as string."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")

    token = authorization[7:]
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(401, "Invalid or expired token")
    return str(user_id)
