"""Serve token metadata JSON for pump.fun to read during token creation."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotProfile, LinkedToken
from app.db.session import get_db
from app.services.metadata import build_metadata

router = APIRouter(prefix="/v1/metadata", tags=["metadata"])


@router.get("/{bot_id}")
async def get_metadata(
    bot_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Serve pump.fun-compatible metadata JSON for a bot's token.
    This URL is passed as the `uri` param when creating the token on-chain.
    """
    result = await db.execute(
        select(LinkedToken).where(LinkedToken.bot_id == bot_id)
    )
    token = result.scalar_one_or_none()

    if token:
        meta = build_metadata(
            name=token.name,
            symbol=token.symbol,
            description=token.description or "",
            image=token.image_url or "",
        )
        return JSONResponse(content=meta)

    # Token not yet created — check bot exists and serve from pending data
    bot = await db.get(BotProfile, bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")

    meta = build_metadata(
        name=bot.name,
        symbol="",
        description="",
        image="",
    )
    return JSONResponse(content=meta)
