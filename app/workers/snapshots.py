"""Workers: periodic snapshots for leaderboard data (tokens + agents)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AgentSnapshot,
    BotProfile,
    BotStage,
    BurnEvent,
    BurnStatus,
    ClaimStatus,
    FeeClaim,
    LinkedToken,
    TokenSnapshot,
    TokenStatus,
)
from app.services.dexscreener import get_token_data

logger = logging.getLogger(__name__)

_STATUS_MAP = {"graduated": TokenStatus.GRADUATED, "bonding": TokenStatus.BONDING}


async def snapshot_tokens_job(db: AsyncSession):
    """Fetch real-time market data from DexScreener for every Eve token."""
    result = await db.execute(select(LinkedToken))
    tokens = result.scalars().all()
    logger.info("snapshot_tokens: %d tokens", len(tokens))

    for token in tokens:
        try:
            data = await get_token_data(token.mint)
            if data:
                snap = TokenSnapshot(
                    mint=token.mint,
                    price_usd=data["price_usd"],
                    mcap_usd=data["mcap_usd"],
                    volume_24h_usd=data["volume_24h_usd"],
                    liquidity_usd=data.get("liquidity_usd"),
                    status=_STATUS_MAP.get(data.get("status", ""), TokenStatus.UNKNOWN),
                )
            else:
                snap = TokenSnapshot(
                    mint=token.mint,
                    price_usd=0.0,
                    mcap_usd=0.0,
                    volume_24h_usd=0.0,
                    status=TokenStatus.UNKNOWN,
                )
            db.add(snap)
        except Exception:
            logger.exception("snapshot_tokens: failed for %s", token.mint)

    await db.commit()
    logger.info("snapshot_tokens: done")


async def snapshot_agents_job(db: AsyncSession):
    """Aggregate claim/burn stats per bot and store agent snapshots."""
    result = await db.execute(
        select(BotProfile).where(
            BotProfile.stage.in_([
                BotStage.LAUNCHED,
                BotStage.TRADING_ARMED,
                BotStage.LIVE,
            ])
        )
    )
    bots = result.scalars().all()
    logger.info("snapshot_agents: %d bots", len(bots))

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    for bot in bots:
        try:
            total_fees = (
                await db.scalar(
                    select(func.coalesce(func.sum(FeeClaim.amount_sol), 0.0)).where(
                        FeeClaim.bot_id == bot.id,
                        FeeClaim.status == ClaimStatus.CONFIRMED,
                    )
                )
            ) or 0.0

            fees_24h = (
                await db.scalar(
                    select(func.coalesce(func.sum(FeeClaim.amount_sol), 0.0)).where(
                        FeeClaim.bot_id == bot.id,
                        FeeClaim.status == ClaimStatus.CONFIRMED,
                        FeeClaim.created_at >= day_ago,
                    )
                )
            ) or 0.0

            total_burns = (
                await db.scalar(
                    select(func.count()).where(
                        BurnEvent.bot_id == bot.id,
                        BurnEvent.status == BurnStatus.CONFIRMED,
                    )
                )
            ) or 0

            burns_24h = (
                await db.scalar(
                    select(func.count()).where(
                        BurnEvent.bot_id == bot.id,
                        BurnEvent.status == BurnStatus.CONFIRMED,
                        BurnEvent.created_at >= day_ago,
                    )
                )
            ) or 0

            snap = AgentSnapshot(
                bot_id=bot.id,
                claimed_fees_total_sol=total_fees,
                claimed_fees_24h_sol=fees_24h,
                burns_total=total_burns,
                burns_24h=burns_24h,
            )
            db.add(snap)

        except Exception:
            logger.exception("snapshot_agents: failed for bot %s", bot.name)

    await db.commit()
    logger.info("snapshot_agents: done")
