import secrets
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.schemas import UserOut
from app.services.jwt_auth import create_access_token
from app.services.x_oauth import (
    build_authorize_url,
    encrypt_tokens,
    exchange_code,
    generate_pkce,
    get_user_profile,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/auth", tags=["auth"])

_pkce_store: dict[str, str] = {}


async def _store_pkce(state: str, verifier: str):
    try:
        from app.services.redis_store import store_pkce
        await store_pkce(state, verifier)
    except Exception:
        _pkce_store[state] = verifier


async def _pop_pkce(state: str) -> str | None:
    try:
        from app.services.redis_store import pop_pkce
        val = await pop_pkce(state)
        if val:
            return val
    except Exception:
        pass
    return _pkce_store.pop(state, None)


@router.get("/x/start")
async def x_oauth_start():
    if not settings.x_client_id:
        raise HTTPException(501, "X OAuth not configured — set X_CLIENT_ID and X_CLIENT_SECRET")

    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce()
    await _store_pkce(state, verifier)

    authorize_url = build_authorize_url(state, challenge)
    return {"authorize_url": authorize_url, "state": state}


@router.get("/x/callback")
async def x_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    verifier = await _pop_pkce(state)
    if not verifier:
        raise HTTPException(400, "Invalid or expired state")

    try:
        token_data = await exchange_code(code, verifier)
    except Exception as e:
        logger.exception("Token exchange failed")
        raise HTTPException(502, f"Token exchange failed: {e}")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    try:
        profile = await get_user_profile(access_token)
    except Exception as e:
        logger.exception("Profile fetch failed")
        raise HTTPException(502, f"Profile fetch failed: {e}")

    x_user_id = profile.get("id", "")
    x_handle = profile.get("username", "")
    x_display = profile.get("name", "")
    x_avatar = profile.get("profile_image_url", "")

    if not x_user_id:
        raise HTTPException(502, "X API returned no user ID")

    access_enc, refresh_enc = encrypt_tokens(access_token, refresh_token)

    result = await db.execute(select(User).where(User.x_user_id == x_user_id))
    user = result.scalar_one_or_none()

    if user:
        user.x_handle = x_handle
        user.x_display_name = x_display
        user.x_avatar_url = x_avatar
        user.x_access_token_enc = access_enc
        user.x_refresh_token_enc = refresh_enc
    else:
        user = User(
            x_user_id=x_user_id,
            x_handle=x_handle,
            x_display_name=x_display,
            x_avatar_url=x_avatar,
            x_access_token_enc=access_enc,
            x_refresh_token_enc=refresh_enc,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    jwt_token = create_access_token(user.id)

    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "x_handle": user.x_handle,
            "x_display_name": user.x_display_name,
            "x_avatar_url": user.x_avatar_url,
        },
    }


@router.get("/me", response_model=UserOut)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return UserOut.model_validate(user)


# ── Dev-only login (works when X_CLIENT_ID is not set) ───────────


from pydantic import BaseModel


class DevLoginBody(BaseModel):
    handle: str = "dev_user"
    display_name: str = "Dev User"


@router.post("/dev-login")
async def dev_login(
    body: DevLoginBody,
    db: AsyncSession = Depends(get_db),
):
    """
    Create or reuse a dev user and return a JWT.
    Only available when X OAuth is NOT configured (local dev).
    """
    if settings.x_client_id:
        raise HTTPException(403, "Dev login disabled — X OAuth is configured")

    x_user_id = f"dev_{body.handle}"

    result = await db.execute(select(User).where(User.x_user_id == x_user_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            x_user_id=x_user_id,
            x_handle=body.handle,
            x_display_name=body.display_name,
            x_avatar_url="",
            x_access_token_enc="",
            x_refresh_token_enc="",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    jwt_token = create_access_token(user.id)

    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "x_handle": user.x_handle,
            "x_display_name": user.x_display_name,
            "x_avatar_url": user.x_avatar_url,
        },
    }
