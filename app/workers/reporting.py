"""Worker: generate and post reports to X/Twitter."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotProfile,
    BotStage,
    BurnEvent,
    BurnStatus,
    ClaimStatus,
    FeeClaim,
    LinkedToken,
    ReportPost,
    ReportType,
    User,
)
from app.services.x_oauth import post_tweet

logger = logging.getLogger(__name__)


# ── Report templates ─────────────────────────────────────────────


def _daily_report(
    bot_name: str,
    token_symbol: str,
    fees_24h: float,
    fees_total: float,
    burns_24h: int,
    burns_total: int,
) -> str:
    return (
        f"📊 {bot_name} — Daily Report\n\n"
        f"Token: ${token_symbol}\n"
        f"Fees claimed (24h): {fees_24h:.4f} SOL\n"
        f"Total fees: {fees_total:.4f} SOL\n"
        f"Burns (24h): {burns_24h}\n"
        f"Total burns: {burns_total}\n\n"
        f"Powered by Eve 🌿"
    )


def _weekly_report(
    bot_name: str,
    token_symbol: str,
    fees_7d: float,
    fees_total: float,
    burns_7d: int,
    burns_total: int,
) -> str:
    return (
        f"📈 {bot_name} — Weekly Report\n\n"
        f"Token: ${token_symbol}\n"
        f"Fees claimed (7d): {fees_7d:.4f} SOL\n"
        f"Total fees: {fees_total:.4f} SOL\n"
        f"Burns (7d): {burns_7d}\n"
        f"Total burns: {burns_total}\n\n"
        f"Powered by Eve 🌿"
    )


def _event_claim_report(bot_name: str, token_symbol: str, amount_sol: float, tx_sig: str) -> str:
    short_sig = tx_sig[:8] if tx_sig else "..."
    return (
        f"💰 {bot_name} claimed {amount_sol:.4f} SOL in creator fees\n"
        f"Token: ${token_symbol}\n"
        f"tx: {short_sig}…\n\n"
        f"Powered by Eve 🌿"
    )


def _event_burn_report(bot_name: str, token_symbol: str, amount_burned: float, tx_sig: str) -> str:
    short_sig = tx_sig[:8] if tx_sig else "..."
    return (
        f"🔥 {bot_name} burned {amount_burned:,.0f} ${token_symbol}\n"
        f"tx: {short_sig}…\n\n"
        f"Powered by Eve 🌿"
    )


# ── Aggregate helpers ────────────────────────────────────────────


async def _get_fees_in_period(db: AsyncSession, bot_id, since: datetime) -> float:
    return (
        await db.scalar(
            select(func.coalesce(func.sum(FeeClaim.amount_sol), 0.0)).where(
                FeeClaim.bot_id == bot_id,
                FeeClaim.status == ClaimStatus.CONFIRMED,
                FeeClaim.created_at >= since,
            )
        )
    ) or 0.0


async def _get_total_fees(db: AsyncSession, bot_id) -> float:
    return (
        await db.scalar(
            select(func.coalesce(func.sum(FeeClaim.amount_sol), 0.0)).where(
                FeeClaim.bot_id == bot_id,
                FeeClaim.status == ClaimStatus.CONFIRMED,
            )
        )
    ) or 0.0


async def _get_burns_in_period(db: AsyncSession, bot_id, since: datetime) -> int:
    return (
        await db.scalar(
            select(func.count()).where(
                BurnEvent.bot_id == bot_id,
                BurnEvent.status == BurnStatus.CONFIRMED,
                BurnEvent.created_at >= since,
            )
        )
    ) or 0


async def _get_total_burns(db: AsyncSession, bot_id) -> int:
    return (
        await db.scalar(
            select(func.count()).where(
                BurnEvent.bot_id == bot_id,
                BurnEvent.status == BurnStatus.CONFIRMED,
            )
        )
    ) or 0


# ── Job runners ──────────────────────────────────────────────────


async def _post_and_record(
    db: AsyncSession,
    bot: BotProfile,
    report_type: ReportType,
    content: str,
):
    """Post tweet and save ReportPost record."""
    owner: User = bot.owner
    access_token_enc = owner.x_access_token_enc

    report = ReportPost(
        bot_id=bot.id,
        report_type=report_type,
        content=content,
        status="pending",
    )
    db.add(report)
    await db.flush()

    if not access_token_enc:
        logger.warning("Bot %s: owner has no X access token, skipping post", bot.name)
        report.status = "skipped"
        return

    tweet_id = await post_tweet(access_token_enc, content)
    if tweet_id:
        report.x_tweet_id = tweet_id
        report.status = "posted"
        logger.info("Bot %s: posted %s report, tweet_id=%s", bot.name, report_type.value, tweet_id)
    else:
        report.status = "failed"
        logger.error("Bot %s: failed to post %s report", bot.name, report_type.value)


async def run_daily_reports(db: AsyncSession):
    """Generate and post daily reports for all live bots."""
    result = await db.execute(
        select(BotProfile).where(
            BotProfile.stage.in_([BotStage.TRADING_ARMED, BotStage.LIVE])
        )
    )
    bots = result.scalars().all()
    logger.info("daily_reports: %d bots", len(bots))

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    for bot in bots:
        token = bot.linked_token
        if not token:
            continue

        fees_24h = await _get_fees_in_period(db, bot.id, day_ago)
        fees_total = await _get_total_fees(db, bot.id)
        burns_24h = await _get_burns_in_period(db, bot.id, day_ago)
        burns_total = await _get_total_burns(db, bot.id)

        content = _daily_report(bot.name, token.symbol, fees_24h, fees_total, burns_24h, burns_total)
        await _post_and_record(db, bot, ReportType.DAILY, content)

    await db.commit()


async def run_weekly_reports(db: AsyncSession):
    """Generate and post weekly reports for all live bots."""
    result = await db.execute(
        select(BotProfile).where(
            BotProfile.stage.in_([BotStage.TRADING_ARMED, BotStage.LIVE])
        )
    )
    bots = result.scalars().all()
    logger.info("weekly_reports: %d bots", len(bots))

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    for bot in bots:
        token = bot.linked_token
        if not token:
            continue

        fees_7d = await _get_fees_in_period(db, bot.id, week_ago)
        fees_total = await _get_total_fees(db, bot.id)
        burns_7d = await _get_burns_in_period(db, bot.id, week_ago)
        burns_total = await _get_total_burns(db, bot.id)

        content = _weekly_report(bot.name, token.symbol, fees_7d, fees_total, burns_7d, burns_total)
        await _post_and_record(db, bot, ReportType.WEEKLY, content)

    await db.commit()


async def post_event_report(
    db: AsyncSession,
    bot: BotProfile,
    event_type: str,
    **kwargs,
):
    """Post an event-driven report (claim, burn, launch)."""
    token = bot.linked_token
    if not token:
        return

    if event_type == "claim":
        content = _event_claim_report(
            bot.name, token.symbol,
            kwargs.get("amount_sol", 0),
            kwargs.get("tx_signature", ""),
        )
        report_type = ReportType.EVENT_CLAIM
    elif event_type == "burn":
        content = _event_burn_report(
            bot.name, token.symbol,
            kwargs.get("amount_burned", 0),
            kwargs.get("tx_signature", ""),
        )
        report_type = ReportType.EVENT_BURN
    else:
        return

    await _post_and_record(db, bot, report_type, content)
    await db.commit()
